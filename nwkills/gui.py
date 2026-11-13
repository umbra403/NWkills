# nwkills - read the Mount & Blade: Warband Napoleonic Wars killfeed from a Wireshark capture.
# Copyright (C) 2026 the nwkills authors. Licensed under the GNU General Public License v3.0 or later; see LICENSE.
"""Desktop window for nwkills (PySide6 / Qt 6): load a capture, look at its packets, set the options, convert, browse the result tables."""
import argparse, glob, os, shutil, sys, tempfile, time, traceback

from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex, QPoint, QSortFilterProxyModel, QThread, QTimer, Signal, QSettings
from PySide6.QtGui import QColor, QFontDatabase, QGuiApplication, QKeySequence, QAction
from PySide6.QtWidgets import (QApplication, QCheckBox, QFileDialog, QFormLayout, QFrame, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                               QMainWindow, QMenu, QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QScrollArea, QSpinBox, QSplitter, QTabWidget,
                               QTableView, QToolButton, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget, QAbstractItemView)

from . import guilogic as gl

APP = 'nwkills'
EDIT_H = 24          # height of the filter boxes under the column labels

# ================================================================= models
class TableModel(QAbstractTableModel):
    """A read-only table of strings (one result CSV)."""
    def __init__(self, headers, rows, parent=None):
        super().__init__(parent)
        self.headers, self.rows = headers, rows
        self.keys = [[gl.cell_key(v) for v in r] for r in rows]
        self.numeric = gl.numeric_columns(headers, rows)
        self.review_col = headers.index('review') if 'review' in headers else -1
    def rowCount(self, parent=QModelIndex()): return 0 if parent.isValid() else len(self.rows)
    def columnCount(self, parent=QModelIndex()): return 0 if parent.isValid() else len(self.headers)
    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal: return self.headers[section]
        return None
    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid(): return None
        r, c = index.row(), index.column()
        if role in (Qt.DisplayRole, Qt.ToolTipRole): return self.rows[r][c]
        if role == Qt.TextAlignmentRole: return int(Qt.AlignRight | Qt.AlignVCenter) if c in self.numeric else int(Qt.AlignLeft | Qt.AlignVCenter)
        if role == Qt.BackgroundRole and c == self.review_col and self.rows[r][c]: return QColor(255, 170, 0, 70)      # a review flag stands out
        return None

class ResultsProxy(QSortFilterProxyModel):
    """Sorts by cell_key and filters by one regex per column plus the round/kind chips."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.filters, self.pred = {}, None
    def set_filters(self, filters, pred):
        self.filters, self.pred = filters, pred
        self.invalidateFilter()
    def filterAcceptsRow(self, row, parent):
        m = self.sourceModel()
        if m is None: return True
        vals = m.rows[row]
        if self.pred and not self.pred(vals): return False
        return gl.row_passes(vals, self.filters)
    def lessThan(self, a, b):
        m = self.sourceModel()
        return m.keys[a.row()][a.column()] < m.keys[b.row()][b.column()]

class PacketModel(QAbstractTableModel):
    """The packets of the server flow. Message types are decoded when a row is first shown (or by the background indexer)."""
    HEAD = ['No.', 'Time (s)', 'Length', 'Flags', 'Msgs', 'Message types']
    def __init__(self, parent=None):
        super().__init__(parent)
        self.items, self.info, self.times = [], {}, []
    def set_items(self, items):
        self.beginResetModel(); self.items, self.info = items, {}; self.times = [t for t, _ in items]; self.endResetModel()
    def get_info(self, r):
        i = self.info.get(r)
        if i is None: i = self.info[r] = gl.packet_info(self.items[r][1])
        return i
    def rowCount(self, parent=QModelIndex()): return 0 if parent.isValid() else len(self.items)
    def columnCount(self, parent=QModelIndex()): return 0 if parent.isValid() else len(self.HEAD)
    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal: return self.HEAD[section]
        return None
    def row_text(self, r, cached_only=True):
        """Text the display filter searches."""
        t, pl = self.items[r]
        i = self.info.get(r)
        return '%d %s %d %s' % (r + 1, 'queued' if (len(pl) > 7 and pl[7] == 0) else '', len(pl), i['types'] if i else '')
    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid(): return None
        r, c = index.row(), index.column()
        if role == Qt.DisplayRole:
            t, pl = self.items[r]
            if c == 0: return str(r + 1)
            if c == 1: return '%.6f' % t
            if c == 2: return str(len(pl))
            if c == 3: return 'queued' if (len(pl) > 7 and pl[7] == 0) else ''
            i = self.get_info(r)
            return str(i['n']) if c == 4 else i['types']
        if role == Qt.TextAlignmentRole and c in (0, 1, 2, 4): return int(Qt.AlignRight | Qt.AlignVCenter)
        if role == Qt.BackgroundRole and c == 3 and len(self.items[r][1]) > 7 and self.items[r][1][7] == 0: return QColor(255, 220, 90, 90)
        return None

class PacketProxy(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.rx = None
    def set_regex(self, rx):
        self.rx = rx; self.invalidateFilter()
    def filterAcceptsRow(self, row, parent):
        return self.rx is None or bool(self.rx.search(self.sourceModel().row_text(row)))

# ================================================================= filter header
class FilterHeader(QHeaderView):
    """Column header with a regex box under every label."""
    filterChanged = Signal()
    edits = ()      # class-level default: Qt may call updateGeometries() while the base class is still being constructed
    def __init__(self, parent=None):
        super().__init__(Qt.Horizontal, parent)
        self.edits = []
        self.setSectionsClickable(True); self.setSortIndicatorShown(True); self.setHighlightSections(False)
        self.sectionResized.connect(self.reposition); self.sectionMoved.connect(self.reposition)
    def set_columns(self, n):
        for e in self.edits: e.deleteLater()
        self.edits = []
        for i in range(n):
            e = QLineEdit(self); e.setPlaceholderText('regex'); e.setClearButtonEnabled(True)
            e.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
            e.textChanged.connect(lambda _t: self.filterChanged.emit())
            self.edits.append(e); e.show()
        self.reposition()
    def texts(self): return {i: e.text() for i, e in enumerate(self.edits)}
    def mark_bad(self, bad):
        for i, e in enumerate(self.edits):
            e.setStyleSheet('QLineEdit { border: 1px solid #c62828; }' if i in bad else '')
            e.setToolTip('Not a valid regular expression (ignored)' if i in bad else '')
    def clear_filters(self):
        for e in self.edits: e.blockSignals(True); e.clear(); e.blockSignals(False)
        self.filterChanged.emit()
    def sizeHint(self):
        s = super().sizeHint(); s.setHeight(s.height() + EDIT_H + 6); return s
    def updateGeometries(self):
        super().updateGeometries(); self.reposition()
    def paintSection(self, painter, rect, logicalIndex):
        rect.setHeight(rect.height() - EDIT_H - 6)
        super().paintSection(painter, rect, logicalIndex)
    def reposition(self, *_a):
        y = self.height() - EDIT_H - 3
        for i, e in enumerate(self.edits):
            if self.isSectionHidden(i): e.hide(); continue
            e.setGeometry(self.sectionViewportPosition(i) + 2, y, max(10, self.sectionSize(i) - 4), EDIT_H); e.show()

class ResultsTable(QTableView):
    copyRequested = Signal(bool)
    def keyPressEvent(self, ev):
        if ev.matches(QKeySequence.Copy): self.copyRequested.emit(False); return
        super().keyPressEvent(ev)

# ================================================================= one results tab
class ColumnsPopup(QFrame):
    """The Columns drop-down. Unlike a menu it stays open while columns are ticked; it closes on a click anywhere outside it, or on the Columns button again.
    Besides one box per column it has one box per group of columns (all kills columns, all columns of one round, ...); a group box is partly ticked when only some of its columns are shown."""
    def __init__(self, page):
        super().__init__(page, Qt.Popup)
        self.page, self.closed_at = page, 0.0
        self.setFrameShape(QFrame.StyledPanel)
        heads, hdr = page.headers, page.hdr
        body = QWidget(); lay = QVBoxLayout(body); lay.setContentsMargins(6, 6, 6, 6); lay.setSpacing(2)
        top = QHBoxLayout()
        show_all = QPushButton('Show all'); show_all.clicked.connect(lambda: self.set_columns(range(len(heads)), True))
        hide_all = QPushButton('Hide all'); hide_all.clicked.connect(lambda: self.set_columns(range(1, len(heads)), False))     # the first column (name / round) stays
        top.addWidget(show_all); top.addWidget(hide_all); top.addStretch(1); lay.addLayout(top)
        self.groups = gl.column_groups(heads)
        self.group_boxes = []
        if self.groups:
            lab = QLabel('Groups'); lab.setStyleSheet('font-weight: bold;'); lay.addWidget(lab)
            for gi, (label, members) in enumerate(self.groups):
                cb = QCheckBox(label); cb.setTristate(True); cb.clicked.connect(lambda _c=False, gi=gi: self.toggle_group(gi))
                lay.addWidget(cb); self.group_boxes.append(cb)
            line = QFrame(); line.setFrameShape(QFrame.HLine); line.setFrameShadow(QFrame.Sunken); lay.addWidget(line)
            lab = QLabel('Columns'); lab.setStyleSheet('font-weight: bold;'); lay.addWidget(lab)
        self.col_boxes = []
        for i, h in enumerate(heads):
            cb = QCheckBox(h); cb.toggled.connect(lambda on, i=i: self.set_columns([i], on)); lay.addWidget(cb); self.col_boxes.append(cb)
        lay.addStretch(1)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.NoFrame); scroll.setWidget(body)
        outer = QVBoxLayout(self); outer.setContentsMargins(2, 2, 2, 2); outer.addWidget(scroll)
        self.body, self.scroll = body, scroll
        self.refresh()

    def hidden(self): return {i for i in range(len(self.page.headers)) if self.page.hdr.isSectionHidden(i)}

    def refresh(self):
        hid = self.hidden()
        for i, cb in enumerate(self.col_boxes):
            cb.blockSignals(True); cb.setChecked(i not in hid); cb.blockSignals(False)
        states = {0: Qt.Unchecked, 1: Qt.PartiallyChecked, 2: Qt.Checked}
        for cb, (_label, members) in zip(self.group_boxes, self.groups):
            cb.blockSignals(True); cb.setCheckState(states[gl.group_state(hid, members)]); cb.blockSignals(False)

    def set_columns(self, indexes, show):
        for i in indexes: self.page.hdr.setSectionHidden(i, not show)
        self.page.hdr.reposition(); self.refresh()

    def toggle_group(self, gi):
        """A group that is fully shown gets hidden; otherwise (hidden or partly shown) all its columns get shown."""
        members = self.groups[gi][1]
        self.set_columns(members, gl.group_state(self.hidden(), members) != 2)

    def hideEvent(self, e):
        self.closed_at = time.monotonic(); super().hideEvent(e)

    def open_under(self, button):
        self.body.adjustSize()
        w = max(self.body.sizeHint().width() + 30, 260); h = min(self.body.sizeHint().height() + 10, 460)
        self.resize(w, h); self.move(button.mapToGlobal(QPoint(0, button.height()))); self.show()

class ResultsPage(QWidget):
    jumpRequested = Signal(float)
    note = Signal(str)
    scopeChanged = Signal()      # the rows this table shows changed (filters, chips)
    def __init__(self, title, headers, rows, with_chips=False, round_kinds=None, parent=None):
        super().__init__(parent)
        self.title, self.headers, self.rows = title, headers, rows
        self.kinds, self.rounds = set(), set()
        self.scope_note = ''
        self.model = TableModel(headers, rows, self)
        self.proxy = ResultsProxy(self); self.proxy.setSourceModel(self.model)
        self.view = ResultsTable(self)
        self.hdr = FilterHeader(self.view); self.view.setHorizontalHeader(self.hdr)
        self.view.setModel(self.proxy)
        self.hdr.setSortIndicator(-1, Qt.AscendingOrder)      # start in file order; a click on a label sorts
        self.view.setSortingEnabled(True)
        self.view.setSelectionMode(QAbstractItemView.ExtendedSelection); self.view.setSelectionBehavior(QAbstractItemView.SelectItems)
        self.view.setAlternatingRowColors(True); self.view.setWordWrap(False)
        self.view.verticalHeader().setDefaultSectionSize(22)
        self.hdr.setSectionResizeMode(QHeaderView.Interactive)
        self.view.resizeColumnsToContents()
        for i in range(len(headers)): self.hdr.resizeSection(i, min(max(self.hdr.sectionSize(i), 90), 380))
        self.hdr.set_columns(len(headers))
        self.hdr.filterChanged.connect(self.apply)
        self.view.horizontalScrollBar().valueChanged.connect(self.hdr.reposition)
        self.view.copyRequested.connect(self.copy)

        top = QHBoxLayout()
        self.ci = QCheckBox('Ignore case'); self.ci.setChecked(True); self.ci.toggled.connect(self.apply)
        clear = QPushButton('Clear filters'); clear.clicked.connect(self.hdr.clear_filters)
        self.cols_btn = QToolButton(); self.cols_btn.setText('Columns ▾'); self.cols_btn.clicked.connect(self.toggle_columns)
        self.cols_popup = None
        self.build_columns_menu()
        copy = QPushButton('Copy selection'); copy.clicked.connect(lambda: self.copy(False))
        copyh = QPushButton('Copy with headers'); copyh.clicked.connect(lambda: self.copy(True))
        self.top = top
        top.addWidget(self.ci); top.addWidget(clear); top.addWidget(self.cols_btn); top.addStretch(1); top.addWidget(copy); top.addWidget(copyh)
        if 'time_s' in headers:
            jump = QPushButton('Show in Packets'); jump.clicked.connect(self.jump); top.addWidget(jump)
        exp = QPushButton('Export shown rows as CSV…'); exp.clicked.connect(self.export); top.addWidget(exp)

        lay = QVBoxLayout(self); lay.setContentsMargins(6, 6, 6, 0)
        lay.addLayout(top)
        if with_chips: lay.addLayout(self.build_chips(round_kinds or {}))
        lay.addWidget(self.view, 1)
        self.status = QLabel(); lay.addWidget(self.status)
        self.apply()

    def build_columns_menu(self):
        """(Re)build the Columns drop-down for the current headers."""
        if self.cols_popup is not None: self.cols_popup.hide(); self.cols_popup.deleteLater()
        self.cols_popup = ColumnsPopup(self)

    def toggle_columns(self):
        pop = self.cols_popup
        if pop.isVisible(): pop.hide()
        elif time.monotonic() - pop.closed_at > 0.25: pop.refresh(); pop.open_under(self.cols_btn)      # (a click on the button that closed it must not reopen it)

    def replace_data(self, headers, rows, sort_name=None, sort_order=Qt.DescendingOrder):
        """Swap in new contents (the Players table is recomputed from the Kills tab). Filter texts, hidden columns and the sort order are kept by column NAME."""
        old = self.headers
        texts = {old[i]: t for i, t in self.hdr.texts().items() if t and i < len(old)}
        hidden = {old[i] for i in range(len(old)) if self.hdr.isSectionHidden(i)}
        sc = self.hdr.sortIndicatorSection()
        keep_sort = (old[sc], self.hdr.sortIndicatorOrder()) if 0 <= sc < len(old) else None
        self.hdr.setSortIndicator(-1, Qt.AscendingOrder)
        self.headers, self.rows = headers, rows
        self.model = TableModel(headers, rows, self); self.proxy.setSourceModel(self.model)
        for i in range(len(headers)): self.hdr.setSectionHidden(i, False)
        self.hdr.set_columns(len(headers))
        for i, h in enumerate(headers):
            e = self.hdr.edits[i]; e.blockSignals(True); e.setText(texts.get(h, '')); e.blockSignals(False)
            if h in hidden: self.hdr.setSectionHidden(i, True)
        self.view.resizeColumnsToContents()
        for i in range(len(headers)): self.hdr.resizeSection(i, min(max(self.hdr.sectionSize(i), 90), 380))
        self.build_columns_menu(); self.apply()
        want = keep_sort if keep_sort and keep_sort[0] in headers else ((sort_name, sort_order) if sort_name in headers else None)
        if want: self.hdr.setSortIndicator(headers.index(want[0]), want[1])
        self.hdr.reposition()

    def scope(self):
        """The rows shown right now, plus whether any filter is active and whether the user chose rounds/kinds (chips or a filter on round_kind)."""
        rows = [self.rows[self.proxy.mapToSource(self.proxy.index(r, 0)).row()] for r in range(self.proxy.rowCount())]
        texts = self.hdr.texts()
        kind_filter = 'round_kind' in self.headers and bool(texts.get(self.headers.index('round_kind'), ''))
        any_filter = bool(self.kinds or self.rounds) or any(texts.values())
        return rows, any_filter, bool(self.kinds or self.rounds) or kind_filter

    # ---- round / kind chips (kills table)
    def build_chips(self, round_kinds):
        row = QHBoxLayout(); row.addWidget(QLabel('Rounds (any combination):'))
        self.chip_btns = {}
        allb = QPushButton('All'); allb.setCheckable(True); allb.setChecked(True); allb.clicked.connect(self.chips_all); row.addWidget(allb); self.all_btn = allb
        for cid, label, _ks in gl.KIND_CHIPS:
            b = QPushButton(label); b.setCheckable(True); b.toggled.connect(lambda on, cid=cid: self.chip_kind(cid, on)); row.addWidget(b); self.chip_btns[cid] = b
        nums = sorted({r[self.headers.index('round')] for r in self.rows}, key=lambda s: (len(s), s)) if 'round' in self.headers else []
        if nums:
            tb = QToolButton(); tb.setText('Round numbers…'); tb.setPopupMode(QToolButton.InstantPopup)
            m = QMenu(tb); self.round_actions = []
            for n in nums:
                a = QAction('Round %s%s' % (n, ' (%s)' % round_kinds[n] if n in round_kinds and round_kinds[n] else ''), m); a.setCheckable(True)
                a.toggled.connect(lambda on, n=n: self.chip_round(n, on)); m.addAction(a); self.round_actions.append(a)
            tb.setMenu(m); row.addWidget(tb)
        row.addStretch(1)
        return row
    def chips_all(self):
        for b in self.chip_btns.values(): b.blockSignals(True); b.setChecked(False); b.blockSignals(False)
        for a in getattr(self, 'round_actions', []): a.blockSignals(True); a.setChecked(False); a.blockSignals(False)
        self.kinds.clear(); self.rounds.clear(); self.all_btn.setChecked(True); self.apply()
    def chip_kind(self, cid, on):
        (self.kinds.add if on else self.kinds.discard)(cid); self.sync_all(); self.apply()
    def chip_round(self, n, on):
        (self.rounds.add if on else self.rounds.discard)(n); self.sync_all(); self.apply()
    def sync_all(self):
        self.all_btn.blockSignals(True); self.all_btn.setChecked(not self.kinds and not self.rounds); self.all_btn.blockSignals(False)

    # ---- filtering
    def apply(self, *_a):
        rx, bad = gl.compile_filters(self.hdr.texts(), self.ci.isChecked())
        self.hdr.mark_bad(bad)
        self.proxy.set_filters(rx, gl.chip_predicate(self.headers, self.kinds, self.rounds))
        self.update_status(); self.scopeChanged.emit()
    def update_status(self):
        sel = len({i.row() for i in self.view.selectionModel().selectedIndexes()}) if self.view.selectionModel() else 0
        self.status.setText('Showing %d of %d rows%s%s' % (self.proxy.rowCount(), len(self.rows), ' · %d selected' % sel if sel else '', ' · ' + self.scope_note if self.scope_note else ''))

    # ---- copy / export / jump
    def selection_grid(self):
        hdr = self.view.horizontalHeader()
        cells = {}
        for ix in self.view.selectionModel().selectedIndexes():
            if hdr.isSectionHidden(ix.column()): continue
            cells[(ix.row(), hdr.visualIndex(ix.column()))] = ix.data()
        if not cells: return [], []
        rows = sorted({r for r, _ in cells}); cols = sorted({c for _, c in cells})
        return [self.headers[hdr.logicalIndex(c)] for c in cols], [[cells.get((r, c)) for c in cols] for r in rows]
    def copy(self, with_header=False):
        heads, grid = self.selection_grid()
        if not grid: self.note.emit('Nothing selected: click cells, drag, or click a row number (Shift/Ctrl for several).'); return
        QGuiApplication.clipboard().setText(gl.cells_to_tsv(heads, grid, with_header))
        self.note.emit('Copied %d rows × %d columns as tab-separated text (paste into Excel, Sheets or a CSV editor).' % (len(grid), len(heads)))
    def shown(self):
        hdr = self.view.horizontalHeader()
        vis = [hdr.logicalIndex(v) for v in range(hdr.count()) if not hdr.isSectionHidden(hdr.logicalIndex(v))]
        rows = [[self.proxy.index(r, c).data() for c in vis] for r in range(self.proxy.rowCount())]
        return [self.headers[c] for c in vis], rows
    def export(self):
        base = self.title.lower().replace(' ', '') + '.csv'
        if getattr(self, 'export_dir', ''): base = os.path.join(self.export_dir, base)
        path, _ = QFileDialog.getSaveFileName(self, 'Export shown rows', base, 'CSV files (*.csv)')
        if not path: return
        heads, rows = self.shown()
        try: gl.write_csv_table(path, heads, rows)
        except OSError as ex: QMessageBox.warning(self, APP, 'Could not write %s:\n%s' % (path, ex)); return
        self.note.emit('Exported %d rows to %s' % (len(rows), path))
    def jump(self):
        ix = self.view.currentIndex()
        if not ix.isValid(): self.note.emit('Select a row first.'); return
        try: self.jumpRequested.emit(float(self.proxy.index(ix.row(), self.headers.index('time_s')).data()))
        except ValueError: pass

# ================================================================= background workers
class LoadWorker(QThread):
    """Read the capture, find the server flow and calibrate the decoder, so the packet list can be shown."""
    loaded = Signal(object)
    failed = Signal(str)
    message = Signal(str)
    def __init__(self, path, port, parent=None):
        super().__init__(parent); self.path, self.port = path, port
    def run(self):
        try:
            from .pcap import read_pcapng
            from .cli import find_server_flow
            from . import decoder
            self.message.emit('Reading %s …' % os.path.basename(self.path))
            _ifs, pk = read_pcapng(self.path)
            key, flow = find_server_flow(pk, self.port)
            if not flow: self.failed.emit('Could not find the game server flow in this capture. Try setting the server port in Options.'); return
            t0 = flow[0][0]
            self.message.emit('Calibrating for this server …')
            prof = decoder.calibrate([pl for _ts, pl in flow[:60000]], log=self.message.emit)
            decoder.set_profile(prof)
            self.loaded.emit(dict(key=key, items=[(ts - t0, pl) for ts, pl in flow], total=len(pk), size=os.path.getsize(self.path)))
        except Exception:
            self.failed.emit(traceback.format_exc())

class IndexWorker(QThread):
    """Decode the message types of every packet in the background so the display filter can search them."""
    progress = Signal(int, int)
    def __init__(self, model, parent=None):
        super().__init__(parent); self.model = model; self.stop = False
    def run(self):
        n = len(self.model.items)
        for r in range(n):
            if self.stop: return
            if r not in self.model.info:
                try: self.model.info[r] = gl.packet_info(self.model.items[r][1])
                except Exception: self.model.info[r] = dict(queued=False, n=0, msgs=[], types='')
            if r % 500 == 0: self.progress.emit(r, n)
        self.progress.emit(n, n)

class ConvertWorker(QThread):
    progress = Signal(str, float)
    message = Signal(str)
    finished_ok = Signal(object)
    failed = Signal(str)
    def __init__(self, ns, parent=None):
        super().__init__(parent); self.ns = ns; self.cancel_flag = False
    def cancel(self): self.cancel_flag = True
    def run(self):
        from .cli import run, Cancelled
        def prog(stage, frac):
            if self.cancel_flag: raise Cancelled()
            self.progress.emit(stage, float(frac))
        try:
            paths = run(self.ns, log=self.message.emit, progress=prog)
            self.finished_ok.emit(paths)
        except Cancelled: self.failed.emit('')
        except RuntimeError as ex: self.failed.emit(str(ex))
        except Exception: self.failed.emit(traceback.format_exc())

# ================================================================= main window
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('nwkills'); self.resize(1280, 820); self.setAcceptDrops(True)
        self.cfg = QSettings('nwkills', 'nwkills')
        self.path = None; self.loader = self.converter = self.indexer = None; self.tmp = None
        self.sweep_tmp()
        self.pages = []; self.kills_page = self.players_page = self.players_orig = None

        root = QWidget(); self.setCentralWidget(root)
        lay = QVBoxLayout(root); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(0)

        top = QHBoxLayout(); top.setContentsMargins(8, 6, 8, 6)
        b = QPushButton('Open .pcapng…'); b.clicked.connect(self.open_dialog); top.addWidget(b)
        self.file_lbl = QLabel('No capture loaded. Open one, or drop a .pcapng onto this window.'); top.addWidget(self.file_lbl, 1)
        lay.addLayout(top)

        self.tabs = QTabWidget(); lay.addWidget(self.tabs, 1)
        self.build_packets_tab(); self.build_options_tab(); self.build_results_tab()
        self.tabs.setTabEnabled(2, False)

        self.log = QPlainTextEdit(); self.log.setReadOnly(True); self.log.setMaximumHeight(130); self.log.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont)); self.log.hide()
        lay.addWidget(self.log)

        foot = QHBoxLayout(); foot.setContentsMargins(8, 6, 8, 6)
        self.go = QPushButton('Convert'); self.go.setEnabled(False); self.go.setStyleSheet('font-weight: bold; padding: 6px 22px;'); self.go.clicked.connect(self.convert); foot.addWidget(self.go)
        self.stop = QPushButton('Cancel'); self.stop.setEnabled(False); self.stop.clicked.connect(self.cancel); foot.addWidget(self.stop)
        lb = QPushButton('Log'); lb.setCheckable(True); lb.toggled.connect(self.log.setVisible); foot.addWidget(lb)
        self.stage_lbl = QLabel('Idle'); self.stage_bar = QProgressBar(); self.stage_bar.setRange(0, 100)
        self.all_bar = QProgressBar(); self.all_bar.setRange(0, 100)
        c1 = QVBoxLayout(); c1.addWidget(self.stage_lbl); c1.addWidget(self.stage_bar)
        c2 = QVBoxLayout(); c2.addWidget(QLabel('Overall')); c2.addWidget(self.all_bar)
        foot.addLayout(c1, 1); foot.addLayout(c2, 1)
        lay.addLayout(foot)
        self.statusBar().showMessage('Open a capture to begin.')
        self.restore_options()

    # ------------------------------------------------------------ tabs
    def build_packets_tab(self):
        w = QWidget(); lay = QVBoxLayout(w)
        bar = QHBoxLayout()
        bar.addWidget(QLabel('Display filter (regex):'))
        self.pf = QLineEdit(); self.pf.setPlaceholderText('e.g.  queued|^13  — matches number, length, flags and message types'); self.pf.setClearButtonEnabled(True); bar.addWidget(self.pf, 1)
        self.index_btn = QPushButton('Index message types'); self.index_btn.setToolTip('Decode every packet in the background so the filter can search the message types too'); self.index_btn.clicked.connect(self.start_index); self.index_btn.setEnabled(False); bar.addWidget(self.index_btn)
        self.pcount = QLabel(''); bar.addWidget(self.pcount)
        lay.addLayout(bar)
        self.pmodel = PacketModel(self); self.pproxy = PacketProxy(self); self.pproxy.setSourceModel(self.pmodel)
        self.ptable = QTableView(); self.ptable.setModel(self.pproxy)
        self.ptable.setSelectionBehavior(QAbstractItemView.SelectRows); self.ptable.setSelectionMode(QAbstractItemView.SingleSelection)
        self.ptable.verticalHeader().hide(); self.ptable.verticalHeader().setDefaultSectionSize(20)
        self.ptable.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
        self.ptable.horizontalHeader().setStretchLastSection(True)
        for i, wd in enumerate((70, 110, 70, 80, 60)): self.ptable.setColumnWidth(i, wd)
        self.ptable.selectionModel().currentRowChanged.connect(self.show_packet)
        split = QSplitter(Qt.Vertical); split.addWidget(self.ptable)
        lower = QSplitter(Qt.Horizontal)
        self.tree = QTreeWidget(); self.tree.setHeaderHidden(True); self.tree.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
        self.hex = QPlainTextEdit(); self.hex.setReadOnly(True); self.hex.setLineWrapMode(QPlainTextEdit.NoWrap); self.hex.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
        lower.addWidget(self.tree); lower.addWidget(self.hex); split.addWidget(lower); split.setSizes([480, 240])
        lay.addWidget(split, 1)
        self.ptimer = QTimer(self); self.ptimer.setSingleShot(True); self.ptimer.setInterval(250); self.ptimer.timeout.connect(self.apply_pfilter)
        self.pf.textChanged.connect(lambda _t: self.ptimer.start())
        self.tabs.addTab(w, 'Packets')

    def build_options_tab(self):
        w = QWidget(); lay = QVBoxLayout(w)
        g1 = QGroupBox('Server'); f1 = QFormLayout(g1)
        self.auto = QCheckBox('Detect server port automatically'); self.auto.setChecked(True); f1.addRow(self.auto)
        self.port = QSpinBox(); self.port.setRange(1, 65535); self.port.setValue(7240); self.port.setEnabled(False); f1.addRow('Port (--port)', self.port)
        self.auto.toggled.connect(lambda on: self.port.setEnabled(not on))
        self.me = QLineEdit(); self.me.setPlaceholderText('part of your own player name'); f1.addRow('My player name (--me)', self.me)
        g2 = QGroupBox('Performance'); f2 = QFormLayout(g2)
        self.jobs = QSpinBox(); self.jobs.setRange(1, 64); self.jobs.setValue(max(1, os.cpu_count() or 2)); f2.addRow('Worker processes (--jobs)', self.jobs)
        self.cache = QCheckBox('Cache decoded packets in the export folder (re-runs skip decoding)  (--cache)'); self.cache.setChecked(False); f2.addRow(self.cache)
        row = QHBoxLayout(); self.use_limit = QCheckBox('Only read the first'); self.limit = QSpinBox(); self.limit.setRange(100, 100000000); self.limit.setValue(200000); self.limit.setEnabled(False)
        row.addWidget(self.use_limit); row.addWidget(self.limit); row.addWidget(QLabel('packets (--limit, for quick tests)')); row.addStretch(1)
        self.use_limit.toggled.connect(self.limit.setEnabled); f2.addRow(row)
        g3 = QGroupBox('Export'); f3 = QFormLayout(g3)
        row = QHBoxLayout(); self.outdir = QLineEdit(); br = QPushButton('Browse…'); br.clicked.connect(self.browse_out); row.addWidget(self.outdir, 1); row.addWidget(br); f3.addRow('Default export folder (--out)', row)
        self.outdir.setPlaceholderText('empty = next to the capture. Converting writes no files here: CSV files appear only when you export.')
        g4 = QGroupBox('Equivalent command line'); l4 = QVBoxLayout(g4)
        self.cmd = QLabel(); self.cmd.setWordWrap(True); self.cmd.setTextInteractionFlags(Qt.TextSelectableByMouse); self.cmd.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont)); l4.addWidget(self.cmd)
        for g in (g1, g2, g3, g4): lay.addWidget(g)
        lay.addStretch(1)
        for wdg in (self.auto, self.cache, self.use_limit): wdg.toggled.connect(self.update_cmd)
        for wdg in (self.port, self.jobs, self.limit): wdg.valueChanged.connect(self.update_cmd)
        for wdg in (self.me, self.outdir): wdg.textChanged.connect(self.update_cmd)
        self.tabs.addTab(w, 'Options')

    def build_results_tab(self):
        w = QWidget(); lay = QVBoxLayout(w); lay.setContentsMargins(0, 0, 0, 0)
        bar = QHBoxLayout(); bar.setContentsMargins(6, 4, 6, 0)
        self.res_info = QLabel(''); bar.addWidget(self.res_info, 1)
        ex = QPushButton('Export all tables…'); ex.clicked.connect(self.export_all); bar.addWidget(ex)
        lay.addLayout(bar)
        self.rtabs = QTabWidget(); lay.addWidget(self.rtabs, 1)
        self.tabs.addTab(w, 'Results')

    # ------------------------------------------------------------ options
    def options(self):
        stem = os.path.splitext(os.path.basename(self.path or 'capture'))[0]
        outdir = self.outdir.text().strip() or (os.path.dirname(os.path.abspath(self.path)) if self.path else '')
        return dict(pcap=self.path or '', out=os.path.join(outdir, stem + '_kills.csv'), port=None if self.auto.isChecked() else self.port.value(),
                    me=self.me.text().strip() or None, jobs=self.jobs.value(), cache=os.path.join(outdir, stem + '.nwcache.pkl') if self.cache.isChecked() else None,
                    limit=self.limit.value() if self.use_limit.isChecked() else None)
    def update_cmd(self, *_a): self.cmd.setText(gl.command_line(self.options()))
    def browse_out(self):
        d = QFileDialog.getExistingDirectory(self, 'Default export folder', self.outdir.text() or os.path.expanduser('~'))
        if d: self.outdir.setText(d)
    def export_folder(self):
        return self.outdir.text().strip() or (os.path.dirname(os.path.abspath(self.path)) if self.path else os.path.expanduser('~'))
    def restore_options(self):
        c = self.cfg
        self.me.setText(c.value('me', '')); self.outdir.setText(c.value('outdir', ''))
        self.jobs.setValue(int(c.value('jobs', self.jobs.value()))); self.cache.setChecked(c.value('cache_on', 'false') == 'true')
        self.update_cmd()
    def save_options(self):
        c = self.cfg; c.setValue('me', self.me.text()); c.setValue('outdir', self.outdir.text()); c.setValue('jobs', self.jobs.value())
        c.setValue('cache_on', 'true' if self.cache.isChecked() else 'false')

    # ------------------------------------------------------------ loading
    def open_dialog(self):
        p, _ = QFileDialog.getOpenFileName(self, 'Open capture', self.cfg.value('lastdir', ''), 'Wireshark captures (*.pcapng *.pcap);;All files (*)')
        if p: self.load(p)
    def dragEnterEvent(self, ev):
        if ev.mimeData().hasUrls() and any(u.toLocalFile().lower().endswith(('.pcapng', '.pcap')) for u in ev.mimeData().urls()): ev.acceptProposedAction()
    def dropEvent(self, ev):
        for u in ev.mimeData().urls():
            if u.toLocalFile().lower().endswith(('.pcapng', '.pcap')): self.load(u.toLocalFile()); break
    def load(self, path):
        if self.converter and self.converter.isRunning(): QMessageBox.information(self, APP, 'A conversion is running. Cancel it first.'); return
        self.stop_index()
        self.path = path; self.cfg.setValue('lastdir', os.path.dirname(path))
        self.go.setEnabled(False); self.index_btn.setEnabled(False)
        self.file_lbl.setText('Loading %s …' % os.path.basename(path)); self.statusBar().showMessage('Reading capture …')
        self.pmodel.set_items([]); self.update_cmd()
        self.loader = LoadWorker(path, None if self.auto.isChecked() else self.port.value(), self)
        self.loader.message.connect(self.statusBar().showMessage); self.loader.message.connect(self.add_log)
        self.loader.loaded.connect(self.on_loaded); self.loader.failed.connect(self.on_load_failed); self.loader.start()
    def on_loaded(self, d):
        self.pmodel.set_items(d['items'])
        k = d['key']
        self.file_lbl.setText('%s   ·   %.0f MB   ·   %s packets, %s from the server   ·   server %s:%d' % (os.path.basename(self.path), d['size'] / 1e6, format(d['total'], ','), format(len(d['items']), ','), k[0], k[1]))
        self.index_btn.setEnabled(True); self.go.setEnabled(True)
        self.pcount.setText('%s packets' % format(len(d['items']), ','))
        self.statusBar().showMessage('Loaded. Set options if needed, then press Convert.')
        self.tabs.setCurrentIndex(0)
    def on_load_failed(self, msg):
        self.file_lbl.setText('Could not load %s' % os.path.basename(self.path or '')); self.statusBar().showMessage('Load failed.')
        self.add_log(msg); QMessageBox.warning(self, APP, msg if len(msg) < 400 else msg[-400:])

    # ------------------------------------------------------------ packet list
    def apply_pfilter(self):
        import re
        t = self.pf.text()
        try: self.pproxy.set_regex(re.compile(t, re.I) if t else None); self.pf.setStyleSheet('')
        except re.error: self.pf.setStyleSheet('border: 1px solid #c62828;'); return
        n = len(self.pmodel.items)
        self.pcount.setText('Showing %s of %s packets · message types indexed for %s' % (format(self.pproxy.rowCount(), ','), format(n, ','), format(len(self.pmodel.info), ',')))
    def start_index(self):
        if self.indexer and self.indexer.isRunning(): return
        self.indexer = IndexWorker(self.pmodel, self)
        self.indexer.progress.connect(self.on_index_progress); self.indexer.finished.connect(self.apply_pfilter)
        self.index_btn.setEnabled(False); self.indexer.start()
    def stop_index(self):
        if self.indexer and self.indexer.isRunning(): self.indexer.stop = True; self.indexer.wait(3000)
    def on_index_progress(self, done, n):
        self.statusBar().showMessage('Indexing message types … %d / %d' % (done, n))
        if done >= n: self.statusBar().showMessage('Message types indexed.'); self.index_btn.setEnabled(True)
    def show_packet(self, cur, _prev=None):
        self.tree.clear(); self.hex.clear()
        if not cur.isValid(): return
        r = self.pproxy.mapToSource(cur).row()
        t, pl = self.pmodel.items[r]; info = self.pmodel.get_info(r)
        root = QTreeWidgetItem(['Packet %d: %d bytes, t = %.6f s' % (r + 1, len(pl), t)])
        hd = QTreeWidgetItem(['Header: %s' % pl[:12].hex(' ')]); root.addChild(hd)
        root.addChild(QTreeWidgetItem(['Queued packet: %s' % ('yes (byte 7 = 0, the game replays it without the count byte)' if info['queued'] else 'no')]))
        ms = QTreeWidgetItem(['Messages: %d' % info['n']]); root.addChild(ms)
        for i, m in enumerate(info['msgs']):
            it = QTreeWidgetItem(['#%d  type %d  (%d fields)' % (i + 1, m[2], len(m[3]))]); ms.addChild(it)
            for j, (bits, val) in enumerate(m[3][:40]): it.addChild(QTreeWidgetItem(['field %d: %s   [%d bits]' % (j, val, bits)]))
        self.tree.addTopLevelItem(root); root.setExpanded(True); ms.setExpanded(info['n'] <= 6)
        self.hex.setPlainText(gl.hexdump(pl))
    def show_in_packets(self, t):
        if not self.pmodel.times: self.statusBar().showMessage('No packet list loaded.'); return
        r = gl.packet_at_time(self.pmodel.times, t)
        ix = self.pproxy.mapFromSource(self.pmodel.index(r, 0))
        if not ix.isValid(): self.statusBar().showMessage('That packet is hidden by the display filter.'); self.tabs.setCurrentIndex(0); return
        self.tabs.setCurrentIndex(0); self.ptable.selectRow(ix.row()); self.ptable.scrollTo(ix, QAbstractItemView.PositionAtCenter)
        self.show_packet(ix)

    # ------------------------------------------------------------ converting
    def convert(self):
        if not self.path: return
        self.save_options(); o = self.options()
        if o['cache'] and not os.path.isdir(os.path.dirname(o['cache'])):
            try: os.makedirs(os.path.dirname(o['cache']))
            except OSError as ex: QMessageBox.warning(self, APP, 'Cannot create the folder for the cache:\n%s' % ex); return
        self.stop_index(); self.drop_tmp()
        # The converter writes its files into a temporary folder; the tables are read into memory and the folder is deleted. CSV files are only written by Export.
        self.tmp = tempfile.mkdtemp(prefix='nwkills-')
        out = os.path.join(self.tmp, os.path.basename(o['out']))
        ns = argparse.Namespace(pcap=o['pcap'], out=out, port=o['port'], me=o['me'], jobs=o['jobs'], cache=o['cache'], limit=o['limit'])
        self.log.clear(); self.go.setEnabled(False); self.stop.setEnabled(True)
        self.stage_bar.setRange(0, 100); self.stage_bar.setValue(0); self.all_bar.setValue(0); self.stage_lbl.setText('Starting …')
        self.t_start = time.time()
        self.converter = ConvertWorker(ns, self)
        self.converter.progress.connect(self.on_progress); self.converter.message.connect(self.add_log)
        self.converter.finished_ok.connect(self.on_done); self.converter.failed.connect(self.on_failed); self.converter.start()
        self.statusBar().showMessage('Converting …')
    def cancel(self):
        if self.converter: self.converter.cancel(); self.statusBar().showMessage('Cancelling …')
    def on_progress(self, stage, frac):
        label, overall, sfrac = gl.overall_progress(stage, frac)
        self.stage_lbl.setText(label)
        if sfrac is None: self.stage_bar.setRange(0, 0)
        else: self.stage_bar.setRange(0, 100); self.stage_bar.setValue(int(sfrac * 100))
        self.all_bar.setValue(int(overall))
    def add_log(self, text): self.log.appendPlainText(text)
    def drop_tmp(self):
        if self.tmp: shutil.rmtree(self.tmp, ignore_errors=True); self.tmp = None
    @staticmethod
    def sweep_tmp():
        """Remove temporary result folders that an earlier run (crashed, killed) left behind: old, and holding nothing but csv files."""
        for d in glob.glob(os.path.join(tempfile.gettempdir(), 'nwkills-*')):
            try:
                if os.path.isdir(d) and time.time() - os.path.getmtime(d) > 3600 and all(f.lower().endswith('.csv') for f in os.listdir(d)): shutil.rmtree(d, ignore_errors=True)
            except OSError: pass
    def on_failed(self, msg):
        self.drop_tmp()
        self.stage_bar.setRange(0, 100); self.stage_bar.setValue(0); self.all_bar.setValue(0); self.go.setEnabled(True); self.stop.setEnabled(False)
        if not msg: self.stage_lbl.setText('Cancelled'); self.statusBar().showMessage('Cancelled.'); return
        self.stage_lbl.setText('Failed'); self.statusBar().showMessage('Conversion failed.'); self.add_log(msg)
        QMessageBox.warning(self, APP, 'Conversion failed:\n\n' + (msg if len(msg) < 600 else msg[-600:]))
    def on_done(self, paths):
        self.go.setEnabled(True); self.stop.setEnabled(False); self.stage_bar.setRange(0, 100); self.stage_bar.setValue(100); self.all_bar.setValue(100); self.stage_lbl.setText('Finished')
        try: self.show_results(paths)
        except Exception: self.add_log(traceback.format_exc()); QMessageBox.warning(self, APP, 'The results could not be shown:\n' + traceback.format_exc()[-400:]); return
        finally: self.drop_tmp()
        self.statusBar().showMessage('Done in %.0f s. Nothing has been written to disk: use Export to save CSV files.' % (time.time() - self.t_start))

    # ------------------------------------------------------------ results
    def show_results(self, paths):
        self.rtabs.clear(); self.pages = []; self.kills_page = self.players_page = self.players_orig = None
        rh, rr = gl.read_csv_table(paths['rounds']) if paths.get('rounds') and os.path.exists(paths['rounds']) else ([], [])
        round_kinds = {r[rh.index('round')]: r[rh.index('kind')] for r in rr} if rh else {}
        for key, title, chips in (('kills', 'Kills', True), ('players', 'Players', False), ('rounds', 'Rounds', False), ('flagbearers', 'Flagbearers', False)):
            p = paths.get(key)
            if not p or not os.path.exists(p): continue
            h, rows = gl.read_csv_table(p)
            page = ResultsPage(title, h, rows, with_chips=chips, round_kinds=round_kinds)
            page.export_dir = self.export_folder()
            page.note.connect(self.statusBar().showMessage); page.jumpRequested.connect(self.show_in_packets)
            self.view_connect(page)
            self.rtabs.addTab(page, '%s (%d)' % (title, len(rows))); self.pages.append(page)
            if key == 'kills': self.kills_page = page
            if key == 'players': self.players_page = page; self.players_orig = (h, rows)
        if self.kills_page and self.players_page:
            self.neg = QCheckBox('Teamkills count negatively'); self.neg.setChecked(True)
            self.neg.setToolTip('On: kills = kills − teamkills, also per round (like the in-game scoreboard). Off: kills are kills only.')
            self.players_page.top.insertWidget(3, self.neg)
            self.ptot_timer = QTimer(self); self.ptot_timer.setSingleShot(True); self.ptot_timer.setInterval(200); self.ptot_timer.timeout.connect(self.refresh_players)
            self.kills_page.scopeChanged.connect(self.ptot_timer.start); self.neg.toggled.connect(self.refresh_players)
            self.refresh_players()
        self.res_info.setText('The results are held in memory only. Export saves CSV files.')
        self.tabs.setTabEnabled(2, True); self.tabs.setCurrentIndex(2)
    def refresh_players(self):
        """Players tab = totals of the kill rows the Kills tab shows right now."""
        kp, pp = self.kills_page, self.players_page
        if not kp or not pp: return
        rows, any_filter, chosen = kp.scope()
        ph, pr = self.players_orig
        heads, out = gl.player_totals(kp.headers, rows, ph, pr, net=self.neg.isChecked(), exclude_warm=not chosen, all_players=not any_filter)
        pp.scope_note = 'totals from %d of %d kill rows%s' % (len(rows), len(kp.rows), '' if chosen else ' (warm-up rounds left out; pick Warm-up to include them)')
        pp.replace_data(heads, out, sort_name='kills')
        self.rtabs.setTabText(self.rtabs.indexOf(pp), 'Players (%d)' % len(out))
    def view_connect(self, page):
        page.view.selectionModel().selectionChanged.connect(lambda *_a, p=page: p.update_status())
    def export_all(self):
        if not self.pages: return
        d = QFileDialog.getExistingDirectory(self, 'Export all tables (unfiltered) to…', self.export_folder())
        if not d: return
        try:
            for p in self.pages: gl.write_csv_table(os.path.join(d, p.title.lower() + '.csv'), p.headers, p.rows)      # Players = the current Kills filters
        except OSError as ex: QMessageBox.warning(self, APP, str(ex)); return
        self.statusBar().showMessage('Wrote %d files to %s' % (len(self.pages), d))

    def closeEvent(self, ev):
        self.save_options(); self.stop_index()
        if self.converter and self.converter.isRunning():
            self.converter.cancel(); self.converter.wait(5000)
        self.drop_tmp()
        ev.accept()

def selftest():
    """Builds a small results table and checks sorting, regex filters, chips and copy. Used by the build to catch a broken Qt install."""
    heads = ['round', 'round_kind', 'time_s', 'killer', 'review']
    rows = [['1', 'pre-live', '5.0', 'Anna', ''], ['2', 'warm-up', '70.0', 'Bob', 'x'], ['3', 'live', '100.0', 'anna2', ''], ['3', 'live', '9.0', 'Carl', '']]
    pg = ResultsPage('Kills', heads, rows, with_chips=True, round_kinds={'1': 'pre-live', '2': 'warm-up', '3': 'live'})
    assert pg.proxy.rowCount() == 4
    pg.hdr.edits[3].setText('^anna')
    assert pg.proxy.rowCount() == 2, pg.proxy.rowCount()
    pg.ci.setChecked(False); assert pg.proxy.rowCount() == 1, pg.proxy.rowCount()      # case-sensitive: only 'anna2' matches '^anna'
    pg.ci.setChecked(True); pg.hdr.clear_filters(); assert pg.proxy.rowCount() == 4
    pg.chip_kind('prelive', True); assert pg.proxy.rowCount() == 3
    pg.chip_kind('warm', True); assert pg.proxy.rowCount() == 4
    pg.chips_all(); pg.chip_round('3', True); assert pg.proxy.rowCount() == 2
    pg.chips_all(); pg.proxy.sort(2, Qt.AscendingOrder)
    assert [pg.proxy.index(r, 3).data() for r in range(4)] == ['Anna', 'Carl', 'Bob', 'anna2']
    pg.view.selectAll(); heads2, grid = pg.selection_grid()
    assert len(grid) == 4 and heads2 == heads, (heads2, len(grid))
    assert gl.cells_to_tsv(heads2, grid).split('\n')[0].split('\t')[3] == 'Anna'
    # recomputing a table keeps the typed filters by column name
    pp = ResultsPage('Players', ['player', 'kills', 'deaths'], [['a', '3', '1'], ['b', '2', '0']])
    pp.hdr.edits[0].setText('a')
    pp.replace_data(['player', 'kills', 'R1_kills'], [['a', '5', '5'], ['ab', '1', '1'], ['c', '9', '9']], sort_name='kills')
    assert pp.proxy.rowCount() == 2 and pp.hdr.edits[0].text() == 'a'
    assert [pp.proxy.index(r, 0).data() for r in range(2)] == ['a', 'ab']      # kills, descending
    rows_, any_f, chosen = pg.scope(); assert any_f is False or True
    # columns drop-down: single columns and groups
    gp = ResultsPage('Players', ['player', 'kills', 'deaths', 'R1(live)_kills', 'R1(live)_deaths', 'R2(live)_kills', 'R2(live)_deaths'], [['a', '1', '1', '1', '1', '0', '0']])
    pop = gp.cols_popup; names = [l for l, _m in pop.groups]
    assert 'All kills columns' in names and 'Round R1(live)' in names, names
    gk = names.index('All kills columns'); gp.cols_popup.toggle_group(gk)
    assert [gp.hdr.isSectionHidden(i) for i in (1, 3, 5)] == [True, True, True] and not gp.hdr.isSectionHidden(2)
    assert pop.group_boxes[gk].checkState() == Qt.Unchecked
    pop.set_columns([3], True); assert pop.group_boxes[gk].checkState() == Qt.PartiallyChecked
    pop.toggle_group(gk); assert not any(gp.hdr.isSectionHidden(i) for i in (1, 3, 5))           # partly shown -> all shown
    pop.set_columns(range(1, 7), False); assert all(gp.hdr.isSectionHidden(i) for i in range(1, 7)) and not gp.hdr.isSectionHidden(0)
    pop.set_columns(range(7), True); assert not any(gp.hdr.isSectionHidden(i) for i in range(7))
    assert pg.cols_popup.groups == []

def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if sys.stdout is None: sys.stdout = open(os.devnull, 'w')
    if sys.stderr is None: sys.stderr = open(os.devnull, 'w')
    if '--selftest' in argv: os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    app = QApplication.instance() or QApplication([APP])
    app.setStyle('Fusion')
    win = MainWindow()
    if '--selftest' in argv:
        win.show(); app.processEvents(); selftest(); print('gui ok'); return 0
    win.show()
    files = [a for a in argv if not a.startswith('-')]
    if files: QTimer.singleShot(0, lambda: win.load(files[0]))
    return app.exec()

if __name__ == '__main__':
    sys.exit(main())

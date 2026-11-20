"""`nwkills-gui --selftest`: builds small tables and a window offscreen and checks sorting, filters, chips, copy and the tabs.
The build runs it to catch a broken Qt install."""
import os
import tempfile

from PySide6.QtCore import Qt

from ..packets.server_profile import NWE_PROFILE
from ..viewlogic import CsvTableFile, MultikillFinder, PacketSummarizer, TabSeparatedFormatter
from .main_window import MainWindow
from .results_page import ResultsPage

KILL_HEADERS = ['round', 'round_kind', 'time_s', 'mm:ss', 'killer', 'victim', 'weapon', 'teamkill', 'death_type', 'review']
VOLLEY_ROWS = [['1', 'live', '10.0', '0:10', 'G', 'a', 'artillery: cannonball', '', 'kill', ''],
               ['1', 'live', '10.0', '0:10', 'G', 'b', 'artillery: cannonball', 'yes', 'kill', ''],
               ['1', 'live', '10.4', '0:10', 'G', 'c', 'artillery: cannonball', '', 'kill', ''],
               ['1', 'live', '50.0', '0:50', 'G', 'd', 'artillery: cannonball', '', 'kill', '']]


def check_filters_chips_sorting_and_copy() -> None:
    headers = ['round', 'round_kind', 'time_s', 'killer', 'review']
    rows = [['1', 'pre-live', '5.0', 'Anna', ''], ['2', 'warm-up', '70.0', 'Bob', 'x'], ['3', 'live', '100.0', 'anna2', ''], ['3', 'live', '9.0', 'Carl', '']]
    page = ResultsPage('Kills', headers, rows, with_chips=True, round_kinds={'1': 'pre-live', '2': 'warm-up', '3': 'live'})
    assert page.proxy.rowCount() == 4
    page.header_view.filter_boxes[3].setText('^anna')
    assert page.proxy.rowCount() == 2, page.proxy.rowCount()
    page.ignore_case_box.setChecked(False)
    assert page.proxy.rowCount() == 1, page.proxy.rowCount()      # case-sensitive: only 'anna2' matches '^anna'
    page.ignore_case_box.setChecked(True)
    page.header_view.clear_filters()
    assert page.proxy.rowCount() == 4
    page.chip_bar.set_chip('prelive', True)
    assert page.proxy.rowCount() == 3
    page.chip_bar.set_chip('warm', True)
    assert page.proxy.rowCount() == 4
    page.chip_bar.select_all()
    page.chip_bar.set_round('3', True)
    assert page.proxy.rowCount() == 2
    page.chip_bar.select_all()
    page.proxy.sort(2, Qt.AscendingOrder)
    assert [page.proxy.index(row, 3).data() for row in range(4)] == ['Anna', 'Carl', 'Bob', 'anna2']
    page.view.selectAll()
    selected_headers, grid = page.selection_grid()
    assert len(grid) == 4 and selected_headers == headers, (selected_headers, len(grid))
    assert TabSeparatedFormatter.format(selected_headers, grid).split('\n')[0].split('\t')[3] == 'Anna'
    scope = page.scope()
    assert len(scope.rows) == 4 and scope.any_filter_active is False and scope.rounds_chosen is False


def check_replacing_a_table_keeps_filters_by_column_name() -> None:
    page = ResultsPage('Players', ['player', 'kills', 'deaths'], [['a', '3', '1'], ['b', '2', '0']])
    page.header_view.filter_boxes[0].setText('a')
    page.replace_data(['player', 'kills', 'R1_kills'], [['a', '5', '5'], ['ab', '1', '1'], ['c', '9', '9']], sort_name='kills')
    assert page.proxy.rowCount() == 2 and page.header_view.filter_boxes[0].text() == 'a'
    assert [page.proxy.index(row, 0).data() for row in range(2)] == ['a', 'ab']      # kills, descending


def check_multikills_table() -> None:
    table = MultikillFinder(KILL_HEADERS).find(VOLLEY_ROWS)
    assert len(table.rows) == 1 and table.rows[0][1] == '3' and table.rows[0][2] == '2' and table.rows[0][3] == '1', table.rows
    page = ResultsPage('Multikills', table.headers, table.rows)
    page.replace_data(table.headers, MultikillFinder(KILL_HEADERS).find(VOLLEY_ROWS, include_teamkills=False).rows, sort_name='kills')
    assert page.proxy.rowCount() == 1


def check_columns_popup() -> None:
    headers = ['player', 'kills', 'deaths', 'R1(live)_kills', 'R1(live)_deaths', 'R2(live)_kills', 'R2(live)_deaths']
    page = ResultsPage('Players', headers, [['a', '1', '1', '1', '1', '0', '0']])
    popup = page.columns_popup
    names = [group.label for group in popup.groups]
    assert 'All kills columns' in names and 'Round R1(live)' in names, names
    kills_group = names.index('All kills columns')
    popup.toggle_group(kills_group)
    assert [page.header_view.isSectionHidden(column) for column in (1, 3, 5)] == [True, True, True] and not page.header_view.isSectionHidden(2)
    assert popup.group_boxes[kills_group].checkState() == Qt.Unchecked
    popup.set_columns([3], True)
    assert popup.group_boxes[kills_group].checkState() == Qt.PartiallyChecked
    popup.toggle_group(kills_group)
    assert not any(page.header_view.isSectionHidden(column) for column in (1, 3, 5))           # partly shown -> all shown
    popup.set_columns(range(1, 7), False)
    assert all(page.header_view.isSectionHidden(column) for column in range(1, 7)) and not page.header_view.isSectionHidden(0)
    popup.set_columns(range(7), True)
    assert not any(page.header_view.isSectionHidden(column) for column in range(7))
    assert ResultsPage('Kills', ['round', 'time_s', 'killer', 'review'], []).columns_popup.groups == []         # the kills table has none


def check_options_tab(window: MainWindow, folder: str) -> None:
    capture_path = os.path.join(folder, 'cap.pcapng')
    window.options_tab.output_folder_edit.setText('')                    # a folder remembered from an earlier run would move the file
    request = window.options_tab.build_request(capture_path)
    assert request.kills_path == os.path.join(os.path.dirname(os.path.abspath(capture_path)), 'cap_kills.csv'), request
    assert request.server_port is None and request.process_count >= 1
    window.options_tab.show_command_line(capture_path)
    assert window.options_tab.command_line_label.text().startswith('nwkills "'), window.options_tab.command_line_label.text()


def check_packets_tab(window: MainWindow) -> None:
    packets = window.packets_tab
    packets.show_packets([(0.0, b'\x00' * 7 + b'\x01'), (1.0, b'\x00' * 8)], PacketSummarizer(NWE_PROFILE))
    assert packets.model.rowCount() == 2 and packets.proxy.rowCount() == 2
    assert packets.model.index(1, 3).data() == 'queued' and packets.model.index(0, 3).data() == ''
    assert packets.show_packet_at_time(0.9) is True
    assert packets.table.selectionModel().selectedRows()[0].row() == 1
    packets.filter_box.setText('queued')
    packets.apply_filter()
    assert packets.proxy.rowCount() == 1
    packets.filter_box.setText('')
    packets.apply_filter()
    assert packets.proxy.rowCount() == 2
    packets.clear()
    assert packets.model.rowCount() == 0 and packets.show_packet_at_time(1.0) is False


def check_results_tab(window: MainWindow, folder: str) -> None:
    paths = {name: os.path.join(folder, name + '.csv') for name in ('kills', 'players', 'rounds')}
    CsvTableFile.write(paths['kills'], KILL_HEADERS, VOLLEY_ROWS)
    CsvTableFile.write(paths['players'], ['player', 'score_at_capture_start', 'score_at_capture_end', 'score_gap', 'R1(live)_score_gap'], [['Z', '0', '1', '1', '1']])
    CsvTableFile.write(paths['rounds'], ['round', 'kind'], [['1', 'live']])
    results = window.results_tab
    results.show_results(paths, folder)
    titles = [results.page_tabs.tabText(index) for index in range(results.page_tabs.count())]
    assert titles[0] == 'Kills (4)' and titles[1] == 'Multikills (1)' and titles[2].startswith('Players ('), titles
    players = {row[0]: row for row in results.players_page.rows}
    assert players['G'][1] == '2' and 'Z' in players, players                    # kills 3 - teamkills 1; the converter's player without kills is listed
    assert results.multikills_page.rows[0][0] == 'G'
    results.kills_page.header_view.filter_boxes[KILL_HEADERS.index('killer')].setText('^G$')      # a filter on the Kills tab changes the Players tab
    results.players_controller.refresh()
    assert 'Z' not in {row[0] for row in results.players_page.rows}


def run_self_test(window: MainWindow) -> None:
    check_filters_chips_sorting_and_copy()
    check_replacing_a_table_keeps_filters_by_column_name()
    check_multikills_table()
    check_columns_popup()
    folder = tempfile.mkdtemp(prefix='nwkills-selftest-')
    try:
        check_options_tab(window, folder)
        check_packets_tab(window)
        check_results_tab(window, folder)
    finally:
        for name in os.listdir(folder):
            os.remove(os.path.join(folder, name))
        os.rmdir(folder)
    assert window.capture_tab.state_label.text() and window.capture_tab.stop_button.isEnabled() is False and not window.capture_tab.capturing      # idle

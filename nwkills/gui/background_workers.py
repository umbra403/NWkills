"""The threads that keep the window responsive: loading a capture, stopping pktmon, indexing packets, converting."""
import os
import traceback
from dataclasses import dataclass
from typing import List, Optional, Tuple

from PySide6.QtCore import QThread, Signal

from ..capture import pktmon
from ..packets.profile_calibrator import ProfileCalibrator
from ..packets.server_flow import FlowKey
from ..packets.server_profile import ServerProfile
from ..pipeline import Cancelled, KillReportPipeline, ServerFlowReader
from ..viewlogic import ConversionRequest, PacketSummaryCache

CALIBRATION_PACKET_LIMIT = 60000
NO_GAME_FLOW_MESSAGE = 'Could not find the game server flow in this capture. Try setting the server port in Options.'


@dataclass
class LoadedPacketList:
    """What the Packets tab needs of a capture."""
    server_flow_key: FlowKey
    items: List[Tuple[float, bytes]]            # (seconds from the first server packet, payload)
    frame_count: int                            # all frames in the file
    file_size: int
    profile: ServerProfile


class CaptureLoadWorker(QThread):
    """Read the capture, find the server flow and calibrate the decoder, so the packet list can be shown."""
    loaded = Signal(object)
    failed = Signal(str)
    message = Signal(str)

    def __init__(self, path: str, server_port: Optional[int], parent=None):
        super().__init__(parent)
        self.path, self.server_port = path, server_port

    def run(self):
        try:
            self.message.emit('Reading %s …' % os.path.basename(self.path))
            server_flow = ServerFlowReader().read(self.path, self.server_port)
            if not server_flow.payloads:
                self.failed.emit(NO_GAME_FLOW_MESSAGE)
                return
            first_time = server_flow.payloads[0][0]
            self.message.emit('Calibrating for this server …')
            profile = ProfileCalibrator().calibrate([payload for _time, payload in server_flow.payloads[:CALIBRATION_PACKET_LIMIT]], log=self.message.emit)
            items = [(time_s - first_time, payload) for time_s, payload in server_flow.payloads]
            self.loaded.emit(LoadedPacketList(server_flow.key, items, server_flow.frame_count, os.path.getsize(self.path), profile))
        except Exception:
            self.failed.emit(traceback.format_exc())


class PktmonFinishWorker(QThread):
    """Stop pktmon, convert its trace and keep only the game server's packets (this can take a while for a long capture)."""
    done = Signal(str, str)
    failed = Signal(str)
    message = Signal(str)

    def __init__(self, trace_path: str, final_path: str, parent=None):
        super().__init__(parent)
        self.trace_path, self.final_path = trace_path, final_path

    def run(self):
        try:
            kept, seen = pktmon.PktmonCapture().finish(self.trace_path, self.final_path, log=self.message.emit)
            self.done.emit(self.final_path, 'kept %s of %s captured packets' % (format(kept, ','), format(seen, ',')))
        except Exception as error:
            self.failed.emit(str(error) or traceback.format_exc())


class PacketIndexWorker(QThread):
    """Decode the message types of every packet in the background so the display filter can search them."""
    progress = Signal(int, int)

    def __init__(self, summaries: PacketSummaryCache, parent=None):
        super().__init__(parent)
        self.summaries = summaries
        self.stop_requested = False

    def run(self):
        self.summaries.fill_all(lambda: self.stop_requested, self.progress.emit)


class ConversionWorker(QThread):
    progress = Signal(str, float)
    message = Signal(str)
    finished_ok = Signal(object)
    failed = Signal(str)                         # an empty message means the run was cancelled

    def __init__(self, request: ConversionRequest, parent=None):
        super().__init__(parent)
        self.request = request
        self.cancel_requested = False

    def cancel(self) -> None:
        self.cancel_requested = True

    def _report_progress(self, stage: str, fraction: float) -> None:
        if self.cancel_requested:
            raise Cancelled()
        self.progress.emit(stage, float(fraction))

    def run(self):
        try:
            paths = KillReportPipeline().run(self.request.to_pipeline_options(), self.message.emit, self._report_progress)
            self.finished_ok.emit(paths)
        except Cancelled:
            self.failed.emit('')
        except RuntimeError as error:
            self.failed.emit(str(error))
        except Exception:
            self.failed.emit(traceback.format_exc())

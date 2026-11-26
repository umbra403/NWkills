"""Capture without Wireshark.

pktmon (Packet Monitor) ships with Windows 10 1809 and later and needs administrator rights. We capture all UDP at the network adapters,
convert the trace to pcapng, find the game server's flow with the same rule the reader uses, and write a small pcapng that holds only that
flow (both directions). Everything else that was captured is dropped and never kept."""
import ctypes
import os
import shutil
import subprocess
import sys
import time
from typing import Callable, List, Optional, Tuple

from .flow_pruner import ServerFlowPruner

DEFAULT_BUFFER_MB = 4096          # pktmon's circular log; it overwrites its own start when full (its default would be 512)
CREATE_NO_WINDOW = 0x08000000
MINIMUM_CAPTURE_FILE_BYTES = 100


class HostEnvironment:
    """What this computer offers for capturing."""

    @staticmethod
    def is_windows() -> bool:
        return sys.platform.startswith('win')

    def is_administrator(self) -> bool:
        if not self.is_windows():
            return False
        try:
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:
            return False

    @staticmethod
    def pktmon_path() -> Optional[str]:
        return shutil.which('pktmon')


class CommandRunner:
    """Runs a command line and returns its output."""

    def __init__(self, creation_flags: Optional[int] = None):
        self._creation_flags = creation_flags if creation_flags is not None else (CREATE_NO_WINDOW if HostEnvironment.is_windows() else 0)

    def run(self, command: List[str], check: bool = True, timeout: int = 600) -> str:
        """The command's output. With `check`, a non-zero exit code raises RuntimeError that holds the output."""
        process = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout, creationflags=self._creation_flags)
        output = process.stdout.decode('utf-8', 'replace').strip()
        if check and process.returncode != 0:
            raise RuntimeError('%s failed (exit %d):\n%s' % (' '.join(command[:3]), process.returncode, output))
        return output


class PktmonCommands:
    """The pktmon command lines."""

    @staticmethod
    def start_commands(trace_path: str, buffer_mb: int = DEFAULT_BUFFER_MB) -> List[List[str]]:
        """Start a capture of all UDP at the network adapters, with whole packets."""
        return [['pktmon', 'filter', 'remove'],
                ['pktmon', 'filter', 'add', '-t', 'UDP'],
                ['pktmon', 'start', '--capture', '--comp', 'nics', '--pkt-size', '0', '--file-name', trace_path, '--file-size', str(int(buffer_mb))]]

    @staticmethod
    def stop_commands(trace_path: str, pcapng_path: str) -> List[List[str]]:
        return [['pktmon', 'stop'], ['pktmon', 'etl2pcap', trace_path, '--out', pcapng_path]]

    @staticmethod
    def remove_filters_command() -> List[str]:
        return ['pktmon', 'filter', 'remove']


class PktmonCapture:
    """Starts, stops and cleans up a pktmon capture."""

    def __init__(self, runner: Optional[CommandRunner] = None, environment: Optional[HostEnvironment] = None,
                 pruner: Optional[ServerFlowPruner] = None):
        self._runner = runner or CommandRunner()
        self._environment = environment or HostEnvironment()
        self._pruner = pruner or ServerFlowPruner()

    def check_ready(self) -> Optional[str]:
        """An error text when capturing cannot start here, else None."""
        if not self._environment.is_windows():
            return 'Capturing needs Windows (pktmon). On other systems, capture with Wireshark or tcpdump and open the file.'
        if not self._environment.pktmon_path():
            return 'pktmon was not found. It is part of Windows 10 (version 1809) and later.'
        if not self._environment.is_administrator():
            return 'Capturing needs administrator rights. Close this window, right-click nwkills-gui.exe and choose "Run as administrator".'
        return None

    def start(self, trace_path: str, buffer_mb: int = DEFAULT_BUFFER_MB) -> None:
        not_ready_message = self.check_ready()
        if not_ready_message:
            raise RuntimeError(not_ready_message)
        os.makedirs(os.path.dirname(os.path.abspath(trace_path)), exist_ok=True)
        self._runner.run(['pktmon', 'stop'], check=False)                  # an earlier session that was left running would block the new one
        if os.path.exists(trace_path):
            os.remove(trace_path)
        try:
            for command in PktmonCommands.start_commands(trace_path, buffer_mb):
                self._runner.run(command)
        except Exception:
            self._runner.run(PktmonCommands.remove_filters_command(), check=False)
            raise

    def stop_and_convert(self, trace_path: str, pcapng_path: str) -> None:
        """Stop the capture and convert the trace. Raises when no trace could be written."""
        try:
            for command in PktmonCommands.stop_commands(trace_path, pcapng_path):
                self._runner.run(command, check=(command[1] != 'stop'))
        finally:
            self._runner.run(PktmonCommands.remove_filters_command(), check=False)
        if not os.path.exists(pcapng_path) or os.path.getsize(pcapng_path) < MINIMUM_CAPTURE_FILE_BYTES:
            raise RuntimeError('pktmon produced no capture file. Was anything captured?')

    def discard(self, trace_path: str) -> None:
        """Stop a running capture and throw it away."""
        try:
            self._runner.run(['pktmon', 'stop'], check=False)
        finally:
            self._runner.run(PktmonCommands.remove_filters_command(), check=False)
            self._remove_quietly(trace_path)

    def finish(self, trace_path: str, final_path: str, wanted_server_port: Optional[int] = None,
               log: Optional[Callable[[str], None]] = None) -> Tuple[int, int]:
        """Stop, convert, keep only the game server's packets in `final_path` and delete the big temporary files. Returns (kept, seen)."""
        full_capture_path = final_path + '.raw.pcapng'
        try:
            if log:
                log('Stopping the capture and converting it ...')
            self.stop_and_convert(trace_path, full_capture_path)
            if log:
                log('Looking for the game server ...')
            result = self._pruner.prune(full_capture_path, final_path, wanted_server_port, log)
            return result.packets_kept, result.packets_seen
        finally:
            for temporary_path in (full_capture_path, trace_path):
                self._remove_quietly(temporary_path)

    @staticmethod
    def _remove_quietly(path: str) -> None:
        try:
            os.remove(path)
        except OSError:
            pass


def timestamped_capture_name(prefix: str = 'capture', now: Optional[float] = None) -> str:
    """For example capture_2026-11-19_2001."""
    return '%s_%s' % (prefix, time.strftime('%Y-%m-%d_%H%M', time.localtime(now)))

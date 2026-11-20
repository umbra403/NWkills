import os
import tempfile
import unittest
import support
from nwkills.capture import pktmon
from nwkills.capture.flow_pruner import ServerFlowPruner
from nwkills.packets.pcapng_file import PcapngReader, PcapngWriter
from nwkills.packets.server_flow import FlowKey
from test_server_flow import CLIENT, SERVER, frame, game_capture


class ServerFlowPrunerTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.mkdtemp()
        self.source = os.path.join(self.directory, 'a.pcapng')
        self.destination = os.path.join(self.directory, 'b.pcapng')

    def test_keeps_both_directions_of_the_game_flow_only(self):
        frames = game_capture(120)
        PcapngWriter().write_frames(self.source, frames)
        messages = []
        result = ServerFlowPruner().prune(self.source, self.destination, log=messages.append)
        self.assertEqual(result.flow_key, FlowKey(SERVER, 7240, CLIENT, 5555))
        self.assertEqual((result.packets_seen, result.packets_kept), (len(frames), 240))
        self.assertEqual(len(list(PcapngReader().read_frames(self.destination))), 240)
        self.assertEqual(len(messages), 1)

    def test_a_capture_without_the_game_raises(self):
        PcapngWriter().write_frames(self.source, [frame('1.1.1.1', 53, CLIENT, 6001, b'dns' * 10) for _ in range(100)])
        with self.assertRaisesRegex(RuntimeError, 'game server'):
            ServerFlowPruner().prune(self.source, self.destination)

    def test_a_wanted_port_that_is_not_in_the_capture_raises(self):
        PcapngWriter().write_frames(self.source, game_capture(120))
        with self.assertRaises(RuntimeError):
            ServerFlowPruner().prune(self.source, self.destination, wanted_server_port=1234)


class PktmonCommandsTest(unittest.TestCase):
    def test_start_adds_a_udp_filter_and_captures_whole_packets(self):
        commands = pktmon.PktmonCommands.start_commands(r'C:\caps\x.etl', 4096)
        self.assertEqual(commands[1], ['pktmon', 'filter', 'add', '-t', 'UDP'])
        self.assertEqual(commands[2][:3], ['pktmon', 'start', '--capture'])
        self.assertEqual(commands[2][commands[2].index('--pkt-size') + 1], '0')
        self.assertEqual(commands[2][-2:], ['--file-size', '4096'])

    def test_stop_converts_the_trace(self):
        self.assertEqual(pktmon.PktmonCommands.stop_commands('a.etl', 'a.pcapng'), [['pktmon', 'stop'], ['pktmon', 'etl2pcap', 'a.etl', '--out', 'a.pcapng']])

    def test_remove_filters_command(self):
        self.assertEqual(pktmon.PktmonCommands.remove_filters_command(), ['pktmon', 'filter', 'remove'])


class FakeRunner:
    def __init__(self, files_to_create=None, failing_word=None):
        self.commands, self._files_to_create, self._failing_word = [], files_to_create or {}, failing_word

    def run(self, command, check=True, timeout=600):
        self.commands.append(command)
        if check and self._failing_word and self._failing_word in command:
            raise RuntimeError('failed')
        if command[:2] == ['pktmon', 'etl2pcap']:
            for path, writer in self._files_to_create.items():
                writer(path)
        return ''


class FakeEnvironment:
    def __init__(self, windows=True, pktmon_path='pktmon.exe', administrator=True):
        self._windows, self._pktmon_path, self._administrator = windows, pktmon_path, administrator

    def is_windows(self): return self._windows
    def pktmon_path(self): return self._pktmon_path
    def is_administrator(self): return self._administrator


class PktmonCaptureTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.mkdtemp()
        self.trace = os.path.join(self.directory, 'x.etl')

    def capture(self, runner=None, environment=None):
        return pktmon.PktmonCapture(runner or FakeRunner(), environment or FakeEnvironment())

    def test_check_ready_names_the_missing_requirement(self):
        self.assertIn('Windows', self.capture(environment=FakeEnvironment(windows=False)).check_ready())
        self.assertIn('pktmon was not found', self.capture(environment=FakeEnvironment(pktmon_path=None)).check_ready())
        self.assertIn('administrator', self.capture(environment=FakeEnvironment(administrator=False)).check_ready())
        self.assertIsNone(self.capture().check_ready())

    def test_start_stops_an_old_session_then_runs_the_start_commands(self):
        runner = FakeRunner()
        self.capture(runner).start(self.trace, 512)
        self.assertEqual(runner.commands[0], ['pktmon', 'stop'])
        self.assertEqual([command[1] for command in runner.commands[1:]], ['filter', 'filter', 'start'])

    def test_start_refuses_when_not_ready(self):
        with self.assertRaises(RuntimeError):
            self.capture(environment=FakeEnvironment(administrator=False)).start(self.trace)

    def test_a_failing_start_removes_the_filters_again(self):
        runner = FakeRunner(failing_word='start')
        with self.assertRaises(RuntimeError):
            self.capture(runner).start(self.trace)
        self.assertEqual(runner.commands[-1], ['pktmon', 'filter', 'remove'])

    def test_start_removes_a_trace_left_from_before(self):
        open(self.trace, 'wb').close()
        self.capture().start(self.trace)
        self.assertFalse(os.path.exists(self.trace))

    def test_stop_and_convert_needs_a_capture_file(self):
        with self.assertRaisesRegex(RuntimeError, 'no capture file'):
            self.capture().stop_and_convert(self.trace, os.path.join(self.directory, 'missing.pcapng'))

    def test_discard_stops_and_deletes_the_trace(self):
        open(self.trace, 'wb').close()
        runner = FakeRunner()
        self.capture(runner).discard(self.trace)
        self.assertFalse(os.path.exists(self.trace))
        self.assertEqual(runner.commands[0], ['pktmon', 'stop'])

    def test_finish_keeps_only_the_game_flow_and_deletes_the_big_files(self):
        final = os.path.join(self.directory, 'final.pcapng')
        open(self.trace, 'wb').close()
        runner = FakeRunner({final + '.raw.pcapng': lambda path: PcapngWriter().write_frames(path, game_capture(120))})
        kept, seen = self.capture(runner).finish(self.trace, final)
        self.assertEqual((kept, seen), (240, 360))
        self.assertTrue(os.path.exists(final))
        self.assertFalse(os.path.exists(final + '.raw.pcapng') or os.path.exists(self.trace))

    def test_timestamped_capture_name(self):
        self.assertRegex(pktmon.timestamped_capture_name('capture', 0), r'^capture_\d{4}-\d\d-\d\d_\d{4}$')


class HostEnvironmentAndRunnerTest(unittest.TestCase):
    def test_runner_returns_the_output_of_a_command(self):
        self.assertEqual(pktmon.CommandRunner().run([__import__('sys').executable, '-c', 'print("hi")']), 'hi')

    def test_runner_raises_on_a_failing_command_when_checking(self):
        runner = pktmon.CommandRunner()
        command = [__import__('sys').executable, '-c', 'import sys; print("boom"); sys.exit(3)']
        with self.assertRaisesRegex(RuntimeError, 'boom'):
            runner.run(command)
        self.assertEqual(runner.run(command, check=False), 'boom')

    def test_this_test_machine_is_not_windows(self):
        self.assertEqual(pktmon.HostEnvironment.is_windows(), os.name == 'nt')
        if os.name != 'nt':
            self.assertFalse(pktmon.HostEnvironment().is_administrator())


if __name__ == '__main__':
    unittest.main()

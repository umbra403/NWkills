import argparse
import csv
import os
import tempfile
import unittest
import support
from nwkills import cli
from nwkills.packets.pcapng_file import PcapngWriter
from nwkills.pipeline import CaptureLoader, Cancelled, KillReportPipeline, LoadedCapture, PipelineOptions, ServerFlowReader
from nwkills.roster import NameSighting, PlayerRoster, SlotNamer
from test_events_kills import KillDecoderTest
from test_server_flow import CLIENT, SERVER, game_capture
from nwkills.packets.server_flow import FlowKey

ROSTER_SIGHTINGS = {1: [NameSighting(0.0, 500.0, 'Ann', 9)], 2: [NameSighting(0.0, 500.0, 'Bob', 9)]}


class ServerFlowReaderTest(unittest.TestCase):
    def setUp(self):
        self.path = os.path.join(tempfile.mkdtemp(), 'a.pcapng')

    def test_returns_the_game_flow_with_its_payloads_and_the_frame_count(self):
        frames = game_capture(120)
        PcapngWriter().write_frames(self.path, frames)
        flow = ServerFlowReader().read(self.path)
        self.assertEqual(flow.key, FlowKey(SERVER, 7240, CLIENT, 5555))
        self.assertEqual((len(flow.payloads), flow.frame_count), (120, len(frames)))

    def test_a_capture_without_a_game_flow_has_no_key_and_no_payloads(self):
        PcapngWriter().write_frames(self.path, game_capture(10))
        flow = ServerFlowReader().read(self.path)
        self.assertEqual((flow.key, flow.payloads), (None, []))

    def test_a_wanted_port_is_passed_on(self):
        PcapngWriter().write_frames(self.path, game_capture(120))
        self.assertIsNone(ServerFlowReader().read(self.path, 9999).key)


class PipelineOptionsTest(unittest.TestCase):
    def test_only_the_capture_is_required(self):
        options = PipelineOptions('a.pcapng')
        self.assertEqual((options.kills_path, options.server_port, options.own_name_part, options.cache_path, options.packet_limit), (None,) * 5)
        self.assertGreaterEqual(options.process_count, 1)


class CaptureLoaderTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.mkdtemp()
        self.capture = os.path.join(self.directory, 'a.pcapng')
        self.log_lines, self.stages = [], []

    def load(self, **changes):
        options = PipelineOptions(self.capture, process_count=1, **changes)
        return CaptureLoader().load(options, self.log_lines.append, lambda stage, fraction: self.stages.append(stage), 0.0)

    def test_a_capture_is_decoded_into_one_record_per_packet(self):
        PcapngWriter().write_frames(self.capture, game_capture(120))
        loaded = self.load()
        self.assertEqual(len(loaded.packet_records), 120)
        self.assertEqual(len(loaded.timed_payloads), 120)
        self.assertEqual(loaded.timed_payloads[0][0], 0.0)
        self.assertEqual([stage for stage in self.stages if stage in ('read', 'roster', 'decode')][-1], 'decode')
        self.assertTrue(any('server flow' in line for line in self.log_lines))

    def test_the_packet_limit_cuts_the_decoding_short(self):
        PcapngWriter().write_frames(self.capture, game_capture(120))
        self.assertEqual(len(self.load(packet_limit=30).packet_records), 30)

    def test_a_capture_without_the_game_raises(self):
        PcapngWriter().write_frames(self.capture, game_capture(10))
        with self.assertRaisesRegex(RuntimeError, 'could not find the game server'):
            self.load()

    def test_the_cache_is_written_and_read_back(self):
        PcapngWriter().write_frames(self.capture, game_capture(120))
        cache = os.path.join(self.directory, 'cache.pkl')
        first = self.load(cache_path=cache)
        os.remove(self.capture)
        second = self.load(cache_path=cache)
        self.assertEqual(second.packet_records, first.packet_records)
        self.assertEqual(second.timed_payloads, first.timed_payloads)
        self.assertTrue(any('loaded 120 decoded packets' in line for line in self.log_lines))

    def test_read_payloads_counts_time_from_the_first_packet(self):
        PcapngWriter().write_frames(self.capture, game_capture(120))
        payloads = CaptureLoader().read_payloads(PipelineOptions(self.capture))
        self.assertEqual((len(payloads), payloads[0][0]), (120, 0.0))


class FakeLoader:
    def __init__(self, loaded):
        self._loaded = loaded

    def load(self, options, log, progress, started_s):
        return self._loaded

    def read_payloads(self, options):
        return []


class KillReportPipelineTest(unittest.TestCase):
    def run_pipeline(self, **changes):
        directory = tempfile.mkdtemp()
        records = KillDecoderTest().records()
        loaded = LoadedCapture(records, PlayerRoster({slot: list(sightings) for slot, sightings in ROSTER_SIGHTINGS.items()}), [])
        options = PipelineOptions(os.path.join(directory, 'cap.pcapng'), kills_path=os.path.join(directory, 'cap_kills.csv'), **changes)
        stages, log_lines = [], []
        paths = KillReportPipeline(FakeLoader(loaded)).run(options, log_lines.append, lambda stage, fraction: stages.append(stage))
        return paths, stages, log_lines

    def read(self, path):
        with open(path, newline='', encoding='utf-8-sig') as csv_file:
            return list(csv.reader(csv_file))

    def test_all_the_files_are_written(self):
        paths, stages, _log = self.run_pipeline()
        self.assertEqual(sorted(paths), ['flagbearers', 'kills', 'players', 'rounds'])
        for key in ('kills', 'players', 'rounds', 'flagbearers'):
            self.assertTrue(os.path.exists(paths[key]), key)
        self.assertEqual(stages, ['events', 'rounds', 'players', 'done'])

    def test_the_kill_is_in_the_kills_file(self):
        paths, _stages, log_lines = self.run_pipeline()
        rows = self.read(paths['kills'])
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1][4:9], ['Ann', 'Bob', 'firearm: musket/rifle', '', 'kill'])
        self.assertTrue(any('1 kills ->' in line for line in log_lines))

    def test_the_players_file_counts_the_kill(self):
        paths, _stages, _log = self.run_pipeline()
        rows = {row[0]: row for row in self.read(paths['players'])[1:]}
        self.assertEqual(rows['Ann'][1], '1')
        self.assertEqual(rows['Bob'][2], '1')

    def test_cancelling_from_a_progress_callback_stops_the_run(self):
        directory = tempfile.mkdtemp()
        loaded = LoadedCapture(KillDecoderTest().records(), PlayerRoster({}), [])

        def stop(stage, fraction):
            raise Cancelled()

        with self.assertRaises(Cancelled):
            KillReportPipeline(FakeLoader(loaded)).run(PipelineOptions(os.path.join(directory, 'c.pcapng')), lambda text: None, stop)

    def test_names_missing_in_the_roster_are_filled_from_the_payloads(self):
        directory = tempfile.mkdtemp()
        loaded = LoadedCapture(KillDecoderTest().records(), PlayerRoster({1: [NameSighting(0.0, 500.0, 'Ann', 9)]}),
                               [(1.0, support.name_record(3, 'Wellington')), (2.0, support.name_record(3, 'Wellington')), (60.0, support.name_record(3, 'Wellington'))])
        options = PipelineOptions(os.path.join(directory, 'cap.pcapng'), kills_path=os.path.join(directory, 'cap_kills.csv'))
        paths = KillReportPipeline(FakeLoader(loaded)).run(options, lambda text: None)
        with open(paths['kills'], newline='', encoding='utf-8-sig') as csv_file:
            self.assertEqual(list(csv.reader(csv_file))[1][5], 'Wellington')


class CommandLineTest(unittest.TestCase):
    def test_the_parser_knows_the_documented_options(self):
        arguments = cli.build_argument_parser().parse_args(['a.pcapng', '--out', 'x.csv', '--port', '7240', '--me', 'Bob', '--jobs', '2', '--cache', 'c.pkl', '--limit', '10'])
        self.assertEqual((arguments.pcap, arguments.out, arguments.port, arguments.me, arguments.jobs, arguments.cache, arguments.limit),
                         ('a.pcapng', 'x.csv', 7240, 'Bob', 2, 'c.pkl', 10))

    def test_arguments_become_pipeline_options(self):
        namespace = argparse.Namespace(pcap='a.pcapng', out='x.csv', port=7240, me='Bob', jobs=2, cache='c.pkl', limit=10)
        options = cli.options_from_arguments(namespace)
        self.assertEqual((options.capture_path, options.kills_path, options.server_port, options.own_name_part, options.process_count, options.cache_path, options.packet_limit),
                         ('a.pcapng', 'x.csv', 7240, 'Bob', 2, 'c.pkl', 10))

    def test_main_without_a_capture_is_a_usage_error(self):
        with self.assertRaises(SystemExit) as raised:
            cli.main([])
        self.assertEqual(raised.exception.code, 2)

    def test_main_reports_a_run_error_as_the_exit_message(self):
        path = os.path.join(tempfile.mkdtemp(), 'a.pcapng')
        PcapngWriter().write_frames(path, game_capture(10))
        with self.assertRaises(SystemExit) as raised:
            cli.main([path, '--jobs', '1'])
        self.assertIn('could not find the game server', str(raised.exception.code))

    def test_run_goes_through_the_pipeline(self):
        path = os.path.join(tempfile.mkdtemp(), 'a.pcapng')
        PcapngWriter().write_frames(path, game_capture(10))
        namespace = argparse.Namespace(pcap=path, out=None, port=None, me=None, jobs=1, cache=None, limit=None)
        with self.assertRaises(RuntimeError):
            cli.run(namespace, lambda text: None)


class SlotNamerTest(unittest.TestCase):
    def test_names_by_slot_kind(self):
        namer = SlotNamer(PlayerRoster({1: [NameSighting(0.0, 9.0, 'Ann', 3)]}))
        self.assertEqual((namer(None, 1.0), namer(-1, 1.0), namer(1, 1.0), namer(7, 1.0)), ('?', '(AI)', 'Ann', 'player#7'))


if __name__ == '__main__':
    unittest.main()

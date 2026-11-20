import os
import tempfile
import time
import unittest
import support
from nwkills.pipeline import PipelineOptions
from nwkills.viewlogic import (DEFAULT_STAGES, ConversionRequest, OverallProgress, ProgressReport, ProgressStage, ResultsScope, StaleResultFolderSweeper,
                               TemporaryResultFolder, default_export_folder, describe_running_capture, scope_note)


class ConversionRequestFromFormTest(unittest.TestCase):
    def build(self, capture_path='/caps/game.pcapng', output_folder_text='', **changes):
        form = dict(server_port=None, own_name_text='', process_count=4, use_cache=False, packet_limit=None)
        form.update(changes)
        return ConversionRequest.from_form(capture_path, output_folder_text, **form)

    def test_the_kills_file_goes_next_to_the_capture_by_default(self):
        request = self.build()
        self.assertEqual((request.capture_path, request.kills_path), ('/caps/game.pcapng', os.path.join(os.path.dirname(os.path.abspath('/caps/game.pcapng')), 'game_kills.csv')))

    def test_a_chosen_output_folder_is_used(self):
        self.assertEqual(self.build(output_folder_text=' /out ').kills_path, os.path.join('/out', 'game_kills.csv'))

    def test_without_a_capture_the_name_is_capture(self):
        request = self.build(capture_path=None, output_folder_text='/out')
        self.assertEqual((request.capture_path, request.kills_path), ('', os.path.join('/out', 'capture_kills.csv')))

    def test_the_cache_is_a_file_next_to_the_exports_when_asked(self):
        self.assertEqual(self.build(output_folder_text='/out', use_cache=True).cache_path, os.path.join('/out', 'game.nwcache.pkl'))
        self.assertIsNone(self.build(output_folder_text='/out').cache_path)

    def test_a_blank_own_name_means_none(self):
        self.assertIsNone(self.build(own_name_text='  ').own_name_part)
        self.assertEqual(self.build(own_name_text=' Bob ').own_name_part, 'Bob')

    def test_the_other_choices_are_passed_on(self):
        request = self.build(server_port=7243, process_count=2, packet_limit=500)
        self.assertEqual((request.server_port, request.process_count, request.packet_limit), (7243, 2, 500))


class ConversionRequestTest(unittest.TestCase):
    def test_the_command_line_shows_every_choice_made(self):
        request = ConversionRequest('a.pcapng', 'o.csv', 7243, 'x', 4, 'c.pkl', 100)
        self.assertEqual(request.command_line(), 'nwkills "a.pcapng" --out "o.csv" --port 7243 --me "x" --jobs 4 --cache "c.pkl" --limit 100')

    def test_the_command_line_leaves_out_what_is_not_chosen(self):
        command = ConversionRequest('a.pcapng', 'o.csv', None, None, 1, None, None).command_line()
        self.assertEqual(command, 'nwkills "a.pcapng" --out "o.csv" --jobs 1')

    def test_the_pipeline_options_carry_every_field(self):
        options = ConversionRequest('a.pcapng', 'o.csv', 7243, 'x', 4, 'c.pkl', 100).to_pipeline_options()
        self.assertEqual(options, PipelineOptions('a.pcapng', 'o.csv', 7243, 'x', 4, 'c.pkl', 100))


class DefaultExportFolderTest(unittest.TestCase):
    def test_the_chosen_folder_wins(self):
        self.assertEqual(default_export_folder(' /out ', '/caps/a.pcapng'), '/out')

    def test_then_the_folder_of_the_capture(self):
        self.assertEqual(default_export_folder('', '/caps/a.pcapng'), os.path.dirname(os.path.abspath('/caps/a.pcapng')))

    def test_then_the_home_folder(self):
        self.assertEqual(default_export_folder('', None, home_folder='/home/me'), '/home/me')
        self.assertEqual(default_export_folder('', None), os.path.expanduser('~'))


class OverallProgressTest(unittest.TestCase):
    def test_the_weights_add_up_to_a_hundred(self):
        self.assertEqual(sum(stage.weight for stage in DEFAULT_STAGES), 100)

    def test_the_first_stage_starts_at_zero(self):
        self.assertEqual(OverallProgress().report('read', 0), ProgressReport('Reading capture', 0, 0))

    def test_a_measurable_stage_adds_its_share(self):
        report = OverallProgress().report('decode', 0.5)
        self.assertEqual((report.label, report.overall_percent, report.stage_fraction), ('Decoding packets', 15 + 27.5, 0.5))

    def test_a_busy_stage_reports_no_fraction(self):
        report = OverallProgress().report('events', 0.7)
        self.assertEqual((report.overall_percent, report.stage_fraction), (70, None))

    def test_done_is_a_hundred_percent(self):
        self.assertEqual(OverallProgress().report('done', 1), ProgressReport('Finished', 100.0, 1.0))

    def test_an_unknown_stage_keeps_its_name(self):
        report = OverallProgress().report('mystery', 0.5)
        self.assertEqual((report.label, report.overall_percent, report.stage_fraction), ('mystery', 100, None))

    def test_other_stages_can_be_given(self):
        calculator = OverallProgress([ProgressStage('a', 'First', 40), ProgressStage('b', 'Second', 60)])
        self.assertEqual(calculator.report('b', 0.5).overall_percent, 70)


class ResultsScopeTest(unittest.TestCase):
    def test_the_scope_holds_the_rows_and_two_flags(self):
        scope = ResultsScope([['a']], True, False)
        self.assertEqual((scope.rows, scope.any_filter_active, scope.rounds_chosen), ([['a']], True, False))

    def test_the_note_says_how_many_rows_it_is_computed_from(self):
        self.assertEqual(scope_note('totals', 12, 40, True), 'totals from 12 of 40 kill rows')

    def test_the_note_mentions_the_left_out_warm_up_when_no_rounds_were_chosen(self):
        self.assertEqual(scope_note('multikills', 1, 2, False), 'multikills from 1 of 2 kill rows (warm-up rounds left out; pick Warm-up to include them)')


class DescribeRunningCaptureTest(unittest.TestCase):
    def test_the_text_has_the_elapsed_time_and_the_log_size(self):
        text, nearly_full = describe_running_capture(3725, 512 * 1048576, 4096)
        self.assertEqual((text, nearly_full), ('Capturing: 1:02:05, 512 MB of 4096 MB logged.', False))

    def test_a_nearly_full_log_is_warned_about(self):
        text, nearly_full = describe_running_capture(10, 4000 * 1048576, 4096)
        self.assertTrue(nearly_full)
        self.assertIn('nearly full', text)

    def test_exactly_ninety_percent_counts_as_nearly_full(self):
        self.assertTrue(describe_running_capture(0, 900 * 1048576, 1000)[1])
        self.assertFalse(describe_running_capture(0, 899 * 1048576, 1000)[1])


class StaleResultFolderSweeperTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()

    def folder(self, name, files, age_s):
        path = os.path.join(self.root, name)
        os.mkdir(path)
        for file_name in files:
            open(os.path.join(path, file_name), 'w').close()
        old = time.time() - age_s
        os.utime(path, (old, old))
        return path

    def test_an_old_folder_with_only_csv_files_is_removed(self):
        stale = self.folder('nwkills-old', ['a.csv', 'B.CSV'], 7200)
        self.assertEqual(StaleResultFolderSweeper(self.root).sweep(), 1)
        self.assertFalse(os.path.exists(stale))

    def test_a_recent_folder_stays(self):
        recent = self.folder('nwkills-new', ['a.csv'], 10)
        self.assertEqual(StaleResultFolderSweeper(self.root).sweep(), 0)
        self.assertTrue(os.path.exists(recent))

    def test_an_old_folder_with_other_files_stays(self):
        other = self.folder('nwkills-keep', ['a.csv', 'notes.txt'], 7200)
        StaleResultFolderSweeper(self.root).sweep()
        self.assertTrue(os.path.exists(other))

    def test_folders_with_other_names_stay(self):
        other = self.folder('something', ['a.csv'], 7200)
        StaleResultFolderSweeper(self.root).sweep()
        self.assertTrue(os.path.exists(other))

    def test_the_age_limit_can_be_set(self):
        self.folder('nwkills-x', [], 100)
        self.assertEqual(StaleResultFolderSweeper(self.root, max_age_s=50).sweep(), 1)

    def test_the_time_can_be_given(self):
        self.folder('nwkills-x', [], 0)
        self.assertEqual(StaleResultFolderSweeper(self.root).sweep(now_s=time.time() + 7200), 1)


class TemporaryResultFolderTest(unittest.TestCase):
    def test_there_is_no_path_before_it_is_created(self):
        self.assertIsNone(TemporaryResultFolder().path)

    def test_create_makes_a_folder_that_discard_removes(self):
        folder = TemporaryResultFolder()
        path = folder.create()
        self.assertTrue(os.path.isdir(path))
        self.assertEqual(folder.path, path)
        self.assertTrue(os.path.basename(path).startswith('nwkills-'))
        folder.discard()
        self.assertFalse(os.path.exists(path))
        self.assertIsNone(folder.path)

    def test_file_path_is_inside_the_folder(self):
        folder = TemporaryResultFolder()
        path = folder.create()
        self.assertEqual(folder.file_path('a_kills.csv'), os.path.join(path, 'a_kills.csv'))
        folder.discard()

    def test_creating_again_discards_the_earlier_folder(self):
        folder = TemporaryResultFolder()
        first = folder.create()
        second = folder.create()
        self.assertFalse(os.path.exists(first))
        self.assertTrue(os.path.exists(second))
        folder.discard()

    def test_discarding_twice_is_harmless(self):
        folder = TemporaryResultFolder()
        folder.discard()
        folder.create()
        folder.discard()
        folder.discard()


if __name__ == '__main__':
    unittest.main()

"""The whole run, step by step."""
import json
import os
import time
from typing import Callable, Dict, List, Optional, Tuple

from ..analysis.death_classifier import DeathClassifier
from ..analysis.kill_labels import AdminDeathLabeler, OwnerlessMountLabeler, WorldKillerLabeler
from ..analysis.player_tally import PlayerTally
from ..analysis.scoreboard import ScoreChangeLedger, ScoreGapAnalyzer, ScoreboardHistory
from ..events import KillDecoder
from ..events.admin_actions import AdminActionFinder
from ..events.kill_event import KillEvent
from ..flagbearers import FlagTable, FlagbearerReport, ServerKindDetector
from ..output import FlagbearersCsvWriter, KillsCsvWriter, OutputPaths, PlayersCsvWriter, RoundsCsvWriter
from ..roster import PlayerRoster, RosterFiller, SlotNamer, UnnamedSlotFinder
from ..rounds import RoundDetector, RoundTimeline
from .capture_loader import CaptureLoader, LoadedCapture
from .options import PipelineOptions

PACKAGE_DIRECTORY = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIRECTORY = os.path.join(PACKAGE_DIRECTORY, 'data')

Log = Callable[[str], None]
Progress = Callable[[str, float], None]


class KillReportPipeline:
    """Capture -> decoded packets -> roster -> kills -> rounds -> the four CSV files. `progress(stage, fraction)` may raise Cancelled to stop."""

    def __init__(self, loader: Optional[CaptureLoader] = None, classifier: Optional[DeathClassifier] = None):
        self._loader = loader or CaptureLoader()
        self._classifier = classifier or DeathClassifier()

    def run(self, options: PipelineOptions, log: Log = print, progress: Progress = lambda stage, fraction: None) -> Dict[str, Optional[str]]:
        """Returns the paths of the files written (flagbearers is None when this server type has no table)."""
        started_s = time.time()
        loaded = self._loader.load(options, log, progress, started_s)
        records, roster = loaded.packet_records, loaded.roster
        progress('events', 0.0)
        events = self._find_kills(options, loaded, log)
        WorldKillerLabeler().apply(events)
        progress('rounds', 0.0)
        rounds = RoundDetector().detect(records)
        timeline = RoundTimeline(rounds)
        paths = OutputPaths.for_capture(options.capture_path, options.kills_path)
        RoundsCsvWriter().write(paths.rounds, rounds, events, timeline)
        flagbearers_path = self._write_flagbearers(paths, records, timeline, SlotNamer(roster), log)
        AdminDeathLabeler().apply(events, AdminActionFinder().find(records))
        OwnerlessMountLabeler(self._classifier).apply(events)
        KillsCsvWriter(self._classifier).write(paths.kills, events, timeline)
        progress('players', 0.0)
        tally = PlayerTally(self._classifier)
        tally.add_events(events, timeline)
        scoreboard = ScoreboardHistory.from_records(records)
        ledger = ScoreChangeLedger(events, scoreboard, self._classifier)
        admin_reset_times = sorted(record['t'] for record in records if any('Has reset the Map' in line for line in record.get('txt') or ()))      # an admin reset zeroes the scoreboard
        score_gaps = ScoreGapAnalyzer(roster).analyze(scoreboard, ledger, rounds, admin_reset_times)
        PlayersCsvWriter().write(paths.players, tally, score_gaps, rounds)
        log('%d kills -> %s\nper player -> %s\ndone in %.0f s' % (len(events), paths.kills, paths.players, time.time() - started_s))
        progress('done', 1.0)
        return dict(kills=paths.kills, players=paths.players, rounds=paths.rounds, flagbearers=flagbearers_path)

    def _find_kills(self, options: PipelineOptions, loaded: LoadedCapture, log: Log) -> List[KillEvent]:
        roster, records = loaded.roster, loaded.packet_records
        new_names = roster.merge_join_records(records)
        if new_names:
            log('%d more player names read from join messages' % new_names)
        unknown_since = roster.retire_moved_names()
        own_slot = roster.slot_of_name_containing(options.own_name_part) if options.own_name_part else None
        with open(os.path.join(DATA_DIRECTORY, 'items.json')) as items_file:
            item_names = json.load(items_file)
        decoder = KillDecoder(SlotNamer(roster), item_names)
        events, _local_slot = decoder.decode(records, own_slot)
        slots_without_name, slots_with_earlier_occupant = UnnamedSlotFinder(roster).find(events)
        slots_needing_names = slots_without_name | slots_with_earlier_occupant
        payloads = loaded.timed_payloads
        if slots_needing_names and payloads is None:
            payloads = self._loader.read_payloads(options)
        if slots_needing_names and payloads:
            RosterFiller().fill(roster, payloads, slots_needing_names, unknown_since, slots_with_earlier_occupant)
            events, _local_slot = decoder.decode(records, own_slot)
        return events

    @staticmethod
    def _write_flagbearers(paths: OutputPaths, records: List[dict], timeline: RoundTimeline, namer, log: Log) -> Optional[str]:
        """Who spawned carrying a flag, per round (a separate file)."""
        table = FlagTable.load(DATA_DIRECTORY, ServerKindDetector().detect(records))
        if table:
            rows = FlagbearerReport(table, timeline, namer).build(records)
            FlagbearersCsvWriter().write(paths.flagbearers, rows)
            log('%d flagbearer rows -> %s' % (len(rows), paths.flagbearers))
            return paths.flagbearers
        log('flagbearers: skipped (no troop/item table for this server type)')
        if os.path.exists(paths.flagbearers):
            os.remove(paths.flagbearers)              # a leftover from an earlier run must not be shown as this run's result
        return None

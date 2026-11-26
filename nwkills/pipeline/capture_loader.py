"""From a capture file (or a cache of an earlier run) to the decoded packets and the player roster."""
import os
import pickle
import time
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple

from ..packets.parallel_decoding import ParallelPacketDecoder
from ..packets.profile_calibrator import ProfileCalibrator
from ..roster import PlayerRoster
from .options import PipelineOptions
from .server_flow_reader import ServerFlowReader

TimedPayloads = List[Tuple[float, bytes]]
NO_SERVER_MESSAGE = 'could not find the game server flow in the capture (try --port)'
CALIBRATION_PACKET_LIMIT = 60000


@dataclass
class LoadedCapture:
    packet_records: List[dict]
    roster: PlayerRoster
    timed_payloads: Optional[TimedPayloads]               # None for a cache from before the payloads were kept in it


class CaptureLoader:
    def __init__(self, flow_reader: Optional[ServerFlowReader] = None):
        self._flow_reader = flow_reader or ServerFlowReader()

    def load(self, options: PipelineOptions, log: Callable[[str], None], progress: Callable[[str, float], None], started_s: float) -> LoadedCapture:
        if options.cache_path and os.path.exists(options.cache_path):
            return self._load_cache(options, log)
        loaded = self._decode_capture(options, log, progress, started_s)
        if options.cache_path:
            with open(options.cache_path, 'wb') as cache_file:
                pickle.dump((loaded.packet_records, loaded.roster.sightings_by_slot, loaded.timed_payloads), cache_file)
        return loaded

    def read_payloads(self, options: PipelineOptions) -> TimedPayloads:
        """The packets of the game server, with times counted from the first one."""
        flow = self._flow_reader.read(options.capture_path, options.server_port)
        return [(time_s - flow.payloads[0][0], payload) for time_s, payload in flow.payloads]

    @staticmethod
    def _load_cache(options: PipelineOptions, log) -> LoadedCapture:
        with open(options.cache_path, 'rb') as cache_file:
            cached = pickle.load(cache_file)
        log('loaded %d decoded packets from %s' % (len(cached[0]), options.cache_path))
        return LoadedCapture(cached[0], PlayerRoster(cached[1]), cached[2] if len(cached) > 2 else None)

    def _decode_capture(self, options: PipelineOptions, log, progress, started_s: float) -> LoadedCapture:
        progress('read', 0.0)
        log('reading capture ...')
        flow = self._flow_reader.read(options.capture_path, options.server_port)
        progress('read', 1.0)
        if not flow.payloads:
            raise RuntimeError(NO_SERVER_MESSAGE)
        key = flow.key
        log('server flow %s:%d -> %s:%d, %d packets' % (key[0], key[1], key[2], key[3], len(flow.payloads)))
        payloads = flow.payloads[:options.packet_limit] if options.packet_limit else flow.payloads
        first_s = payloads[0][0]
        timed_payloads = [(time_s - first_s, payload) for time_s, payload in payloads]
        roster = PlayerRoster.scan(timed_payloads)
        log('%d player names found' % roster.name_count())
        progress('roster', 1.0)
        log('calibrating bit widths for this server ...')
        profile = ProfileCalibrator().calibrate([payload for _time_s, payload in payloads[:CALIBRATION_PACKET_LIMIT]], log=log)
        jobs = [(index, time_s - first_s, payload) for index, (time_s, payload) in enumerate(payloads) if len(payload) > 12]

        def report_decoding(done: int, total: int) -> None:
            if done % 200 == 0:
                progress('decode', done / max(1, total))
            if done % 5000 == 0:
                log('  decoded %d / %d packets  (%.0f s)' % (done, total, time.time() - started_s))

        keep_all_agent_properties = bool(os.environ.get('NWKEEP_ALL_AGENT_PROPS'))
        decoded = ParallelPacketDecoder(profile, options.process_count, keep_all_agent_properties).decode_all(jobs, report_decoding)
        records = [packet.to_legacy_record() for packet in decoded]
        self._report_decoding_quality(records, log)
        progress('decode', 1.0)
        return LoadedCapture(records, roster, timed_payloads)

    @staticmethod
    def _report_decoding_quality(records: List[dict], log) -> None:
        read_to_end = sum(1 for record in records if record['tail'] and record['L'] - record['tail']['end'] < 8)
        queued = sum(1 for record in records if record.get('q'))
        log('%d/%d packets read to the end%s' % (read_to_end, len(records),
                                                 '; %d more were stored by the game and replayed with a later packet' % queued if queued else ''))
        unread = len(records) - read_to_end - queued
        if unread > 0:
            log('WARNING: %d packets could not be read to the end (unknown message type?); their last messages are lost' % unread)

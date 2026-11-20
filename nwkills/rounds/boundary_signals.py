"""The signals the server itself gives for a round border."""
import re
from typing import Iterable, List, Optional, Tuple

BoundaryTime = Tuple[float, str]            # (time, 'map' or 'reset')


class BoundaryMessageReader:
    """Round boundaries exactly as the server sends them, nothing inferred: message type 0 (map change: the client starts loading) and
    message type 41 (reset of the same map). The server sends each announcement several times in a row, and its first field counts
    0, 1, 2 ... through them; the count starting again is the next announcement."""

    DUPLICATE_WINDOW_S = 2.0

    def read(self, packet_records: List[dict]) -> Optional[List[BoundaryTime]]:
        """The boundaries, or None for records decoded before these messages were kept."""
        if packet_records and 'bnd' not in packet_records[0]:
            return None
        boundaries: List[BoundaryTime] = []
        latest = {}                         # kind -> (count, time) of the latest message
        for record in packet_records:
            for kind, count in record.get('bnd') or ():
                previous = latest.get(kind)
                if previous is None or count < previous[0] or (count == previous[0] and record['t'] - previous[1] > self.DUPLICATE_WINDOW_S):      # the same count again within a moment is a duplicate
                    boundaries.append((record['t'], kind))
                latest[kind] = (count, record['t'])
        return boundaries


class ServerTextBoundaryFinder:
    """Round boundaries announced in the server's text lines: 'Changed the map to ...' (map load) and 'Has reset the Map.' (admin reset; also a
    type-41 marker). Every round start is also followed, 30 s later, by 'Friendly fire is now on' - so a restart done without those lines (for
    example the admin 'Slayed Everyone') is recovered from that message (start = t - 30 s, snapped to a nearby 'Slayed Everyone' line)."""

    DEFAULT_FRIENDLY_FIRE_DELAY_S = 30.0
    MAP_MERGE_S = 60.0
    RESET_MERGE_S = 20.0
    ANY_MERGE_S = 3.0
    FRIENDLY_FIRE_REPEAT_S = 15.0
    EXPLAINED_WITHIN_S = 10.0
    SNAP_TO_SLAY_S = 12.0
    DELAY_PATTERN = re.compile(r'(?:after|to) (\d+) second')

    def find(self, packet_records: Iterable[dict]) -> List[BoundaryTime]:
        events: List[BoundaryTime] = []
        friendly_fire: List[Tuple[float, float]] = []            # (time of the line, the delay the server announced)
        slay_times: List[float] = []
        delay = self.DEFAULT_FRIENDLY_FIRE_DELAY_S
        for record in packet_records:
            for line in record.get('txt', ()):
                match = self.DELAY_PATTERN.search(line)
                if match and ('Friendly fire' in line or 'friendly fire' in line):
                    delay = float(match.group(1))                  # the server-configured delay (20/30 s ...)
                if 'Changed the map to' in line:
                    events.append((record['t'], 'map'))
                elif 'Has reset the Map' in line:
                    events.append((record['t'], 'reset'))
                elif 'Friendly fire is now on' in line:
                    friendly_fire.append((record['t'], delay))
                elif 'Slayed Everyone' in line:
                    slay_times.append(record['t'])
            if record.get('rst'):
                events.append((record['t'], 'reset'))
        events.sort()
        has_reset = any(kind == 'reset' for _t, kind in events)
        if not has_reset and not friendly_fire:
            return []                                              # a server without admin chat lines
        if not has_reset and not any(kind == 'map' for _t, kind in events):
            return []
        boundaries = self._merge_close_events(events)
        self._add_restarts_from_friendly_fire(boundaries, friendly_fire, slay_times)
        boundaries.sort()
        return boundaries

    def _merge_close_events(self, events: List[BoundaryTime]) -> List[BoundaryTime]:
        merged: List[BoundaryTime] = []
        for time_s, kind in events:
            if merged and merged[-1][1] == kind and time_s - merged[-1][0] < (self.MAP_MERGE_S if kind == 'map' else self.RESET_MERGE_S):
                continue
            if merged and time_s - merged[-1][0] < self.ANY_MERGE_S:
                continue
            merged.append((time_s, kind))
        return merged

    def _add_restarts_from_friendly_fire(self, boundaries: List[BoundaryTime], friendly_fire, slay_times: List[float]) -> None:
        previous_line_s = None
        for line_s, delay in sorted(friendly_fire):
            if previous_line_s is not None and line_s - previous_line_s < self.FRIENDLY_FIRE_REPEAT_S:
                continue
            previous_line_s = line_s
            start_s = line_s - delay
            if any(abs(time_s - start_s) <= self.EXPLAINED_WITHIN_S or line_s - 50 <= time_s <= line_s - 10 for time_s, _kind in boundaries):
                continue                  # explained by a map change / reset line (the delay may be unknown at capture start)
            nearby_slays = [slay_s for slay_s in slay_times if abs(slay_s - start_s) <= self.SNAP_TO_SLAY_S]
            boundaries.append((min(nearby_slays, key=lambda slay_s: abs(slay_s - start_s)) if nearby_slays else start_s, 'reset'))


class RestartAnnouncementFinder:
    """Times of admin lines announcing a restart ('reset and live', 'rest and live', 'reset et puis live' ...). A segment that contains one is
    a warm-up: the admin restarts the round right after it."""

    PATTERN = re.compile(r'\*Admin[^:]*:.*(\b(re?s?et|rest|restart)\b.*\blive\b|\blive\b.*\b(re?s?et|rest|restart)\b)', re.I)      # 'reset and live' and 'Live on Reset!'
    REPEAT_WINDOW_S = 5.0

    def find(self, packet_records: Iterable[dict]) -> List[float]:
        times: List[float] = []
        last_s = -99.0
        for record in packet_records:
            for line in record.get('txt', ()):
                if self.PATTERN.search(line) and record['t'] - last_s > self.REPEAT_WINDOW_S:
                    times.append(record['t'])
                    last_s = record['t']
        return times

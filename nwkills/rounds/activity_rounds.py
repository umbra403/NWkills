"""Rounds from the activity of the server, for captures where it gives no direct signal. Signals: a mass score reset (many players' score above 0
falls to 0 or less within 10 s), a flood of type-51 messages (a full resync), a gap of two seconds in the packets, and a long lull in spawns and
deaths followed by a new wave. Signals within a minute are one boundary."""
import collections
import statistics
from typing import List, Tuple

from .death_times import death_message_times
from .round_model import Round

Signal = Tuple[float, str]


class ActivityRoundDetector:
    MERGE_S = 60.0
    EDGE_S = 30.0
    MINIMUM_ROUND_S = 60
    MINIMUM_KILLS = 25
    # lulls: activity (spawns + deaths) falls below 30 % of the median for at least 40 s (everyone dead, between rounds), then a new wave spawns
    LULL_MINIMUM_S = 40
    LULL_FRACTION = 0.3
    LULL_BIN_S = 10
    # gaps, score resets and resyncs
    GAP_S = 2.0
    SCORE_RESET_MINIMUM_PLAYERS = 15
    SCORE_RESET_BIN_S = 10
    RESYNC_MESSAGE_TYPE = 51
    RESYNC_MINIMUM_MESSAGES = 500
    RESYNC_BIN_S = 5
    MAXIMUM_PLAYER_SLOT = 300
    SPAWN_MESSAGE_TYPE, DEATH_MESSAGE_TYPE = 5, 13

    def detect(self, packet_records: List[dict]) -> List[Round]:
        if not packet_records:
            return []
        first_s, last_s = packet_records[0]['t'], packet_records[-1]['t']
        cuts: List[list] = []
        for time_s, signal in self._signals(packet_records):
            if cuts and time_s - cuts[-1][0] < self.MERGE_S:
                cuts[-1][1].append(signal)
            else:
                cuts.append([time_s, [signal]])
        cuts = [cut for cut in cuts if first_s + self.EDGE_S < cut[0] < last_s - 5 or any(signal.startswith('gap') for signal in cut[1])]       # no borders in the first and last seconds of the capture
        starts = [first_s] + [cut[0] for cut in cuts]
        reasons = ['capture start'] + [','.join(sorted(set(cut[1]))) for cut in cuts]
        kill_times = death_message_times(packet_records)
        rounds = []
        for index, start_s in enumerate(starts):
            end_s = starts[index + 1] if index + 1 < len(starts) else last_s
            kill_count = sum(1 for time_s in kill_times if start_s <= time_s < end_s)
            review = []
            if end_s - start_s < self.MINIMUM_ROUND_S:
                review.append('short (<60 s)')
            if kill_count < self.MINIMUM_KILLS:
                review.append('few kills (%d): dud?' % kill_count)
            rounds.append(Round(number=index + 1, start_s=start_s, end_s=end_s, kill_count=kill_count, signals=reasons[index],
                                method='activity', review='; '.join(review)))
        return rounds

    def _signals(self, packet_records: List[dict]) -> List[Signal]:
        signals = self._lull_ends(packet_records)
        previous_s = None
        scores = {}
        dropped_players = collections.defaultdict(set)
        resync_counts = collections.Counter()
        for record in packet_records:
            time_s = record['t']
            if previous_s is not None and time_s - previous_s >= self.GAP_S:
                signals.append((previous_s, 'gap%.0fs' % (time_s - previous_s)))
            previous_s = time_s
            for message in record['msgs']:
                if message[0] == self.RESYNC_MESSAGE_TYPE:
                    resync_counts[int(time_s // self.RESYNC_BIN_S)] += 1
            state_block = record.get('tail')
            if state_block and record['L'] - state_block['end'] < 8:
                bin_index = int(time_s // self.SCORE_RESET_BIN_S)
                for player, property_number, value in state_block['players']:
                    if property_number == 0 and player < self.MAXIMUM_PLAYER_SLOT:
                        score = value - 8192 if value >= 4096 else value
                        if scores.get(player, 0) > 0 and score <= 0:
                            dropped_players[bin_index].add(player)
                        scores[player] = score
        for bin_index, players in dropped_players.items():
            if len(players) >= self.SCORE_RESET_MINIMUM_PLAYERS:
                signals.append((bin_index * float(self.SCORE_RESET_BIN_S), 'score-reset(%d)' % len(players)))
        for bin_index, count in resync_counts.items():
            if count >= self.RESYNC_MINIMUM_MESSAGES:
                signals.append((bin_index * float(self.RESYNC_BIN_S), 'resync'))
        return sorted(signals)

    def _lull_ends(self, packet_records: List[dict]) -> List[Signal]:
        """The times a long lull in spawns and deaths ends."""
        activity = collections.Counter()
        for record in packet_records:
            for message in record['msgs']:
                if message[0] in (self.SPAWN_MESSAGE_TYPE, self.DEATH_MESSAGE_TYPE):
                    activity[int(record['t'] // self.LULL_BIN_S)] += 1
        bin_count = int(packet_records[-1]['t'] // self.LULL_BIN_S) + 1
        per_bin = [activity.get(index, 0) for index in range(bin_count)]
        smoothed = [sum(per_bin[max(0, index - 1):index + 2]) for index in range(bin_count)]
        busy = [value for value in smoothed if value > 0]
        if not busy:
            return []
        limit = self.LULL_FRACTION * statistics.median(busy)
        lull_ends: List[Signal] = []
        index = 0
        while index < bin_count:
            if smoothed[index] < limit:
                end = index
                while end < bin_count and smoothed[end] < limit:
                    end += 1
                if end - index >= self.LULL_MINIMUM_S // self.LULL_BIN_S and end < bin_count:
                    lull_ends.append((end * float(self.LULL_BIN_S), 'lull-end(%ds)' % ((end - index) * self.LULL_BIN_S)))
                index = end
            else:
                index += 1
        return lull_ends

"""The death messages of a capture, as a count of when they came."""
from typing import Iterable, List

DEATH_MESSAGE_TYPE = 13


def death_message_times(packet_records: Iterable[dict]) -> List[float]:
    """The time of every death message (one death is sent many times, so this is a raw count)."""
    return [record['t'] for record in packet_records for message in record['msgs'] if message[0] == DEATH_MESSAGE_TYPE]

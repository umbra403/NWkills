"""Choosing how to find the rounds of a capture."""
from typing import List, Optional

from .activity_rounds import ActivityRoundDetector
from .boundary_signals import BoundaryMessageReader, ServerTextBoundaryFinder
from .round_model import Round
from .server_message_rounds import ServerMessageRoundDetector
from .ticket_rounds import TicketResetRoundDetector, TicketSeriesFinder


class RoundDetector:
    """The best signal that is there: the server's boundary messages (or, in a decode that kept none, its text lines), else the module's ticket
    resets, else the activity of the server."""

    def __init__(self, boundary_reader: Optional[BoundaryMessageReader] = None, text_finder: Optional[ServerTextBoundaryFinder] = None,
                 ticket_finder: Optional[TicketSeriesFinder] = None, server_detector: Optional[ServerMessageRoundDetector] = None,
                 ticket_detector: Optional[TicketResetRoundDetector] = None, activity_detector: Optional[ActivityRoundDetector] = None):
        self._boundary_reader = boundary_reader or BoundaryMessageReader()
        self._text_finder = text_finder or ServerTextBoundaryFinder()
        self._ticket_finder = ticket_finder or TicketSeriesFinder()
        self._server_detector = server_detector or ServerMessageRoundDetector()
        self._ticket_detector = ticket_detector or TicketResetRoundDetector()
        self._activity_detector = activity_detector or ActivityRoundDetector()

    def detect(self, packet_records: List[dict]) -> List[Round]:
        if not packet_records:
            return []
        boundaries = self._boundary_reader.read(packet_records)
        if boundaries is None:
            boundaries = self._text_finder.find(packet_records)       # a cache from before the boundary messages were kept: chat lines instead
        ticket_series = self._ticket_finder.find(packet_records)
        if boundaries:
            return self._server_detector.detect(packet_records, boundaries, ticket_series)
        if ticket_series:
            return self._ticket_detector.detect(packet_records, ticket_series)
        return self._activity_detector.detect(packet_records)

"""The text shown while a pktmon capture is running."""
from typing import Tuple

BYTES_PER_MEGABYTE = 1048576
NEARLY_FULL_FRACTION = 0.9


def describe_running_capture(elapsed_seconds: int, logged_bytes: int, buffer_megabytes: int) -> Tuple[str, bool]:
    """-> (rich text, whether the circular log is nearly full and about to overwrite the start of the capture)."""
    nearly_full = logged_bytes >= NEARLY_FULL_FRACTION * buffer_megabytes * BYTES_PER_MEGABYTE
    text = 'Capturing: %d:%02d:%02d, %.0f MB of %d MB logged.%s' % (
        elapsed_seconds // 3600, elapsed_seconds // 60 % 60, elapsed_seconds % 60, logged_bytes / BYTES_PER_MEGABYTE, buffer_megabytes,
        '  <b>The log is nearly full and will start overwriting the beginning.</b>' if nearly_full else '')
    return text, nearly_full

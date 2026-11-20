"""Temporary result folders left behind by a run that crashed or was killed."""
import glob
import os
import shutil
import tempfile
import time
from typing import Optional


class StaleResultFolderSweeper:
    """Removes the temporary folders `nwkills-*` that are old and hold nothing but csv files."""

    def __init__(self, temporary_root: Optional[str] = None, max_age_s: float = 3600):
        self._temporary_root = temporary_root or tempfile.gettempdir()
        self._max_age_s = max_age_s

    def sweep(self, now_s: Optional[float] = None) -> int:
        """-> the number of folders removed."""
        now_s = time.time() if now_s is None else now_s
        removed = 0
        for folder in glob.glob(os.path.join(self._temporary_root, 'nwkills-*')):
            try:
                if self._is_stale(folder, now_s):
                    shutil.rmtree(folder, ignore_errors=True)
                    removed += 1
            except OSError:
                pass
        return removed

    def _is_stale(self, folder: str, now_s: float) -> bool:
        return (os.path.isdir(folder) and now_s - os.path.getmtime(folder) > self._max_age_s
                and all(name.lower().endswith('.csv') for name in os.listdir(folder)))

"""The folder a conversion writes its files into; the window reads them into memory and deletes the folder."""
import os
import shutil
import tempfile
from typing import Optional


class TemporaryResultFolder:
    def __init__(self):
        self._path: Optional[str] = None

    @property
    def path(self) -> Optional[str]:
        return self._path

    def create(self) -> str:
        self.discard()
        self._path = tempfile.mkdtemp(prefix='nwkills-')
        return self._path

    def file_path(self, file_name: str) -> str:
        return os.path.join(self._path, file_name)

    def discard(self) -> None:
        if self._path:
            shutil.rmtree(self._path, ignore_errors=True)
            self._path = None

"""What the Options tab asks for, as one object."""
import os
from dataclasses import dataclass
from typing import Optional

from ..pipeline import PipelineOptions


@dataclass
class ConversionRequest:
    capture_path: str
    kills_path: str
    server_port: Optional[int] = None
    own_name_part: Optional[str] = None
    process_count: int = 1
    cache_path: Optional[str] = None
    packet_limit: Optional[int] = None

    @classmethod
    def from_form(cls, capture_path: Optional[str], output_folder_text: str, server_port: Optional[int], own_name_text: str, process_count: int,
                  use_cache: bool, packet_limit: Optional[int]) -> 'ConversionRequest':
        """`output_folder_text` empty = next to the capture. The cache is a file next to the exports."""
        stem = os.path.splitext(os.path.basename(capture_path or 'capture'))[0]
        output_folder = output_folder_text.strip() or (os.path.dirname(os.path.abspath(capture_path)) if capture_path else '')
        return cls(capture_path=capture_path or '', kills_path=os.path.join(output_folder, stem + '_kills.csv'), server_port=server_port,
                   own_name_part=own_name_text.strip() or None, process_count=process_count,
                   cache_path=os.path.join(output_folder, stem + '.nwcache.pkl') if use_cache else None, packet_limit=packet_limit)

    def command_line(self) -> str:
        """The command line that does the same, shown on the Options tab."""
        parts = 'nwkills "%s" --out "%s"' % (self.capture_path, self.kills_path)
        if self.server_port:
            parts += ' --port %d' % self.server_port
        if self.own_name_part:
            parts += ' --me "%s"' % self.own_name_part
        parts += ' --jobs %d' % self.process_count
        if self.cache_path:
            parts += ' --cache "%s"' % self.cache_path
        if self.packet_limit:
            parts += ' --limit %d' % self.packet_limit
        return parts

    def to_pipeline_options(self) -> PipelineOptions:
        return PipelineOptions(capture_path=self.capture_path, kills_path=self.kills_path, server_port=self.server_port, own_name_part=self.own_name_part,
                               process_count=self.process_count, cache_path=self.cache_path, packet_limit=self.packet_limit)


def default_export_folder(output_folder_text: str, capture_path: Optional[str], home_folder: Optional[str] = None) -> str:
    """Where the export dialogs start: the chosen folder, else next to the capture, else the home folder."""
    return output_folder_text.strip() or (os.path.dirname(os.path.abspath(capture_path)) if capture_path else (home_folder or os.path.expanduser('~')))

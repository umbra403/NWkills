"""The stages of a conversion and how far along the whole run is."""
from dataclasses import dataclass
from typing import NamedTuple, Optional, Sequence


@dataclass(frozen=True)
class ProgressStage:
    stage_id: str
    label: str
    weight: int                              # its share of the whole run, in percent
    reports_fraction: bool = True            # False: the stage cannot say how far it is (a busy bar is shown)


DEFAULT_STAGES = (
    ProgressStage('read', 'Reading capture', 10),
    ProgressStage('roster', 'Calibrating for this server', 5, reports_fraction=False),
    ProgressStage('decode', 'Decoding packets', 55),
    ProgressStage('events', 'Reading kill events', 15, reports_fraction=False),
    ProgressStage('rounds', 'Detecting rounds and flagbearers', 5, reports_fraction=False),
    ProgressStage('players', 'Scores and per-player totals', 10, reports_fraction=False),
)


class ProgressReport(NamedTuple):
    label: str
    overall_percent: float
    stage_fraction: Optional[float]          # 0..1, or None when the stage has no measurable progress


class OverallProgress:
    def __init__(self, stages: Sequence[ProgressStage] = DEFAULT_STAGES):
        self._stages = stages

    def report(self, stage_id: str, fraction: float) -> ProgressReport:
        if stage_id == 'done':
            return ProgressReport('Finished', 100.0, 1.0)
        finished_percent = 0.0
        for stage in self._stages:
            if stage.stage_id == stage_id:
                if not stage.reports_fraction:
                    return ProgressReport(stage.label, finished_percent, None)
                return ProgressReport(stage.label, finished_percent + stage.weight * fraction, fraction)
            finished_percent += stage.weight
        return ProgressReport(stage_id, finished_percent, None)

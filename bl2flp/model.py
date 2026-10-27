"""Project model shared by the BandLab parser and the FLP writer."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class MidiNote:
    pitch: int
    velocity: int
    start_sec: float
    duration_sec: float


@dataclass
class Clip:
    id: str
    name: str
    start_sec: float
    duration_sec: float
    offset_sec: float = 0.0
    audio_path: Path | None = None
    notes: list[MidiNote] = field(default_factory=list)


@dataclass
class Effect:
    slug: str
    enabled: bool
    params: dict[str, float]


@dataclass
class Track:
    id: str
    name: str
    kind: str  # "audio", "midi", "drum"
    volume: float = 0.8  # 0..1, 1.0 = unity
    pan: float = 0.0  # -1..1
    muted: bool = False
    solo: bool = False
    clips: list[Clip] = field(default_factory=list)
    effects: list[Effect] = field(default_factory=list)
    automation: dict[str, list[tuple[float, float]]] = field(default_factory=dict)


@dataclass
class Project:
    name: str
    bpm: float
    time_signature: tuple[int, int]
    tracks: list[Track]
    source: Path | None = None


@dataclass
class Warning_:
    code: str
    message: str


@dataclass
class Report:
    warnings: list[Warning_] = field(default_factory=list)
    stats: dict[str, int] = field(default_factory=dict)

    def warn(self, code: str, message: str) -> None:
        self.warnings.append(Warning_(code, message))

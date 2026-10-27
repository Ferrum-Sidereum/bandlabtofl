"""BandLab revision manifest parser.

BandLab has no public, versioned schema for revision manifests.  The parser is
therefore deliberately tolerant: it accepts the field names seen in exported
manifests and in the web client, normalises units, and reports anything it has
to guess instead of failing silently.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from .model import Clip, Effect, MidiNote, Project, Report, Track

AUDIO_EXTS = {".wav", ".aif", ".aiff", ".mp3", ".ogg", ".flac"}
CONVERT_EXTS = {".m4a", ".aac", ".opus", ".webm", ".mp4"}


def _get(obj: Any, *names: str, default=None):
    if not isinstance(obj, dict):
        return default
    for name in names:
        if name in obj and obj[name] is not None:
            return obj[name]
    return default


def _float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _bool(value, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return default


def _unwrap(data: Any) -> dict:
    if not isinstance(data, dict):
        raise ValueError("Revision JSON must be an object")
    for key in ("revision", "data", "project"):
        inner = data.get(key)
        if isinstance(inner, dict) and (
            "tracks" in inner or "trackList" in inner
        ):
            return inner
    return data


def load_revision(path: Path, workdir: Path | None = None) -> tuple[dict, Path, Path | None]:
    """Load a revision manifest.

    Returns ``(manifest, assets_dir, extracted_root)``.  ``.zip`` archives are
    extracted into a temporary directory owned by the caller.
    """
    path = Path(path)
    if path.suffix.lower() == ".zip":
        root = Path(tempfile.mkdtemp(prefix="bl2flp-", dir=workdir))
        with zipfile.ZipFile(path) as archive:
            archive.extractall(root)
        manifests = sorted(root.rglob("*.json"))
        if not manifests:
            raise ValueError("Archive contains no JSON manifest")
        manifest_path = manifests[0]
        assets = manifest_path.parent / "assets"
        if not assets.is_dir():
            assets = manifest_path.parent
        return json.loads(manifest_path.read_text(encoding="utf-8")), assets, root

    data = json.loads(path.read_text(encoding="utf-8"))
    assets = path.parent / "assets"
    if not assets.is_dir():
        assets = path.parent
    return data, assets, None


def parse_project(
    data: dict,
    assets_dir: Path,
    *,
    positions: str = "auto",
    ppq: int = 96,
) -> tuple[Project, Report]:
    report = Report()
    data = _unwrap(data)

    bpm = _float(_get(data, "bpm", "tempo"), 0.0)
    if bpm <= 0:
        bpm = 120.0
        report.warn("tempo-default", "No tempo found in manifest; using 120 BPM")
    if bpm < 20 or bpm > 400:
        report.warn("tempo-range", f"Unusual tempo {bpm}; kept as-is")

    ts_raw = _get(data, "timeSignature", "time_signature", default={})
    if isinstance(ts_raw, dict):
        numerator = int(_get(ts_raw, "numerator", "num", default=4))
        denominator = int(_get(ts_raw, "denominator", "den", default=4))
    elif isinstance(ts_raw, (list, tuple)) and len(ts_raw) == 2:
        numerator, denominator = int(ts_raw[0]), int(ts_raw[1])
    else:
        numerator, denominator = 4, 4

    ticks_hint = _get(data, "ticksPerBeat", "ppq") is not None
    if positions == "ticks":
        ticks_hint = True
    elif positions == "seconds":
        ticks_hint = False

    def to_seconds(value) -> float:
        seconds = max(0.0, _float(value))
        if ticks_hint:
            beats = seconds / max(1, ppq)
            return beats * 60.0 / bpm
        return seconds

    samples = _build_sample_index(data, assets_dir, report)
    tracks_raw = _get(data, "tracks", "trackList", default=[])
    if not isinstance(tracks_raw, list):
        raise ValueError("Manifest has no track list")

    tracks: list[Track] = []
    for index, raw in enumerate(tracks_raw):
        if not isinstance(raw, dict):
            continue
        name = str(_get(raw, "name", "title", default=f"Track {index + 1}"))
        raw_type = str(_get(raw, "type", "kind", "trackType", default="")).lower()
        regions_raw = _get(raw, "regions", "clips", "segments", "blocks", default=[])
        if not isinstance(regions_raw, list):
            regions_raw = []
        drum_patterns = _get(raw, "drumPatterns", "patterns", default=[])
        has_notes = any(_get(region, "notes", "midiNotes") for region in regions_raw)

        if raw_type in {"voice", "audio", "vocal", "recording", "sample"}:
            kind = "audio"
        elif raw_type in {"drum-machine", "drums", "drum", "beat"} or drum_patterns:
            kind = "drum"
        elif raw_type in {"instrument", "midi", "synth", "piano", "keys"} or has_notes:
            kind = "midi"
        else:
            kind = "audio" if not has_notes else "midi"

        track = Track(
            id=str(_get(raw, "id", "_id", default=f"track-{index}")),
            name=name,
            kind=kind,
            volume=_volume(_get(raw, "volume", "gain", "level")),
            pan=_pan(_get(raw, "pan", "panning")),
            muted=_bool(_get(raw, "isMuted", "muted", "mute"), False),
            solo=_bool(_get(raw, "isSolo", "solo"), False),
            effects=_effects(_get(raw, "effects", "fx", "inserts", default=[]), report, name),
        )

        for region_index, region in enumerate(regions_raw):
            if not isinstance(region, dict):
                continue
            clip = _clip(region, region_index, name, to_seconds, samples, report)
            if kind == "drum":
                clip.notes.extend(_drum_notes(region, bpm, report))
            if kind == "audio" and clip.audio_path is None and clip.notes:
                track.kind = "midi"
                kind = "midi"
            if clip.duration_sec <= 0:
                report.warn("zero-clip", f"Clip '{clip.name}' has zero duration")
                continue
            track.clips.append(clip)

        if kind == "drum" and drum_patterns:
            drum_clip = _drum_clip(drum_patterns, name, bpm, report)
            if drum_clip is not None:
                track.clips.append(drum_clip)

        automation = _get(raw, "automation", default={})
        if isinstance(automation, dict):
            for param, points in automation.items():
                if not isinstance(points, list):
                    continue
                parsed = []
                for point in points:
                    if isinstance(point, dict):
                        parsed.append(
                            (to_seconds(_get(point, "time", "position")), _float(_get(point, "value")))
                        )
                if parsed:
                    track.automation[str(param)] = parsed
            if track.automation:
                report.warn(
                    "automation-not-native",
                    f"Track '{name}': automation is exported as data but not written as FL automation clips",
                )

        tracks.append(track)

    if not tracks:
        report.warn("no-tracks", "Manifest contains no usable tracks")

    project_name = str(_get(data, "name", "title", default="BandLab Project"))
    project = Project(
        name=project_name,
        bpm=bpm,
        time_signature=(numerator, denominator),
        tracks=tracks,
    )
    report.stats.update(
        {
            "tracks": len(tracks),
            "clips": sum(len(t.clips) for t in tracks),
            "notes": sum(len(c.notes) for t in tracks for c in t.clips),
        }
    )
    return project, report


def _build_sample_index(data: dict, assets_dir: Path, report: Report) -> dict[str, Path]:
    index: dict[str, Path] = {}
    entries = _get(data, "samples", "assets", "files", default=[])
    if not isinstance(entries, list):
        entries = []

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        sample_id = str(_get(entry, "id", "_id", "sampleId", default=""))
        candidates = [
            _get(entry, "fileName", "filename", "name"),
            _get(entry, "path", "file"),
        ]
        resolved = None
        for candidate in candidates:
            if not candidate:
                continue
            path = Path(str(candidate))
            if not path.is_absolute():
                path = assets_dir / path.name
            if path.is_file():
                resolved = path
                break
        if resolved is None and sample_id:
            resolved = _find_asset(assets_dir, sample_id)
        if resolved is None:
            report.warn("missing-sample", f"Sample '{sample_id or candidates}' is not present in {assets_dir}")
            continue
        if sample_id:
            index[sample_id] = resolved
        for candidate in candidates:
            if candidate:
                index[str(candidate)] = resolved
    return index


def _find_asset(assets_dir: Path, sample_id: str) -> Path | None:
    if not assets_dir.is_dir():
        return None
    safe = re.sub(r"[^A-Za-z0-9._-]+", "", sample_id)
    for ext in AUDIO_EXTS | CONVERT_EXTS:
        direct = assets_dir / f"{sample_id}{ext}"
        if direct.is_file():
            return direct
    if safe:
        for path in assets_dir.iterdir():
            if path.is_file() and safe in path.name:
                return path
    return None


def _clip(region: dict, index: int, track_name: str, to_seconds, samples, report: Report) -> Clip:
    clip_name = str(_get(region, "name", "title", default=f"{track_name} {index + 1}"))
    start = to_seconds(_get(region, "startPosition", "start", "startTime", "position", default=0))
    duration = to_seconds(_get(region, "duration", "length", "loopLength", default=0))
    offset = to_seconds(_get(region, "sampleOffset", "offset", "startOffset", default=0))

    sample_id = _get(region, "sampleId", "sampleID", "sample", "audioId", "assetId")
    audio_path = samples.get(str(sample_id)) if sample_id is not None else None
    if audio_path is not None:
        audio_path = ensure_wav(audio_path, report)

    notes = []
    for raw_note in _get(region, "notes", "midiNotes", "events", default=[]) or []:
        if not isinstance(raw_note, dict):
            continue
        pitch = int(_float(_get(raw_note, "pitch", "key", "midiNote", "note"), 60))
        velocity = int(_float(_get(raw_note, "velocity", "vel"), 100))
        start_note = to_seconds(_get(raw_note, "startTime", "start", "position", default=0))
        length_note = to_seconds(_get(raw_note, "duration", "length", default=0.25))
        if start_note > duration and start >= 0 and duration > 0:
            start_note = max(0.0, start_note - start)
        notes.append(
            MidiNote(
                pitch=max(0, min(127, pitch)),
                velocity=max(1, min(127, velocity)),
                start_sec=start_note,
                duration_sec=max(0.01, length_note),
            )
        )

    return Clip(
        id=str(_get(region, "id", "_id", default=f"clip-{index}")),
        name=clip_name,
        start_sec=start,
        duration_sec=duration,
        offset_sec=max(0.0, offset),
        audio_path=audio_path,
        notes=notes,
    )


def _drum_notes(region: dict, bpm: float, report: Report) -> list[MidiNote]:
    steps = _get(region, "steps", "cells", "pattern")
    if not isinstance(steps, list) or not steps:
        return []
    midi_note = int(_float(_get(region, "midiNote", "note", "pitch"), 36))
    step_sec = 60.0 / bpm / 4.0
    notes = []
    for index, step in enumerate(steps):
        if not step:
            continue
        velocity = 100
        pitch = midi_note
        if isinstance(step, dict):
            velocity = int(_float(_get(step, "velocity", "vel"), velocity))
            pitch = int(_float(_get(step, "midiNote", "note", "pitch"), pitch))
        notes.append(
            MidiNote(
                pitch=max(0, min(127, pitch)),
                velocity=max(1, min(127, velocity)),
                start_sec=index * step_sec,
                duration_sec=step_sec * 0.5,
            )
        )
    if notes:
        report.warn("drum-steps", f"Drum steps expanded using 1/16 grid ({len(notes)} hits)")
    return notes


def _drum_clip(patterns, track_name: str, bpm: float, report: Report) -> Clip | None:
    if not isinstance(patterns, list):
        return None
    notes: list[MidiNote] = []
    step_sec = 60.0 / bpm / 4.0
    for pad_index, pad in enumerate(patterns):
        if not isinstance(pad, dict):
            continue
        steps = _get(pad, "steps", "cells", "pattern")
        if not isinstance(steps, list):
            continue
        pitch = int(_float(_get(pad, "midiNote", "note", "pitch"), 36 + pad_index))
        for index, step in enumerate(steps):
            if not step:
                continue
            velocity = int(_float(_get(step, "velocity", "vel") if isinstance(step, dict) else 100, 100))
            notes.append(
                MidiNote(
                    pitch=max(0, min(127, pitch)),
                    velocity=max(1, min(127, velocity)),
                    start_sec=index * step_sec,
                    duration_sec=step_sec * 0.5,
                )
            )
    if not notes:
        return None
    length = max(note.start_sec + note.duration_sec for note in notes)
    report.warn("drum-machine", f"Drum machine '{track_name}' expanded to {len(notes)} MIDI notes")
    return Clip(
        id=f"drums-{track_name}",
        name=f"{track_name} (drums)",
        start_sec=0.0,
        duration_sec=length,
        notes=notes,
    )


def _effects(raw, report: Report, track_name: str) -> list[Effect]:
    from .vststate import CATALOG, canonical_slug

    effects = []
    if not isinstance(raw, list):
        return effects
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        slug = str(_get(entry, "slug", "type", "id", "name", default="")).strip()
        slug = slug.lower().replace("bandlab-", "").replace("bandlab_", "")
        slug = re.sub(r"^(bl|bandlab)[_-]", "", slug)
        slug = re.sub(r"[^a-z0-9]+", "_", slug).strip("_")
        if not slug:
            continue
        params_raw = _get(entry, "params", "parameters", default={})
        params = {}
        if isinstance(params_raw, dict):
            params = {str(k): _float(v) for k, v in params_raw.items() if isinstance(v, (int, float))}
        elif isinstance(params_raw, list):
            for item in params_raw:
                if isinstance(item, dict):
                    key = _get(item, "name", "id", "key")
                    if key is not None:
                        params[str(key)] = _float(_get(item, "value", "val"))
        effects.append(
            Effect(
                slug=canonical_slug(slug),
                enabled=not _bool(_get(entry, "bypass", "bypassed", "disabled"), False),
                params=params,
            )
        )
        if canonical_slug(slug) not in CATALOG:
            report.warn("unknown-effect", f"Track '{track_name}': effect '{slug}' has no state mapping")
    return effects


def _volume(value) -> float:
    if value is None:
        return 0.8
    v = _float(value, 0.8)
    if 0.0 <= v <= 1.0:
        return v
    if -60.0 <= v < 0.0:
        return min(1.0, 10 ** (v / 20.0))
    if 1.0 < v <= 128.0:
        return min(1.0, v / 100.0)
    if v > 128.0:
        return min(1.0, v / 12800.0)
    return 0.8


def _pan(value) -> float:
    if value is None:
        return 0.0
    p = _float(value, 0.0)
    if -1.0 <= p <= 1.0:
        return p
    if 1.0 < p <= 127.0:
        return max(-1.0, min(1.0, (p - 64.0) / 64.0))
    return max(-1.0, min(1.0, p / 100.0))


def ensure_wav(path: Path, report: Report) -> Path:
    path = Path(path)
    if path.suffix.lower() in AUDIO_EXTS:
        return path
    if path.suffix.lower() not in CONVERT_EXTS:
        report.warn("unknown-audio", f"Unknown audio container: {path.name}")
        return path
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        report.warn("no-ffmpeg", f"Cannot convert {path.name}: ffmpeg is not on PATH")
        return path
    target = path.with_suffix(".wav")
    if target.is_file() and target.stat().st_mtime >= path.stat().st_mtime:
        return target
    result = subprocess.run(
        [ffmpeg, "-y", "-loglevel", "error", "-i", str(path), "-acodec", "pcm_s24le", str(target)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 or not target.is_file():
        report.warn("ffmpeg-failed", f"Could not convert {path.name}: {result.stderr.strip()[:200]}")
        return path
    return target

"""Binary state chunks shared with the VST3 plug-in.

Layout (little endian, 76 bytes): ``<4sII16f``.
"""

from __future__ import annotations

import struct
from pathlib import Path

MAGIC = b"BLWB"
VERSION = 1
CHUNK = struct.Struct("<4sII16f")

PARAM_ORDER = (
    "rev_mix",
    "rev_decay",
    "rev_predelay",
    "rev_damping",
    "cho_mode",
    "cho_mix",
    "cmp_squeeze",
    "cmp_attack",
    "cmp_release",
    "cmp_makeup",
    "amp_drive",
    "amp_bass",
    "amp_mid",
    "amp_treble",
    "amp_presence",
    "amp_cab",
)

#: Alternate spellings seen in exported manifests and web-client payloads.
SLUG_ALIASES = {
    "spacemaker": "space_maker",
    "space_maker_reverb": "space_maker",
    "reverb": "space_maker",
    "dimensionb": "dimension_b",
    "dimension": "dimension_b",
    "chorus": "dimension_b",
    "fbkcompressor": "fbk_compressor",
    "fbk": "fbk_compressor",
    "compressor": "fbk_compressor",
    "guitaramp": "guitar_amp",
    "amp": "guitar_amp",
}


def canonical_slug(slug: str) -> str:
    key = slug.strip().lower().replace("-", "_").replace(" ", "_")
    key = key.removeprefix("bl_").removeprefix("bandlab_")
    return SLUG_ALIASES.get(key, key)


#: Canonical effect slug -> (module bit, {parameter: (index, converter, aliases)}).
CATALOG: dict[str, tuple[int, dict[str, tuple[int, object]]]] = {
    "space_maker": (
        1,
        {
            "mix": (0, None, ("wet", "wetdry", "wet_dry")),
            "decay": (1, lambda v: _norm(v, 0.1, 10.0), ("decaytime", "decay_time", "room_size", "roomsize")),
            "predelay": (2, lambda v: _norm(v, 0.0, 200.0), ("pre_delay", "predelaytime")),
            "damping": (3, None, ("damp", "hf_damping", "hfdamping")),
        },
    ),
    "dimension_b": (
        2,
        {
            "mode": (4, lambda v: _norm(v, 1.0, 4.0), ("preset", "type")),
            "mix": (5, None, ("wet", "depth")),
        },
    ),
    "fbk_compressor": (
        3,
        {
            "squeeze": (6, None, ("amount", "compression")),
            "attack": (7, None, ("attacktime", "attack_time")),
            "release": (8, None, ("releasetime", "release_time")),
            "makeup": (9, None, ("makeupgain", "makeup_gain", "gain")),
        },
    ),
    "guitar_amp": (
        4,
        {
            "drive": (10, None, ("gain", "distortion")),
            "bass": (11, None, ("low",)),
            "mid": (12, None, ("middle",)),
            "treble": (13, None, ("high",)),
            "presence": (14, None, ()),
            "cab_model": (15, None, ("cabinet", "cab", "speaker")),
        },
    ),
}


def _norm(value: float, low: float, high: float) -> float:
    if high <= low:
        return 0.0
    return (float(value) - low) / (high - low)


def build_state(effects) -> bytes:
    params = [0.0] * 16
    active_mask = 0
    for effect in effects:
        spec = CATALOG.get(canonical_slug(effect.slug))
        if spec is None or not effect.enabled:
            continue
        module_bit, mapping = spec
        active_mask |= 1 << module_bit
        lowered = {str(k).strip().lower().replace("-", "_"): v for k, v in effect.params.items()}
        for name, (index, converter, aliases) in mapping.items():
            value = lowered.get(name)
            if value is None:
                for alias in aliases:
                    if alias in lowered:
                        value = lowered[alias]
                        break
            if value is None:
                continue
            try:
                params[index] = min(1.0, max(0.0, converter(value) if converter else float(value)))
            except (TypeError, ValueError):
                continue
    return CHUNK.pack(MAGIC, VERSION, active_mask, *params)


def read_state(path: Path) -> dict:
    raw = Path(path).read_bytes()
    if len(raw) != CHUNK.size:
        raise ValueError(f"{path}: expected {CHUNK.size} bytes, got {len(raw)}")
    magic, version, mask, *values = CHUNK.unpack(raw)
    if magic != MAGIC:
        raise ValueError(f"{path}: bad magic {magic!r}")
    if version != VERSION:
        raise ValueError(f"{path}: unsupported version {version}")
    return {"mask": mask, "params": dict(zip(PARAM_ORDER, values))}

"""Create a small BandLab-style fixture and run the converter end to end."""

from __future__ import annotations

import json
import math
import struct
import sys
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FIXTURE = ROOT / "fixtures" / "demo"
ASSETS = FIXTURE / "assets"


def make_wav(path: Path, seconds: float = 2.0) -> None:
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(2)
        wav.setsampwidth(2)
        wav.setframerate(44100)
        frames = bytearray()
        for i in range(int(44100 * seconds)):
            value = int(9000 * math.sin(2 * math.pi * 220 * i / 44100))
            frames += struct.pack("<hh", value, value)
        wav.writeframes(bytes(frames))


def main() -> int:
    ASSETS.mkdir(parents=True, exist_ok=True)
    make_wav(ASSETS / "sample-1.wav")
    manifest = {
        "id": "demo-revision",
        "name": "Demo Song",
        "bpm": 128,
        "timeSignature": {"numerator": 4, "denominator": 4},
        "samples": [{"id": "sample-1", "fileName": "sample-1.wav"}],
        "tracks": [
            {
                "id": "t1",
                "name": "Vocal",
                "type": "voice",
                "volume": 0.72,
                "pan": -0.25,
                "effects": [
                    {
                        "slug": "bl_space_maker",
                        "params": {"mix": 0.3, "decay": 2.5, "predelay": 20, "damping": 0.5},
                    },
                    {"slug": "bl_fbk_compressor", "params": {"squeeze": 0.4, "makeup": 0.2}},
                ],
                "regions": [
                    {
                        "id": "r1",
                        "name": "Verse 1",
                        "startPosition": 1.0,
                        "duration": 4.0,
                        "sampleId": "sample-1",
                    }
                ],
                "automation": {"volume": [{"time": 0, "value": 0.8}, {"time": 4, "value": 0.4}]},
            },
            {
                "id": "t2",
                "name": "Keys",
                "type": "instrument",
                "volume": 0.6,
                "pan": 0.1,
                "effects": [{"slug": "bl_dimension_b", "params": {"mode": 2, "mix": 0.4}}],
                "regions": [
                    {
                        "id": "r2",
                        "name": "Chords",
                        "startPosition": 0.0,
                        "duration": 4.0,
                        "notes": [
                            {"pitch": 60, "velocity": 100, "startTime": 0.0, "duration": 1.0},
                            {"pitch": 64, "velocity": 96, "startTime": 1.0, "duration": 1.0},
                            {"pitch": 67, "velocity": 110, "startTime": 2.0, "duration": 2.0},
                        ],
                    }
                ],
            },
            {
                "id": "t3",
                "name": "Drums",
                "type": "drum-machine",
                "volume": 0.9,
                "pan": 0.0,
                "drumPatterns": [
                    {"midiNote": 36, "steps": [1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0]},
                    {"midiNote": 38, "steps": [0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0]},
                ],
            },
        ],
    }
    manifest_path = FIXTURE / "revision.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    sys.path.insert(0, str(ROOT.parent))
    from bl2flp.pipeline import convert

    summary = convert(
        manifest_path,
        FIXTURE / "Demo.flp",
        assets=ASSETS,
        template=Path(r"C:\Program Files\Image-Line\FL Studio 2026\Data\System\Empty.flp"),
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

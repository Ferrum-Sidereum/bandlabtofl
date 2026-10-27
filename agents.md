# AGENTS.md

## Project Overview

**BL2FLP** converts a BandLab revision manifest into a native FL Studio project
and ships a JUCE VST3 with modelled effects.  Two subsystems:

1. **Python converter (`bl2flp/`)** — parses a local revision JSON/ZIP, resolves
   audio assets, rebuilds the FLP binary graph by mutating a real FL Studio
   template, and writes MIDI + `.blwb` state sidecars.
2. **JUCE VST3 / Standalone (`plugin/Source/`)** — four DSP modules and a
   `.blwb` state loader.

The converter is deliberately honest about unsupported features: every guess or
loss is emitted as a warning in `*.report.json`.

## Verified behaviour (2026-10-27)

- `python -m bl2flp` GUI and CLI convert `dev/fixtures/demo` into an FLP with
  3 tracks, 3 channels, 2 patterns, 3 playlist items, tempo 128, title
  `Demo Song`.
- Playlist items are written as **88-byte** records, matching records saved by
  FL Studio 2026 (`project fleur.flp`, `beat.flp`).
- FL Studio 2026 opened a prototype with cloned channels and a named pattern
  (`Pattern 1`). Playlist rendering could not be re-verified because FL Studio
  stopped creating a main window in the test session, even with no project.
- VST3 builds and `juce_vst3_helper -validate` accepts the bundle. Standalone
  opens and renders the editor.
- `.blwb` is 76 bytes in both Python and C++ (`static_assert` in the plugin).

## Repository structure

```text
bl2flp/
  compat.py     pyflp/EventEnum shim for Python 3.13+
  bandlab.py    tolerant manifest parser, unit conversion, ffmpeg fallback
  model.py      dataclasses + report
  flp.py        FLP writer (channels, patterns, 88-byte playlist, metadata)
  midi.py       MIDI fallback
  vststate.py   shared BLWB chunk contract
  pipeline.py   template discovery + orchestration + report JSON
  cli.py        argparse CLI
  gui.py        Tkinter UI
plugin/Source/  PluginProcessor(.h/.cpp), PluginEditor(.h/.cpp)
CMakeLists.txt  JUCE 8.0.6 build (vendor/JUCE)
dev/            smoke fixture + verification helpers (not shipped)
```

## Build and run

```powershell
python -m pip install -r requirements.txt
.\BL2FLP.cmd
python -m bl2flp revision.json Output.flp --assets .\assets
.\build-plugin.ps1
```

## Contracts that must not drift

### BLWB state chunk

`<4sII16f` = 76 bytes little-endian: magic `BLWB`, version `1`, module mask,
16 normalised floats.  Indices:

| Index | Parameter | Module |
|---|---|---|
| 0–3 | rev_mix, rev_decay, rev_predelay, rev_damping | SpaceMaker |
| 4–5 | cho_mode, cho_mix | Dimension B |
| 6–9 | cmp_squeeze, cmp_attack, cmp_release, cmp_makeup | FBK compressor |
| 10–15 | amp_drive, amp_bass, amp_mid, amp_treble, amp_presence, amp_cab | Guitar amp |

Any change requires bumping both `VERSION` in `vststate.py` and the C++
`StateChunk.version` and keeping the size equal.

### FLP playlist format

FL Studio 2026 reads 88-byte playlist records.  The first 60 bytes follow the
legacy layout; offsets 32 (clip UID), 52 (audio default 1.0), 68 (1.875) and
76 (-1) must be preserved.  Do **not** write 60-byte records for FL 2026.

### FLP template

`FlpBuilder` requires an FL Studio project with a channel rack, an arrangement,
and a playlist event.  The installed `Data/System/Empty.flp` is used by default.
Do not synthesise an FLP from an empty byte string.

## Engineering rules

Python:

- Time conversion: `ticks = round(seconds / 60 * bpm * ppq)`; minimum 1 tick.
- Channel volume: `int(volume * 12800)`, pan `int(6400 + pan * 6400)`.
- Channel-to-insert routing is **per BandLab track**, not per clip.
- Missing samples, unknown effects, automation and format guesses must produce
  report warnings, never silent success.
- pyflp 2.2.1 is GPL-3.0 and incompatible with Python 3.14's `EnumType.__call__`;
  `bl2flp/compat.py` must be applied before parsing.

C++:

- No allocation, locks, or file I/O in `processBlock` or DSP `process` methods.
- Delay lines are allocated in `prepare`.
- `juce::ScopedNoDenormals` in `processBlock`.
- Filter coefficients are computed with the sample rate; never hardcode 44100.
- No floating-point literals in parameter IDs; keep the 16-parameter order.

## Non-goals / known gaps

- Cloud download from BandLab (no documented, stable API).
- Native FL automation clips.
- Mixer insert fader values (template has no params for empty inserts).
- Bit-exact BandLab DSP, AutoPitch, Drum Machine.
- Automatic insertion of the VST3 into FL mixer slots.

"""Standard MIDI export used as a portable fallback for the arrangement."""

from __future__ import annotations

from pathlib import Path

import mido

from .model import Project

PPQ = 480


def export_midi(project: Project, output: Path) -> Path:
    midi = mido.MidiFile(ticks_per_beat=PPQ)
    conductor = mido.MidiTrack()
    conductor.append(mido.MetaMessage("track_name", name=project.name, time=0))
    conductor.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(project.bpm), time=0))
    conductor.append(
        mido.MetaMessage(
            "time_signature",
            numerator=project.time_signature[0],
            denominator=project.time_signature[1],
            time=0,
        )
    )
    midi.tracks.append(conductor)

    def ticks(seconds: float) -> int:
        return max(0, int(round(seconds * project.bpm / 60.0 * PPQ)))

    for track in project.tracks:
        if not any(clip.notes for clip in track.clips):
            continue
        midi_track = mido.MidiTrack()
        midi_track.append(mido.MetaMessage("track_name", name=track.name, time=0))
        events: list[tuple[int, int, mido.Message]] = []
        for clip in track.clips:
            for note in clip.notes:
                start = ticks(clip.start_sec + note.start_sec)
                end = start + max(1, ticks(note.duration_sec))
                events.append(
                    (
                        start,
                        1,
                        mido.Message("note_on", note=note.pitch, velocity=note.velocity, time=0),
                    )
                )
                events.append(
                    (
                        end,
                        0,
                        mido.Message("note_off", note=note.pitch, velocity=0, time=0),
                    )
                )
        events.sort(key=lambda item: (item[0], item[1]))
        last = 0
        for position, _, message in events:
            message.time = max(0, position - last)
            last = position
            midi_track.append(message)
        midi.tracks.append(midi_track)

    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    midi.save(output)
    return output

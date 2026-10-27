"""Build a native FL Studio project from the intermediate model.

The writer mutates a real FL Studio template instead of synthesising the TLV
stream from scratch.  Two format details matter for FL Studio 2024+:

* playlist items are 88-byte records (the legacy pyflp layout is 60 bytes),
* patterns are stored as a ``New``/``Name``/``Length``/``Notes`` event group
  before the channel rack.

Anything that cannot be represented faithfully is reported instead of being
silently dropped.
"""

from __future__ import annotations

import copy
import struct
from dataclasses import dataclass
from pathlib import Path

from pyflp import U16Event, U32Event, UnicodeEvent, UnknownDataEvent, parse, save
from pyflp._events import EventTree, I8Event, IndexedEvent
from pyflp.arrangement import ArrangementID
from pyflp.channel import ChannelID
from pyflp.pattern import NotesEvent, PatternID, _NoteFlags

from .model import Clip, Project, Report, Track

PPQ_DEFAULT = 96
PATTERN_BASE = 20480
MAX_PLAYLIST_TRACKS = 500


@dataclass
class _BuiltClip:
    clip: Clip
    track_index: int
    channel_iid: int
    pattern_iid: int | None


def _text_event(event_id, value: str) -> UnicodeEvent:
    event = UnicodeEvent(event_id, b"")
    event.value = value
    return event


def _label(track_name: str, clip_name: str) -> str:
    if clip_name.lower().startswith(track_name.lower()):
        return clip_name
    return f"{track_name} - {clip_name}"


def _note_payload(*, position: int, rack_channel: int, length: int, key: int, pan: int, velocity: int) -> dict:
    return {
        "position": max(0, position),
        "flags": _NoteFlags(16384),
        "rack_channel": rack_channel,
        "length": max(1, length),
        "key": max(0, min(131, key)),
        "group": 0,
        "fine_pitch": 120,
        "_u1": 0,
        "release": 0,
        "midi_channel": 0,
        "pan": max(0, min(128, pan)),
        "velocity": max(1, min(127, velocity)),
        "mod_x": 128,
        "mod_y": 128,
    }


def _playlist_record(
    *,
    position: int,
    item_index: int,
    length: int,
    track_rvidx: int,
    uid: int,
    start_offset: float,
    end_offset: float,
    audio: bool,
) -> bytes:
    record = bytearray(88)
    struct.pack_into("<I", record, 0, max(0, position))
    struct.pack_into("<H", record, 4, PATTERN_BASE)
    struct.pack_into("<H", record, 6, item_index)
    struct.pack_into("<I", record, 8, max(1, length))
    struct.pack_into("<H", record, 12, track_rvidx)
    struct.pack_into("<H", record, 14, 0)
    record[16:18] = b"\x78\x00"
    struct.pack_into("<H", record, 18, 64)
    record[20:24] = b"\x40\x64\x80\x80"
    struct.pack_into("<f", record, 24, start_offset)
    struct.pack_into("<f", record, 28, end_offset)
    struct.pack_into("<I", record, 32, uid)
    if audio:
        # FL Studio writes 1.0 in this audio-only field for untrimmed clips.
        struct.pack_into("<f", record, 52, 1.0)
    struct.pack_into("<f", record, 68, 1.875)
    struct.pack_into("<i", record, 76, -1)
    return bytes(record)


class FlpBuilder:
    def __init__(self, template: Path):
        self.template = Path(template)
        if not self.template.is_file():
            raise FileNotFoundError(f"FL Studio template not found: {self.template}")

    def build(self, project: Project, output: Path, state_dir: Path | None = None) -> Report:
        report = Report()
        flp = parse(str(self.template))
        ppq = flp.ppq or PPQ_DEFAULT
        events = list(flp.events)

        first_channel = self._first_index(events, ChannelID.New)
        if first_channel is None:
            raise ValueError("Template contains no channel rack data")
        arrangement_start = self._first_index(events, ArrangementID.New, start=first_channel)
        if arrangement_start is None:
            raise ValueError("Template contains no arrangement data")

        header = [e for e in events[:first_channel] if not isinstance(e.id, PatternID)]
        channel_events = events[first_channel:arrangement_start]
        rest = events[arrangement_start:]

        prototype = self._first_channel_block(channel_events)
        if prototype is None:
            raise ValueError("Template contains no sampler channel to clone")

        blocks, built = self._build_channels(project, prototype)
        pattern_events = self._build_patterns(project, built, ppq, report)

        playlist_payload = self._build_playlist(project, built, ppq, report)
        rest = self._replace_playlist(rest, playlist_payload)
        header, rest = self._set_project_metadata(header, rest, project)

        ordered = header + pattern_events + [e for block in blocks for e in block] + rest
        flp.events = EventTree(init=(IndexedEvent(i, event) for i, event in enumerate(ordered)))

        self._apply_channel_settings(flp, built, report)

        output = Path(output)
        output.parent.mkdir(parents=True, exist_ok=True)
        save(flp, str(output))

        if state_dir is not None:
            self._write_state_sidecars(built, state_dir, report)

        report.stats.update(
            {
                "tracks": len(project.tracks),
                "channels": len(built["channels"]),
                "patterns": len(built["patterns"]),
                "clips": len(built["clips"]),
                "playlist_items": len(built["playlist"]),
            }
        )
        return report

    # ------------------------------------------------------------------ layout

    @staticmethod
    def _first_index(events, event_id, start: int = 0):
        for i in range(start, len(events)):
            if events[i].id == event_id:
                return i
        return None

    @staticmethod
    def _first_channel_block(events):
        blocks = []
        current = []
        for event in events:
            if event.id == ChannelID.New:
                if current:
                    blocks.append(current)
                current = [event]
            elif current:
                current.append(event)
        if current:
            blocks.append(current)
        return copy.deepcopy(blocks[0]) if blocks else None

    # ------------------------------------------------------------------ build

    def _build_channels(self, project: Project, prototype: list):
        blocks: list[list] = []
        built = {"channels": [], "clips": [], "patterns": [], "playlist": []}
        channel_iid = 0

        for track_index, track in enumerate(project.tracks):
            if track.kind == "audio":
                for clip in track.clips:
                    blocks.append(
                        self._clone_channel(
                            prototype, channel_iid, _label(track.name, clip.name), clip.audio_path
                        )
                    )
                    built["channels"].append(
                        {"iid": channel_iid, "track": track, "track_index": track_index, "clip": clip}
                    )
                    built["clips"].append(
                        _BuiltClip(clip, track_index, channel_iid, None)
                    )
                    channel_iid += 1
            else:
                blocks.append(self._clone_channel(prototype, channel_iid, track.name, None))
                built["channels"].append(
                    {"iid": channel_iid, "track": track, "track_index": track_index, "clip": None}
                )
                for clip in track.clips:
                    pattern_iid = len(built["patterns"]) + 1
                    built["patterns"].append(
                        {"iid": pattern_iid, "clip": clip, "track": track, "channel_iid": channel_iid}
                    )
                    built["clips"].append(
                        _BuiltClip(clip, track_index, channel_iid, pattern_iid)
                    )
                channel_iid += 1

        return blocks, built

    @staticmethod
    def _clone_channel(prototype: list, iid: int, name: str, sample: Path | None) -> list:
        block = []
        for event in prototype:
            clone = copy.deepcopy(event)
            if clone.id == ChannelID.New:
                clone.value = iid
            if clone.id.value == 203:  # PluginID.Name
                clone.value = name
            block.append(clone)

        sample_event = next((e for e in block if e.id == ChannelID.SamplePath), None)
        if sample_event is None:
            sample_event = UnicodeEvent(ChannelID.SamplePath, b"")
            block.append(sample_event)
        sample_event.value = str(sample) if sample else ""

        if all(e.id != ChannelID.RoutedTo for e in block):
            block.append(I8Event(ChannelID.RoutedTo, b"\x00"))
        return block

    def _build_patterns(self, project: Project, built: dict, ppq: int, report: Report) -> list:
        events = []
        for entry in built["patterns"]:
            clip: Clip = entry["clip"]
            pattern_iid = entry["iid"]
            new_event = U16Event(PatternID.New, b"\x00\x00")
            new_event.value = pattern_iid
            events.append(new_event)
            events.append(_text_event(PatternID.Name, _label(entry["track"].name, clip.name)))

            length_ticks = max(1, self._ticks(clip.duration_sec, project.bpm, ppq))
            length_event = U32Event(PatternID.Length, b"\x00\x00\x00\x00")
            length_event.value = length_ticks
            events.append(length_event)

            if clip.notes:
                notes_event = NotesEvent(PatternID.Notes, b"\x00" * 24)
                payload = [
                    _note_payload(
                        position=self._ticks(note.start_sec, project.bpm, ppq),
                        rack_channel=entry["channel_iid"],
                        length=self._ticks(note.duration_sec, project.bpm, ppq),
                        key=note.pitch,
                        pan=64,
                        velocity=note.velocity,
                    )
                    for note in clip.notes
                ]
                notes_event[0] = payload[0]
                for item in payload[1:]:
                    notes_event.append(item)
                events.append(notes_event)
            else:
                report.warn("empty-pattern", f"Pattern '{clip.name}' has no notes")
        return events

    def _build_playlist(self, project: Project, built: dict, ppq: int, report: Report) -> bytes:
        records = []
        uid = 1
        for item in built["clips"]:
            if item.track_index >= MAX_PLAYLIST_TRACKS:
                report.warn(
                    "playlist-track-overflow",
                    f"Track '{built['channels'][item.channel_iid]['track'].name}' is beyond the 500-track limit",
                )
                continue
            clip = item.clip
            position = self._ticks(clip.start_sec, project.bpm, ppq)
            length = max(1, self._ticks(clip.duration_sec, project.bpm, ppq))
            audio = item.pattern_iid is None
            item_index = item.channel_iid if audio else PATTERN_BASE + item.pattern_iid
            start_offset, end_offset = self._offsets(clip, audio)
            records.append(
                _playlist_record(
                    position=position,
                    item_index=item_index,
                    length=length,
                    track_rvidx=MAX_PLAYLIST_TRACKS - 1 - item.track_index,
                    uid=uid,
                    start_offset=start_offset,
                    end_offset=end_offset,
                    audio=audio,
                )
            )
            uid += 1
        if not records:
            report.warn("empty-playlist", "No clips were placed on the playlist")
        built["playlist"] = records
        return b"".join(records)

    @staticmethod
    def _offsets(clip: Clip, audio: bool) -> tuple[float, float]:
        if not audio or clip.offset_sec <= 0.0001:
            return (-1.0, -1.0)
        return (float(clip.offset_sec), -1.0)

    @staticmethod
    def _replace_playlist(rest: list, payload: bytes) -> list:
        if not payload:
            return rest
        result = []
        replaced = False
        for event in rest:
            if event.id == ArrangementID.Playlist:
                result.append(UnknownDataEvent(ArrangementID.Playlist, payload))
                replaced = True
            else:
                result.append(event)
        if not replaced:
            raise ValueError("Template contains no playlist event")
        return result

    @staticmethod
    def _set_project_metadata(header: list, rest: list, project: Project):
        for event in header + rest:
            value = event.id.value
            if value == 156:
                event.value = int(round(project.bpm * 1000))
            elif value == 194:
                event.value = project.name
            elif value == 195:
                event.value = "Converted from BandLab by BL2FLP"
            elif value == 17:
                event.value = project.time_signature[0]
            elif value == 18:
                event.value = project.time_signature[1]
        return header, rest

    def _apply_channel_settings(self, flp, built: dict, report: Report) -> None:
        max_insert = 16
        try:
            max_insert = max(1, len(flp.mixer) - 2)
        except Exception:
            pass

        for entry in built["channels"]:
            iid = entry["iid"]
            track: Track = entry["track"]
            try:
                channel = flp.channels[iid]
            except Exception:
                continue

            channel.volume = max(0, min(12800, int(round(track.volume * 12800))))
            channel.pan = max(0, min(12800, int(round(6400 + track.pan * 6400))))
            channel.enabled = not track.muted

            routed_event = next(iter(channel.events.get(ChannelID.RoutedTo)), None)
            if routed_event is not None:
                routed_event.value = min(entry["track_index"] + 1, max_insert)

        seen_tracks = set()
        for entry in built["channels"]:
            track_index = entry["track_index"]
            if track_index in seen_tracks:
                continue
            seen_tracks.add(track_index)
            if track_index + 1 > max_insert:
                report.warn(
                    "insert-overflow",
                    f"Track '{entry['track'].name}' routed to insert {max_insert}; "
                    f"template exposes {max_insert} inserts",
                )

    def _write_state_sidecars(self, built: dict, state_dir: Path, report: Report) -> None:
        from .vststate import build_state

        state_dir = Path(state_dir)
        state_dir.mkdir(parents=True, exist_ok=True)
        written = {}
        for entry in built["channels"]:
            track: Track = entry["track"]
            written.setdefault(id(track), (entry["track_index"], track))
        for track_index, track in written.values():
            safe = "".join(c if c.isalnum() else "_" for c in track.name).strip("_") or f"track{track_index}"
            (state_dir / f"{track_index + 1:02d}_{safe}.blwb").write_bytes(build_state(track.effects))
        report.stats["vst_states"] = len(written)

    @staticmethod
    def _ticks(seconds: float, bpm: float, ppq: int) -> int:
        return max(0, int(round((seconds / 60.0) * bpm * ppq)))

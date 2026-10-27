"""Command line interface."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .pipeline import convert, find_template


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bl2flp",
        description="Convert a BandLab revision manifest into an FL Studio project.",
    )
    parser.add_argument("revision", nargs="?", help="revision JSON or ZIP exported from BandLab")
    parser.add_argument("output", nargs="?", help="destination .flp file")
    parser.add_argument("--assets", help="folder with the project's audio samples")
    parser.add_argument("--template", help="FL Studio template .flp (default: installed Empty.flp)")
    parser.add_argument(
        "--positions",
        choices=("auto", "seconds", "ticks"),
        default="auto",
        help="unit used by clip/note positions (default: auto)",
    )
    parser.add_argument("--no-midi", action="store_true", help="do not write the MIDI fallback")
    parser.add_argument("--no-states", action="store_true", help="do not write .blwb state files")
    parser.add_argument("--show-template", action="store_true", help="print the detected template and exit")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.show_template:
        print(find_template(args.template))
        return 0

    if not args.revision or not args.output:
        parser.error("revision and output are required")

    try:
        summary = convert(
            args.revision,
            args.output,
            assets=args.assets,
            template=args.template,
            positions=args.positions,
            export_midi_file=not args.no_midi,
            write_states=not args.no_states,
        )
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    stats = summary["stats"]
    print(f"FLP:      {summary['output']}")
    print(f"Template: {summary['template']}")
    print(
        "Content:  {tracks} tracks, {channels} channels, {patterns} patterns, {playlist_items} playlist items".format(
            **{key: stats.get(key, 0) for key in ("tracks", "channels", "patterns", "playlist_items")}
        )
    )
    if summary["midi"]:
        print(f"MIDI:     {summary['midi']}")
    if summary["states"]:
        print(f"States:   {summary['states']}")
    for warning in summary["warnings"]:
        print(f"warning[{warning['code']}]: {warning['message']}")
    print(f"Report:   {summary['report']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

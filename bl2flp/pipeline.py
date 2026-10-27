"""End-to-end conversion pipeline."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from .bandlab import load_revision, parse_project
from .flp import FlpBuilder
from .midi import export_midi
from .model import Project, Report

TEMPLATE_CANDIDATES = (
    Path(r"C:\Program Files\Image-Line\FL Studio 2026\Data\System\Empty.flp"),
    Path(r"C:\Program Files\Image-Line\FL Studio 2026\Data\Templates\Minimal\Empty\Empty.flp"),
    Path(r"C:\Program Files\Image-Line\FL Studio 2025\Data\System\Empty.flp"),
    Path(r"C:\Program Files\Image-Line\FL Studio 2024\Data\System\Empty.flp"),
    Path(r"C:\Program Files\Image-Line\FL Studio 21\Data\System\Empty.flp"),
    Path(r"C:\Program Files\Image-Line\FL Studio 20\Data\System\Empty.flp"),
)


def find_template(explicit: str | Path | None = None) -> Path:
    if explicit:
        path = Path(explicit)
        if not path.is_file():
            raise FileNotFoundError(f"Template not found: {path}")
        return path

    env = os.environ.get("BL2FLP_TEMPLATE")
    if env and Path(env).is_file():
        return Path(env)

    local = Path("EmptyTemplate.flp")
    if local.is_file():
        return local.resolve()

    for candidate in TEMPLATE_CANDIDATES:
        if candidate.is_file():
            return candidate

    for base in (Path(r"C:\Program Files\Image-Line"), Path(r"C:\Program Files (x86)\Image-Line")):
        if base.is_dir():
            for candidate in sorted(base.glob("FL Studio*/Data/System/Empty.flp"), reverse=True):
                return candidate
    raise FileNotFoundError(
        "No FL Studio Empty.flp template found. Pass --template or set BL2FLP_TEMPLATE."
    )


def convert(
    revision: str | Path,
    output: str | Path,
    *,
    assets: str | Path | None = None,
    template: str | Path | None = None,
    positions: str = "auto",
    export_midi_file: bool = True,
    write_states: bool = True,
) -> dict:
    revision_path = Path(revision)
    output_path = Path(output)
    if not revision_path.is_file():
        raise FileNotFoundError(f"Revision manifest not found: {revision_path}")

    template_path = find_template(template)
    extracted_root = None
    try:
        data, assets_dir, extracted_root = load_revision(revision_path)
        if assets:
            assets_dir = Path(assets)
        if not assets_dir.is_dir():
            raise FileNotFoundError(f"Assets directory not found: {assets_dir}")

        project, report = parse_project(data, assets_dir, positions=positions)
        project.source = revision_path

        builder = FlpBuilder(template_path)
        state_dir = output_path.parent / "bl_vst_states" if write_states else None
        build_report = builder.build(project, output_path, state_dir=state_dir)
        report.warnings.extend(build_report.warnings)
        report.stats.update(build_report.stats)

        midi_path = None
        if export_midi_file:
            midi_path = export_midi(project, output_path.with_suffix(".mid"))
            report.stats["midi_file"] = 1

        summary = {
            "output": str(output_path),
            "template": str(template_path),
            "midi": str(midi_path) if midi_path else None,
            "states": str(state_dir) if state_dir else None,
            "stats": report.stats,
            "warnings": [{"code": w.code, "message": w.message} for w in report.warnings],
        }
        report_path = output_path.with_suffix(".report.json")
        report_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
        summary["report"] = str(report_path)
        return summary
    finally:
        if extracted_root is not None:
            shutil.rmtree(extracted_root, ignore_errors=True)

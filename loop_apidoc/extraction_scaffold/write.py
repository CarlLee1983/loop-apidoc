"""The extraction scaffold's sole write-side I/O boundary."""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from loop_apidoc.extraction_scaffold.collect import ExtractionScaffoldInputError
from loop_apidoc.extraction_scaffold.models import ScaffoldBundle


_README = """# Extraction scaffold (non-authoritative)

This directory is a deterministic aid built from explicitly structured Markdown facts.
It is not the --extraction argument for `verify-extraction` or `assemble`.

Copy `inventory.json` and the files in `endpoints/` into the real extraction workdir,
then review every cited source section. Fill security schemes, endpoint tags/security,
integration.json when applicable, and every item in `missing` before verification.
Never treat omitted values as permission to infer API conventions.
"""


def write_scaffold(bundle: ScaffoldBundle, output_dir: Path) -> None:
    """Write a complete scaffold tree without overwriting non-empty output."""
    _check_output_collision(output_dir)
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.", dir=output_dir.parent))
    try:
        _write_bundle_tree(bundle, temporary)
        if output_dir.exists():
            output_dir.rmdir()
        temporary.rename(output_dir)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def _check_output_collision(output_dir: Path) -> None:
    if not output_dir.exists():
        return
    if not output_dir.is_dir() or any(output_dir.iterdir()):
        raise ExtractionScaffoldInputError(f"output already exists: {output_dir}")


def _write_bundle_tree(bundle: ScaffoldBundle, destination: Path) -> None:
    endpoints_dir = destination / "endpoints"
    endpoints_dir.mkdir()
    _write_json(destination / "inventory.json", bundle.inventory)
    _write_json(destination / "scaffold-report.json", bundle.report)
    for endpoint in bundle.endpoints:
        _write_json(endpoints_dir / endpoint.filename, endpoint.body)
    (destination / "README.md").write_text(_README, encoding="utf-8")


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


__all__ = ["ExtractionScaffoldInputError", "write_scaffold"]

from __future__ import annotations

from pathlib import Path

import pytest

from loop_apidoc.foundry import importer, paths, register
from loop_apidoc.foundry.models import Docset, FoundryInputError
from tests.foundry._fixtures import write_run_dir

_RUN_ID = "20260702T120000.000000Z"


def _register(tmp_path: Path) -> None:
    register.register_docset(
        tmp_path,
        Docset(docset_id="tappay-backend", title="T", provider="tappay", product="backend-api"),
    )


def test_import_copies_run_into_candidate(tmp_path: Path) -> None:
    _register(tmp_path)
    run_dir = write_run_dir(tmp_path / "output" / _RUN_ID)

    result = importer.import_run(tmp_path, "tappay-backend", run_dir)

    assert result.run_id == _RUN_ID
    dest = paths.candidate_dir(tmp_path, "tappay-backend", _RUN_ID)
    assert result.candidate_dir == dest
    assert (dest / "openapi.yaml").is_file()
    assert (dest / "validation" / "report.json").is_file()
    assert (dest / "handoff" / "sdk-hints.json").is_file()


def test_import_missing_docset_raises(tmp_path: Path) -> None:
    run_dir = write_run_dir(tmp_path / "output" / _RUN_ID)
    with pytest.raises(FoundryInputError, match="docset.json"):
        importer.import_run(tmp_path, "nope", run_dir)


def test_import_incomplete_run_raises(tmp_path: Path) -> None:
    _register(tmp_path)
    run_dir = write_run_dir(tmp_path / "output" / _RUN_ID)
    (run_dir / "openapi.yaml").unlink()
    with pytest.raises(FoundryInputError, match="openapi.yaml"):
        importer.import_run(tmp_path, "tappay-backend", run_dir)


def test_import_duplicate_candidate_raises_without_overwrite(tmp_path: Path) -> None:
    _register(tmp_path)
    run_dir = write_run_dir(tmp_path / "output" / _RUN_ID)
    importer.import_run(tmp_path, "tappay-backend", run_dir)
    with pytest.raises(FoundryInputError, match="candidate already exists"):
        importer.import_run(tmp_path, "tappay-backend", run_dir)


def test_import_overwrite_replaces_candidate(tmp_path: Path) -> None:
    _register(tmp_path)
    run_dir = write_run_dir(tmp_path / "output" / _RUN_ID)
    importer.import_run(tmp_path, "tappay-backend", run_dir)
    result = importer.import_run(tmp_path, "tappay-backend", run_dir, overwrite=True)
    assert result.candidate_dir.is_dir()

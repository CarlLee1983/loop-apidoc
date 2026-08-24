from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

import pytest

import loop_apidoc.atomic_publish as atomic_publish
from loop_apidoc.agentcli import assemble as assemble_mod
from loop_apidoc.descriptor_output import DescriptorOutputError, DescriptorOutputPath
from loop_apidoc.shadow.models import ArchitectureMode
from tests.source_quality_support import write_passing_source_quality


def _write_extraction(extraction_dir: Path) -> None:
    extraction_dir.mkdir(parents=True)
    (extraction_dir / "inventory.json").write_text(
        json.dumps(
            {
                "overview": "Demo API",
                "environments": [
                    {
                        "name": "prod",
                        "base_url": "https://api.example.com",
                        "version": None,
                        "source": "§1",
                    }
                ],
                "security_schemes": [],
                "endpoints": [
                    {
                        "method": "GET",
                        "path": "/ping",
                        "summary": "健康檢查",
                        "source": "§2",
                    }
                ],
                "schemas": [],
                "errors": [],
                "operational": [],
                "missing": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    endpoints = extraction_dir / "endpoints"
    endpoints.mkdir()
    (endpoints / "ep0.json").write_text(
        json.dumps(
            {
                "method": "GET",
                "path": "/ping",
                "parameters": [],
                "request": None,
                "responses": [
                    {"status": "200", "description": "OK", "schema": None}
                ],
                "examples": [],
                "missing": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _assemble_kwargs(tmp_path: Path, run_id: str) -> dict[str, object]:
    extraction_dir = tmp_path / "extraction"
    _write_extraction(extraction_dir)
    sources_root = tmp_path / "sources"
    sources_root.mkdir()
    (sources_root / "manual.md").write_text(
        "# Demo API\nGET /ping", encoding="utf-8"
    )
    generated_at = datetime(2026, 8, 24, tzinfo=timezone.utc)
    return {
        "sources_root": sources_root,
        "extraction_dir": extraction_dir,
        "output_root": tmp_path / "out",
        "run_id": run_id,
        "generated_at": generated_at,
        "source_quality_dir": write_passing_source_quality(
            sources_root=sources_root,
            output=tmp_path / "source-quality",
            generated_at=generated_at,
        ),
        "urls": [],
    }


def test_assemble_rejects_a_staging_directory_replaced_before_publish(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The completed run must retain the identity of the stage we assembled."""
    kwargs = _assemble_kwargs(tmp_path, "run-stage-replaced")
    output_root = kwargs["output_root"]
    assert isinstance(output_root, Path)
    original_publish = assemble_mod.publish_directory_noreplace
    replacement: dict[str, Path] = {}

    def replace_staging_then_publish(
        staging: Path, destination: Path, **kwargs: object
    ) -> None:
        staging_path = output_root / staging
        moved_stage = staging_path.with_name(f"{staging_path.name}.moved")
        staging_path.rename(moved_stage)
        staging_path.mkdir()
        foreign_file = staging_path / "foreign.txt"
        foreign_file.write_text("must not publish", encoding="utf-8")
        replacement.update({"moved_stage": moved_stage, "foreign_file": foreign_file})
        original_publish(staging, destination, **kwargs)

    monkeypatch.setattr(
        assemble_mod, "publish_directory_noreplace", replace_staging_then_publish
    )

    with pytest.raises(RuntimeError, match="run 目錄發佈失敗"):
        assemble_mod.run_assemble_pipeline(**kwargs)

    assert not (output_root / "run-stage-replaced").exists()
    assert replacement["moved_stage"].is_dir()
    assert replacement["foreign_file"].read_text(encoding="utf-8") == "must not publish"


def test_assemble_never_writes_through_a_stage_name_replaced_after_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The held stage descriptor, not its mutable name, owns every run write."""
    kwargs = _assemble_kwargs(tmp_path, "run-stage-write-replaced")
    output_root = kwargs["output_root"]
    assert isinstance(output_root, Path)
    outside = tmp_path / "outside"
    outside.mkdir()
    original_open = atomic_publish.open_directory_relative
    replacement: dict[str, Path] = {}

    def open_stage_then_replace(parent_fd: int, name: str, label: str) -> int:
        descriptor = original_open(parent_fd, name, label)
        staging_path = output_root / name
        moved_stage = staging_path.with_name(f"{staging_path.name}.moved")
        staging_path.rename(moved_stage)
        staging_path.symlink_to(outside, target_is_directory=True)
        replacement.update({"moved_stage": moved_stage, "symlink": staging_path})
        return descriptor

    monkeypatch.setattr(atomic_publish, "open_directory_relative", open_stage_then_replace)

    with pytest.raises(RuntimeError, match="run 目錄發佈失敗"):
        assemble_mod.run_assemble_pipeline(**kwargs)

    assert replacement["moved_stage"].is_dir()
    assert replacement["symlink"].is_symlink()
    assert not (outside / "manifest.json").exists()


def test_assemble_rejects_a_stage_replaced_before_it_is_opened(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The descriptor opened for a new stage must match mkdirat's inode."""
    kwargs = _assemble_kwargs(tmp_path, "run-stage-preopen-replaced")
    output_root = kwargs["output_root"]
    assert isinstance(output_root, Path)
    original_open = atomic_publish.open_directory_relative
    replacement: dict[str, Path] = {}

    def replace_before_open(parent_fd: int, name: str, label: str) -> int:
        staging_path = output_root / name
        moved_stage = staging_path.with_name(f"{staging_path.name}.moved")
        staging_path.rename(moved_stage)
        staging_path.mkdir()
        foreign_file = staging_path / "foreign.txt"
        foreign_file.write_text("must not become a stage", encoding="utf-8")
        replacement.update({"moved_stage": moved_stage, "foreign_file": foreign_file})
        return original_open(parent_fd, name, label)

    monkeypatch.setattr(atomic_publish, "open_directory_relative", replace_before_open)

    with pytest.raises(RuntimeError, match="run 暫存目錄建立失敗"):
        assemble_mod.run_assemble_pipeline(**kwargs)

    assert not (output_root / "run-stage-preopen-replaced").exists()
    assert replacement["moved_stage"].is_dir()
    assert replacement["foreign_file"].read_text(encoding="utf-8") == "must not become a stage"


def test_assemble_never_uses_process_cwd_for_stage_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A caller thread changing cwd cannot redirect a held stage's artifacts."""
    kwargs = _assemble_kwargs(tmp_path, "run-cwd-replaced")
    outside = tmp_path / "outside"
    outside.mkdir()
    original_write_text = DescriptorOutputPath.write_text
    changed = False

    def change_cwd_before_first_write(
        self: DescriptorOutputPath, *args: object, **kwargs: object
    ) -> int:
        nonlocal changed
        if not changed:
            changed = True
            worker = threading.Thread(target=os.chdir, args=(outside,))
            worker.start()
            worker.join()
        return original_write_text(self, *args, **kwargs)

    monkeypatch.setattr(
        DescriptorOutputPath, "write_text", change_cwd_before_first_write
    )
    original_cwd = Path.cwd()
    try:
        result = assemble_mod.run_assemble_pipeline(**kwargs)
    finally:
        os.chdir(original_cwd)

    assert not (outside / "manifest.json").exists()
    assert (Path(result.run_dir) / "manifest.json").is_file()


def test_assemble_rejects_a_hardlinked_stage_leaf_without_mutating_its_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A pre-existing hard link must abort, never be opened for replacement."""
    kwargs = _assemble_kwargs(tmp_path, "run-hardlink-leaf")
    output_root = kwargs["output_root"]
    assert isinstance(output_root, Path)
    outside = tmp_path / "outside.txt"
    outside.write_text("must remain unchanged", encoding="utf-8")
    original_write_text = DescriptorOutputPath.write_text
    injected = False

    def link_before_manifest_write(
        self: DescriptorOutputPath, *args: object, **kwargs: object
    ) -> int:
        nonlocal injected
        if not injected and self.name == "manifest.json":
            injected = True
            parent_fd, leaf = self._open_leaf_parent()
            try:
                os.link(outside, leaf, dst_dir_fd=parent_fd)
            finally:
                os.close(parent_fd)
        return original_write_text(self, *args, **kwargs)

    monkeypatch.setattr(DescriptorOutputPath, "write_text", link_before_manifest_write)

    with pytest.raises(DescriptorOutputError, match="output leaf already exists"):
        assemble_mod.run_assemble_pipeline(**kwargs)

    assert outside.read_text(encoding="utf-8") == "must remain unchanged"
    assert not (output_root / "run-hardlink-leaf").exists()


@pytest.mark.parametrize(
    "architecture_mode", [ArchitectureMode.SHADOW, ArchitectureMode.STRICT]
)
def test_assemble_never_writes_architecture_sidecars_through_a_replaced_stage_name(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    architecture_mode: ArchitectureMode,
) -> None:
    """Shadow and strict sidecars remain below the descriptor-held stage."""
    kwargs = _assemble_kwargs(tmp_path, f"run-{architecture_mode.value}-stage-swap")
    kwargs["architecture_mode"] = architecture_mode
    output_root = kwargs["output_root"]
    assert isinstance(output_root, Path)
    outside = tmp_path / "outside"
    outside.mkdir()
    original_open = atomic_publish.open_directory_relative

    def open_stage_then_replace(parent_fd: int, name: str, label: str) -> int:
        descriptor = original_open(parent_fd, name, label)
        staging_path = output_root / name
        staging_path.rename(staging_path.with_name(f"{staging_path.name}.moved"))
        staging_path.symlink_to(outside, target_is_directory=True)
        return descriptor

    monkeypatch.setattr(atomic_publish, "open_directory_relative", open_stage_then_replace)

    with pytest.raises(RuntimeError, match="run 目錄發佈失敗"):
        assemble_mod.run_assemble_pipeline(**kwargs)

    assert not (outside / "core").exists()


@pytest.mark.parametrize(
    "architecture_mode", [ArchitectureMode.SHADOW, ArchitectureMode.STRICT]
)
def test_assemble_rejects_a_replaced_core_directory_before_sidecar_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    architecture_mode: ArchitectureMode,
) -> None:
    """Core sidecars reopen only the directory inode created by the stage."""
    kwargs = _assemble_kwargs(tmp_path, f"run-{architecture_mode.value}-core-swap")
    kwargs["architecture_mode"] = architecture_mode
    outside = tmp_path / "outside"
    outside.mkdir()
    original_mkdir = DescriptorOutputPath.mkdir
    swapped = False

    def replace_core_after_creation(
        self: DescriptorOutputPath, *args: object, **kwargs: object
    ) -> None:
        nonlocal swapped
        original_mkdir(self, *args, **kwargs)
        if not swapped and self._parts == ("core",):
            swapped = True
            parent_fd = self.parent._open_directory(self.parent._parts, create=False)
            try:
                os.rename(
                    self.name,
                    ".core-moved",
                    src_dir_fd=parent_fd,
                    dst_dir_fd=parent_fd,
                )
                os.symlink(outside, self.name, target_is_directory=True, dir_fd=parent_fd)
            finally:
                os.close(parent_fd)

    monkeypatch.setattr(DescriptorOutputPath, "mkdir", replace_core_after_creation)

    with pytest.raises(DescriptorOutputError, match="output (directory|stage namespace)"):
        assemble_mod.run_assemble_pipeline(**kwargs)

    assert not (outside / "error.json").exists()
    assert not (outside / "execution.json").exists()


def test_assemble_quarantines_a_foreign_stage_published_during_rename(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An identity mismatch after rename cannot occupy the canonical run name."""
    kwargs = _assemble_kwargs(tmp_path, "run-publish-swap")
    output_root = kwargs["output_root"]
    assert isinstance(output_root, Path)
    original_rename = atomic_publish.rename_directory_noreplace
    replacement: dict[str, Path] = {}
    swapped = False

    def replace_source_inside_rename(parent_fd: int, source: bytes, destination: bytes) -> None:
        nonlocal swapped
        if not swapped:
            swapped = True
            stage = output_root / os.fsdecode(source)
            moved_stage = stage.with_name(f"{stage.name}.moved")
            stage.rename(moved_stage)
            stage.mkdir()
            foreign_file = stage / "foreign.txt"
            foreign_file.write_text("must be quarantined", encoding="utf-8")
            replacement.update({"moved_stage": moved_stage, "foreign_file": foreign_file})
        original_rename(parent_fd, source, destination)

    monkeypatch.setattr(
        atomic_publish, "rename_directory_noreplace", replace_source_inside_rename
    )

    with pytest.raises(RuntimeError, match="run 目錄發佈失敗"):
        assemble_mod.run_assemble_pipeline(**kwargs)

    assert not (output_root / "run-publish-swap").exists()
    quarantines = list(output_root.glob(".run-publish-swap-rejected-*"))
    assert len(quarantines) == 1
    assert (quarantines[0] / "foreign.txt").read_text(encoding="utf-8") == "must be quarantined"
    assert replacement["moved_stage"].is_dir()


def test_assemble_quarantines_a_regular_file_substituted_during_rename(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A non-directory substitute cannot retain the canonical run name either."""
    kwargs = _assemble_kwargs(tmp_path, "run-publish-file-swap")
    output_root = kwargs["output_root"]
    assert isinstance(output_root, Path)
    original_rename = atomic_publish.rename_directory_noreplace
    swapped = False

    def replace_source_with_file(parent_fd: int, source: bytes, destination: bytes) -> None:
        nonlocal swapped
        if not swapped:
            swapped = True
            stage = output_root / os.fsdecode(source)
            stage.rename(stage.with_name(f"{stage.name}.moved"))
            stage.write_text("must be quarantined", encoding="utf-8")
        original_rename(parent_fd, source, destination)

    monkeypatch.setattr(
        atomic_publish, "rename_directory_noreplace", replace_source_with_file
    )

    with pytest.raises(RuntimeError, match="run 目錄發佈失敗"):
        assemble_mod.run_assemble_pipeline(**kwargs)

    assert not (output_root / "run-publish-file-swap").exists()
    quarantines = list(output_root.glob(".run-publish-file-swap-rejected-*"))
    assert len(quarantines) == 1
    assert quarantines[0].read_text(encoding="utf-8") == "must be quarantined"


def test_assemble_quarantines_child_content_replaced_after_prepublication_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The post-rename verifier closes the child-swap publication window."""
    kwargs = _assemble_kwargs(tmp_path, "run-child-publish-swap")
    output_root = kwargs["output_root"]
    assert isinstance(output_root, Path)
    original_publish = assemble_mod.publish_directory_noreplace

    def replace_manifest_then_publish(
        staging: Path, destination: Path, **publish_kwargs: object
    ) -> None:
        stage = output_root / staging
        manifest = stage / "manifest.json"
        manifest.rename(stage / ".manifest-original")
        manifest.write_text("foreign manifest", encoding="utf-8")
        original_publish(staging, destination, **publish_kwargs)

    monkeypatch.setattr(
        assemble_mod, "publish_directory_noreplace", replace_manifest_then_publish
    )

    with pytest.raises(RuntimeError, match="run 目錄發佈失敗"):
        assemble_mod.run_assemble_pipeline(**kwargs)

    assert not (output_root / "run-child-publish-swap").exists()
    quarantines = list(output_root.glob(".run-child-publish-swap-rejected-*"))
    assert len(quarantines) == 1
    assert (quarantines[0] / "manifest.json").read_text(encoding="utf-8") == "foreign manifest"


def test_assemble_rejects_an_output_parent_replaced_after_publish(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A returned run path must still name the pinned publication parent."""
    kwargs = _assemble_kwargs(tmp_path, "run-parent-replaced")
    output_root = kwargs["output_root"]
    assert isinstance(output_root, Path)
    original_publish = assemble_mod.publish_directory_noreplace
    foreign_file = output_root / "foreign.txt"

    def publish_then_replace_parent(
        staging: Path, destination: Path, **publish_kwargs: object
    ) -> None:
        original_publish(staging, destination, **publish_kwargs)
        output_root.rename(output_root.with_name("moved-out"))
        output_root.mkdir()
        foreign_file.write_text("must not return", encoding="utf-8")

    monkeypatch.setattr(
        assemble_mod, "publish_directory_noreplace", publish_then_replace_parent
    )

    with pytest.raises(RuntimeError, match="run 目錄發佈失敗"):
        assemble_mod.run_assemble_pipeline(**kwargs)

    assert foreign_file.read_text(encoding="utf-8") == "must not return"

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from typer.testing import CliRunner

from loop_apidoc.cli import app


runner = CliRunner()


def test_import_supplementary_note_writes_source_and_provenance(
    tmp_path: Path,
) -> None:
    """摘錄本身無法驗證,所以出處必須與內容綁在同一個檔案雜湊上 ——
    記下摘錄者是為了可追責,這是這條路徑與其他所有來源的本質差異。"""
    excerpt = tmp_path / "excerpt.md"
    excerpt.write_text(
        "# 測試環境金鑰\n\n沙箱金鑰由窗口另行以工單提供,不在文件中。\n",
        encoding="utf-8",
    )
    sources = tmp_path / "sources"

    result = runner.invoke(
        app,
        [
            "import-supplementary-note",
            "--input",
            str(excerpt),
            "--from",
            "engineer@provider.example",
            "--received-at",
            "2026-08-16T10:00:00+08:00",
            "--subject",
            "測試環境金鑰取得方式",
            "--excerpted-by",
            "carl",
            "--sources",
            str(sources),
        ],
    )

    assert result.exit_code == 0, result.stdout
    written = sources / "excerpt.md"
    assert written.read_bytes() == excerpt.read_bytes()
    digest = hashlib.sha256(excerpt.read_bytes()).hexdigest()
    provenance = json.loads(
        (sources / "excerpt.md.source.json").read_text(encoding="utf-8")
    )
    assert provenance == {
        "schema_version": 1,
        "authority": "supplementary",
        "received_from": "engineer@provider.example",
        "received_at": "2026-08-16T10:00:00+08:00",
        "subject": "測試環境金鑰取得方式",
        "excerpted_by": "carl",
        "imported_sha256": digest,
        "source_file": "excerpt.md",
    }


def _import_note(tmp_path: Path, sources: Path, *, name: str = "excerpt.md") -> None:
    excerpt = tmp_path / f"in-{name}"
    excerpt.write_text("# 補充\n\n沙箱金鑰由窗口另行提供。\n", encoding="utf-8")
    result = runner.invoke(
        app,
        [
            "import-supplementary-note",
            "--input",
            str(excerpt),
            "--from",
            "engineer@provider.example",
            "--received-at",
            "2026-08-16T10:00:00+08:00",
            "--excerpted-by",
            "carl",
            "--sources",
            str(sources),
            "--filename",
            name,
        ],
    )
    assert result.exit_code == 0, result.stdout


def test_manifest_marks_supplementary_sources_and_defaults_to_normative(
    tmp_path: Path,
) -> None:
    """等級與出處是同一件事的兩面 —— 一份東西之所以是次級,正是因為它的
    出處是一封信。寫在同一個檔案裡,兩者就不會各說各話。"""
    sources = tmp_path / "sources"
    sources.mkdir()
    (sources / "manual.md").write_text("# API\n\nGET /ping\n", encoding="utf-8")
    _import_note(tmp_path, sources)

    manifest_path = tmp_path / "manifest.json"
    result = runner.invoke(
        app,
        ["manifest", "--sources", str(sources), "--output", str(manifest_path)],
    )

    assert result.exit_code == 0, result.stdout
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    authority = {
        source["relative_path"]: source["authority"]
        for source in manifest["local_sources"]
        if source["status"] == "pending"
    }
    assert authority == {"excerpt.md": "supplementary", "manual.md": "normative"}


def _invoke(tmp_path: Path, sources: Path, **overrides) -> object:
    excerpt = overrides.pop("input_file", None)
    if excerpt is None:
        excerpt = tmp_path / "excerpt.md"
        if not excerpt.exists():
            excerpt.write_text("# 補充\n\n內容。\n", encoding="utf-8")
    args = {
        "--input": str(excerpt),
        "--from": "engineer@provider.example",
        "--received-at": "2026-08-16T10:00:00+08:00",
        "--excerpted-by": "carl",
        "--sources": str(sources),
    }
    args.update(overrides)
    flat: list[str] = ["import-supplementary-note"]
    for key, value in args.items():
        flat += [key, value]
    return runner.invoke(app, flat)


def test_import_supplementary_note_requires_a_timezone_aware_timestamp(
    tmp_path: Path,
) -> None:
    """沒有時區的時間戳無法排序,出處紀錄就失去了它唯一的用途。"""
    result = _invoke(
        tmp_path, tmp_path / "sources", **{"--received-at": "2026-08-16T10:00:00"}
    )

    assert result.exit_code == 2
    assert "timezone" in result.stderr
    assert not (tmp_path / "sources").exists()


def test_import_supplementary_note_refuses_to_overwrite_existing_evidence(
    tmp_path: Path,
) -> None:
    sources = tmp_path / "sources"
    sources.mkdir()
    (sources / "excerpt.md").write_text("先前的證據\n", encoding="utf-8")

    result = _invoke(tmp_path, sources)

    assert result.exit_code == 2
    assert "already exists" in result.stderr
    assert (sources / "excerpt.md").read_text(encoding="utf-8") == "先前的證據\n"


def test_import_supplementary_note_rejects_a_path_as_filename(tmp_path: Path) -> None:
    result = _invoke(tmp_path, tmp_path / "sources", **{"--filename": "nested/a.md"})

    assert result.exit_code == 2
    assert "single file name" in result.stderr


def test_import_supplementary_note_rejects_non_markdown(tmp_path: Path) -> None:
    """摘錄是人寫的散文與表格,Markdown 是唯一能被 source_facts 掃描的形狀。"""
    excerpt = tmp_path / "excerpt.pdf"
    excerpt.write_bytes(b"%PDF-1.4\n")

    result = _invoke(tmp_path, tmp_path / "sources", input_file=excerpt)

    assert result.exit_code == 2
    assert "Markdown" in result.stderr


def test_import_supplementary_note_requires_an_excerpter(tmp_path: Path) -> None:
    """摘錄無法驗證,只能可追責 —— 沒有署名就連追責都做不到。"""
    result = _invoke(tmp_path, tmp_path / "sources", **{"--excerpted-by": "  "})

    assert result.exit_code == 2
    assert "excerpted_by" in result.stderr


def test_manifest_refuses_a_sidecar_it_cannot_read(tmp_path: Path) -> None:
    """缺席才是 normative,讀不動不是。一個截斷的寫入若被當成正式文件,
    整個功能就被一個壞檔案靜默關掉,而操作者看不到任何差別。"""
    sources = tmp_path / "sources"
    sources.mkdir()
    _import_note(tmp_path, sources)
    (sources / "excerpt.md.source.json").write_text("{broken", encoding="utf-8")

    result = runner.invoke(
        app,
        ["manifest", "--sources", str(sources), "--output", str(tmp_path / "m.json")],
    )

    assert result.exit_code == 2
    assert "sidecar" in result.stderr
    assert not (tmp_path / "m.json").exists()


def test_manifest_refuses_a_sidecar_that_does_not_match_its_source(
    tmp_path: Path,
) -> None:
    """宣告要綁在內容上 —— 否則一個從別處複製來的兩行 sidecar 就能
    把一份正式手冊降級,而降級後的手冊會整份退出新鮮度指紋。"""
    sources = tmp_path / "sources"
    sources.mkdir()
    (sources / "manual.md").write_text("# API\n\nGET /ping\n", encoding="utf-8")
    (sources / "manual.md.source.json").write_text(
        json.dumps({"authority": "supplementary"}), encoding="utf-8"
    )

    result = runner.invoke(
        app,
        ["manifest", "--sources", str(sources), "--output", str(tmp_path / "m.json")],
    )

    assert result.exit_code == 2
    assert "sidecar" in result.stderr


def test_manifest_accepts_a_rendered_url_sidecar_as_normative(tmp_path: Path) -> None:
    """`import-rendered-url` 寫的 provenance 沒有 authority 欄位 —— 那是
    一份已驗證出處的正式文件,不是判定失敗。"""
    sources = tmp_path / "sources"
    sources.mkdir()
    (sources / "page.md").write_text("# API\n\nGET /ping\n", encoding="utf-8")
    (sources / "page.md.source.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "original_url": "https://docs.example.com/a",
                "canonical_url": "https://docs.example.com/a",
                "captured_at": "2026-08-16T10:00:00+08:00",
                "capture_method": "browser_save",
                "imported_sha256": "irrelevant",
                "source_file": "page.md",
            }
        ),
        encoding="utf-8",
    )
    manifest_path = tmp_path / "m.json"

    result = runner.invoke(
        app,
        ["manifest", "--sources", str(sources), "--output", str(manifest_path)],
    )

    assert result.exit_code == 0, result.stdout
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert [
        source["authority"]
        for source in manifest["local_sources"]
        if source["status"] == "pending"
    ] == ["normative"]

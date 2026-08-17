"""次級佐證進入一次真實的 `assemble` 之後會發生什麼。

最危險的交互作用不是新功能本身,而是它對既有 run 的副作用:`sole_source()`
在 manifest 收斂成剛好一份可用文件時,讓沒有定位資訊的引用仍可歸屬,而
`source_violations` 在同一條件下整個跳過。次級佐證若計入文件數,一份原本
只有一份手冊的 run 加進一份信件摘錄之後,會在建立 run 目錄之前就被邊界
拒絕 —— 補充資料反而讓正式文件失去歸屬。
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from tests.focus.support import assemble, setup

_NOTE = "# 補充\n\n沙箱金鑰由窗口另行以工單提供。\n"
_NOTE_SIDECAR = json.dumps(
    {
        "schema_version": 1,
        "authority": "supplementary",
        "received_from": "engineer@provider.example",
        "received_at": "2026-08-16T10:00:00+08:00",
        "excerpted_by": "carl",
        # 讀取端把宣告綁在內容上,所以夾具也得算真的 digest。
        "imported_sha256": hashlib.sha256(_NOTE.encode("utf-8")).hexdigest(),
        "source_file": "note.md",
    },
    ensure_ascii=False,
)


def _cite_by_section(extraction: Path) -> None:
    """把引用改成只指到章節,不指到檔名 —— 這正是靠單一文件歸屬的形狀。"""
    inventory_path = extraction / "inventory.json"
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    for section in ("environments", "endpoints"):
        for entry in inventory.get(section) or []:
            entry["source"] = "第 2 節"
    inventory_path.write_text(
        json.dumps(inventory, ensure_ascii=False), encoding="utf-8"
    )
    for endpoint_file in sorted((extraction / "endpoints").glob("*.json")):
        endpoint = json.loads(endpoint_file.read_text(encoding="utf-8"))
        endpoint["source"] = "第 2 節"
        endpoint_file.write_text(
            json.dumps(endpoint, ensure_ascii=False), encoding="utf-8"
        )


def test_adding_a_supplementary_note_does_not_refuse_the_run_at_the_boundary(
    tmp_path: Path,
) -> None:
    """加一份摘錄不得讓整個 run 在建立目錄前被拒 —— `source_guard` 問的是
    `sole_normative_source()`。但引用歸屬是另一回事:摘錄是第二份文件,
    無法解析的 locator 從此曖昧,只能是 unverified,不能被記成手冊說過。"""
    sources, extraction, _ = setup(
        tmp_path,
        extra_sources={"note.md": _NOTE, "note.md.source.json": _NOTE_SIDECAR},
    )
    _cite_by_section(extraction)

    result = assemble(tmp_path, sources, extraction, None, "--json")

    # exit 2 是邊界拒絕(run 目錄不存在);exit 1 只是驗證 FAIL,產物仍在。
    assert result.exit_code != 2, result.stdout
    payload = json.loads(result.stdout)
    plan = json.loads(
        (Path(payload["run_dir"]) / "plan" / "normalization-plan.json").read_text(
            encoding="utf-8"
        )
    )
    assert [entry["status"] for entry in plan["endpoints"]] == [
        "unverified",
        "unverified",
    ]
    assert [
        entry["citations"][0]["manifest_source"] for entry in plan["endpoints"]
    ] == [None, None]


def test_an_unresolvable_locator_is_never_attributed_to_the_manual(
    tmp_path: Path,
) -> None:
    """一條寫著「供應商信件」的引用被記成 manual.md 支持,正是這整個
    等級區分要防的事 —— 而它會由修正本身重新引進。"""
    sources, extraction, _ = setup(
        tmp_path,
        extra_sources={"note.md": _NOTE, "note.md.source.json": _NOTE_SIDECAR},
    )
    _cite_by_section(extraction)

    result = assemble(tmp_path, sources, extraction, None, "--json")

    payload = json.loads(result.stdout)
    plan = json.loads(
        (Path(payload["run_dir"]) / "plan" / "normalization-plan.json").read_text(
            encoding="utf-8"
        )
    )
    cited = {
        citation["manifest_source"]
        for entry in plan["endpoints"]
        for citation in entry["citations"]
    }
    assert "manual.md" not in cited


def test_a_second_normative_document_still_ends_sole_attribution(
    tmp_path: Path,
) -> None:
    """對照組:排除的是次級佐證,不是「第二份文件」這件事本身。"""
    sources, extraction, _ = setup(
        tmp_path, extra_sources={"second.md": "# 另一份手冊\n\nGET /other\n"}
    )
    _cite_by_section(extraction)

    result = assemble(tmp_path, sources, extraction, None, "--json")

    assert result.exit_code == 2, result.stdout


def _add_operational_citing_note(extraction: Path) -> None:
    inventory_path = extraction / "inventory.json"
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    inventory["title"] = "Demo API"
    inventory["operational"] = [
        {
            "topic": "沙箱金鑰",
            "detail": "由窗口另行以工單提供,文件未載明。",
            "source": "note.md",
        }
    ]
    inventory_path.write_text(
        json.dumps(inventory, ensure_ascii=False), encoding="utf-8"
    )


def test_a_claim_resting_only_on_a_supplementary_source_is_named_individually(
    tmp_path: Path,
) -> None:
    """「這條規範性主張的唯一依據是一封信」不該變成 run 層級的背景噪音 ——
    SOURCE_FACTS_UNSCANNED 的前例已經證明那會被讀者當成雜訊。"""
    sources, extraction, _ = setup(
        tmp_path,
        extra_sources={"note.md": _NOTE, "note.md.source.json": _NOTE_SIDECAR},
    )
    _add_operational_citing_note(extraction)

    result = assemble(tmp_path, sources, extraction, None, "--json")

    assert result.exit_code != 2, result.stdout
    payload = json.loads(result.stdout)
    supplementary = [
        issue
        for issue in payload["report"]["issues"]
        if issue["code"] == "SUPPLEMENTARY_SUPPORT"
    ]
    assert [(issue["location"], issue["severity"]) for issue in supplementary] == [
        ("operational[0]", "warning")
    ]
    assert "note.md" in supplementary[0]["evidence"]


def test_a_claim_also_backed_by_a_normative_source_is_not_named(
    tmp_path: Path,
) -> None:
    """標記只出現在真正需要注意的地方。"""
    sources, extraction, _ = setup(
        tmp_path,
        extra_sources={"note.md": _NOTE, "note.md.source.json": _NOTE_SIDECAR},
    )

    result = assemble(tmp_path, sources, extraction, None, "--json")

    payload = json.loads(result.stdout)
    assert [
        issue
        for issue in payload["report"]["issues"]
        if issue["code"] == "SUPPLEMENTARY_SUPPORT"
    ] == []


def test_freshness_fingerprint_omits_supplementary_sources(tmp_path: Path) -> None:
    """`check-freshness` 的前提是來源可被重新取得並比對雜湊。一封信沒有
    URL、沒有版本,納入 watchlist 只會對它永遠給出無意義的判定。"""
    from typer.testing import CliRunner

    from loop_apidoc.cli import app

    sources, extraction, _ = setup(
        tmp_path,
        extra_sources={"note.md": _NOTE, "note.md.source.json": _NOTE_SIDECAR},
    )
    result = assemble(tmp_path, sources, extraction, None, "--json")
    assert result.exit_code != 2, result.stdout
    run_dir = json.loads(result.stdout)["run_dir"]

    fingerprint_path = tmp_path / "source-fingerprint.json"
    record = CliRunner().invoke(
        app,
        [
            "record-fingerprint",
            "--run-dir",
            run_dir,
            "--output",
            str(fingerprint_path),
        ],
    )

    assert record.exit_code == 0, record.stdout
    fingerprint = json.loads(fingerprint_path.read_text(encoding="utf-8"))
    assert [entry["id"] for entry in fingerprint["sources"]] == ["manual.md"]


def _recite(extraction: Path, source: str) -> None:
    inventory_path = extraction / "inventory.json"
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    for section in ("environments", "endpoints"):
        for entry in inventory.get(section) or []:
            entry["source"] = source
    inventory_path.write_text(
        json.dumps(inventory, ensure_ascii=False), encoding="utf-8"
    )
    for endpoint_file in sorted((extraction / "endpoints").glob("*.json")):
        endpoint = json.loads(endpoint_file.read_text(encoding="utf-8"))
        endpoint["source"] = source
        endpoint_file.write_text(
            json.dumps(endpoint, ensure_ascii=False), encoding="utf-8"
        )


def test_a_run_with_nothing_re_obtainable_refuses_to_write_a_fingerprint(
    tmp_path: Path,
) -> None:
    """空指紋不會失敗,它會永遠回報新鮮 —— 那是無聲的監控喪失。"""
    from typer.testing import CliRunner

    from loop_apidoc.cli import app

    sources, extraction, _ = setup(tmp_path)
    (sources / "manual.md").unlink()
    (sources / "note.md").write_text(_NOTE, encoding="utf-8")
    (sources / "note.md.source.json").write_text(_NOTE_SIDECAR, encoding="utf-8")
    _recite(extraction, "note.md")
    result = assemble(tmp_path, sources, extraction, None, "--json")
    # 條件式跳過會讓這個測試在邊界行為改變時無聲空轉,所以斷言它走到底。
    assert result.exit_code != 2, result.stdout
    run_dir = json.loads(result.stdout)["run_dir"]

    record = CliRunner().invoke(
        app,
        [
            "record-fingerprint",
            "--run-dir",
            run_dir,
            "--output",
            str(tmp_path / "fp.json"),
        ],
    )

    assert record.exit_code != 0
    assert not (tmp_path / "fp.json").exists()


def test_shadow_core_never_gives_a_supplementary_citation_explicit_support(
    tmp_path: Path,
) -> None:
    """strict/shadow 的整個意義是「每條主張都要對得上精確證據」。filename-only
    引用本來就降級成 insufficient,所以真正的暴露面是 v1 精確證據 —— 它擁有
    自己宣告的 claim path,會把摘錄以與手冊同等的身分寫進 Core candidate。"""
    from loop_apidoc.domain.evidence import fragment_digest

    sources, extraction, _ = setup(
        tmp_path,
        extra_sources={"note.md": _NOTE, "note.md.source.json": _NOTE_SIDECAR},
    )
    inventory_path = extraction / "inventory.json"
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    inventory["title"] = "Demo API"
    inventory_path.write_text(
        json.dumps(inventory, ensure_ascii=False), encoding="utf-8"
    )
    endpoint_path = extraction / "endpoints" / "ep0.json"
    endpoint = json.loads(endpoint_path.read_text(encoding="utf-8"))
    endpoint["source"] = "note.md"
    endpoint["summary"] = "沙箱金鑰由窗口另行以工單提供。"
    endpoint["evidence"] = [
        {
            "version": 1,
            "source": "note.md",
            "locator": {"kind": "line_range", "start_line": 3, "end_line": 3},
            "fragment_digest": fragment_digest("沙箱金鑰由窗口另行以工單提供。"),
            "claim_path": "/summary",
        }
    ]
    endpoint_path.write_text(
        json.dumps(endpoint, ensure_ascii=False), encoding="utf-8"
    )

    result = assemble(
        tmp_path, sources, extraction, None, "--json", "--architecture-mode", "shadow"
    )

    assert result.exit_code != 2, result.stdout
    core = Path(json.loads(result.stdout)["run_dir"]) / "core"
    assert not (core / "error.json").exists(), (core / "error.json").read_text(
        encoding="utf-8"
    )
    evidence = json.loads((core / "evidence.json").read_text(encoding="utf-8"))
    note_artifacts = {
        artifact["id"]
        for artifact in evidence["artifacts"]
        if any("note.md" in str(pair) for pair in artifact.get("acquisition_metadata", []))
    }
    note_fragments = {
        fragment["id"]
        for fragment in evidence["fragments"]
        if fragment.get("source_artifact_id") in note_artifacts
    }
    assert note_fragments, "摘錄應該仍然進入證據束 —— 它可以被引用"

    relationships = json.loads(
        (core / "relationships.json").read_text(encoding="utf-8")
    )
    on_note = [
        item
        for item in _walk(relationships)
        if isinstance(item, dict) and item.get("fragment_id") in note_fragments
    ]
    assert on_note == [], "摘錄不得支撐任何 Core 主張"

    # 對照組:同樣形狀的精確證據指向正式手冊時,確實會產生 explicit_support。
    # 沒有這一半,上面的斷言可能只是因為夾具根本做不出關係而空轉。
    control = _shadow_with_evidence_on(tmp_path / "control", "manual.md")
    assert "explicit_support" in control


def _walk(value):
    if isinstance(value, dict):
        yield value
        for item in value.values():
            yield from _walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk(item)


def _shadow_with_evidence_on(tmp_path: Path, source_name: str) -> set[str]:
    """跑一次 shadow,回傳掛在 `source_name` 片段上的關係種類。"""
    from loop_apidoc.domain.evidence import fragment_digest

    summary = "沙箱金鑰由窗口另行以工單提供。"
    sources, extraction, _ = setup(
        tmp_path,
        extra_sources={"note.md": _NOTE, "note.md.source.json": _NOTE_SIDECAR},
    )
    (sources / "manual.md").write_text(
        f"# Demo API\nGET /ping\n{summary}\nPOST /notify\nSettle callback\n",
        encoding="utf-8",
    )
    inventory_path = extraction / "inventory.json"
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    inventory["title"] = "Demo API"
    inventory_path.write_text(
        json.dumps(inventory, ensure_ascii=False), encoding="utf-8"
    )
    endpoint_path = extraction / "endpoints" / "ep0.json"
    endpoint = json.loads(endpoint_path.read_text(encoding="utf-8"))
    endpoint["source"] = source_name
    endpoint["summary"] = summary
    endpoint["evidence"] = [
        {
            "version": 1,
            "source": source_name,
            "locator": {"kind": "line_range", "start_line": 3, "end_line": 3},
            "fragment_digest": fragment_digest(summary),
            "claim_path": "/summary",
        }
    ]
    endpoint_path.write_text(
        json.dumps(endpoint, ensure_ascii=False), encoding="utf-8"
    )
    result = assemble(
        tmp_path, sources, extraction, None, "--json", "--architecture-mode", "shadow"
    )
    core = Path(json.loads(result.stdout)["run_dir"]) / "core"
    evidence = json.loads((core / "evidence.json").read_text(encoding="utf-8"))
    artifacts = {
        artifact["id"]
        for artifact in evidence["artifacts"]
        if any(
            source_name in str(pair)
            for pair in artifact.get("acquisition_metadata", [])
        )
    }
    fragments = {
        fragment["id"]
        for fragment in evidence["fragments"]
        if fragment.get("source_artifact_id") in artifacts
    }
    relationships = json.loads(
        (core / "relationships.json").read_text(encoding="utf-8")
    )
    return {
        item.get("relationship")
        for item in _walk(relationships)
        if isinstance(item, dict) and item.get("fragment_id") in fragments
    }

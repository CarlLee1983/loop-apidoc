# loop-apidoc agent-native plugin Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `loop-apidoc` 包成 Claude Code plugin —— agent 自己擷取(寫出固定 schema 的 JSON),再呼叫一個新的確定性 CLI 子命令 `assemble` 跑完 manifest→plan→generate→validate,並由 agent 主導修正迴圈。

**Architecture:** 反轉控制權:不再由 Python spawn `claude -p`,改由 agent(skill)驅動。新增一個薄的 `assemble` 命令,從 agent 寫好的 `inventory.json` + `endpoints/*.json` 組出既有的 `ExtractionResult`,之後完全複用既有 plan/generate/validate。既有 `run`(NotebookLM)與 `run-agent`(`claude -p`)後端保留不動。

**Tech Stack:** Python ≥3.11、`uv`、`typer`(CLI)、`pydantic`(models)、`pytest`。Plugin 以 `.claude-plugin/plugin.json` + `skills/loop-apidoc/SKILL.md` 形式存在於本倉庫,skill 用 `uv run --project "${CLAUDE_PLUGIN_ROOT}" loop-apidoc assemble ...` 呼叫。

## Global Constraints

- Python `>=3.11`;一律用 `uv`(`uv run` / `uv sync`),不用 `pip`。
- **來源依據原則**:來源未述明者一律 `null` 並加進 `missing`,不臆測、不套 REST/OAuth 慣例。
- 不修改既有 `run` / `run-agent` 後端的行為(向後相容)。
- 不重寫 plan / generate / validate;`assemble` 必須複用既有純函式。
- 註解與文件用繁體中文;commit 訊息用 `<type>: [scope] subject` 格式。

## File Structure

- Create `loop_apidoc/agentcli/assemble.py` —— 檔案讀取 + `ExtractionResult` 組裝 + `run_assemble_pipeline`。
- Modify `loop_apidoc/cli.py` —— 新增 `assemble` 子命令(含 `--json`)。
- Create `tests/agentcli/test_assemble.py` —— 核心單元測試。
- Create `tests/test_cli_assemble.py` —— CLI 端到端測試。
- Create `.claude-plugin/plugin.json`、`.claude-plugin/marketplace.json` —— plugin 安裝清單。
- Create `skills/loop-apidoc/SKILL.md` —— agent 流程指令(內嵌兩個 schema)。
- Create `tests/test_plugin_manifest.py` —— 驗證 plugin 清單與 skill 結構。

---

### Task 1: `assemble` 核心 —— 讀檔與 ExtractionResult 組裝

**Files:**
- Create: `loop_apidoc/agentcli/assemble.py`
- Test: `tests/agentcli/test_assemble.py`

**Interfaces:**
- Consumes:
  - `loop_apidoc.agentcli.extraction.inventory_to_stage_answers(inventory: dict) -> dict[str, str]`(既有純函式)
  - `loop_apidoc.extraction.store.ExtractionStore(extraction_dir: Path)`,方法 `.record(*, query_id, stage_id, kind, question, answer, returncode) -> AnswerArtifact`
  - `loop_apidoc.extraction.models.ExtractionResult(notebook_url: str, artifacts: list[AnswerArtifact])`
  - `loop_apidoc.extraction.stages.QueryKind`(`QueryKind.INITIAL`)
- Produces:
  - `AssembleInputError(ValueError)`
  - `load_extraction_inputs(extraction_dir: Path) -> tuple[dict, list[str]]`
  - `build_extraction_from_files(inventory: dict, endpoint_texts: list[str], store: ExtractionStore) -> ExtractionResult`

- [ ] **Step 1: 寫失敗測試**

```python
# tests/agentcli/test_assemble.py
from __future__ import annotations

import json
from pathlib import Path

import pytest

from loop_apidoc.agentcli.assemble import (
    AssembleInputError,
    build_extraction_from_files,
    load_extraction_inputs,
)
from loop_apidoc.extraction.store import ExtractionStore

_INVENTORY = {
    "overview": "Demo API",
    "environments": [{"name": "prod", "base_url": "https://api.example.com",
                      "version": None, "source": "§1"}],
    "security_schemes": [],
    "endpoints": [{"method": "GET", "path": "/ping", "summary": "健康檢查",
                   "source": "§2"}],
    "schemas": [],
    "errors": [],
    "operational": [],
    "missing": [],
}
_ENDPOINT = {
    "method": "GET", "path": "/ping",
    "parameters": [], "request": None,
    "responses": [{"status": "200", "description": "OK", "schema": None}],
    "examples": [], "missing": [],
}


def _write_extraction(extraction_dir: Path) -> None:
    extraction_dir.mkdir(parents=True, exist_ok=True)
    (extraction_dir / "inventory.json").write_text(
        json.dumps(_INVENTORY, ensure_ascii=False), encoding="utf-8")
    eps = extraction_dir / "endpoints"
    eps.mkdir()
    (eps / "ep0.json").write_text(
        json.dumps(_ENDPOINT, ensure_ascii=False), encoding="utf-8")


def test_load_extraction_inputs_reads_inventory_and_endpoints(tmp_path):
    _write_extraction(tmp_path / "extraction")
    inventory, endpoint_texts = load_extraction_inputs(tmp_path / "extraction")
    assert inventory["overview"] == "Demo API"
    assert len(endpoint_texts) == 1
    assert json.loads(endpoint_texts[0])["path"] == "/ping"


def test_load_extraction_inputs_missing_inventory_raises(tmp_path):
    (tmp_path / "extraction").mkdir()
    with pytest.raises(AssembleInputError):
        load_extraction_inputs(tmp_path / "extraction")


def test_load_extraction_inputs_bad_json_raises(tmp_path):
    d = tmp_path / "extraction"
    d.mkdir()
    (d / "inventory.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(AssembleInputError):
        load_extraction_inputs(d)


def test_build_extraction_from_files_produces_stage_and_endpoint_artifacts(tmp_path):
    store = ExtractionStore(tmp_path / "store")
    extraction = build_extraction_from_files(
        _INVENTORY, [json.dumps(_ENDPOINT, ensure_ascii=False)], store)
    stage_ids = {a.stage_id for a in extraction.artifacts}
    # inventory 切出 03/04/05/07/08/09 + 敘事 01/02/10,per-endpoint 為 06
    assert {"03", "04", "05", "06", "07", "08", "09"} <= stage_ids
    ep06 = [a for a in extraction.artifacts if a.stage_id == "06"]
    assert len(ep06) == 1
    assert json.loads(ep06[0].answer)["path"] == "/ping"
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `uv run pytest tests/agentcli/test_assemble.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'loop_apidoc.agentcli.assemble'`

- [ ] **Step 3: 寫最小實作**

```python
# loop_apidoc/agentcli/assemble.py
from __future__ import annotations

import json
from pathlib import Path

from loop_apidoc.agentcli.extraction import inventory_to_stage_answers
from loop_apidoc.extraction.models import AnswerArtifact, ExtractionResult
from loop_apidoc.extraction.stages import QueryKind
from loop_apidoc.extraction.store import ExtractionStore


class AssembleInputError(ValueError):
    """agent 產出的擷取檔缺漏或格式錯誤時拋出(fail loudly)。"""


def load_extraction_inputs(extraction_dir: Path) -> tuple[dict, list[str]]:
    """讀 inventory.json(物件)與 endpoints/*.json(原始文字,依檔名排序)。"""
    inv_path = extraction_dir / "inventory.json"
    if not inv_path.is_file():
        raise AssembleInputError(f"找不到 inventory.json:{inv_path}")
    try:
        inventory = json.loads(inv_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise AssembleInputError(f"inventory.json 不是合法 JSON:{exc}") from exc
    if not isinstance(inventory, dict):
        raise AssembleInputError("inventory.json 必須是一個 JSON 物件")

    endpoint_texts: list[str] = []
    endpoints_dir = extraction_dir / "endpoints"
    if endpoints_dir.is_dir():
        for path in sorted(endpoints_dir.glob("*.json")):
            text = path.read_text(encoding="utf-8")
            try:
                json.loads(text)
            except json.JSONDecodeError as exc:
                raise AssembleInputError(
                    f"{path.name} 不是合法 JSON:{exc}") from exc
            endpoint_texts.append(text)
    return inventory, endpoint_texts


def build_extraction_from_files(
    inventory: dict, endpoint_texts: list[str], store: ExtractionStore
) -> ExtractionResult:
    """把 agent 產出的 inventory + per-endpoint JSON 組成 ExtractionResult,
    產出與 NotebookLM/`claude -p` 後端相同的 artifact 形狀,讓 plan 不需改動。"""
    artifacts: list[AnswerArtifact] = []
    for stage_id, answer in inventory_to_stage_answers(inventory).items():
        artifacts.append(store.record(
            query_id=f"{stage_id}-initial", stage_id=stage_id,
            kind=QueryKind.INITIAL, question="(agent inventory)",
            answer=answer, returncode=0,
        ))
    for idx, text in enumerate(endpoint_texts):
        artifacts.append(store.record(
            query_id=f"06-ep{idx}", stage_id="06", kind=QueryKind.INITIAL,
            question="(agent endpoint detail)", answer=text, returncode=0,
        ))
    return ExtractionResult(notebook_url="", artifacts=artifacts)
```

- [ ] **Step 4: 跑測試確認通過**

Run: `uv run pytest tests/agentcli/test_assemble.py -v`
Expected: PASS(4 passed)

- [ ] **Step 5: Commit**

```bash
git add loop_apidoc/agentcli/assemble.py tests/agentcli/test_assemble.py
git commit -m "feat: [assemble] 從 agent 產出的擷取 JSON 組裝 ExtractionResult"
```

---

### Task 2: `run_assemble_pipeline` —— 串接 manifest→plan→generate→validate

**Files:**
- Modify: `loop_apidoc/agentcli/assemble.py`(在 Task 1 的檔案末端追加)
- Test: `tests/agentcli/test_assemble.py`(追加)

**Interfaces:**
- Consumes:
  - `loop_apidoc.manifest.builder.build_manifest(sources_root: Path, urls: list[str], generated_at: datetime) -> Manifest`
  - `loop_apidoc.plan.builder.build_normalization_plan(extraction: ExtractionResult, manifest: Manifest) -> NormalizationPlan`
  - `loop_apidoc.run.pipeline._persist_plan(run_dir: Path, plan) -> None`
  - `loop_apidoc.generate.writer.generate_outputs(plan, manifest, run_dir: Path) -> GenerateResult`
  - `loop_apidoc.validate.validator.validate_outputs(plan, result, manifest) -> ValidationReport`
  - `loop_apidoc.validate.report.write_reports(report, validation_dir: Path) -> None`
  - `loop_apidoc.run.models.RunResult`, `RunStatus`
- Produces:
  - `run_assemble_pipeline(*, sources_root: Path, extraction_dir: Path, output_root: Path, run_id: str, generated_at: datetime, urls: list[str] | None = None) -> RunResult`

- [ ] **Step 1: 寫失敗測試**

```python
# 追加到 tests/agentcli/test_assemble.py
from datetime import datetime, timezone

from loop_apidoc.agentcli.assemble import run_assemble_pipeline
from loop_apidoc.run.models import RunStatus


def test_run_assemble_pipeline_writes_outputs(tmp_path):
    _write_extraction(tmp_path / "extraction")
    sources = tmp_path / "sources"
    sources.mkdir()
    (sources / "manual.md").write_text("# Demo API\nGET /ping", encoding="utf-8")
    out = tmp_path / "out"

    result = run_assemble_pipeline(
        sources_root=sources,
        extraction_dir=tmp_path / "extraction",
        output_root=out,
        run_id="run-test",
        generated_at=datetime(2026, 6, 27, tzinfo=timezone.utc),
        urls=[],
    )

    run_dir = out / "run-test"
    assert (run_dir / "manifest.json").is_file()
    assert (run_dir / "openapi.yaml").is_file()
    assert (run_dir / "api-guide.zh-TW.md").is_file()
    assert (run_dir / "provenance.json").is_file()
    assert (run_dir / "plan" / "normalization-plan.json").is_file()
    assert (run_dir / "validation" / "report.json").is_file()
    assert result.status in (RunStatus.PASSED, RunStatus.FAILED)
    assert result.run_dir == str(run_dir)
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `uv run pytest tests/agentcli/test_assemble.py::test_run_assemble_pipeline_writes_outputs -v`
Expected: FAIL，`ImportError: cannot import name 'run_assemble_pipeline'`

- [ ] **Step 3: 寫最小實作**

```python
# 追加到 loop_apidoc/agentcli/assemble.py
from datetime import datetime  # 置於檔案頂端 import 區

from loop_apidoc.generate.writer import generate_outputs
from loop_apidoc.manifest.builder import build_manifest
from loop_apidoc.plan.builder import build_normalization_plan
from loop_apidoc.run.models import RunResult, RunStatus
from loop_apidoc.run.pipeline import _persist_plan
from loop_apidoc.validate.report import write_reports
from loop_apidoc.validate.validator import validate_outputs


def run_assemble_pipeline(
    *,
    sources_root: Path,
    extraction_dir: Path,
    output_root: Path,
    run_id: str,
    generated_at: datetime,
    urls: list[str] | None = None,
) -> RunResult:
    """agent-native 組裝:manifest(原始來源)→ 由 agent 產出的擷取檔組 plan
    → generate → validate。不做擷取、不 spawn 任何 agent。

    註:tail 與 agentcli.pipeline.run_agent_pipeline 刻意維持小幅重複,
    以免改動既有 `run-agent` 後端(向後相容優先於 DRY)。"""
    run_dir = output_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    manifest = build_manifest(
        sources_root=sources_root, urls=urls or [], generated_at=generated_at)
    (run_dir / "manifest.json").write_text(
        manifest.model_dump_json(indent=2), encoding="utf-8")

    inventory, endpoint_texts = load_extraction_inputs(extraction_dir)
    store = ExtractionStore(run_dir / "extraction")
    extraction = build_extraction_from_files(inventory, endpoint_texts, store)

    plan = build_normalization_plan(extraction, manifest)
    _persist_plan(run_dir, plan)
    result = generate_outputs(plan, manifest, run_dir)
    report = validate_outputs(plan, result, manifest)
    write_reports(report, run_dir / "validation")

    return RunResult(
        run_id=run_id,
        run_dir=str(run_dir),
        report=report,
        rounds=0,
        status=RunStatus.PASSED if report.ok else RunStatus.FAILED,
    )
```

- [ ] **Step 4: 跑測試確認通過**

Run: `uv run pytest tests/agentcli/test_assemble.py -v`
Expected: PASS(5 passed)

- [ ] **Step 5: Commit**

```bash
git add loop_apidoc/agentcli/assemble.py tests/agentcli/test_assemble.py
git commit -m "feat: [assemble] run_assemble_pipeline 串接 manifest→plan→generate→validate"
```

---

### Task 3: CLI `assemble` 子命令(含 `--json`)

**Files:**
- Modify: `loop_apidoc/cli.py`
- Test: `tests/test_cli_assemble.py`

**Interfaces:**
- Consumes:
  - `loop_apidoc.agentcli.assemble.run_assemble_pipeline(...)`、`AssembleInputError`
  - `loop_apidoc.run.runid.make_run_id(now: datetime) -> str`(既有,cli.py 已 import)
  - 既有模組層級的 `app`(typer.Typer)、`datetime`、`timezone`
- Produces:
  - typer 命令 `assemble`;`--json` 時印出 `{"run_id","run_dir","ok","status","report":{...}}`,退出碼:輸入錯誤=2、驗證 FAIL=1、PASS=0。

- [ ] **Step 1: 寫失敗測試**

```python
# tests/test_cli_assemble.py
from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from loop_apidoc.cli import app

runner = CliRunner()

_INVENTORY = {
    "overview": "Demo API",
    "environments": [{"name": "prod", "base_url": "https://api.example.com",
                      "version": None, "source": "§1"}],
    "security_schemes": [], "schemas": [], "errors": [], "operational": [],
    "endpoints": [{"method": "GET", "path": "/ping", "summary": "健康檢查",
                   "source": "§2"}],
    "missing": [],
}
_ENDPOINT = {
    "method": "GET", "path": "/ping", "parameters": [], "request": None,
    "responses": [{"status": "200", "description": "OK", "schema": None}],
    "examples": [], "missing": [],
}


def _setup(tmp_path: Path) -> tuple[Path, Path, Path]:
    extraction = tmp_path / "extraction"
    (extraction / "endpoints").mkdir(parents=True)
    (extraction / "inventory.json").write_text(
        json.dumps(_INVENTORY, ensure_ascii=False), encoding="utf-8")
    (extraction / "endpoints" / "ep0.json").write_text(
        json.dumps(_ENDPOINT, ensure_ascii=False), encoding="utf-8")
    sources = tmp_path / "sources"
    sources.mkdir()
    (sources / "manual.md").write_text("# Demo API\nGET /ping", encoding="utf-8")
    return sources, extraction, tmp_path / "out"


def test_assemble_json_emits_run_dir_and_report(tmp_path):
    sources, extraction, out = _setup(tmp_path)
    res = runner.invoke(app, [
        "assemble", "--sources", str(sources), "--extraction", str(extraction),
        "--output", str(out), "--json",
    ])
    assert res.exit_code in (0, 1)  # PASS 或驗證 FAIL,皆非崩潰
    payload = json.loads(res.stdout)
    assert "report" in payload and "run_dir" in payload
    assert Path(payload["run_dir"]).is_dir()


def test_assemble_missing_inventory_exits_2(tmp_path):
    sources, extraction, out = _setup(tmp_path)
    (extraction / "inventory.json").unlink()
    res = runner.invoke(app, [
        "assemble", "--sources", str(sources), "--extraction", str(extraction),
        "--output", str(out),
    ])
    assert res.exit_code == 2
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `uv run pytest tests/test_cli_assemble.py -v`
Expected: FAIL(`assemble` 命令不存在,typer 以 exit code 2 報 "No such command" —— 但 `test_assemble_json_*` 會因無 `report` 鍵而失敗,確認尚未實作)

- [ ] **Step 3: 寫最小實作**

在 `loop_apidoc/cli.py` 頂端 import 區加入 `import json`,並在 `run_agent` 命令之後、`def main()` 之前新增:

```python
@app.command()
def assemble(
    sources: Path = typer.Option(
        ..., "--sources", help="本機來源目錄",
        exists=True, file_okay=False, dir_okay=True, readable=True,
    ),
    extraction: Path = typer.Option(
        ..., "--extraction",
        help="agent 產出的擷取目錄(inventory.json + endpoints/*.json)",
        exists=True, file_okay=False, dir_okay=True, readable=True,
    ),
    output: Path = typer.Option(
        ..., "--output", help="輸出根目錄(將建立 <run-id> 子目錄)"
    ),
    url: list[str] = typer.Option([], "--url", help="公開來源 URL,可重複指定"),
    json_out: bool = typer.Option(
        False, "--json", help="把結果以 JSON 印到 stdout(供 agent 解析)"
    ),
) -> None:
    """從 agent 產出的擷取 JSON 組裝:manifest→plan→generate→validate(不擷取)。"""
    from loop_apidoc.agentcli.assemble import (
        AssembleInputError,
        run_assemble_pipeline,
    )

    now = datetime.now(timezone.utc)
    try:
        result = run_assemble_pipeline(
            sources_root=sources,
            extraction_dir=extraction,
            output_root=output,
            run_id=make_run_id(now),
            generated_at=now,
            urls=list(url),
        )
    except AssembleInputError as exc:
        typer.echo(f"擷取輸入錯誤:{exc}", err=True)
        raise typer.Exit(code=2) from exc

    if json_out:
        payload = {
            "run_id": result.run_id,
            "run_dir": result.run_dir,
            "ok": result.ok,
            "status": result.status.value,
            "report": result.report.model_dump(mode="json"),
        }
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        typer.echo(
            f"狀態 {result.status.value}:error {len(result.report.errors())}，"
            f"warning {len(result.report.warnings())}；輸出於 {result.run_dir}"
        )
    raise typer.Exit(code=0 if result.ok else 1)
```

- [ ] **Step 4: 跑測試確認通過**

Run: `uv run pytest tests/test_cli_assemble.py -v`
Expected: PASS(2 passed)

- [ ] **Step 5: Commit**

```bash
git add loop_apidoc/cli.py tests/test_cli_assemble.py
git commit -m "feat: [cli] 新增 assemble 子命令(--json 供 agent 驅動修正)"
```

---

### Task 4: Plugin 清單 + SKILL.md

**Files:**
- Create: `.claude-plugin/plugin.json`
- Create: `.claude-plugin/marketplace.json`
- Create: `skills/loop-apidoc/SKILL.md`
- Test: `tests/test_plugin_manifest.py`

**Interfaces:**
- Consumes:(無程式碼依賴)skill 在執行期使用 Claude Code 注入的 `${CLAUDE_PLUGIN_ROOT}` 環境變數定位 plugin 目錄。
- Produces:可安裝的 plugin(plugin.json + 一個 skill)。

- [ ] **Step 1: 寫失敗測試**

```python
# tests/test_plugin_manifest.py
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_plugin_json_valid():
    data = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text("utf-8"))
    assert data["name"] == "loop-apidoc"
    assert "description" in data


def test_marketplace_lists_plugin():
    data = json.loads(
        (ROOT / ".claude-plugin" / "marketplace.json").read_text("utf-8"))
    names = [p["name"] for p in data["plugins"]]
    assert "loop-apidoc" in names


def test_skill_has_frontmatter_and_assemble_call():
    text = (ROOT / "skills" / "loop-apidoc" / "SKILL.md").read_text("utf-8")
    assert text.startswith("---")
    assert "name: loop-apidoc" in text
    assert "loop-apidoc assemble" in text
    assert "CLAUDE_PLUGIN_ROOT" in text
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `uv run pytest tests/test_plugin_manifest.py -v`
Expected: FAIL，`FileNotFoundError`(清單檔尚未建立)

- [ ] **Step 3: 寫最小實作**

`.claude-plugin/plugin.json`:

```json
{
  "name": "loop-apidoc",
  "version": "0.1.0",
  "description": "來源依據式 API 文件 pipeline:給定文檔來源,agent 驅動擷取→組裝→驗證→修正,產出 OpenAPI 3.1 / 繁中 Markdown / provenance。",
  "author": { "name": "carl" }
}
```

`.claude-plugin/marketplace.json`:

```json
{
  "name": "loop-apidoc-marketplace",
  "owner": { "name": "carl" },
  "plugins": [
    {
      "name": "loop-apidoc",
      "source": "./",
      "description": "來源依據式 API 文件 pipeline(agent-native)。"
    }
  ]
}
```

`skills/loop-apidoc/SKILL.md`:

````markdown
---
name: loop-apidoc
description: 從一或多個 API 文檔來源(本機 PDF/MD/HTML 或公開 URL)產出標準化的 OpenAPI 3.1 + 繁中 Markdown 串接文件。由 agent 擷取、呼叫確定性 CLI 組裝與驗證,驗證失敗時自動回頭補齊缺漏。當使用者要把雜亂的 API 串接文件整理成一致、可追溯的規格時使用。
---

# loop-apidoc:來源依據式 API 文件產生

你要把使用者提供的 API 文檔來源,整理成標準化、可追溯的產物。**唯一事實依據是來源**:來源沒寫的一律 `null` 並記入 `missing`,**絕不臆測、絕不套用 REST/OAuth 慣例**。

CLI 以本 plugin 內含的套件執行,一律用:

```bash
uv run --project "${CLAUDE_PLUGIN_ROOT}" loop-apidoc <command> ...
```

## 流程

### 1. 蒐集來源
- 本機檔案(PDF/MD/HTML):用 Read 直接讀。
- 公開 URL:用 WebFetch 或 defuddle 抓成文字。
- 把本機來源目錄記為 `<SOURCES>`(供 manifest/provenance 用);URL 用 `--url` 傳入。

### 2. 擷取 inventory → 寫 `<WORK>/inventory.json`
讀完所有來源後,輸出**一個** JSON 物件(嚴格依來源填寫),schema:

```json
{"overview": "str",
 "environments": [{"name":"str","base_url":"str","version":"str|null","source":"str"}],
 "security_schemes": [{"name":"str","type":"str|null","location":"str|null","details":"str|null","source":"str"}],
 "endpoints": [{"method":"str","path":"str","summary":"str","source":"str"}],
 "schemas": [{"name":"str","fields":[{}],"enums":["str"],"constraints":"str|null","source":"str"}],
 "errors": [{"code":"str","meaning":"str","http_status":"str|null","source":"str"}],
 "operational": [{"topic":"str","detail":"str","source":"str"}],
 "missing": ["str"]}
```
包含**每一個** endpoint 與**每一個** error code。每個 `source` 引用來源章節/頁碼。

### 3. 擷取每個 endpoint 細節 → 寫 `<WORK>/endpoints/<NN>.json`
對 inventory.endpoints 的**每一個** endpoint,各輸出一個 JSON 檔(`ep0.json`, `ep1.json`, …),schema:

```json
{"method":"str","path":"str",
 "parameters":[{"name":"str","in":"query|header|path|body|null","type":"str|null","required":"bool|null","description":"str|null"}],
 "request":{"content_type":"str|null","schema":"str|null","required":"bool|null","description":"str|null"} ,
 "responses":[{"status":"str","description":"str|null","schema":"str|null"}],
 "examples":[{}],"missing":["str"]}
```
`request` 無內容時為 `null`。來源沒寫的填 null/空陣列並加進 `missing`。

### 4. 組裝 + 驗證
```bash
uv run --project "${CLAUDE_PLUGIN_ROOT}" loop-apidoc assemble \
  --sources "<SOURCES>" --extraction "<WORK>" --output "<OUT>" --json
```
解析 stdout 的 JSON:`ok`、`run_dir`、`report.issues`。

### 5. 修正迴圈(最多 3 輪)
- `ok == true` → 回報 `run_dir` 內的 `openapi.yaml` / `api-guide.zh-TW.md` / `provenance.json` / `validation/report.md`,結束。
- `ok == false` → 看 `report.issues`(每筆有 `severity`/`code`/`area`/`detail`),**只針對缺漏的欄位回頭重讀對應來源**,覆寫 `inventory.json` 或對應的 `endpoints/<NN>.json`,然後回到步驟 4。
- 連續 3 輪仍 FAIL → 把剩餘的缺漏/衝突清單呈現給使用者,**不要硬編補寫**。

## 重要
- `<WORK>` 用一個工作目錄(可放在 `<OUT>` 之外的暫存區)。
- 每輪覆寫同一份 `inventory.json` / `endpoints/*.json` 再重跑 assemble。
- 退出碼:0=PASS、1=驗證 FAIL、2=擷取輸入檔錯誤(修正你寫出的 JSON)。
````

- [ ] **Step 4: 跑測試確認通過**

Run: `uv run pytest tests/test_plugin_manifest.py -v`
Expected: PASS(3 passed)

- [ ] **Step 5: Commit**

```bash
git add .claude-plugin/plugin.json .claude-plugin/marketplace.json \
        skills/loop-apidoc/SKILL.md tests/test_plugin_manifest.py
git commit -m "feat: [plugin] 加入 plugin 清單與 loop-apidoc agent-native skill"
```

---

### Task 5: 文件更新 + 全量測試

**Files:**
- Modify: `README.md`(新增 plugin / agent-native 用法一節)
- Modify: `README.en.md`(對應英文)

**Interfaces:** 無程式碼介面;僅文件。

- [ ] **Step 1: 在 README.md 的「運作方式」之後新增一節**

```markdown
## 以 Claude Code plugin 執行(agent-native)

除了 CLI,本專案也是一個 Claude Code plugin:在 Claude session 裡呼叫 `loop-apidoc` skill,給它一或多個來源(本機檔案或公開 URL),由 agent 自己擷取、呼叫 `loop-apidoc assemble` 組裝與驗證,並在驗證失敗時自動回頭補齊缺漏(最多 3 輪)。

此模式**不**透過 NotebookLM、也**不** spawn `claude -p`,而是由當前 agent 直接擔任擷取引擎。安裝 plugin 後即可在 Claude Code 中使用;CLI 由 plugin 內含,透過 `uv run --project "${CLAUDE_PLUGIN_ROOT}" loop-apidoc assemble` 呼叫。
```

- [ ] **Step 2: 在 README.en.md 對應位置新增等義英文段落**

```markdown
## Run as a Claude Code plugin (agent-native)

Besides the CLI, this project is also a Claude Code plugin: invoke the
`loop-apidoc` skill inside a Claude session, give it one or more sources (local
files or public URLs), and the agent extracts them itself, calls
`loop-apidoc assemble` to assemble and validate, and re-fills missing fields
automatically when validation fails (up to 3 rounds).

This mode uses neither NotebookLM nor a nested `claude -p`; the current agent is
the extraction engine. The bundled CLI is invoked via
`uv run --project "${CLAUDE_PLUGIN_ROOT}" loop-apidoc assemble`.
```

- [ ] **Step 3: 跑全量測試套件**

Run: `uv run pytest -q`
Expected: 全數通過(既有測試 + 本計畫新增的 assemble / cli / plugin 測試),無 regression。

- [ ] **Step 4: Commit**

```bash
git add README.md README.en.md
git commit -m "docs: [plugin] README 補充 agent-native plugin 用法"
```

---

## Self-Review

**1. Spec coverage**
- 反轉控制權(agent 呼叫 Python,不 spawn claude)→ Task 1–3(`assemble` 不含任何 adapter/agent 呼叫)+ Task 4 skill。✓
- 新 CLI `assemble`(`--sources/--extraction/--output/--url/--json`)→ Task 3。✓
- 資料契約(inventory.json + endpoints/*.json,schema 同既有常數)→ Task 1 讀取 + Task 4 skill 內嵌 schema。✓
- agent 主導修正迴圈(結構化 `--json` 報告)→ Task 3 `--json` payload + Task 4 skill 步驟 5。✓
- 本機檔案 + 公開 URL,不碰 NotebookLM/不前處理 → Task 4 skill 步驟 1。✓
- plugin 內含 CLI,`uv run --project ${CLAUDE_PLUGIN_ROOT}` → Task 4。✓
- 保留既有 `run`/`run-agent`,不重寫 plan/generate/validate → 全程僅新增檔案 + cli.py 追加命令;Task 2 明示不動 `run_agent_pipeline`。✓
- fail loudly(壞 JSON/缺檔)→ Task 1 `AssembleInputError` + Task 3 exit code 2。✓
- 測試(確定性單元 + CLI + smoke)→ Task 1/2/3 單元與 CLI 測試;Task 5 全量。✓

**2. Placeholder scan**:無 TBD/TODO;每個程式步驟皆附完整程式碼與預期輸出。✓

**3. Type consistency**:`load_extraction_inputs` / `build_extraction_from_files` / `run_assemble_pipeline` / `AssembleInputError` 在 Task 1–3 命名一致;`make_run_id`、`RunResult`、`ValidationReport.model_dump(mode="json")`、`store.record(...)` 參數均對齊既有簽章。✓

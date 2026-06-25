# Loop API 文件 Pipeline — Plan 2：NotebookLM Adapter 與 doctor

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立一個與瀏覽器自動化細節解耦的 NotebookLM adapter（透過指定 skill 的 `scripts/run.py` wrapper 呼叫 `auth_manager.py status` 與 `ask_question.py`），含命令建構、輸出解析、錯誤分類與有限技術重試；並交付可運作的 `loop-apidoc doctor` 環境預檢命令。

**Architecture:** Adapter 把「如何執行子行程」抽成可注入的 `ProcessRunner` seam（正式環境用 `subprocess`，測試用 fake），核心邏輯只處理 argv 建構（`commands`）、輸出解析（`parsing`）與失敗分類（`classify`）。錯誤以型別化例外表達 spec §11 的處理分支；技術重試（`retry`）只重試暫時性錯誤且與三輪內容修正分開計數。`doctor` 是 adapter 的唯讀消費者，只回報環境就緒度，不修改 skill 或輸出。

**Tech Stack:** Python ≥3.11、Typer（CLI）、Pydantic v2（資料模型）、標準庫 `subprocess` / `shutil` / `importlib.util`、pytest。沿用 Plan 1 的 `loop_apidoc/` 套件、注入式副作用與 TDD 流程。**本計畫不新增第三方依賴。**

這是六份計畫中的第 2 份。Plan 1（基礎建設＋manifest）已完成並併入 master。Plan 3（擷取＋規格化計畫）會以本計畫的 `NotebookLMAdapter.ask()` 與 `run_with_retries()` 來執行多輪查詢。

## Global Constraints

下列為整份 spec 的專案級要求，每個 task 都隱含遵守（值逐字取自 spec）：

- **所有 skill script 只能透過 `scripts/run.py` wrapper 執行**；不可直接執行 `auth_manager.py`、`notebook_manager.py` 或 `ask_question.py`（spec §4.1）。
- **核心流程不得直接耦合瀏覽器自動化細節**，一律透過 adapter（spec §4.1）。
- **錯誤處理分支**（spec §11）：
  - NotebookLM 未驗證 → 停止並提供登入指示。
  - Notebook 無法存取 → 停止，不進入規格化。
  - 查詢額度或暫時錯誤 → 有限次技術重試，**與三輪內容修正分開計數**。
  - skill 輸出格式異常 → 保存 stdout／stderr，停止該次執行。
- **機密資料**：輸出及 log 不應保存 Google cookie、browser state 或憑證；skill 的 `data/`、`.venv/` 與瀏覽器狀態不得複製至專案或提交 Git（spec §11）。
- **`doctor` 唯讀**：檢查 Python、NotebookLM skill、skill 依賴、Chrome、驗證狀態及必要驗證工具，**不修改 Notebook 或輸出文件**（spec §5）。
- **第一版不自動建立 Notebook、不上傳來源**（spec §2.2）→ adapter 不包裝 `notebook_manager.py add`。
- **每個 follow-up 問題必須自帶完整上下文**，不可依賴上一個回答（spec §4.2）→ 由 Plan 3 的 orchestrator 負責；adapter 的 `ask()` 為無狀態單次查詢。
- Python ≥3.11；CLI 用 Typer；資料模型用 Pydantic v2；套件管理用 uv（沿用 Plan 1）。

---

## 參考：notebooklm-skill 執行契約（來源實證，供解析與分類使用）

以下契約取自 `PleasePrompto/notebooklm-skill` 原始碼，是本計畫所有 marker 字串的依據。實作時請以此為準；標示「未定」者於真實 smoke test（Plan 6 之外的手動驗證）再核對。

- **wrapper**：`python <skill_root>/scripts/run.py <script>.py <args...>`。`run.py` 以自身 `__file__` 定位 skill root，不需特定 CWD；首次執行會自動建立 `<skill_root>/.venv`。
- **auth status**：`run.py auth_manager.py status`。stdout 為**純文字**，含 `Authenticated: Yes` 或 `Authenticated: No`；未驗證時 **exit code 仍為 0**。state 過舊時可能前綴 `⚠️ Browser state is N.N days old, ...`。
- **ask**：`run.py ask_question.py --question "..." --notebook-url "..."`（旗標為連字號：`--question`、`--notebook-url`）。成功 exit 0，答案為**純文字**，夾在下列結構中：

  ```text
  ============================================================
  Question: {question}
  ============================================================

  {answer_text}

  EXTREMELY IMPORTANT: Is that ALL you need to know? You can always ask another question! ...

  ============================================================
  ```

  （分隔線為 60 個 `=`；follow-up 提醒為固定常數，無條件附加在答案之後。）
- **失敗 marker（exit 1）**：未驗證 → stdout 含 `Not authenticated`；逾時 → `Timeout waiting for answer`；找不到輸入框 → `Could not find query input`；導覽/例外 → `❌ Error:`；環境建置失敗 → `Failed to set up environment`。Rate limit 無專屬偵測，實務上表現為逾時。

---

### Task 1：NotebookLM 套件骨架 — SkillConfig 與 ProcessRunner

定義 skill 定位設定、子行程結果模型與可注入的執行 seam（正式環境用 `subprocess`）。

**Files:**
- Create: `loop_apidoc/notebooklm/__init__.py`
- Create: `loop_apidoc/notebooklm/config.py`
- Create: `loop_apidoc/notebooklm/runner.py`
- Create: `tests/notebooklm/__init__.py`
- Create: `tests/notebooklm/test_runner.py`

**Interfaces:**
- Consumes: 無。
- Produces：
  - `SkillConfig(BaseModel)`：`skill_root: Path`、`python: str = sys.executable`；property `run_py -> Path`（= `skill_root/"scripts"/"run.py"`）；`is_present() -> bool`（`run_py.is_file()`）；`venv_initialized() -> bool`（`(skill_root/".venv").is_dir()`）。
  - `CommandResult(BaseModel)`：`argv: list[str]`、`returncode: int`、`stdout: str`、`stderr: str`。
  - `ProcessRunner`（`typing.Protocol`）：`__call__(self, argv: list[str]) -> CommandResult`。
  - `subprocess_runner(config: SkillConfig, timeout_seconds: float = 300.0) -> ProcessRunner`：以 `subprocess.run(argv, cwd=config.skill_root, capture_output=True, text=True, timeout=timeout_seconds)` 執行；逾時回傳 `CommandResult(returncode=124, stderr="Timeout waiting for answer", stdout=<部分輸出或空字串>)`。只擷取被呼叫 script 的 stdout/stderr，不接觸 skill 的 `data/` 或瀏覽器狀態（spec §11）。

- [ ] **Step 1：建立 `tests/notebooklm/__init__.py`**

```python
```

- [ ] **Step 2：寫失敗測試 `tests/notebooklm/test_runner.py`**

```python
from __future__ import annotations

import sys
from pathlib import Path

from loop_apidoc.notebooklm.config import SkillConfig
from loop_apidoc.notebooklm.runner import CommandResult, subprocess_runner


def test_skill_config_paths(tmp_path: Path):
    config = SkillConfig(skill_root=tmp_path)
    assert config.run_py == tmp_path / "scripts" / "run.py"
    assert config.is_present() is False
    assert config.venv_initialized() is False

    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "run.py").write_text("", encoding="utf-8")
    (tmp_path / ".venv").mkdir()
    assert config.is_present() is True
    assert config.venv_initialized() is True


def test_subprocess_runner_captures_streams_and_code(tmp_path: Path):
    config = SkillConfig(skill_root=tmp_path)
    run = subprocess_runner(config)
    argv = [sys.executable, "-c", "import sys; print('hi'); sys.stderr.write('e'); sys.exit(3)"]

    result = run(argv)

    assert isinstance(result, CommandResult)
    assert result.returncode == 3
    assert result.stdout.strip() == "hi"
    assert result.stderr == "e"
    assert result.argv == argv


def test_subprocess_runner_timeout_is_marked_transient(tmp_path: Path):
    config = SkillConfig(skill_root=tmp_path)
    run = subprocess_runner(config, timeout_seconds=0.5)
    argv = [sys.executable, "-c", "import time; time.sleep(5)"]

    result = run(argv)

    assert result.returncode == 124
    assert "Timeout waiting for answer" in result.stderr
```

- [ ] **Step 3：執行測試確認失敗**

Run: `uv run pytest tests/notebooklm/test_runner.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'loop_apidoc.notebooklm'`）。

- [ ] **Step 4：建立 `loop_apidoc/notebooklm/__init__.py`**

```python
"""NotebookLM skill adapter (PleasePrompto/notebooklm-skill)."""
```

- [ ] **Step 5：實作 `loop_apidoc/notebooklm/config.py`**

```python
from __future__ import annotations

import sys
from pathlib import Path

from pydantic import BaseModel


class SkillConfig(BaseModel):
    """Locates the notebooklm-skill checkout and the interpreter used to launch
    its scripts/run.py wrapper (spec §4.1: all scripts run via run.py)."""

    skill_root: Path
    python: str = sys.executable

    @property
    def run_py(self) -> Path:
        return self.skill_root / "scripts" / "run.py"

    def is_present(self) -> bool:
        return self.run_py.is_file()

    def venv_initialized(self) -> bool:
        return (self.skill_root / ".venv").is_dir()
```

- [ ] **Step 6：實作 `loop_apidoc/notebooklm/runner.py`**

```python
from __future__ import annotations

import subprocess
from typing import Protocol

from pydantic import BaseModel

from loop_apidoc.notebooklm.config import SkillConfig


class CommandResult(BaseModel):
    argv: list[str]
    returncode: int
    stdout: str
    stderr: str


class ProcessRunner(Protocol):
    def __call__(self, argv: list[str]) -> CommandResult: ...


def subprocess_runner(
    config: SkillConfig, timeout_seconds: float = 300.0
) -> ProcessRunner:
    """Real runner: executes argv via subprocess, capturing only the invoked
    script's stdout/stderr — never the skill's browser state or data/ (§11)."""

    def run(argv: list[str]) -> CommandResult:
        try:
            completed = subprocess.run(
                argv,
                cwd=config.skill_root,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            return CommandResult(
                argv=argv,
                returncode=124,
                stdout=exc.stdout or "",
                stderr="Timeout waiting for answer",
            )
        return CommandResult(
            argv=argv,
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )

    return run
```

- [ ] **Step 7：執行測試確認通過**

Run: `uv run pytest tests/notebooklm/test_runner.py -v`
Expected: PASS（三個測試；timeout 測試約耗時 0.5 秒）。

- [ ] **Step 8：Commit**

```bash
git add loop_apidoc/notebooklm/__init__.py loop_apidoc/notebooklm/config.py loop_apidoc/notebooklm/runner.py tests/notebooklm/
git commit -m "feat: add notebooklm skill config and process runner"
```

---

### Task 2：型別化錯誤階層

把 spec §11 的處理分支表達為例外型別，攜帶 stdout/stderr 以利保存與診斷。

**Files:**
- Create: `loop_apidoc/notebooklm/errors.py`
- Create: `tests/notebooklm/test_errors.py`

**Interfaces:**
- Consumes: 無。
- Produces（皆繼承 `NotebookLMError`）：
  - `NotebookLMError(Exception)`：`__init__(message: str, *, stdout: str = "", stderr: str = "")`；屬性 `message`、`stdout`、`stderr`。
  - `AuthRequired`、`NotebookInaccessible`、`TransientError`、`MalformedOutput`、`SkillSetupError`、`SkillError`。

- [ ] **Step 1：寫失敗測試 `tests/notebooklm/test_errors.py`**

```python
from __future__ import annotations

import pytest

from loop_apidoc.notebooklm.errors import (
    AuthRequired,
    MalformedOutput,
    NotebookInaccessible,
    NotebookLMError,
    SkillError,
    SkillSetupError,
    TransientError,
)


def test_base_error_carries_streams():
    error = NotebookLMError("boom", stdout="out", stderr="err")
    assert error.message == "boom"
    assert error.stdout == "out"
    assert error.stderr == "err"
    assert str(error) == "boom"


@pytest.mark.parametrize(
    "cls",
    [AuthRequired, NotebookInaccessible, TransientError, MalformedOutput, SkillSetupError, SkillError],
)
def test_subclasses_are_notebooklm_errors(cls):
    error = cls("x")
    assert isinstance(error, NotebookLMError)
    assert error.stdout == ""
    assert error.stderr == ""
```

- [ ] **Step 2：執行測試確認失敗**

Run: `uv run pytest tests/notebooklm/test_errors.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'loop_apidoc.notebooklm.errors'`）。

- [ ] **Step 3：實作 `loop_apidoc/notebooklm/errors.py`**

```python
from __future__ import annotations


class NotebookLMError(Exception):
    """Base class for NotebookLM adapter failures (spec §11)."""

    def __init__(self, message: str, *, stdout: str = "", stderr: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.stdout = stdout
        self.stderr = stderr


class AuthRequired(NotebookLMError):
    """Browser session is not authenticated; stop and provide login
    instructions (spec §11: NotebookLM 未驗證 -> 停止並提供登入指示)."""


class NotebookInaccessible(NotebookLMError):
    """The notebook could not be opened; stop, do not normalize (spec §11)."""


class TransientError(NotebookLMError):
    """A timeout or transient/quota failure eligible for limited technical
    retries, counted separately from the three correction rounds (spec §11)."""


class MalformedOutput(NotebookLMError):
    """Skill exited 0 but output could not be parsed; raw stdout/stderr are
    preserved and the run stops (spec §11)."""


class SkillSetupError(NotebookLMError):
    """The run.py wrapper failed to bootstrap the skill environment."""


class SkillError(NotebookLMError):
    """Unclassified non-zero skill failure; raw output preserved."""
```

- [ ] **Step 4：執行測試確認通過**

Run: `uv run pytest tests/notebooklm/test_errors.py -v`
Expected: PASS（兩個測試函式，含 6 個 parametrize 案例）。

- [ ] **Step 5：Commit**

```bash
git add loop_apidoc/notebooklm/errors.py tests/notebooklm/test_errors.py
git commit -m "feat: add notebooklm adapter error hierarchy"
```

---

### Task 3：命令建構

把 adapter 需要的兩個操作（auth status、ask）建成透過 `run.py` 執行的 argv。對應 spec §4.1 的執行契約。

**Files:**
- Create: `loop_apidoc/notebooklm/commands.py`
- Create: `tests/notebooklm/test_commands.py`

**Interfaces:**
- Consumes: `loop_apidoc.notebooklm.config.SkillConfig`。
- Produces：
  - `build_auth_status_argv(config: SkillConfig) -> list[str]` → `[config.python, str(config.run_py), "auth_manager.py", "status"]`。
  - `build_ask_argv(config: SkillConfig, question: str, notebook_url: str) -> list[str]` → `[config.python, str(config.run_py), "ask_question.py", "--question", question, "--notebook-url", notebook_url]`。

- [ ] **Step 1：寫失敗測試 `tests/notebooklm/test_commands.py`**

```python
from __future__ import annotations

import sys
from pathlib import Path

from loop_apidoc.notebooklm.commands import build_ask_argv, build_auth_status_argv
from loop_apidoc.notebooklm.config import SkillConfig


def test_build_auth_status_argv_uses_run_py_wrapper():
    config = SkillConfig(skill_root=Path("/skill"))
    argv = build_auth_status_argv(config)
    assert argv == [
        sys.executable,
        str(Path("/skill") / "scripts" / "run.py"),
        "auth_manager.py",
        "status",
    ]


def test_build_ask_argv_uses_hyphenated_flags_via_run_py():
    config = SkillConfig(skill_root=Path("/skill"))
    argv = build_ask_argv(config, question="List endpoints", notebook_url="https://nb/x")
    assert argv[:3] == [sys.executable, str(Path("/skill") / "scripts" / "run.py"), "ask_question.py"]
    assert "--question" in argv and argv[argv.index("--question") + 1] == "List endpoints"
    assert "--notebook-url" in argv and argv[argv.index("--notebook-url") + 1] == "https://nb/x"
    # The skill is only ever invoked via run.py — never the script directly.
    assert "ask_question.py" == argv[2]
```

- [ ] **Step 2：執行測試確認失敗**

Run: `uv run pytest tests/notebooklm/test_commands.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'loop_apidoc.notebooklm.commands'`）。

- [ ] **Step 3：實作 `loop_apidoc/notebooklm/commands.py`**

```python
from __future__ import annotations

from loop_apidoc.notebooklm.config import SkillConfig


def build_auth_status_argv(config: SkillConfig) -> list[str]:
    return [config.python, str(config.run_py), "auth_manager.py", "status"]


def build_ask_argv(config: SkillConfig, question: str, notebook_url: str) -> list[str]:
    return [
        config.python,
        str(config.run_py),
        "ask_question.py",
        "--question",
        question,
        "--notebook-url",
        notebook_url,
    ]
```

- [ ] **Step 4：執行測試確認通過**

Run: `uv run pytest tests/notebooklm/test_commands.py -v`
Expected: PASS（兩個測試）。

- [ ] **Step 5：Commit**

```bash
git add loop_apidoc/notebooklm/commands.py tests/notebooklm/test_commands.py
git commit -m "feat: add notebooklm command construction via run.py"
```

---

### Task 4：輸出模型與解析

定義 adapter 回傳模型，並解析 `auth status` 與 `ask_question` 的純文字 stdout。對應「輸出解析」（spec §12.1）。

**Files:**
- Create: `loop_apidoc/notebooklm/models.py`
- Create: `loop_apidoc/notebooklm/parsing.py`
- Create: `tests/notebooklm/test_parsing.py`

**Interfaces:**
- Consumes: `loop_apidoc.notebooklm.errors.MalformedOutput`。
- Produces：
  - `AuthStatus(BaseModel)`：`authenticated: bool`、`raw_stdout: str`、`stale_warning: str | None = None`。
  - `AskResult(BaseModel)`：`question: str`、`notebook_url: str`、`answer: str`、`raw_stdout: str`、`returncode: int`。
  - `SEPARATOR = "=" * 60`、`FOLLOW_UP_MARKER = "EXTREMELY IMPORTANT: Is that ALL you need to know?"`（模組常數）。
  - `parse_auth_status(stdout: str) -> AuthStatus`：含 `Authenticated: Yes` → True；含 `Authenticated: No` → False；皆無則 `raise MalformedOutput`。偵測 `⚠️ Browser state is` 開頭行存入 `stale_warning`。
  - `parse_ask_answer(stdout: str) -> str`：取 `FOLLOW_UP_MARKER` 之前、`Question:` 標頭後第一條 `SEPARATOR` 之後的文字並 `strip()`；缺任一標記或答案為空則 `raise MalformedOutput`。

- [ ] **Step 1：寫失敗測試 `tests/notebooklm/test_parsing.py`**

```python
from __future__ import annotations

import pytest

from loop_apidoc.notebooklm.errors import MalformedOutput
from loop_apidoc.notebooklm.parsing import parse_ask_answer, parse_auth_status

SEP = "=" * 60


def _ask_stdout(answer: str = "GET /users and POST /users.") -> str:
    return (
        "💬 Asking: List endpoints\n"
        "📚 Notebook: https://nb/x\n"
        "  ✅ Got answer!\n\n"
        f"{SEP}\n"
        "Question: List endpoints\n"
        f"{SEP}\n\n"
        f"{answer}\n\n"
        "EXTREMELY IMPORTANT: Is that ALL you need to know? You can always ask another question!\n\n"
        f"{SEP}\n"
    )


def test_parse_auth_status_yes_with_stale_warning():
    stdout = (
        "⚠️ Browser state is 9.2 days old, may need re-authentication\n"
        "🔐 Authentication Status:\n"
        "  Authenticated: Yes\n"
        "  State file: /x/state.json\n"
    )
    status = parse_auth_status(stdout)
    assert status.authenticated is True
    assert status.stale_warning is not None
    assert "9.2 days old" in status.stale_warning
    assert status.raw_stdout == stdout


def test_parse_auth_status_no():
    status = parse_auth_status("🔐 Authentication Status:\n  Authenticated: No\n")
    assert status.authenticated is False
    assert status.stale_warning is None


def test_parse_auth_status_unparsable_raises():
    with pytest.raises(MalformedOutput):
        parse_auth_status("totally unrelated output")


def test_parse_ask_answer_extracts_between_markers():
    assert parse_ask_answer(_ask_stdout()) == "GET /users and POST /users."


def test_parse_ask_answer_multiline_answer():
    answer = "Line one.\nLine two.\nLine three."
    assert parse_ask_answer(_ask_stdout(answer)) == answer


def test_parse_ask_answer_missing_followup_raises():
    bad = f"{SEP}\nQuestion: q\n{SEP}\n\nsome answer\n"  # no follow-up marker
    with pytest.raises(MalformedOutput):
        parse_ask_answer(bad)


def test_parse_ask_answer_empty_answer_raises():
    with pytest.raises(MalformedOutput):
        parse_ask_answer(_ask_stdout(answer="   "))
```

- [ ] **Step 2：執行測試確認失敗**

Run: `uv run pytest tests/notebooklm/test_parsing.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'loop_apidoc.notebooklm.parsing'`）。

- [ ] **Step 3：實作 `loop_apidoc/notebooklm/models.py`**

```python
from __future__ import annotations

from pydantic import BaseModel


class AuthStatus(BaseModel):
    authenticated: bool
    raw_stdout: str
    stale_warning: str | None = None


class AskResult(BaseModel):
    question: str
    notebook_url: str
    answer: str
    raw_stdout: str
    returncode: int
```

- [ ] **Step 4：實作 `loop_apidoc/notebooklm/parsing.py`**

```python
from __future__ import annotations

from loop_apidoc.notebooklm.errors import MalformedOutput
from loop_apidoc.notebooklm.models import AuthStatus

SEPARATOR = "=" * 60
FOLLOW_UP_MARKER = "EXTREMELY IMPORTANT: Is that ALL you need to know?"
_AUTH_YES = "Authenticated: Yes"
_AUTH_NO = "Authenticated: No"
_STALE_PREFIX = "⚠️ Browser state is"


def parse_auth_status(stdout: str) -> AuthStatus:
    if _AUTH_YES in stdout:
        authenticated = True
    elif _AUTH_NO in stdout:
        authenticated = False
    else:
        raise MalformedOutput(
            "auth_manager status output missing 'Authenticated:' line",
            stdout=stdout,
        )
    stale_warning = None
    for line in stdout.splitlines():
        stripped = line.strip()
        if stripped.startswith(_STALE_PREFIX):
            stale_warning = stripped
            break
    return AuthStatus(
        authenticated=authenticated, raw_stdout=stdout, stale_warning=stale_warning
    )


def parse_ask_answer(stdout: str) -> str:
    follow_idx = stdout.find(FOLLOW_UP_MARKER)
    if follow_idx == -1:
        raise MalformedOutput(
            "ask_question output missing follow-up reminder marker", stdout=stdout
        )
    head = stdout[:follow_idx]
    question_idx = head.find("Question:")
    if question_idx == -1:
        raise MalformedOutput(
            "ask_question output missing 'Question:' header", stdout=stdout
        )
    sep_idx = head.find(SEPARATOR, question_idx)
    if sep_idx == -1:
        raise MalformedOutput(
            "ask_question output missing closing separator after question",
            stdout=stdout,
        )
    answer = head[sep_idx + len(SEPARATOR) :].strip()
    if not answer:
        raise MalformedOutput("ask_question produced an empty answer", stdout=stdout)
    return answer
```

- [ ] **Step 5：執行測試確認通過**

Run: `uv run pytest tests/notebooklm/test_parsing.py -v`
Expected: PASS（七個測試）。

- [ ] **Step 6：Commit**

```bash
git add loop_apidoc/notebooklm/models.py loop_apidoc/notebooklm/parsing.py tests/notebooklm/test_parsing.py
git commit -m "feat: add notebooklm output models and parsing"
```

---

### Task 5：失敗分類

把非零的 skill 結果映射為 spec §11 的型別化錯誤。marker 字串取自參考契約，第一個命中者勝出。

**Files:**
- Create: `loop_apidoc/notebooklm/classify.py`
- Create: `tests/notebooklm/test_classify.py`

**Interfaces:**
- Consumes: `loop_apidoc.notebooklm.errors.*`、`loop_apidoc.notebooklm.runner.CommandResult`。
- Produces：
  - `classify_failure(result: CommandResult) -> NotebookLMError`：依序比對 `stdout+"\n"+stderr`：`Not authenticated` → `AuthRequired`；`Timeout waiting for answer` → `TransientError`；`Could not find query input` → `TransientError`；`Failed to set up environment` → `SkillSetupError`；`❌ Error:` → `NotebookInaccessible`；其餘 → `SkillError`。回傳的例外都帶上 `stdout`／`stderr`。

- [ ] **Step 1：寫失敗測試 `tests/notebooklm/test_classify.py`**

```python
from __future__ import annotations

import pytest

from loop_apidoc.notebooklm.classify import classify_failure
from loop_apidoc.notebooklm.errors import (
    AuthRequired,
    NotebookInaccessible,
    SkillError,
    SkillSetupError,
    TransientError,
)
from loop_apidoc.notebooklm.runner import CommandResult


def _result(stdout: str = "", stderr: str = "", code: int = 1) -> CommandResult:
    return CommandResult(argv=["x"], returncode=code, stdout=stdout, stderr=stderr)


@pytest.mark.parametrize(
    "stdout, expected",
    [
        ("⚠️ Not authenticated. Run: ...", AuthRequired),
        ("❌ Timeout waiting for answer", TransientError),
        ("❌ Could not find query input", TransientError),
        ("❌ Failed to set up environment", SkillSetupError),
        ("❌ Error: navigation failed\nTraceback ...", NotebookInaccessible),
        ("some unexpected failure", SkillError),
    ],
)
def test_classify_failure_maps_markers(stdout, expected):
    error = classify_failure(_result(stdout=stdout))
    assert isinstance(error, expected)
    assert error.stdout == stdout


def test_classify_preserves_streams():
    error = classify_failure(_result(stdout="o", stderr="e"))
    assert error.stdout == "o"
    assert error.stderr == "e"


def test_auth_wins_over_error_marker_when_both_present():
    # Not-authenticated must take precedence over a generic ❌ Error: line.
    error = classify_failure(_result(stdout="⚠️ Not authenticated\n❌ Error: x"))
    assert isinstance(error, AuthRequired)
```

- [ ] **Step 2：執行測試確認失敗**

Run: `uv run pytest tests/notebooklm/test_classify.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'loop_apidoc.notebooklm.classify'`）。

- [ ] **Step 3：實作 `loop_apidoc/notebooklm/classify.py`**

```python
from __future__ import annotations

from loop_apidoc.notebooklm.errors import (
    AuthRequired,
    NotebookInaccessible,
    NotebookLMError,
    SkillError,
    SkillSetupError,
    TransientError,
)
from loop_apidoc.notebooklm.runner import CommandResult

# Markers grounded in notebooklm-skill source (see Plan 2 reference contract).
_NOT_AUTH = "Not authenticated"
_TIMEOUT = "Timeout waiting for answer"
_NO_INPUT = "Could not find query input"
_SETUP_FAILED = "Failed to set up environment"
_NAV_ERROR = "❌ Error:"


def classify_failure(result: CommandResult) -> NotebookLMError:
    """Map a non-zero skill result to a typed error. First match wins."""
    text = f"{result.stdout}\n{result.stderr}"
    streams = {"stdout": result.stdout, "stderr": result.stderr}
    if _NOT_AUTH in text:
        return AuthRequired("NotebookLM browser session is not authenticated", **streams)
    if _TIMEOUT in text:
        return TransientError("Timed out waiting for a NotebookLM answer", **streams)
    if _NO_INPUT in text:
        return TransientError("NotebookLM query input was not found", **streams)
    if _SETUP_FAILED in text:
        return SkillSetupError("notebooklm-skill environment setup failed", **streams)
    if _NAV_ERROR in text:
        return NotebookInaccessible("Could not open the NotebookLM notebook", **streams)
    return SkillError(f"notebooklm-skill exited with code {result.returncode}", **streams)
```

- [ ] **Step 4：執行測試確認通過**

Run: `uv run pytest tests/notebooklm/test_classify.py -v`
Expected: PASS（三個測試函式，含 6 個 parametrize 案例）。

- [ ] **Step 5：Commit**

```bash
git add loop_apidoc/notebooklm/classify.py tests/notebooklm/test_classify.py
git commit -m "feat: add notebooklm failure classification"
```

---

### Task 6：NotebookLMAdapter

把命令建構、執行、解析與分類組裝成無狀態 adapter。`auth_status()` 與 `ask()` 為 Plan 3 orchestrator 的進入點。

**Files:**
- Create: `loop_apidoc/notebooklm/adapter.py`
- Create: `tests/notebooklm/test_adapter.py`

**Interfaces:**
- Consumes: `commands.{build_auth_status_argv, build_ask_argv}`、`parsing.{parse_auth_status, parse_ask_answer}`、`classify.classify_failure`、`config.SkillConfig`、`runner.ProcessRunner`、`models.{AuthStatus, AskResult}`。
- Produces：
  - `NotebookLMAdapter(config: SkillConfig, runner: ProcessRunner)`。
  - `auth_status() -> AuthStatus`：執行 auth argv；`returncode != 0` → `raise classify_failure(result)`；否則 `parse_auth_status(result.stdout)`。
  - `ask(question: str, notebook_url: str) -> AskResult`：執行 ask argv；`returncode != 0` → `raise classify_failure(result)`；否則 `parse_ask_answer`（可能 `raise MalformedOutput`）並回傳 `AskResult`。

- [ ] **Step 1：寫失敗測試 `tests/notebooklm/test_adapter.py`**

```python
from __future__ import annotations

from pathlib import Path

import pytest

from loop_apidoc.notebooklm.adapter import NotebookLMAdapter
from loop_apidoc.notebooklm.config import SkillConfig
from loop_apidoc.notebooklm.errors import AuthRequired, MalformedOutput, TransientError
from loop_apidoc.notebooklm.runner import CommandResult

SEP = "=" * 60


def _runner(result: CommandResult):
    def run(argv: list[str]) -> CommandResult:
        return CommandResult(argv=argv, returncode=result.returncode, stdout=result.stdout, stderr=result.stderr)
    return run


def _ok(stdout: str) -> CommandResult:
    return CommandResult(argv=[], returncode=0, stdout=stdout, stderr="")


def _fail(stdout: str) -> CommandResult:
    return CommandResult(argv=[], returncode=1, stdout=stdout, stderr="")


def _config() -> SkillConfig:
    return SkillConfig(skill_root=Path("/skill"))


def test_auth_status_parses_success():
    adapter = NotebookLMAdapter(_config(), _runner(_ok("  Authenticated: Yes\n")))
    status = adapter.auth_status()
    assert status.authenticated is True


def test_ask_returns_parsed_answer():
    stdout = (
        f"{SEP}\nQuestion: List endpoints\n{SEP}\n\n"
        "GET /users.\n\n"
        "EXTREMELY IMPORTANT: Is that ALL you need to know?\n\n"
        f"{SEP}\n"
    )
    adapter = NotebookLMAdapter(_config(), _runner(_ok(stdout)))
    result = adapter.ask("List endpoints", "https://nb/x")
    assert result.answer == "GET /users."
    assert result.question == "List endpoints"
    assert result.notebook_url == "https://nb/x"
    assert result.raw_stdout == stdout


def test_ask_raises_auth_required_on_marker():
    adapter = NotebookLMAdapter(_config(), _runner(_fail("⚠️ Not authenticated")))
    with pytest.raises(AuthRequired):
        adapter.ask("q", "https://nb/x")


def test_ask_raises_transient_on_timeout():
    adapter = NotebookLMAdapter(_config(), _runner(_fail("❌ Timeout waiting for answer")))
    with pytest.raises(TransientError):
        adapter.ask("q", "https://nb/x")


def test_ask_raises_malformed_on_unparsable_success():
    adapter = NotebookLMAdapter(_config(), _runner(_ok("garbage with no markers")))
    with pytest.raises(MalformedOutput):
        adapter.ask("q", "https://nb/x")
```

- [ ] **Step 2：執行測試確認失敗**

Run: `uv run pytest tests/notebooklm/test_adapter.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'loop_apidoc.notebooklm.adapter'`）。

- [ ] **Step 3：實作 `loop_apidoc/notebooklm/adapter.py`**

```python
from __future__ import annotations

from loop_apidoc.notebooklm.classify import classify_failure
from loop_apidoc.notebooklm.commands import build_ask_argv, build_auth_status_argv
from loop_apidoc.notebooklm.config import SkillConfig
from loop_apidoc.notebooklm.models import AskResult, AuthStatus
from loop_apidoc.notebooklm.parsing import parse_ask_answer, parse_auth_status
from loop_apidoc.notebooklm.runner import ProcessRunner


class NotebookLMAdapter:
    """Stateless wrapper over the notebooklm-skill run.py contract. Each ask()
    is an independent session with no conversational context (spec §4.2)."""

    def __init__(self, config: SkillConfig, runner: ProcessRunner) -> None:
        self._config = config
        self._runner = runner

    def auth_status(self) -> AuthStatus:
        result = self._runner(build_auth_status_argv(self._config))
        if result.returncode != 0:
            raise classify_failure(result)
        return parse_auth_status(result.stdout)

    def ask(self, question: str, notebook_url: str) -> AskResult:
        result = self._runner(build_ask_argv(self._config, question, notebook_url))
        if result.returncode != 0:
            raise classify_failure(result)
        answer = parse_ask_answer(result.stdout)
        return AskResult(
            question=question,
            notebook_url=notebook_url,
            answer=answer,
            raw_stdout=result.stdout,
            returncode=result.returncode,
        )
```

- [ ] **Step 4：執行測試確認通過**

Run: `uv run pytest tests/notebooklm/test_adapter.py -v`
Expected: PASS（五個測試）。

- [ ] **Step 5：Commit**

```bash
git add loop_apidoc/notebooklm/adapter.py tests/notebooklm/test_adapter.py
git commit -m "feat: add NotebookLMAdapter wiring run/parse/classify"
```

---

### Task 7：有限技術重試

提供只重試 `TransientError` 的重試器，達上限即停止；其餘錯誤立即傳遞。對應 spec §11「有限次技術重試，與三輪內容修正分開計數」與 §12.1「retry 與停止條件」。

**Files:**
- Create: `loop_apidoc/notebooklm/retry.py`
- Create: `tests/notebooklm/test_retry.py`

**Interfaces:**
- Consumes: `loop_apidoc.notebooklm.errors.TransientError`。
- Produces：
  - `run_with_retries(operation: Callable[[], T], *, max_attempts: int = 3) -> T`：最多嘗試 `max_attempts` 次；只在 `TransientError` 時重試；非 `TransientError`（含其他 `NotebookLMError`）立即向外傳遞；耗盡後重新拋出最後一個 `TransientError`；`max_attempts < 1` 時 `raise ValueError`。

- [ ] **Step 1：寫失敗測試 `tests/notebooklm/test_retry.py`**

```python
from __future__ import annotations

import pytest

from loop_apidoc.notebooklm.errors import AuthRequired, TransientError
from loop_apidoc.notebooklm.retry import run_with_retries


def test_succeeds_after_transient_then_success():
    calls = {"n": 0}

    def operation():
        calls["n"] += 1
        if calls["n"] < 2:
            raise TransientError("temporary")
        return "ok"

    assert run_with_retries(operation, max_attempts=3) == "ok"
    assert calls["n"] == 2


def test_non_transient_propagates_immediately_without_retry():
    calls = {"n": 0}

    def operation():
        calls["n"] += 1
        raise AuthRequired("stop")

    with pytest.raises(AuthRequired):
        run_with_retries(operation, max_attempts=3)
    assert calls["n"] == 1  # not retried


def test_exhausts_attempts_then_reraises_last_transient():
    calls = {"n": 0}

    def operation():
        calls["n"] += 1
        raise TransientError(f"fail {calls['n']}")

    with pytest.raises(TransientError):
        run_with_retries(operation, max_attempts=3)
    assert calls["n"] == 3


def test_invalid_max_attempts_raises():
    with pytest.raises(ValueError):
        run_with_retries(lambda: "x", max_attempts=0)
```

- [ ] **Step 2：執行測試確認失敗**

Run: `uv run pytest tests/notebooklm/test_retry.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'loop_apidoc.notebooklm.retry'`）。

- [ ] **Step 3：實作 `loop_apidoc/notebooklm/retry.py`**

```python
from __future__ import annotations

from typing import Callable, TypeVar

from loop_apidoc.notebooklm.errors import TransientError

T = TypeVar("T")


def run_with_retries(operation: Callable[[], T], *, max_attempts: int = 3) -> T:
    """Run operation, retrying ONLY on TransientError up to max_attempts total
    attempts. Non-transient errors propagate immediately (stop). These technical
    retries are counted separately from the three correction rounds (spec §11)."""
    if max_attempts < 1:
        raise ValueError("max_attempts must be >= 1")
    last_error: TransientError | None = None
    for _ in range(max_attempts):
        try:
            return operation()
        except TransientError as error:
            last_error = error
    assert last_error is not None
    raise last_error
```

- [ ] **Step 4：執行測試確認通過**

Run: `uv run pytest tests/notebooklm/test_retry.py -v`
Expected: PASS（四個測試）。

- [ ] **Step 5：Commit**

```bash
git add loop_apidoc/notebooklm/retry.py tests/notebooklm/test_retry.py
git commit -m "feat: add limited technical retry for transient errors"
```

---

### Task 8：doctor 檢查與報告

實作環境預檢的各項檢查與報告組裝／渲染。每項檢查唯讀；auth 檢查在 skill `.venv` 尚未建立時跳過，避免觸發環境建置（保持唯讀）。

**Files:**
- Create: `loop_apidoc/doctor/__init__.py`
- Create: `loop_apidoc/doctor/models.py`
- Create: `loop_apidoc/doctor/checks.py`
- Create: `loop_apidoc/doctor/report.py`
- Create: `tests/doctor/__init__.py`
- Create: `tests/doctor/test_checks.py`
- Create: `tests/doctor/test_report.py`

**Interfaces:**
- Consumes: `loop_apidoc.notebooklm.{config.SkillConfig, adapter.NotebookLMAdapter, runner.{ProcessRunner, CommandResult, subprocess_runner}, errors.NotebookLMError}`。
- Produces：
  - `CheckResult(BaseModel)`：`name: str`、`ok: bool`、`detail: str`、`remedy: str | None = None`、`required: bool = True`。
  - `DoctorReport(BaseModel)`：`checks: list[CheckResult]`；property `ok -> bool`（所有 `required` 為 True 的檢查皆 `ok`）。
  - `check_python() -> CheckResult`（required；`sys.version_info >= (3, 11)`）。
  - `check_skill_present(config) -> CheckResult`（required；`config.is_present()`）。
  - `check_skill_requirements(config) -> CheckResult`（非 required；`requirements.txt` 是否存在，並標註 `.venv` 是否已建立）。
  - `check_chrome() -> CheckResult`（非 required；`shutil.which` 候選名或 macOS `/Applications/Google Chrome.app`）。
  - `check_validation_tools() -> CheckResult`（required；`importlib.util.find_spec` 檢查 `openapi_spec_validator`、`jsonschema`、`yaml`）。
  - `check_auth(config, runner: ProcessRunner | None = None) -> CheckResult`（非 required；skill 不存在或 `.venv` 未建立 → 跳過並回 `ok=False`；否則以 `runner`（預設 `subprocess_runner(config)`）建立 `NotebookLMAdapter` 取 `auth_status()`，捕捉 `NotebookLMError`）。
  - `run_checks(config, runner: ProcessRunner | None = None) -> list[CheckResult]`：依序回傳上述六項（auth 傳入 `runner`）。
  - `build_report(checks) -> DoctorReport`、`render_report(report) -> str`。

- [ ] **Step 1：建立 `tests/doctor/__init__.py`**

```python
```

- [ ] **Step 2：寫失敗測試 `tests/doctor/test_checks.py`**

```python
from __future__ import annotations

from pathlib import Path

from loop_apidoc.doctor.checks import (
    check_auth,
    check_python,
    check_skill_present,
    check_validation_tools,
    run_checks,
)
from loop_apidoc.notebooklm.config import SkillConfig
from loop_apidoc.notebooklm.runner import CommandResult


def _skill(tmp_path: Path, *, with_run_py: bool = False, with_venv: bool = False) -> SkillConfig:
    if with_run_py:
        (tmp_path / "scripts").mkdir(exist_ok=True)
        (tmp_path / "scripts" / "run.py").write_text("", encoding="utf-8")
    if with_venv:
        (tmp_path / ".venv").mkdir(exist_ok=True)
    return SkillConfig(skill_root=tmp_path)


def test_check_python_passes_on_current_runtime():
    result = check_python()
    assert result.ok is True
    assert result.required is True


def test_check_validation_tools_present():
    # openapi-spec-validator / jsonschema / pyyaml are project dependencies.
    result = check_validation_tools()
    assert result.ok is True


def test_check_skill_present_false_when_missing(tmp_path: Path):
    result = check_skill_present(_skill(tmp_path))
    assert result.ok is False
    assert result.remedy is not None


def test_check_auth_skipped_without_venv(tmp_path: Path):
    # No real subprocess must run when the skill .venv is absent.
    result = check_auth(_skill(tmp_path, with_run_py=True), runner=None)
    assert result.ok is False
    assert result.required is False
    assert "略過" in result.detail


def test_check_auth_uses_injected_runner_when_ready(tmp_path: Path):
    config = _skill(tmp_path, with_run_py=True, with_venv=True)

    def fake_runner(argv: list[str]) -> CommandResult:
        return CommandResult(argv=argv, returncode=0, stdout="  Authenticated: Yes\n", stderr="")

    result = check_auth(config, runner=fake_runner)
    assert result.ok is True


def test_run_checks_returns_all_six(tmp_path: Path):
    def fake_runner(argv: list[str]) -> CommandResult:
        return CommandResult(argv=argv, returncode=0, stdout="  Authenticated: No\n", stderr="")

    results = run_checks(_skill(tmp_path, with_run_py=True, with_venv=True), runner=fake_runner)
    names = [r.name for r in results]
    assert names == ["python", "notebooklm-skill", "skill-requirements", "chrome", "validation-tools", "auth"]
```

- [ ] **Step 3：執行測試確認失敗**

Run: `uv run pytest tests/doctor/test_checks.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'loop_apidoc.doctor'`）。

- [ ] **Step 4：建立 `loop_apidoc/doctor/__init__.py`**

```python
"""Environment preflight (loop-apidoc doctor)."""
```

- [ ] **Step 5：實作 `loop_apidoc/doctor/models.py`**

```python
from __future__ import annotations

from pydantic import BaseModel


class CheckResult(BaseModel):
    name: str
    ok: bool
    detail: str
    remedy: str | None = None
    required: bool = True


class DoctorReport(BaseModel):
    checks: list[CheckResult]

    @property
    def ok(self) -> bool:
        return all(check.ok for check in self.checks if check.required)
```

- [ ] **Step 6：實作 `loop_apidoc/doctor/checks.py`**

```python
from __future__ import annotations

import importlib.util
import shutil
import sys
from pathlib import Path

from loop_apidoc.doctor.models import CheckResult
from loop_apidoc.notebooklm.adapter import NotebookLMAdapter
from loop_apidoc.notebooklm.config import SkillConfig
from loop_apidoc.notebooklm.errors import NotebookLMError
from loop_apidoc.notebooklm.runner import ProcessRunner, subprocess_runner

_MIN_PYTHON = (3, 11)
_VALIDATION_MODULES = ("openapi_spec_validator", "jsonschema", "yaml")
_CHROME_CANDIDATES = (
    "google-chrome",
    "google-chrome-stable",
    "chromium",
    "chromium-browser",
)
_MACOS_CHROME = Path("/Applications/Google Chrome.app")
_AUTH_SETUP_REMEDY = "於 skill 目錄執行 python scripts/run.py auth_manager.py setup"


def check_python() -> CheckResult:
    ok = sys.version_info >= _MIN_PYTHON
    version = ".".join(str(part) for part in sys.version_info[:3])
    return CheckResult(
        name="python",
        ok=ok,
        detail=f"Python {version}",
        remedy=None if ok else "需要 Python 3.11 以上",
    )


def check_skill_present(config: SkillConfig) -> CheckResult:
    ok = config.is_present()
    return CheckResult(
        name="notebooklm-skill",
        ok=ok,
        detail=f"run.py {'存在' if ok else '不存在'}：{config.run_py}",
        remedy=None if ok else "git clone https://github.com/PleasePrompto/notebooklm-skill",
    )


def check_skill_requirements(config: SkillConfig) -> CheckResult:
    requirements = config.skill_root / "requirements.txt"
    ok = requirements.is_file()
    if ok and config.venv_initialized():
        detail = "requirements.txt 存在，.venv 已建立"
    elif ok:
        detail = "requirements.txt 存在，.venv 尚未建立（首次執行時自動建立）"
    else:
        detail = f"找不到 requirements.txt：{requirements}"
    return CheckResult(
        name="skill-requirements",
        ok=ok,
        detail=detail,
        remedy=None if ok else "確認 notebooklm-skill checkout 完整",
        required=False,
    )


def check_chrome() -> CheckResult:
    found = next((name for name in _CHROME_CANDIDATES if shutil.which(name)), None)
    if found is None and _MACOS_CHROME.exists():
        found = str(_MACOS_CHROME)
    ok = found is not None
    return CheckResult(
        name="chrome",
        ok=ok,
        detail=f"找到 Chrome：{found}" if ok else "未偵測到 Chrome",
        remedy=None if ok else "安裝 Google Chrome；skill 首次執行時 patchright install chrome",
        required=False,
    )


def check_validation_tools() -> CheckResult:
    missing = [m for m in _VALIDATION_MODULES if importlib.util.find_spec(m) is None]
    ok = not missing
    return CheckResult(
        name="validation-tools",
        ok=ok,
        detail="openapi-spec-validator / jsonschema / pyyaml 均可載入"
        if ok
        else f"缺少模組：{', '.join(missing)}",
        remedy=None if ok else "uv sync 安裝專案依賴",
    )


def check_auth(config: SkillConfig, runner: ProcessRunner | None = None) -> CheckResult:
    if not config.is_present():
        return CheckResult(
            name="auth",
            ok=False,
            detail="略過：notebooklm-skill 不存在",
            remedy="先安裝 notebooklm-skill",
            required=False,
        )
    if not config.venv_initialized():
        return CheckResult(
            name="auth",
            ok=False,
            detail="略過：skill .venv 尚未建立，無法在不修改 skill 的情況下檢查驗證狀態",
            remedy="首次執行 loop-apidoc run 會建立 skill 環境",
            required=False,
        )
    adapter = NotebookLMAdapter(config, runner or subprocess_runner(config))
    try:
        status = adapter.auth_status()
    except NotebookLMError as error:
        return CheckResult(
            name="auth",
            ok=False,
            detail=f"驗證檢查失敗：{error.message}",
            remedy=_AUTH_SETUP_REMEDY,
            required=False,
        )
    return CheckResult(
        name="auth",
        ok=status.authenticated,
        detail="已驗證" if status.authenticated else "未驗證",
        remedy=None if status.authenticated else _AUTH_SETUP_REMEDY,
        required=False,
    )


def run_checks(config: SkillConfig, runner: ProcessRunner | None = None) -> list[CheckResult]:
    return [
        check_python(),
        check_skill_present(config),
        check_skill_requirements(config),
        check_chrome(),
        check_validation_tools(),
        check_auth(config, runner=runner),
    ]
```

- [ ] **Step 7：實作 `loop_apidoc/doctor/report.py`**

```python
from __future__ import annotations

from loop_apidoc.doctor.models import CheckResult, DoctorReport


def build_report(checks: list[CheckResult]) -> DoctorReport:
    return DoctorReport(checks=checks)


def render_report(report: DoctorReport) -> str:
    lines = ["loop-apidoc doctor", ""]
    for check in report.checks:
        if check.ok:
            symbol = "✅"
        elif check.required:
            symbol = "❌"
        else:
            symbol = "⚠️"
        lines.append(f"{symbol} {check.name}: {check.detail}")
        if not check.ok and check.remedy:
            lines.append(f"    → {check.remedy}")
    lines.append("")
    lines.append("整體狀態：通過" if report.ok else "整體狀態：未通過")
    return "\n".join(lines)
```

- [ ] **Step 8：寫報告測試 `tests/doctor/test_report.py`**

```python
from __future__ import annotations

from loop_apidoc.doctor.models import CheckResult
from loop_apidoc.doctor.report import build_report, render_report


def test_report_ok_ignores_non_required_failures():
    checks = [
        CheckResult(name="python", ok=True, detail="3.12"),
        CheckResult(name="chrome", ok=False, detail="未偵測到 Chrome", remedy="安裝 Chrome", required=False),
    ]
    report = build_report(checks)
    assert report.ok is True


def test_report_not_ok_when_required_fails():
    checks = [
        CheckResult(name="notebooklm-skill", ok=False, detail="不存在", remedy="git clone ...", required=True),
    ]
    assert build_report(checks).ok is False


def test_render_marks_required_failure_and_remedy():
    checks = [
        CheckResult(name="python", ok=True, detail="Python 3.12.11"),
        CheckResult(name="notebooklm-skill", ok=False, detail="不存在", remedy="git clone ...", required=True),
        CheckResult(name="chrome", ok=False, detail="未偵測到 Chrome", required=False),
    ]
    text = render_report(build_report(checks))
    assert "✅ python" in text
    assert "❌ notebooklm-skill" in text
    assert "→ git clone ..." in text
    assert "⚠️ chrome" in text
    assert "整體狀態：未通過" in text
```

- [ ] **Step 9：執行 doctor 測試確認通過**

Run: `uv run pytest tests/doctor/ -v`
Expected: PASS（`test_checks.py` 六個 + `test_report.py` 三個）。

- [ ] **Step 10：Commit**

```bash
git add loop_apidoc/doctor/ tests/doctor/
git commit -m "feat: add doctor environment checks and report"
```

---

### Task 9：`loop-apidoc doctor` CLI 命令

把 doctor 接上 CLI，產出 spec §5 的 `loop-apidoc doctor`。唯讀；環境就緒則 exit 0，必要檢查失敗則 exit 1。

**Files:**
- Modify: `loop_apidoc/cli.py`
- Create: `tests/test_cli_doctor.py`

**Interfaces:**
- Consumes: `loop_apidoc.notebooklm.config.SkillConfig`、`loop_apidoc.doctor.checks.run_checks`、`loop_apidoc.doctor.report.{build_report, render_report}`。
- Produces：CLI 子命令 `doctor`，選項 `--skill-root`（預設 `Path("notebooklm-skill")`，可由環境變數 `LOOP_APIDOC_SKILL_ROOT` 覆寫）。輸出 `render_report` 文字；`report.ok` 為 True → `raise typer.Exit(0)`，否則 `raise typer.Exit(1)`。

- [ ] **Step 1：寫失敗測試 `tests/test_cli_doctor.py`**

```python
from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from loop_apidoc.cli import app

runner = CliRunner()


def test_doctor_passes_when_skill_present_and_no_venv(tmp_path: Path):
    # Skill present but no .venv -> auth check is skipped (no real subprocess),
    # required checks (python, skill-present, validation-tools) pass -> exit 0.
    skill = tmp_path / "notebooklm-skill"
    (skill / "scripts").mkdir(parents=True)
    (skill / "scripts" / "run.py").write_text("", encoding="utf-8")
    (skill / "requirements.txt").write_text("patchright==1.55.2\n", encoding="utf-8")

    result = runner.invoke(app, ["doctor", "--skill-root", str(skill)])

    assert result.exit_code == 0, result.stdout
    assert "loop-apidoc doctor" in result.stdout
    assert "整體狀態：通過" in result.stdout
    assert "✅ notebooklm-skill" in result.stdout


def test_doctor_fails_when_skill_missing(tmp_path: Path):
    missing = tmp_path / "absent-skill"

    result = runner.invoke(app, ["doctor", "--skill-root", str(missing)])

    assert result.exit_code == 1
    assert "❌ notebooklm-skill" in result.stdout
    assert "整體狀態：未通過" in result.stdout
```

- [ ] **Step 2：執行測試確認失敗**

Run: `uv run pytest tests/test_cli_doctor.py -v`
Expected: FAIL（`doctor` 子命令尚不存在，Typer 以 exit code 2 回報「No such command」）。

- [ ] **Step 3：把 `loop_apidoc/cli.py` 整檔取代為下列內容（新增 `doctor` 命令與其匯入）**

```python
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import typer

from loop_apidoc.doctor.checks import run_checks
from loop_apidoc.doctor.report import build_report, render_report
from loop_apidoc.manifest.builder import build_manifest
from loop_apidoc.notebooklm.config import SkillConfig

app = typer.Typer(
    help="Loop 來源依據式 API 文件 pipeline",
    no_args_is_help=True,
)


@app.callback()
def _root() -> None:
    """Loop 來源依據式 API 文件 pipeline。"""


@app.command()
def manifest(
    sources: Path = typer.Option(
        ...,
        "--sources",
        help="本機來源目錄",
        exists=True,
        file_okay=False,
        dir_okay=True,
        readable=True,
    ),
    url: list[str] = typer.Option(
        [],
        "--url",
        help="公開來源 URL，可重複指定",
    ),
    output: Path | None = typer.Option(
        None,
        "--output",
        help="manifest.json 輸出路徑；省略則輸出至 stdout",
    ),
) -> None:
    """掃描本機來源並建立來源 manifest。"""
    generated_at = datetime.now(timezone.utc)
    result = build_manifest(
        sources_root=sources,
        urls=list(url),
        generated_at=generated_at,
    )
    payload = result.model_dump_json(indent=2)
    if output is None:
        typer.echo(payload)
    else:
        output.write_text(payload, encoding="utf-8")
        typer.echo(f"manifest 已寫入 {output}")


@app.command()
def doctor(
    skill_root: Path = typer.Option(
        Path("notebooklm-skill"),
        "--skill-root",
        envvar="LOOP_APIDOC_SKILL_ROOT",
        help="notebooklm-skill checkout 目錄",
    ),
) -> None:
    """檢查執行環境：Python、NotebookLM skill、依賴、Chrome、驗證狀態與驗證工具。"""
    config = SkillConfig(skill_root=skill_root)
    report = build_report(run_checks(config))
    typer.echo(render_report(report))
    raise typer.Exit(code=0 if report.ok else 1)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4：執行 CLI 測試確認通過**

Run: `uv run pytest tests/test_cli_doctor.py -v`
Expected: PASS（兩個測試）。

- [ ] **Step 5：執行整體測試套件**

Run: `uv run pytest`
Expected: 全部 PASS（Plan 1 的 20 個 + 本計畫新增約 30 個）。

- [ ] **Step 6：手動驗證 doctor 端到端**

```bash
uv run loop-apidoc doctor --skill-root /tmp/no-such-skill
echo "exit=$?"
```

Expected: 輸出 doctor 報告，`❌ notebooklm-skill` 與「整體狀態：未通過」，`exit=1`。

- [ ] **Step 7：Commit**

```bash
git add loop_apidoc/cli.py tests/test_cli_doctor.py
git commit -m "feat: add loop-apidoc doctor command"
```

---

## 後續計畫銜接

- Plan 3（擷取＋規格化計畫）使用 `NotebookLMAdapter.ask(question, notebook_url)` 與 `run_with_retries(...)` 執行分段查詢；每個 follow-up 問題自帶完整上下文（spec §4.2），由 orchestrator 組裝，不依賴上一個回答。
- Plan 6（完整 run）在進入規格化前先以 adapter 做 NotebookLM 預檢：`auth_status()` 未驗證 → 停止並提供登入指示；首個 `ask` 觸發 `NotebookInaccessible` → 停止。技術重試（`run_with_retries`）與三輪內容修正分開計數。
- **Plan 1 遺留（仍待 Plan 6 處理）**：強化 `scan_sources` 對無法讀取檔案／壞掉 symlink 的處理。

---

## Self-Review

**Spec coverage（本計畫範圍 = §4 技術方案、§5 doctor、§11 錯誤處理與安全中與 adapter/doctor 相關者、§12.1 adapter 與 retry 測試）：**
- §4.1 透過 adapter 呼叫 skill、且只經 `run.py` → Task 1（config 定位 run.py）、Task 3（argv 一律含 run.py，script 名為第 3 個 token）、Task 6（adapter 不直接呼叫 script）。✅
- §4.1 三個示範命令 → auth status（Task 3）、ask（Task 3）；`notebook_manager.py add` 刻意不實作（§2.2 不自動建立／上傳）。✅（已於 Global Constraints 說明）
- §4.2 每次 ask 為獨立無上下文 session → Task 6 adapter 無狀態；follow-up 上下文組裝留待 Plan 3（已標註）。✅
- §5 doctor 檢查 Python／skill／依賴／Chrome／驗證狀態／驗證工具，且唯讀 → Task 8 六項檢查（auth 在 .venv 未建立時跳過以維持唯讀）、Task 9 CLI。✅
- §11 未驗證→停止+登入指示 → `AuthRequired`（Task 2/5/6）+ doctor remedy。✅
- §11 Notebook 無法存取→停止 → `NotebookInaccessible`（Task 2/5）。✅
- §11 額度/暫時錯誤→有限技術重試且分開計數 → `TransientError` + `run_with_retries`（Task 2/5/7）。✅
- §11 輸出格式異常→保存 stdout/stderr+停止 → `MalformedOutput` 攜帶 stdout（Task 2/4/6）。✅
- §11 機密不入 log/輸出、skill data/.venv/browser state 不複製 → adapter/runner 只擷取 script stdout/stderr（Task 1 註解與設計）；Plan 1 `.gitignore` 已排除 skill 狀態；doctor 不讀取 state 內容（只回 yes/no）。✅
- §12.1 「adapter command 建構與輸出解析」「retry 與停止條件」→ Task 3/4/5/6/7 測試。✅
- §11「不支援檔案→manifest issue」屬 Plan 1 manifest，不在本計畫；§12.2/§12.3 整合與真實 smoke test 屬 Plan 6 之外的手動驗證，本計畫不涵蓋（已界定範圍）。

**Placeholder scan：** 無 TBD／TODO／「add error handling」等占位；每個程式步驟皆含完整程式碼；marker 字串皆有來源契約依據。✅

**Type consistency：**
- `SkillConfig`（`skill_root`/`python`/`run_py`/`is_present`/`venv_initialized`）跨 Task 1/3/6/8 一致。✅
- `CommandResult`（`argv`/`returncode`/`stdout`/`stderr`）跨 Task 1/5/6/8 一致。✅
- `ProcessRunner.__call__(argv) -> CommandResult` 與 fake runner、`subprocess_runner`、`check_auth(runner=...)` 簽章一致。✅
- 例外型別名（`AuthRequired`/`NotebookInaccessible`/`TransientError`/`MalformedOutput`/`SkillSetupError`/`SkillError`）於 Task 2 定義，Task 5/6/7/8 一致引用。✅
- `parse_auth_status`/`parse_ask_answer`/`classify_failure`/`run_with_retries`/`run_checks`/`build_report`/`render_report` 簽章在 Interfaces、實作、測試三處一致。✅
- `CheckResult`/`DoctorReport`（`name`/`ok`/`detail`/`remedy`/`required`/`checks`/`ok` property）跨 Task 8/9 一致。✅

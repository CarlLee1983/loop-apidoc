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

from __future__ import annotations

from loop_apidoc.manifest.models import Manifest
from loop_apidoc.plan.models import NormalizationPlan

REQUIRED_MARKDOWN_SECTIONS: tuple[str, ...] = (
    "## 文件範圍與來源",
    "## 串接前置條件",
    "## 環境與 base URL",
    "## 驗證／授權",
    "## 共用規則",
    "## Endpoint",
    "## Request／Response 範例",
    "## 錯誤碼",
    "## 限制與注意事項",
    "## 已知缺漏與來源衝突",
)

_EMPTY = "_來源未提供此項資訊。_"


def _title(plan: NormalizationPlan) -> str:
    return plan.system_groups[0].name if plan.system_groups else "Untitled API"


def _scope(plan: NormalizationPlan, manifest: Manifest) -> list[str]:
    lines = [plan.overview_note or _EMPTY, "", "本文件涵蓋的來源："]
    sources = [s.relative_path for s in manifest.local_sources]
    sources += [u.url for u in manifest.url_sources]
    if sources:
        lines += [f"- `{s}`" for s in sources]
    else:
        lines.append(_EMPTY)
    return lines


def _environments(plan: NormalizationPlan) -> list[str]:
    rows = [e for e in plan.environments if e.base_url or e.name or e.version]
    if not rows:
        return [_EMPTY]
    out = ["| 環境 | base URL | 版本 |", "| --- | --- | --- |"]
    for e in rows:
        out.append(f"| {e.name or '-'} | `{e.base_url or '-'}` | `{e.version or '-'}` |")
    return out


def _security(plan: NormalizationPlan) -> list[str]:
    if not plan.security_schemes:
        return [_EMPTY]
    out = []
    for s in plan.security_schemes:
        out.append(f"- **{s.name or '-'}**（type：`{s.type or '-'}`，位置：`{s.location or '-'}`，"
                   f"名稱：`{s.details or '-'}`）")
    return out


def _schemas(plan: NormalizationPlan) -> list[str]:
    if not plan.schemas:
        return [_EMPTY]
    out = []
    for s in plan.schemas:
        out.append(f"### `{s.name or '-'}`")
        if s.constraints:
            out.append(s.constraints)
        for f in s.fields:
            name = f.get("name")
            if not name:
                continue
            enum = f.get("enum")
            enum_text = f"，enum：{enum}" if enum else ""
            out.append(f"- `{name}`：型別 `{f.get('type') or '-'}`"
                       f"{'（必填）' if f.get('required') else ''}{enum_text}")
    return out


def _endpoints(plan: NormalizationPlan) -> list[str]:
    rows = [e for e in plan.endpoints if e.path or e.method]
    if not rows:
        return [_EMPTY]
    out = []
    for e in rows:
        out.append(f"### `{e.method or '-'}` `{e.path or '-'}`")
        if e.summary:
            out.append(e.summary)
        for p in e.parameters:
            name = p.get("name")
            if name:
                out.append(f"- 參數 `{name}`（位置 `{p.get('in') or p.get('location') or '-'}`，"
                           f"型別 `{p.get('type') or '-'}`）")
        for r in e.responses:
            status = r.get("status")
            if status:
                out.append(f"- 回應 `{status}`：{r.get('description') or '-'}")
    return out


def _examples(plan: NormalizationPlan) -> list[str]:
    out = []
    for e in plan.endpoints:
        for ex in e.examples:
            body = ex.get("body") or ex.get("value")
            if body is None:
                continue
            title = ex.get("title") or f"{e.method or ''} {e.path or ''}".strip()
            out.append(f"**{title}**")
            out.append("```")
            out.append(str(body))
            out.append("```")
    return out or [_EMPTY]


def _errors(plan: NormalizationPlan) -> list[str]:
    if not plan.errors:
        return [_EMPTY]
    out = ["| code | HTTP | 意義 |", "| --- | --- | --- |"]
    for e in plan.errors:
        out.append(f"| `{e.code or '-'}` | `{e.http_status or '-'}` | {e.meaning or '-'} |")
    return out


def _operational(plan: NormalizationPlan) -> list[str]:
    if not plan.operational:
        return [_EMPTY]
    return [f"- **{o.topic or '-'}**：{o.detail or '-'}" for o in plan.operational]


def _gaps(plan: NormalizationPlan) -> list[str]:
    out: list[str] = []
    if plan.missing_items:
        out.append("**已知缺漏：**")
        out += [f"- [{m.area}] {m.detail}" for m in plan.missing_items]
    if plan.source_conflicts:
        out.append("**來源衝突：**")
        out += [f"- [{c.area}] {c.detail}" for c in plan.source_conflicts]
    if plan.unverified_items:
        out.append("**無法確認：**")
        out += [f"- [{u.area}] {u.detail}" for u in plan.unverified_items]
    if plan.conflicts_note:
        out += ["", plan.conflicts_note]
    return out or [_EMPTY]


def build_markdown(plan: NormalizationPlan, manifest: Manifest) -> str:
    sections = [
        _scope(plan, manifest),
        ["完成串接前，請先確認已取得 Notebook 對應的來源並完成驗證設定。"],
        _environments(plan),
        _security(plan),
        _schemas(plan),
        _endpoints(plan),
        _examples(plan),
        _errors(plan),
        _operational(plan),
        _gaps(plan),
    ]
    lines = [f"# {_title(plan)}", ""]
    for heading, body in zip(REQUIRED_MARKDOWN_SECTIONS, sections):
        lines.append(heading)
        lines.append("")
        lines.extend(body)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"

from __future__ import annotations

from loop_apidoc.generate.naming import security_scheme_key, webhook_items
from loop_apidoc.manifest.models import Manifest
from loop_apidoc.plan.models import NormalizationPlan

REQUIRED_MARKDOWN_SECTIONS: tuple[str, ...] = (
    "## 文件範圍與來源",
    "## 串接前置條件",
    "## 環境與 base URL",
    "## 驗證／授權",
    "## 共用規則",
    "## 整合機制",
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
    for idx, s in enumerate(plan.security_schemes):
        # The bolded token is the sanitized component key (so it matches the
        # OpenAPI securitySchemes key for the consistency check); the original
        # name is shown as 原名 for readability.
        key = security_scheme_key(s.name, idx)
        out.append(f"- **{key}**（type：`{s.type or '-'}`，位置：`{s.location or '-'}`，"
                   f"名稱：`{s.details or '-'}`，原名：{s.name or '-'}）")
    return out


def _nesting(name: str) -> tuple[int, str]:
    """(indent depth, short leaf label) for a dotted field name, so
    `OrderDetail[].ItemName` renders as `ItemName` indented under its parent
    rather than as a flat bracketed sibling."""
    parts = name.split(".")
    last = parts[-1]
    label = last[:-2] if last.endswith("[]") else last
    return len(parts) - 1, label


def _field_line(name: str, field: dict, location: str | None = None) -> str:
    """One indented bullet for a parameter or schema field, carrying location
    (for non-body params), type, required flag, enum and the source description
    (previously dropped)."""
    depth, label = _nesting(name)
    bits: list[str] = []
    if location:
        bits.append(f"位置 `{location}`")
    bits.append(f"型別 `{field.get('type') or '-'}`")
    if field.get("required"):
        bits.append("必填")
    enum = field.get("enum")
    if enum:
        bits.append(f"enum：{enum}")
    line = f"{'  ' * depth}- `{label}`（{'，'.join(bits)}）"
    desc = field.get("description")
    if desc:
        line += f" — {desc}"
    return line


def _integration(plan: NormalizationPlan) -> list[str]:
    contract = plan.integration
    if contract is None or not (
        contract.crypto or contract.callbacks or contract.field_conditions or contract.test_cases
    ):
        return ["（來源未提供整合機制資訊)"]
    lines: list[str] = []
    for c in contract.crypto:
        lines.append(f"### 加解密／簽章：{c.name or '(未命名)'}")
        if c.algorithm:
            lines.append(f"- 演算法：{c.algorithm}{f'/{c.mode}' if c.mode else ''}")
        if c.key_source and (c.key_source.key or c.key_source.iv):
            lines.append(f"- 金鑰來源：key={c.key_source.key}, iv={c.key_source.iv}")
        for s in c.payload_assembly:
            lines.append(f"  {s.step}. {s.desc or ''}")
        if c.verify and c.verify.field:
            lines.append(f"- 驗章：{c.verify.field}（{c.verify.method or ''}）")
    for cb in contract.callbacks:
        lines.append(f"### 回呼：{cb.name or '(未命名)'}")
        if cb.expected_response:
            lines.append(f"- 需回應：{cb.expected_response}")
        if cb.verification:
            lines.append(f"- 驗證：{cb.verification}")
    for fc in contract.field_conditions:
        if fc.rule:
            lines.append(f"- 條件：{fc.rule}")
    return lines


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
            if name:
                out.append(_field_line(name, f))
    return out


def _endpoint_detail_lines(e) -> list[str]:
    out: list[str] = []
    if e.summary:
        out.append(e.summary)
    meta: list[str] = []
    if e.tags:
        meta.append("分類：" + "、".join(f"`{t}`" for t in e.tags))
    if e.security:
        meta.append("簽章／認證：" + "、".join(f"`{s}`" for s in e.security))
    if meta:
        out.append("　｜　".join(meta))
    body = [p for p in e.parameters
            if (p.get("in") or p.get("location")) == "body" and p.get("name")]
    other = [p for p in e.parameters
             if (p.get("in") or p.get("location")) != "body" and p.get("name")]
    if other:
        out.append("**參數**")
        for p in other:
            out.append(_field_line(p["name"], p, p.get("in") or p.get("location") or "-"))
    if body:
        out.append("**請求 Body**")
        for p in body:
            out.append(_field_line(p["name"], p))
    if e.responses:
        out.append("**回應**")
        for r in e.responses:
            status = r.get("status")
            if not status:
                continue
            line = f"- `{status}`：{r.get('description') or '-'}"
            ref = r.get("schema_ref")
            if ref:
                line += f"（資料結構：`{ref}`）"
            out.append(line)
    return out


def _endpoints(plan: NormalizationPlan) -> list[str]:
    # Path-bearing endpoints render as `### `METHOD` `path``. Webhooks (a method
    # but no server path — async callbacks) render in a distinct `### Webhook`
    # form so they map to OpenAPI 3.1 `webhooks`, not `paths`.
    rows = [e for e in plan.endpoints if e.path]
    hooks = webhook_items(plan)
    if not rows and not hooks:
        return [_EMPTY]
    out: list[str] = []
    for e in rows:
        out.append(f"### `{e.method or '-'}` `{e.path or '-'}`")
        out.extend(_endpoint_detail_lines(e))
    for name, e in hooks:
        out.append(f"### Webhook `{name}`（method `{(e.method or '-').upper()}`）")
        out.extend(_endpoint_detail_lines(e))
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


def _dedup_by_detail(items) -> list:
    """Collapse items that repeat the same detail text (keeping the first), so a
    gap that the source states once isn't listed many times."""
    seen: set[str] = set()
    out = []
    for it in items:
        if it.detail in seen:
            continue
        seen.add(it.detail)
        out.append(it)
    return out


def _gaps(plan: NormalizationPlan) -> list[str]:
    out: list[str] = []
    missing = _dedup_by_detail(plan.missing_items)
    if missing:
        out.append("**已知缺漏：**")
        out += [f"- [{m.area}] {m.detail}" for m in missing]
    if plan.source_conflicts:
        out.append("**來源衝突：**")
        out += [f"- [{c.area}] {c.detail}" for c in _dedup_by_detail(plan.source_conflicts)]
    if plan.unverified_items:
        out.append("**無法確認：**")
        out += [f"- [{u.area}] {u.detail}" for u in _dedup_by_detail(plan.unverified_items)]
    if plan.conflicts_note:
        out += ["", plan.conflicts_note]
    return out or [_EMPTY]


def build_markdown(plan: NormalizationPlan, manifest: Manifest) -> str:
    sections = [
        _scope(plan, manifest),
        ["完成串接前，請先確認已取得對應的來源文件並完成驗證設定。"],
        _environments(plan),
        _security(plan),
        _schemas(plan),
        _integration(plan),   # NEW — aligns with "## 整合機制"
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

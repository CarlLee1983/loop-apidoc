from __future__ import annotations

from html import escape

from loop_apidoc.generate.models import GenerateResult
from loop_apidoc.generate.naming import (
    schema_key_map,
    security_scheme_key,
    webhook_items,
)
from loop_apidoc.manifest.models import Manifest
from loop_apidoc.plan.models import NormalizationPlan


def _h(value: object | None, fallback: str = "-") -> str:
    if value is None:
        return fallback
    text = str(value).strip()
    return escape(text or fallback, quote=True)


def _status_value(status: object | None) -> str:
    return str(getattr(status, "value", status) or "unknown")


def _status_label(status: object | None) -> str:
    labels = {
        "supported": "有來源",
        "missing": "缺漏",
        "conflicting": "衝突",
        "unverified": "未確認",
        "unknown": "未知",
    }
    return labels.get(_status_value(status), _h(status))


def _source_refs(citations: list) -> str:
    if not citations:
        return '<span class="muted">無來源定位</span>'
    refs: list[str] = []
    for citation in citations:
        bits = [
            citation.manifest_source or None,
            citation.locator or None,
            citation.query_id or None,
        ]
        refs.append(" / ".join(_h(bit) for bit in bits if bit))
    return "<br>".join(refs)


def _artifact_links(result: GenerateResult) -> str:
    links = [
        ("OpenAPI", "openapi.yaml", "openapi.yaml"),
        ("串接文件", "api-guide.zh-TW.md", "api-guide.zh-TW.md"),
        ("來源追溯", "provenance.json", "provenance.json"),
        ("規格化計畫", "plan/normalization-plan.json", "plan/normalization-plan.json"),
        ("驗證報告", "validation/report.md", "validation/report.md"),
    ]
    if result.integration is not None:
        links.append(("整合契約", "integration-contract.json", "integration-contract.json"))
    if result.examples:
        links.append(("請求範例", "examples/README.md", "examples/README.md"))
    if result.handoff:
        links.append(("開發交接", "handoff/integration-tasks.md", "handoff/integration-tasks.md"))
    return "\n".join(
        f'<a class="artifact-link" href="{_h(href)}">'
        f"<strong>{_h(label)}</strong><span>{_h(path)}</span></a>"
        for label, href, path in links
    )


def _metric(label: str, value: int | str, note: str) -> str:
    return (
        '<section class="metric">'
        f"<span>{_h(label)}</span>"
        f"<strong>{_h(value)}</strong>"
        f"<small>{_h(note)}</small>"
        "</section>"
    )


def _risk_items(plan: NormalizationPlan) -> str:
    groups = [
        ("缺漏", plan.missing_items),
        ("來源衝突", plan.source_conflicts),
        ("未確認", plan.unverified_items),
    ]
    rows: list[str] = []
    for label, items in groups:
        for item in items:
            rows.append(
                "<li>"
                f'<span class="pill">{_h(label)}</span>'
                f"<strong>{_h(item.area)}</strong>"
                f"<span>{_h(item.detail)}</span>"
                "</li>"
            )
    if not rows:
        return '<p class="empty">目前沒有計畫層級的缺漏、衝突或未確認項目。</p>'
    return '<ul class="risk-list">' + "\n".join(rows) + "</ul>"


def _source_rows(manifest: Manifest) -> str:
    rows: list[str] = []
    for source in manifest.local_sources:
        rows.append(
            "<tr>"
            f"<td>{_h(source.relative_path)}</td>"
            f"<td>{_h(source.source_format.value)}</td>"
            f"<td>{_h(source.status.value)}</td>"
            "</tr>"
        )
    for source in manifest.url_sources:
        rows.append(
            "<tr>"
            f"<td>{_h(source.url)}</td>"
            "<td>url</td>"
            f"<td>{_h(source.status.value)}</td>"
            "</tr>"
        )
    if not rows:
        return '<tr><td colspan="3" class="empty">沒有來源。</td></tr>'
    return "\n".join(rows)


def _endpoint_rows(plan: NormalizationPlan) -> str:
    rows: list[str] = []
    for endpoint in (e for e in plan.endpoints if e.path):
        method = (endpoint.method or "-").upper()
        rows.append(
            "<tr>"
            f'<td><span class="method">{_h(method)}</span></td>'
            f"<td><code>{_h(endpoint.path)}</code></td>"
            f"<td>{_h(endpoint.summary)}</td>"
            f"<td>{_h(_status_label(endpoint.status))}</td>"
            f"<td>{_h(len(endpoint.parameters))}</td>"
            f"<td>{_h(len(endpoint.responses))}</td>"
            f"<td>{_h(', '.join(endpoint.security) if endpoint.security else '-')}</td>"
            f"<td>{_source_refs(endpoint.citations)}</td>"
            "</tr>"
        )
    for name, endpoint in webhook_items(plan):
        rows.append(
            "<tr>"
            f'<td><span class="method">WEBHOOK</span></td>'
            f"<td><code>{_h(name)}</code></td>"
            f"<td>{_h(endpoint.summary)}</td>"
            f"<td>{_h(_status_label(endpoint.status))}</td>"
            f"<td>{_h(len(endpoint.parameters))}</td>"
            f"<td>{_h(len(endpoint.responses))}</td>"
            f"<td>{_h(', '.join(endpoint.security) if endpoint.security else '-')}</td>"
            f"<td>{_source_refs(endpoint.citations)}</td>"
            "</tr>"
        )
    if not rows:
        return '<tr><td colspan="8" class="empty">沒有 endpoint 或 webhook。</td></tr>'
    return "\n".join(rows)


def _schema_rows(plan: NormalizationPlan) -> str:
    rows: list[str] = []
    key_map = schema_key_map(plan.schemas)
    for idx, schema in enumerate(plan.schemas):
        required = sum(1 for field in schema.fields if field.get("required"))
        rows.append(
            "<tr>"
            f"<td><code>{_h(key_map[idx])}</code></td>"
            f"<td>{_h(schema.name)}</td>"
            f"<td>{_h(_status_label(schema.status))}</td>"
            f"<td>{_h(len(schema.fields))}</td>"
            f"<td>{_h(required)}</td>"
            f"<td>{_source_refs(schema.citations)}</td>"
            "</tr>"
        )
    if not rows:
        return '<tr><td colspan="6" class="empty">沒有 schema。</td></tr>'
    return "\n".join(rows)


def _security_rows(plan: NormalizationPlan) -> str:
    rows: list[str] = []
    for idx, scheme in enumerate(plan.security_schemes):
        rows.append(
            "<tr>"
            f"<td><code>{_h(security_scheme_key(scheme.name, idx))}</code></td>"
            f"<td>{_h(scheme.name)}</td>"
            f"<td>{_h(scheme.type)}</td>"
            f"<td>{_h(scheme.location)}</td>"
            f"<td>{_h(scheme.details)}</td>"
            f"<td>{_source_refs(scheme.citations)}</td>"
            "</tr>"
        )
    if not rows:
        return '<tr><td colspan="6" class="empty">沒有驗證／授權機制。</td></tr>'
    return "\n".join(rows)


def _environment_rows(plan: NormalizationPlan) -> str:
    rows: list[str] = []
    for env in plan.environments:
        rows.append(
            "<tr>"
            f"<td>{_h(env.name)}</td>"
            f"<td><code>{_h(env.base_url)}</code></td>"
            f"<td>{_h(env.version)}</td>"
            f"<td>{_source_refs(env.citations)}</td>"
            "</tr>"
        )
    if not rows:
        return '<tr><td colspan="4" class="empty">沒有環境資訊。</td></tr>'
    return "\n".join(rows)


def _integration_summary(result: GenerateResult) -> str:
    if result.integration is None:
        return '<p class="empty">來源未提供整合契約。</p>'
    contract = result.integration
    rows = [
        ("加解密／簽章", len(contract.get("crypto") or [])),
        ("回呼", len(contract.get("callbacks") or [])),
        ("條件欄位", len(contract.get("field_conditions") or [])),
        ("契約測試", len(contract.get("test_cases") or [])),
        ("整合缺漏", len(contract.get("missing") or [])),
    ]
    body = "\n".join(
        f"<tr><td>{_h(label)}</td><td>{_h(value)}</td>"
        "<td><code>integration-contract.json</code></td></tr>"
        for label, value in rows
    )
    return (
        '<div class="table-wrap"><table class="compact-table">'
        "<thead><tr><th>項目</th><th>數量</th><th>來源產物</th></tr></thead>"
        f"<tbody>{body}</tbody></table></div>"
    )


def _style() -> str:
    return """
:root {
  color-scheme: light;
  --bg: #f7f8fa;
  --panel: #ffffff;
  --text: #1f2933;
  --muted: #667085;
  --line: #d8dee6;
  --accent: #096b72;
  --accent-2: #8a5a00;
  --bad: #b42318;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--text);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  line-height: 1.5;
}
a { color: inherit; }
code {
  padding: 2px 5px;
  border: 1px solid var(--line);
  border-radius: 4px;
  background: #f2f4f7;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 0.92em;
}
.review-dashboard {
  width: min(1180px, calc(100% - 32px));
  margin: 0 auto;
  padding: 32px 0 48px;
}
.page-head {
  display: grid;
  gap: 8px;
  margin-bottom: 24px;
}
.page-head h1 {
  margin: 0;
  font-size: clamp(28px, 4vw, 42px);
  line-height: 1.12;
  letter-spacing: 0;
}
.page-head p,
.muted,
.metric small {
  color: var(--muted);
}
.metrics {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 12px;
}
.metric,
.panel {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 8px;
}
.metric {
  min-height: 108px;
  padding: 14px;
  display: grid;
  align-content: space-between;
}
.metric strong {
  display: block;
  font-size: 30px;
  line-height: 1.1;
}
.artifact-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
  gap: 10px;
}
.artifact-link {
  display: grid;
  gap: 4px;
  min-height: 72px;
  padding: 12px;
  border: 1px solid var(--line);
  border-radius: 8px;
  text-decoration: none;
  background: #fbfcfd;
}
.artifact-link:hover {
  border-color: var(--accent);
}
.artifact-link span {
  color: var(--muted);
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 13px;
}
.panel {
  margin-top: 16px;
  overflow: hidden;
}
.panel > header {
  padding: 16px 18px 0;
}
.panel h2 {
  margin: 0 0 4px;
  font-size: 20px;
  letter-spacing: 0;
}
.panel > .content {
  padding: 16px 18px 18px;
}
.table-wrap {
  overflow-x: auto;
}
table {
  width: 100%;
  border-collapse: collapse;
  min-width: 720px;
}
.compact-table {
  min-width: 420px;
}
th,
td {
  padding: 10px 12px;
  border-top: 1px solid var(--line);
  text-align: left;
  vertical-align: top;
}
th {
  color: var(--muted);
  font-size: 13px;
  font-weight: 650;
}
.method,
.pill {
  display: inline-flex;
  align-items: center;
  min-height: 24px;
  padding: 2px 8px;
  border-radius: 999px;
  background: #e6f4f1;
  color: var(--accent);
  font-size: 12px;
  font-weight: 700;
}
.pill {
  background: #fff6df;
  color: var(--accent-2);
}
.risk-list {
  display: grid;
  gap: 8px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.risk-list li {
  display: grid;
  grid-template-columns: auto minmax(96px, auto) 1fr;
  gap: 10px;
  align-items: start;
  padding: 10px 0;
  border-top: 1px solid var(--line);
}
.empty {
  color: var(--muted);
  margin: 0;
}
@media (max-width: 720px) {
  .review-dashboard { width: min(100% - 20px, 1180px); padding-top: 20px; }
  .risk-list li { grid-template-columns: 1fr; }
}
"""


def build_review_html(
    plan: NormalizationPlan,
    manifest: Manifest,
    result: GenerateResult,
) -> str:
    """Build a self-contained run review page for manual artifact inspection."""
    title = plan.resolved_title or "Untitled API"
    source_count = len(manifest.local_sources) + len(manifest.url_sources)
    endpoint_count = sum(1 for endpoint in plan.endpoints if endpoint.path)
    webhook_count = len(webhook_items(plan))
    gap_count = (
        len(plan.missing_items)
        + len(plan.source_conflicts)
        + len(plan.unverified_items)
    )
    example_count = sum(1 for path in result.examples if path.endswith("request.sh"))
    metrics = "\n".join(
        [
            _metric("來源", source_count, "manifest.json"),
            _metric("Endpoint", endpoint_count, "OpenAPI paths"),
            _metric("Webhook", webhook_count, "OpenAPI webhooks"),
            _metric("Schema", len(plan.schemas), "components.schemas"),
            _metric("Auth", len(plan.security_schemes), "securitySchemes"),
            _metric("範例", example_count, "request examples"),
            _metric("核對風險", gap_count, "缺漏／衝突／未確認"),
        ]
    )
    return f"""<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{_h(title)} - 生成產物核對</title>
  <style>{_style()}</style>
</head>
<body>
<main class="review-dashboard">
  <header class="page-head">
    <p class="muted">Loop API Doc 生成產物核對</p>
    <h1>{_h(title)}</h1>
    <p>這份頁面彙整同一個 run directory 內的生成產物，供人工快速核對範圍、來源、缺漏與主要 API 結構。</p>
  </header>

  <section class="metrics" aria-label="生成摘要">
    {metrics}
  </section>

  <section class="panel">
    <header>
      <h2>產物入口</h2>
      <p class="muted">所有連結皆指向目前 run directory 的相對路徑，可離線開啟。</p>
    </header>
    <div class="content artifact-grid">
      {_artifact_links(result)}
    </div>
  </section>

  <section class="panel">
    <header>
      <h2>人工核對重點</h2>
      <p class="muted">優先檢查缺漏、來源衝突與未確認項目；驗證細節請看 validation/report.md。</p>
    </header>
    <div class="content">
      {_risk_items(plan)}
    </div>
  </section>

  <section class="panel">
    <header>
      <h2>Endpoint / Webhook</h2>
      <p class="muted">核對 method、path、摘要、參數／回應數量、認證與來源定位。</p>
    </header>
    <div class="table-wrap">
      <table>
        <thead>
          <tr><th>方法</th><th>路徑／名稱</th><th>摘要</th><th>狀態</th><th>參數</th><th>回應</th><th>認證</th><th>來源</th></tr>
        </thead>
        <tbody>{_endpoint_rows(plan)}</tbody>
      </table>
    </div>
  </section>

  <section class="panel">
    <header>
      <h2>Schema</h2>
      <p class="muted">核對 component key、來源名稱、欄位數與必填欄位數。</p>
    </header>
    <div class="table-wrap">
      <table>
        <thead>
          <tr><th>Component</th><th>來源名稱</th><th>狀態</th><th>欄位</th><th>必填</th><th>來源</th></tr>
        </thead>
        <tbody>{_schema_rows(plan)}</tbody>
      </table>
    </div>
  </section>

  <section class="panel">
    <header>
      <h2>環境與驗證</h2>
      <p class="muted">核對 base URL 與安全機制是否與來源文件一致。</p>
    </header>
    <div class="table-wrap">
      <table>
        <thead>
          <tr><th>環境</th><th>base URL</th><th>版本</th><th>來源</th></tr>
        </thead>
        <tbody>{_environment_rows(plan)}</tbody>
      </table>
    </div>
    <div class="table-wrap">
      <table>
        <thead>
          <tr><th>Key</th><th>原名</th><th>Type</th><th>位置</th><th>說明</th><th>來源</th></tr>
        </thead>
        <tbody>{_security_rows(plan)}</tbody>
      </table>
    </div>
  </section>

  <section class="panel">
    <header>
      <h2>整合契約</h2>
      <p class="muted">來源有提供簽章、加密、回呼或條件欄位時，這裡提供快速總覽。</p>
    </header>
    <div class="content">
      {_integration_summary(result)}
    </div>
  </section>

  <section class="panel">
    <header>
      <h2>來源清單</h2>
      <p class="muted">用於確認本次 run 的來源範圍。</p>
    </header>
    <div class="table-wrap">
      <table>
        <thead>
          <tr><th>來源</th><th>格式</th><th>狀態</th></tr>
        </thead>
        <tbody>{_source_rows(manifest)}</tbody>
      </table>
    </div>
  </section>
</main>
</body>
</html>
"""

from __future__ import annotations

from collections.abc import Callable
import json
import mimetypes
import secrets
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlsplit

from pydantic import ValidationError

from loop_apidoc.foundry import paths
from loop_apidoc.review.models import (
    ApprovalResult,
    ReviewConflictError,
    ReviewDraft,
    ReviewInputError,
    ReviewSnapshot,
    ReviewStateError,
)
from loop_apidoc.review.workflow import ReviewWorkflow

_MAX_BODY_BYTES = 1_000_000
_ARTIFACTS = frozenset({
    "openapi.yaml",
    "provenance.json",
    "validation/report.json",
    "validation/report.md",
    "review.html",
    "integration-contract.json",
    "score/score.json",
    "core/evidence.json",
    "core/projections/review-data.json",
})


class ReviewWebAdapter:
    """Thin loopback HTTP adapter over the review workflow seam."""

    def __init__(
        self,
        workflow: ReviewWorkflow,
        snapshot: ReviewSnapshot,
        *,
        port: int = 0,
    ):
        self.workflow = workflow
        self.snapshot = snapshot
        self.token = secrets.token_urlsafe(32)
        self._server = ThreadingHTTPServer(("127.0.0.1", port), self._handler())

    @property
    def url(self) -> str:
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}/"

    def serve_forever(self) -> None:
        self._server.serve_forever()

    def shutdown(self) -> None:
        self._server.shutdown()
        self._server.server_close()

    def _handler(self) -> type[BaseHTTPRequestHandler]:
        adapter = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802 - stdlib hook name
                path = urlsplit(self.path).path
                if path == "/":
                    self._html(_page(adapter.token))
                    return
                if path == "/api/review":
                    self._json(adapter.snapshot.model_dump(mode="json"))
                    return
                if path.startswith("/artifact/"):
                    self._artifact(path)
                    return
                self.send_error(HTTPStatus.NOT_FOUND)

            def do_PUT(self) -> None:  # noqa: N802 - stdlib hook name
                if urlsplit(self.path).path != "/api/decision":
                    self.send_error(HTTPStatus.NOT_FOUND)
                    return
                self._write(
                    lambda draft: adapter.workflow.save_decision(
                        adapter.snapshot.key, draft
                    )
                )

            def do_POST(self) -> None:  # noqa: N802 - stdlib hook name
                if urlsplit(self.path).path != "/api/approve":
                    self.send_error(HTTPStatus.NOT_FOUND)
                    return

                def approve(draft: ReviewDraft) -> object:
                    from datetime import datetime, timezone

                    return adapter.workflow.approve_review(
                        adapter.snapshot.key, draft, now=datetime.now(timezone.utc)
                    )

                self._write(approve)

            def _write(
                self,
                operation: Callable[[ReviewDraft], ReviewSnapshot | ApprovalResult],
            ) -> None:
                if self.headers.get("X-Loop-Review-Token") != adapter.token:
                    self._json({"error": "invalid session token"}, HTTPStatus.FORBIDDEN)
                    return
                try:
                    raw_length = int(self.headers.get("Content-Length", "0"))
                except ValueError:
                    self._json({"error": "invalid content length"}, HTTPStatus.BAD_REQUEST)
                    return
                if raw_length < 1 or raw_length > _MAX_BODY_BYTES:
                    self._json({"error": "invalid request body length"}, HTTPStatus.BAD_REQUEST)
                    return
                try:
                    payload = json.loads(self.rfile.read(raw_length))
                    draft = ReviewDraft.model_validate(payload)
                    result = operation(draft)
                except ReviewConflictError as exc:
                    self._json({"error": str(exc)}, HTTPStatus.CONFLICT)
                    return
                except (ReviewInputError, ReviewStateError, ValidationError, ValueError) as exc:
                    self._json({"error": str(exc)}, HTTPStatus.UNPROCESSABLE_ENTITY)
                    return
                payload = result.model_dump(mode="json")
                if isinstance(result, ReviewSnapshot):
                    adapter.snapshot = result
                self._json(payload)

            def _artifact(self, path: str) -> None:
                parts = path.split("/", 3)
                if len(parts) != 4:
                    self.send_error(HTTPStatus.NOT_FOUND)
                    return
                side, relative = parts[2], unquote(parts[3])
                if side not in {"candidate", "base"} or relative not in _ARTIFACTS:
                    self.send_error(HTTPStatus.NOT_FOUND)
                    return
                if side == "candidate":
                    root = paths.candidate_dir(
                        adapter.workflow.project_root,
                        adapter.snapshot.key.docset_id,
                        adapter.snapshot.key.candidate_run_id,
                    )
                elif adapter.snapshot.binding.base_asset_id is not None:
                    root = paths.asset_artifacts_dir(
                        adapter.workflow.project_root,
                        adapter.snapshot.key.docset_id,
                        adapter.snapshot.binding.base_asset_id,
                    )
                else:
                    self.send_error(HTTPStatus.NOT_FOUND)
                    return
                file_path = root / relative
                if not file_path.is_file():
                    self.send_error(HTTPStatus.NOT_FOUND)
                    return
                content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
                data = file_path.read_bytes()
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def _json(self, payload: object, status: HTTPStatus = HTTPStatus.OK) -> None:
                body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _html(self, content: str) -> None:
                body = content.encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, _format: str, *_args: object) -> None:
                # A CLI workbench should not print one HTTP log line per UI action.
                return

        return Handler


def _page(token: str) -> str:
    token_json = json.dumps(token)
    return f"""<!doctype html>
<html lang=\"zh-Hant\"><meta charset=\"utf-8\"><title>loop-apidoc review</title>
<style>body{{font:16px system-ui;max-width:1100px;margin:2rem auto;padding:0 1rem}}pre{{white-space:pre-wrap;background:#f4f4f5;padding:1rem}}section{{border:1px solid #ddd;padding:1rem;margin:1rem 0}}label{{display:block;margin:.6rem 0}}textarea{{width:100%;min-height:7rem}}button{{margin:.5rem .5rem .5rem 0;padding:.5rem .8rem}}</style>
<h1>API contract review</h1><p id=\"summary\">Loading…</p><section><h2>Validation and version diff</h2><pre id=\"evidence\"></pre></section>
<section><h2>Candidate, current, and provenance artifacts</h2><div id=\"artifacts\"></div></section>
<section><h2>Finding decisions</h2><div id=\"subjects\"></div></section>
<section><h2>Manual items and handoff</h2><p>Optional manual review items may cover work not represented by an existing finding. Each item needs <code>subject_id</code>, <code>subject_kind: \"manual\"</code>, and a <code>disposition</code>.</p><textarea id=\"manual-items\">[]</textarea><p>Optional JSON array of open/done handoff tasks with <code>task_id</code>, <code>instruction</code>, and <code>subject_ids</code>.</p><textarea id=\"handoff\">[]</textarea><label>Review note<textarea id=\"note\"></textarea></label><button id=\"save\">Save decision</button><button id=\"approve\">Approve current</button><pre id=\"result\"></pre></section>
<script>
const token={token_json}; let snapshot;
async function request(url, options={{}}) {{ const r=await fetch(url, options); const b=await r.json(); if(!r.ok) throw new Error(b.error||r.statusText); return b; }}
function evidence(s) {{ return {{mode:s.mode, validation:s.validation, score:s.score, diff:s.diff, provenance_count:s.provenance.entries.length}}; }}
function link(side, relative) {{ const a=document.createElement('a'); a.href=`/artifact/${{side}}/${{relative}}`; a.target='_blank'; a.rel='noopener'; a.textContent=`${{side}}: ${{relative}}`; return a; }}
function renderArtifacts(s) {{ const root=document.querySelector('#artifacts'); root.replaceChildren(); const names=['openapi.yaml','provenance.json','validation/report.json','review.html','integration-contract.json','score/score.json',...(s.subjects.some(subject=>subject.evidence.length)?['core/evidence.json','core/projections/review-data.json']:[])]; for(const side of s.binding.base_asset_id?['candidate','base']:['candidate']) {{ const heading=document.createElement('h3'); heading.textContent=side==='base'?`current: ${{s.binding.base_asset_id}}`:'candidate'; root.append(heading); for(const name of names) {{ const item=document.createElement('p'); item.append(link(side,name)); root.append(item); }} }} }}
function renderEvidence(items) {{ const root=document.createElement('div'); for(const item of items) {{ const detail=document.createElement('details'); const title=document.createElement('summary'); title.textContent=`${{item.relationship}} — ${{item.source_id}} (${{item.claim_path}})`; const locator=document.createElement('pre'); locator.textContent=JSON.stringify({{source_locator:item.source_locator,fragment_locator:item.fragment_locator,fragment_digest:item.fragment_digest}},null,2); detail.append(title,locator); if(item.normalized_excerpt) {{ const excerpt=document.createElement('pre'); excerpt.textContent=item.normalized_excerpt; detail.append(excerpt); }} root.append(detail); }} return root; }}
function render(s) {{ snapshot=s; const decision=s.decision||{{items:[],handoff:[],note:''}}; const decisions=new Map(decision.items.map(item=>[item.subject_id,item])); document.querySelector('#summary').textContent=`${{s.key.docset_id}} / ${{s.key.candidate_run_id}} (${{s.mode}})`; document.querySelector('#evidence').textContent=JSON.stringify(evidence(s),null,2); renderArtifacts(s); document.querySelector('#manual-items').value=JSON.stringify(decision.items.filter(item=>item.subject_kind==='manual'),null,2); document.querySelector('#handoff').value=JSON.stringify(decision.handoff,null,2); document.querySelector('#note').value=decision.note||''; const root=document.querySelector('#subjects'); root.replaceChildren(); for(const subject of s.subjects) {{ const item=decisions.get(subject.id); const row=document.createElement('label'); row.textContent=`${{subject.kind}} ${{subject.location}} — ${{subject.summary}}`; const select=document.createElement('select'); select.dataset.id=subject.id; select.dataset.kind=subject.kind; select.innerHTML='<option value="">unreviewed</option><option value="accept">accept</option><option value="needs_evidence">needs_evidence</option><option value="reject">reject</option><option value="skip">skip</option>'; select.value=item?.disposition||''; const note=document.createElement('input'); note.placeholder='note'; note.dataset.noteFor=subject.id; note.value=item?.note||''; row.append(select,note,renderEvidence(subject.evidence)); root.append(row); }} }}
function draft() {{ const subjectItems=[...document.querySelectorAll('select[data-id]')].filter(x=>x.value).map(x=>({{subject_id:x.dataset.id,subject_kind:x.dataset.kind,disposition:x.value,note:document.querySelector(`[data-note-for="${{x.dataset.id}}"]`).value}})); const manualItems=JSON.parse(document.querySelector('#manual-items').value); return {{binding:snapshot.binding,items:[...subjectItems,...manualItems], handoff:JSON.parse(document.querySelector('#handoff').value),note:document.querySelector('#note').value}}; }}
async function send(path) {{ try {{ const out=await request(path,{{method:path.endsWith('decision')?'PUT':'POST',headers:{{'Content-Type':'application/json','X-Loop-Review-Token':token}},body:JSON.stringify(draft())}}); document.querySelector('#result').textContent=JSON.stringify(out,null,2); if(out.key) render(out); }} catch(e) {{ document.querySelector('#result').textContent=e.message; }} }}
document.querySelector('#save').onclick=()=>send('/api/decision'); document.querySelector('#approve').onclick=()=>send('/api/approve'); request('/api/review').then(render).catch(e=>document.querySelector('#result').textContent=e.message);
</script></html>"""

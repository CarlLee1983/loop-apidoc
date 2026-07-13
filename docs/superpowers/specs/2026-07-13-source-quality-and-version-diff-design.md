# 設計文件：來源品質閘門、補件重跑與版本差異

## 1. 目標

在 agent 開始擷取 `inventory.json` 前，對來源資料包建立 deterministic 的品質閘門。無法可靠擷取核心 API 契約時必須退回補件；品質足夠時可直接進入後續流程。每次新來源版本都要與最近一次已通過 `SPEC_REVIEW` 的版本比較來源與 API 契約差異。

本設計不把未知資訊補成推測值。缺口必須留在報告、`missing` 或後續開發沙箱的可追溯問題中。

## 2. 版本與流程狀態

每次收件建立不可變的 `source-set/vN/`，原始檔案、manifest 與品質判定均不可覆寫。比較基準固定為「最近一次品質通過且完成 `SPEC_REVIEW` 的 source set」；被退回的版本不可作為基準。

```text
source-set/vN
  -> source diff (base = last accepted + SPEC_REVIEW source set)
  -> manifest
  -> preprocess (when needed)
  -> source-quality gate
       -> reject: supplement request; stop
       -> pass: inventory -> endpoint extraction -> assemble/validate
  -> contract diff (base = base run; head = current run)
  -> SPEC_REVIEW
  -> development sandbox
       -> trace issue to provenance / quality report / source diff / contract diff
       -> supplement and rerun as source-set/vN+1 when source evidence is insufficient
```

`pass` means the report has no blocking finding. Non-blocking gaps remain visible as warnings and can proceed. Sandbox findings never authorize an agent to invent missing source facts.

## 3. CLI contract

Add a distinct command rather than repurposing post-generation `preparation-report`:

```bash
loop-apidoc assess-sources \
  --sources <SOURCES> \
  --manifest <WORK>/manifest.preflight.json \
  --prepared-sources <WORK>/sources_md \
  --base <BASE_SOURCE_SET_OR_REPORT> \
  --output <WORK>/source-quality
```

`--prepared-sources` is optional and only supplied after PDF/Word preprocessing. `--base` is optional for an initial source set. The command writes:

```text
<WORK>/source-quality/source-quality-report.json
<WORK>/source-quality/source-quality-report.zh-TW.md
<WORK>/source-quality/source-diff.json
<WORK>/source-quality/source-diff.md
```

Exit status:

| Exit | Meaning | Pipeline action |
| --- | --- | --- |
| 0 | pass: no blockers (may contain warnings) | permit inventory extraction |
| 1 | reject: one or more blockers | do not create or update extraction JSON |
| 2 | invalid invocation, malformed input, or unreadable required report | fix operator input; do not classify it as a document-quality result |

## 4. Quality report model

The JSON report is machine-readable and the Markdown report is the supplier-facing supplement request. Its minimum shape is:

```json
{
  "verdict": "pass",
  "source_set": "v2",
  "base_source_set": "v1",
  "summary": {"blockers": 0, "warnings": 2},
  "findings": [
    {
      "id": "SQ-001",
      "severity": "warning",
      "category": "examples_missing",
      "evidence": "HRXT.pdf p.12: request table has no example payload",
      "affected_scope": ["POST /hrxt/credit"],
      "required_supplement": "Provide a request and response example for this operation.",
      "acceptance_criteria": "The example identifies its document version and can be cited by page, section, or attachment."
    }
  ]
}
```

Blockers are limited to source conditions that make core contract extraction unreliable: no usable source, unreadable required pages, unavailable or irreparably damaged endpoint/parameter/error tables, missing referenced attachment containing essential contract data, or unresolved contradictory definitions. Missing examples, base URLs, or HTTP mappings are warnings unless a declared integration requirement makes them essential.

## 5. Diff model and risk classification

The source diff compares source-set manifests and report findings: added/removed/changed files by SHA-256, changed source locations, missing attachments, and quality verdict or finding regressions. It must not claim semantic content changes solely from a file hash.

After a successful `assemble`, invoke existing `loop-apidoc diff` for the contract diff. Its existing `breaking`, `additive`, `changed`, and `source_only` classifications remain authoritative for generated contract changes.

Report high risk whenever either condition holds:

- a source-quality finding regresses from passable to blocker;
- the contract diff has one or more `breaking` changes;
- a source removal eliminates evidence used by an existing contract item.

High risk does not automatically reject the source package; it is carried to `SPEC_REVIEW` and the development sandbox for explicit review.

## 6. Supplement and rerun protocol

For `reject`, render each blocker as a concrete supplement request with evidence, affected API scope, requested material, and acceptance criteria. Do not emit generic wording such as "please improve the PDF".

On receipt of supplemental material:

1. Create `source-set/vN+1/` containing the original sources plus the new material; never mutate `vN`.
2. Recreate the manifest and hash every file.
3. Run source diff against the fixed baseline, then preprocess and `assess-sources`.
4. Mark each prior blocker as `resolved`, `still_open`, or `regressed` in the new report.
5. Only a pass may create a new inventory and downstream API run.

## 7. Agent skill integration

Update `skills/loop-apidoc/SKILL.md` so its ordering becomes:

```text
manifest -> preprocess -> assess-sources -> extraction -> assemble -> validate/diff
```

The agent is responsible for source reading and extraction; the CLI owns deterministic quality classification, report rendering, exit status, and source-set comparisons. A failed source-quality gate stops before read-only extraction fan-out.

## 8. Testing and release scope

Use TDD for the command and report models. Required cases include initial no-base run, pass with warning, reject for unavailable core source, reject for contradictory endpoint evidence, attachment regression, invalid report input, and rerun resolution status. Add CLI tests proving exit 0/1/2 and that reject does not produce extraction output.

Use fixture source sets with text/manifest metadata; do not depend on a real supplier PDF in unit tests. Add a small end-to-end fixture covering source diff plus an existing contract diff.

This is a new CLI capability and flow gate. The current main branch is already `0.5.0`, so release it as the next minor version (`0.6.0`) after tests and plugin metadata are updated. Publishing or installing the release is outside this design step.

## 9. Out of scope

- Automatically contacting suppliers or sending supplement requests externally.
- OCR engine replacement or generic PDF repair.
- Automatically accepting breaking changes.
- Making a sandbox failure alter historical source sets.

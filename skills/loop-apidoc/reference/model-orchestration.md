# Model-neutral orchestration

Use this reference when the work is split across models, agents, or both Codex and Claude.
It defines **logical roles**, not model names: the host chooses the least costly available
model that satisfies each role. The CLI, source files, JSON schemas, and validators are shared
across runtimes.

## Role matrix

| Role | Capability | May read | Must produce | Escalate when |
| --- | --- | --- | --- | --- |
| tool | deterministic CLI | source files / cache | manifest, corpus, validation result | a fetch, schema, or coverage error occurs |
| router | fast / low-cost | catalog or candidate cards | selected URLs, sections, and rationale | the candidate cards cannot distinguish scope |
| extractor | standard | assigned local source scope only | one schema-conformant JSON object or one assigned endpoint file | source is ambiguous, contradictory, or absent |
| integrator | high reasoning | selected evidence and extraction summaries | cross-page conflict/gap assessment | assertion lacks a source citation |
| verifier | high reasoning + CLI | extraction files, validation report, targeted source scope | bounded correction instructions or corrected assigned file | an error remains after targeted re-read |

The router ranks and selects; it does not establish API facts. The extractor never fills gaps
from conventions. The integrator does not replace source evidence with consensus. The CLI's
schema, provenance, coverage, and validation checks decide whether an artifact is acceptable.

## Artifact hand-off

Pass paths and compact summaries, not copied source bodies:

```text
catalog.json / corpus.json / candidates.json
  -> router: selected body_file paths and sections
  -> extractor(s): inventory.json or endpoints/ep<N>.json
  -> verify-extraction / assemble --json
  -> verifier: report.issues + only the named source scope
```

- For URL sources, cache first; give the router candidate cards and let it select local
  `body_file` evidence. Do not place all cached pages in a model context.
- Assign each endpoint extractor one output path and one bounded source scope. Keep the
  existing maximum of six concurrent endpoint extractions unless the host has an explicit
  lower safe limit.
- A hand-off includes source identifiers, assigned scope, output path, schema version, and
  source citations. A model/vendor change must not require rediscovering prior evidence.

## Runtime mapping

### Codex

Map the roles to Codex's configured models or agents. In an OMX-enabled session, a typical
mapping is `explore` for router, `executor` for extractor, and `verifier` for verifier; use the
host's equivalent roles when OMX is not installed. The skill itself does not assume that those
roles or particular model names exist.

### Claude Code

Map the same logical roles using the host's available agent/model controls. The plugin runs the
same `<APIDOC>` commands through `$CLAUDE_PLUGIN_ROOT`; it does not launch a separate Claude
process or require a model-specific CLI. Keep the tool artifacts and JSON contracts identical
to Codex so work can move between runtimes.

## Escalation and stop rules

1. Start with tools, then the router, then bounded extractors.
2. Escalate to a stronger model only for genuine cross-page reasoning, ambiguity, or a failed
   targeted correction.
3. Re-read only the source scope named by `report.issues`; do not restart the full extraction.
4. Stop with a documented gap when the source is silent or conflicting. Do not use a stronger
   model to invent the missing fact.

# Source quality gate

Before inventory extraction, the controller writes `source-quality-observations.json`
from a read-only review subagent. Every observation must cite a source and locator,
describe evidence, scope, required supplement, and acceptance criteria. The subagent
returns JSON only; it never writes files or decides the final verdict.

## `source-quality-observations.json` schema

The file must be a JSON array. `[]` is valid when the review found no observations.
Every non-empty item has this shape:

```json
[
  {
    "source": "transfer-api.md",
    "locator": "# API / Action 19",
    "category": "missing-response-envelope",
    "evidence": "The endpoint documents request fields but no response body.",
    "severity": "blocker",
    "affected_scope": ["POST /transfer"],
    "required_supplement": "Provider response envelope and error codes.",
    "acceptance_criteria": "The envelope fields and outcome semantics are cited."
  }
]
```

`severity` is `blocker` or `warning`; all string fields are required and non-blank.
`affected_scope` is optional and defaults to `[]`.

Run `assess-sources` after manifest/preprocess. A `reject` stops the run before
`inventory.json`. Supplemental materials create a new immutable source-set version.
When a development sandbox issue occurs, trace it through provenance, the source-quality
report, source diff, and contract diff before requesting a supplement or rerunning.

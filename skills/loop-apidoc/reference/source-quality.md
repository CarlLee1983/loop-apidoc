# Source quality gate

Before inventory extraction, the controller writes `source-quality-observations.json`
from a read-only review subagent. Every observation must cite a source and locator,
describe evidence, scope, required supplement, and acceptance criteria. The subagent
returns JSON only; it never writes files or decides the final verdict.

Run `assess-sources` after manifest/preprocess. A `reject` stops the run before
`inventory.json`. Supplemental materials create a new immutable source-set version.
When a development sandbox issue occurs, trace it through provenance, the source-quality
report, source diff, and contract diff before requesting a supplement or rerunning.

---
status: accepted
---

# Supplementary carriers buy accountability, not verifiability

Some normative information about a supplier's API exists only in correspondence — how to obtain
a sandbox key, where the test environment lives, what must be done before go-live, what a
merchant parameter actually means. It is not in any document, and the supplier often has no
intention of putting it there. The same is true of the field-mapping spreadsheet that arrives
alongside the manual.

Until now there were two options and both were bad. Leave it out: the information becomes
`missing`, the integration contract has a hole, but the report is honest. Or let the agent read
it and write it into the extraction: the contract is complete, and `provenance.json` now claims
a normative claim has source support that exists in no manifest entry. The second option makes
the report lie, and nothing in the pipeline would ever notice.

## The decision

Correspondence excerpts and re-saved spreadsheets enter as a third thing: a **supplementary**
source. They may be cited, may fill `missing`, and may make a claim stand. They may not outrank
a formal document, and they may not be indistinguishable from one in a report.

The level lives on the source, not on the claim. Being unre-obtainable is a property the carrier
has, and it holds for every claim that carrier ever supports; putting it on the claim would
restate the same judgement N times and give N chances to get it wrong. It is also deliberately
not folded into `derived_support` — that relationship means *inferential distance*, and mixing
carrier credibility into it would leave nobody able to tell which of the two a
`derived_support` meant.

The dividing line is re-obtainability, not medium. A supplier engineer's email is written by the
supplier, exactly as the PDF is; medium is not what makes it weaker. What makes it weaker is
that `freshness/` compares SHA-256 to detect drift and `governance/` triggers re-review from
that comparison, and an email has no URL, no version, and no second fetch. Anything that
`check-freshness` cannot periodically re-walk is supplementary, whatever it is made of.

## The breach we are accepting

An excerpt is written by a person. That person can transcribe wrongly, compress away a
condition, or read more into a sentence than it said — and no part of the pipeline can tell.
Every other source class in this repository is verifiable: the bytes are hashed, the fragment is
addressable, and a reader can go back to the original and check. This one is not.

`excerpted_by` is therefore not a verification mechanism. It records **who to ask** when a claim
turns out to be wrong. That is strictly weaker than what every other source offers, it is the
entire cost of this path, and it is the reason a supplementary source can never reach
`explicit_support` no matter how well written the excerpt is.

We accept it because the alternative is worse in a specific way. Excluding the carrier does not
make the information stop existing — it makes it arrive through an unrecorded channel, because
an engineer who knows how the sandbox key is obtained will type it into the extraction whether
or not there is a legitimate path for it. A recorded weak source beats an unrecorded one
masquerading as a strong one.

## What follows from it, and what does not

Two questions that looked like one turn out to be different, and they get different functions.

`source_guard` skips `source_violations` entirely when attribution is unambiguous, and it asks
`sole_normative_source()` — supplementary carriers ignored. Otherwise adding one excerpt to a
single-manual corpus would refuse the entire run at the input boundary, before a run directory
exists. Supporting material must never cost the manual its run.

`classify_item` asks `sole_source()`, which counts every usable document including supplementary
ones. Its fallback attributes an unresolvable locator to the one document present, and that
licence rests entirely on there being only one. An excerpt is a second document. Were it
excluded here, a citation reading "供應商信件 2026-08-16" would be recorded as `supported` by
`manual.md` — a claim attributed to a document that never made it, and `SUPPLEMENTARY_SUPPORT`
would stay silent because the citation now names the manual. That is precisely the failure this
distinction exists to prevent, reintroduced by the fix for it.

The asymmetry is the point: skipping a boundary check defers reporting to per-entry validation,
while attributing a locator asserts something about a document's contents. Only the first stays
safe once a second document exists. With an excerpt in the corpus, an unresolvable locator is
ambiguous and stays `UNVERIFIED` until the agent cites precisely.

A claim resting only on a supplementary source is named individually, as a warning-severity
`SUPPLEMENTARY_SUPPORT` at that plan item, and not as one run-level warning.
`SOURCE_FACTS_UNSCANNED` already demonstrated where run-level warnings end up: nine benchmark
cases carry it permanently and it now needs a paragraph of documentation explaining how to tell
its three causes apart. "The only basis for this normative claim is an email" must not become
background noise.

The plan item stays `supported`. `unverified` means the citation does not resolve to a manifest
source; an excerpt resolves fine — it has a file, a digest, and a sidecar. Reusing that status
would make its remedy ("re-read the affected scope and add the citation") advise something that
cannot be done, because there is nothing to re-read.

In `shadow` and `strict`, a supplementary carrier's support proposal and evidence reference are
withdrawn before the Core sees them. Filename-only legacy citations already degrade on their
own, so the exposure was the v1 exact reference: it owns its declared claim path and would
otherwise carry an excerpt into a Core candidate with the manual's standing. The withdrawal is
deliberately not a relabelling to `insufficient` — the Core model forbids a runtime from
proposing that, because insufficiency is Core's conclusion after verification, not a runtime
assertion. Removing the proposal lets Core reach that conclusion itself.

**Not decided here:** what happens when a supplementary source and a formal document disagree.
The intended rule is that the formal document wins without raising `SOURCE_CONFLICT`, since the
resolution is deterministic and needs no human judgement. The deterministic layer cannot enforce
it today: `source_conflicts[]` is free text declared by the extraction agent with no per-source
attribution, so nothing in `validate/` can tell which side of a conflict is supplementary.
Enforcing it requires extending the extraction schema, which is a separate change. Until then
the rule lives as guidance to the extraction agent.

**Falsified if:** a supplementary source becomes indistinguishable from a normative one at any
point where a claim's support is judged. Concretely, this decision no longer holds when
`loop_apidoc/agentcli/source_guard.py` stops asking `sole_normative_source()`, when
`loop_apidoc/validate/authority.py` stops naming supplementary-only claims individually, when
`loop_apidoc/shadow/bridge.py` lets a supplementary citation reach `explicit_support`, when
`loop_apidoc/freshness/record.py` fingerprints a supplementary source, or when
`loop_apidoc/manifest/models.py` drops `SourceAuthority`.

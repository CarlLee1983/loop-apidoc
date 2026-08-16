---
status: accepted
---

# The two Markdown scanners stay separate, and their divergences are pinned

Two modules read structured Markdown and pull endpoint declarations, parameter tables, and
fenced examples out of it: `source_facts/markdown.py` and `markdown_drafts/markdown.py`. They
duplicate the shapes they look for and disagree about several of them. Read cold, that looks
like an oversight waiting to be DRYed up.

It is not. They answer to different consequences. `source_facts` feeds the fail-closed semantic
completeness gate: everything it reads becomes something the extraction *must* produce, so a fact
it invents blocks a correct extraction. `markdown_drafts` produces non-authoritative draft JSON
that an agent copies, re-reads against the source, and fills in by hand; a shape it misses or
over-reads costs a reviewer one more glance. Strictness that is correct on one side is wrong on
the other, in both directions.

## The divergences, as measured

Neither scanner is uniformly the stricter one — each is looser exactly where its own job needs
it. `tests/source_facts/test_scanner_divergence.py` pins every row.

| shape | `source_facts` | `markdown_drafts` | why |
| --- | --- | --- | --- |
| bare / backticked / list / bold declaration line | reads | ignores | The draft's unit is a section, and a declaration with no heading opens none. The gate has no sections: it reads a fact wherever the fact is. |
| heading that *is* the declaration | reads | reads | The least ambiguous shape there is. |
| heading with a prefix (`## 支付 GET /a`) | ignores | reads | The gate anchors its match at the start; the draft searches the whole line. Anchoring is what keeps "見 POST /pay 的說明" out of the fact inventory. |
| lowercase method | ignores | reads (case-insensitive) | Same trade: case-insensitive matching widens the prose surface a fail-closed gate is exposed to. |
| GitBook's `` `GET` `` + `` `/a` `` pair | ignores | reads | **A gap, not a decision** — see below. |
| declaration inside prose | ignores | ignores | Reading it would be guessing, on either side. |
| unlabelled parameter table | reads | ignores | The draft needs a `**Request**`-style label to know which section a field belongs to; the gate only asks whether the source documents the field at all. |
| fenced block in any language | counts as an example | only whitelisted languages | The gate needs the fact "an example exists here"; the draft has to paste the example, so it takes only languages it can carry. |
| closing fence carrying an info string | refuses (strict CommonMark) | accepts | ADR 0008. Leniency in the gate turns two adjacent samples into one open/close pair and leaks the material between them into the fact inventory. |

## Considered options

- Sharing one scanner, or one set of regexes, removes the duplication but couples a fail-closed
  gate to a draft generator: a change made to improve draft output silently moves the gate, and
  the symptom is a run that fails for a reason nobody edited. The duplication is the cheaper of
  the two costs.
- Converging the gate onto the draft's looser rules (prefix headings, lowercase methods) would
  close real recogniser gaps, but it widens the prose surface of the side where a false positive
  is expensive. Measured against the thirteen benchmark cases, all three candidate widenings —
  prefix headings, lowercase methods, and the GitBook pair — occur **zero** times, so there is
  currently no coverage to win and a fail-closed gate to risk.
- Converging the draft onto the gate's stricter rules loses draft coverage for no benefit: the
  draft is reviewed by a human before anything downstream trusts it.

## Consequences

The GitBook `` `GET` `` + `` `/a` `` pair is the one row that is a gap rather than a decision.
It is a literal declaration, not an inference, and recognising it would not weaken the gate. It
stays unrecognised only because no source in the current corpus uses it, and widening a
fail-closed gate for a shape nobody has is speculative work with a real downside. A source that
uses it is the trigger to close the gap — and, until then, such a source shows up as a
`SOURCE_FACTS_UNSCANNED` warning rather than as silence (ADR 0007), which is what makes waiting
safe.

Anything that changes a row in the table changes this decision, and the pinned test is where that
shows up first.

**Falsified if:** the two scanners stop being separately governed. Concretely, this decision no
longer holds when `loop_apidoc/source_facts/markdown.py` and
`loop_apidoc/markdown_drafts/markdown.py` share a scanning implementation or a common regex
module, or when `tests/source_facts/test_scanner_divergence.py` no longer pins both sides of each
divergence.

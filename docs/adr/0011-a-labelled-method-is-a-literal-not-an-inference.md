---
status: accepted
---

# A labelled method on the declaration line is a literal, not an inference

ADR 0007 fixed the source-fact scan to well-structured Markdown and refused to widen the endpoint
recogniser past `METHOD /path`, on the grounds that the eight benchmark sources it could not read
carry "a concrete URL with no method beside it" and that reading them would require *inferring* the
method. ADR 0009 recorded the opposite judgement for one shape — GitBook's `` `GET` `` + `` `/a` ``
pair — calling it "a gap, not a decision", a literal declaration whose only reason for staying
unrecognised is that no source in the corpus uses it.

The two are not in conflict about principle. They are in conflict about one question 0007 never
asked: **when the method is written out on the same line but not in the position the recogniser
expects, is reading it an inference?** It is not. Inference is supplying a fact the bytes do not
carry. Reading `POST` out of `URL <API URL>/CreateMember Method POST Return JSON` supplies nothing.

## What the corpus actually contains

The premise this decision was opened on — that the eight sources use a GitBook-adjacent same-line
shape — is false, and the measurement is the reason this ADR exists rather than the one that was
planned. Applying the proposed rule ("a line containing both a full URL and an uppercase HTTP
method literal is a declaration") to every Markdown source in the thirteen benchmark cases,
outside code fences, yields **zero real declarations and six false ones**. The six are prose:

- `tappay-backend-api.md:7` — "Our server adapts [REST](https://en.wikipedia.org/…) archetype, so
  all requests are sent using HTTP POST." A URL-plus-method rule reads this as
  `POST /wiki/Representational_state_transfer`.
- `RefundApi.md:16`, `RefundApi.md:66`, `VoidApi.md:67`, `VoidApi.md:167` — CyberSource sentences
  that name a path inside a Markdown link and a method later in the same sentence.
- `rsg-game-transfer-wallet.zh-TW.md:1` — the 38 KB single-line dump, which contains every shape at
  once and is already the worked example in ADR 0007.

The real shapes are three, and each crosses a different line:

| source | shape | recognised here |
|---|---|---|
| `jili-legacy-gaming-pdf` (21 `URL`+`Method` lines) | `\|URL\|<API URL>/Login\|Method\|GET\|Return\|HTML\|`, and the flattened `URL <API URL>/CreateMember Method POST Return JSON` | **11 of them** — see below |
| `ecpay-creditcard-pdf` (14 declarations) | `- 正式環境：https://…` on one line, `- HTTP Method ：POST` six lines later | no — cross-line, exactly 0007's inference |
| `tappay-backend` (1 declaration) | method in a table header `\| POST \| Url \|`, URLs in the rows below | no — cross-line |

`newebpay-mpg`, `line-pay-online-v3`, `cybersource-payments`, `github-webhooks` and
`paypal-webhooks-incomplete` are reachable by no same-line rule at all; newebpay's only method
literal lives inside a `<form method=post>` in a fenced block, and the two webhook cases have no
path to key on (0007 already says so).

## Decision

An endpoint declaration is also recognised when one line carries a `URL` label, a value from which
a path can be read literally, and a `Method` (or `HTTP Method`) label followed by an uppercase HTTP
method literal — in that order. Three narrowings carry the whole safety argument:

- **Labels must stand alone as words.** Without that, `curl`, `URLs` and any prose containing them
  become label matches, which is how the six false positives get in.
- **The method must be an uppercase literal.** Lowercase `method = "GET"` is a code key or prose,
  and `line-pay-online-v3` proves the shape exists in the corpus.
- **The value between the labels is capped at 80 characters and must yield a path** — an absolute
  URL's path, a placeholder base plus path (`<API URL>/Login`, `{host}/v1/pay`), or a bare path.
  `| URL | 參見附錄 A | Method | POST |` and a host-only URL produce nothing. Under a fail-closed
  gate a guessed path costs an operator who cannot ship correct work; a missed one costs a check
  that did not run.

Two more narrowings are structural rather than lexical, and both were found by trying to break the
first draft rather than by reading the corpus:

- **Only the first row of a pipe block can be a declaration.** A row in the middle of a real
  parameter table (`|URL|/callback|Method|POST|` as a config row) would otherwise both invent an
  endpoint and cut its own table in half, dropping every field below it — a false fact and lost
  facts from one row.
- **A declaration that precedes every heading ends at the first heading.** Its declaring level is
  0, no heading level is ≤ 0, and the section would otherwise run to the end of the document and
  claim every table in it. PDF-converted sources routinely open with the declaration block, so
  this shape is the norm, not an edge case. The cost is real and chosen: such a declaration can no
  longer own its own sub-headed tables either, so `POST /pay` followed by `## Request` and a
  parameter table now yields no field facts where it used to yield some. Ending only at level-1
  headings would keep those, but a document whose headings are all `##` would go back to being
  swallowed whole. Losing a fact costs a check that did not run; keeping a false one costs an
  operator who cannot ship — so the loss is the right side, and it is pinned as a test rather than
  left as a surprise.

The separator between the labels is one flat character class with one quantifier. Written as three
optional pieces it is ambiguous about which one consumes a space, and a *near-miss* line — the same
labels with column padding, which is exactly what `pdftotext -layout` emits — backtracks
exponentially: sixteen spaces took two seconds, twenty-five did not finish. A correctness suite
cannot see that, so `test_labelled_endpoint.py` asserts the elapsed time on a padded near-miss.

The reverse order (`Method` before `URL`) stays unrecognised, following 0009's precedent: no source
uses it, and widening a fail-closed gate for a shape nobody has is speculative work with a real
downside. So does the GitBook pair — this decision does not close 0009's gap, and the measurement
above shows its stated trigger ("a source that uses it") has still not occurred.

This does not supersede ADR 0007. Its core claim — the scan does not infer a missing method and
does not grow heuristics for flattened prose — survives intact, and `ecpay`'s fourteen cross-line
declarations remain unread precisely because of it. Nor does it touch 0007's falsification
condition: the scan still admits only Markdown, and `fact_coverage.py` still reports what the gate
could not judge.

## A false fact this uncovered, and the second change it forced

Recognising jili's declarations made the gate judge that source for the first time, and it
immediately produced a false requirement: `KickMemberAll` was said to document a parameter named
`Success`. The PDF converter had glued an error-code table onto the end of a parameter table inside
one pipe block, and `Success` is an error *message*, not a field. The gate would have blocked a
correct extraction — the exact failure 0007 exists to prevent, arriving through the widening rather
than despite it.

So a row that has exactly one non-empty cell, and that cell names itself an error-code header
(`Error code:`, `錯誤碼`), now ends the parameter table it appears in; the rows after it belong to
another table. Both halves are load-bearing: a field genuinely named `錯誤碼` — an upstream
gateway's error passthrough — is an ordinary field, and truncating on the name alone would drop
every field below it silently, which is the invisible no-op `fact_coverage.py` exists to surface.
The cut is made before the name column is chosen, not while emitting rows: the error table's code
column (`0`) is not identifier-shaped, so leaving those rows in the body makes the scan pick the
wrong column and lose the real field too — `KickMemberAll` yielded neither `Success` nor `GameId`
until the order was fixed. Generic group labels (`Header`, `Query`) still only skip their own row.

This is a narrowing of what the scan reads, not a widening, and it was latent before this change —
invisible only because no endpoint had been declared above that table.

## Consequences

One benchmark case changes: `jili-legacy-gaming-pdf` loses its `SOURCE_FACTS_UNSCANNED` warning
because its source now scans to facts that match the extraction, which is worth roughly 12 points
in the source-grounding category for that case. The other eight warned cases are unchanged, and
that is the honest reading — their shapes were never what this decision was opened to cover.

**Which half of that source is read matters, and it is half.** The document carries 21
`URL`+`Method` lines; 11 are recognised. Eight of the other ten are refused by the uppercase rule —
the same author writes `Method|Get|` in five places and `Method|Get/Post|` in others — and two by
the label boundary, both struck through (`~~URL~~`) because the endpoint is deprecated, where the
silence is exactly right. Refusing the title-case eight is a deliberate deviation, not an oversight: #97 drew the line at an uppercase literal, and relaxing case
is precisely the row where ADR 0009 records the two scanners diverging on purpose. `Get` in a
`|Method|` column is admittedly no more an inference than `GET`; if that line moves, it moves in
both ADRs at once, and `test_labelled_endpoint.py` pins it as a negative until then.

Coverage of the recognised half is also thinner than the endpoint count suggests: most of jili's
parameter tables open with an empty leading cell (`||Parameter|Type|…`), and a table whose first
header cell is not name-like is not read at all, so eight of the eleven endpoints carry zero
parameter facts. `CreateMember` yields `Account`, `KickMemberAll` yields `GameId`, and the rest give
the gate an endpoint identity and nothing to check on it. The warning is gone because the source is
no longer unjudged, not because it is now fully judged.

No benchmark case was added. The eight are real sources in real shapes and were already a known
failure baseline; a synthetic case would cost a new snapshot and an operator-local `source-quality/`
bundle while proving less.

The boundary lives in `tests/source_facts/test_labelled_endpoint.py` rather than in this prose,
positives and negatives alike, including the six corpus false positives as explicit negatives. A
benchmark tells you a warning disappeared; it does not tell you which spellings were accepted and
which were refused, and narrowness is this decision's entire value.

**Falsified if:** the recogniser stops requiring both the method and the path to be literal on one
line. Concretely, this decision no longer holds when `loop_apidoc/source_facts/markdown.py` derives
a method from a line other than the one carrying the path, accepts a method that is not an uppercase
literal, emits an endpoint whose path was not read out of the declaration's own value, or relaxes
either of the two narrowings that keep prose out — the standalone-word label boundaries and
`_LABELLED_VALUE_MAX_LENGTH`; or when `tests/source_facts/test_labelled_endpoint.py` stops pinning
the negative cases.

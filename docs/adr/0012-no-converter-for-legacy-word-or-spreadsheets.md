---
status: accepted
---

# No converter is built for legacy Word or spreadsheets — the operator converts, the pipeline says so

`.docx` has a complete OOXML subsystem in this repo: preflight validation, rendering, staged
publication, its own risk checks. `.doc` gets a passthrough and a sentence. `.xlsx` gets nothing at
all. Read cold, that reads as unfinished work, and the obvious "fix" is to write the two missing
converters. It is not unfinished. It is a decision, and this record exists because reversing it is
cheap enough that someone will do it by accident.

## The argument

A converter for either format is not a parsing problem, it is a series of judgement calls, and every
judgement call is an opportunity to manufacture a fact. Spreadsheets carry merged cells, formulas
whose displayed value differs from their content, multiple sheets with no declared relationship, and
formatting that means something to a human and nothing to a parser. `html_snapshot.py` needed the
longest single explanation in `AGENTS.md` just to keep `colspan`/`rowspan` from misaligning
parameter tables; a spreadsheet is that problem with more degrees of freedom and less structure to
appeal to. Legacy `.doc` is an OLE compound file whose text extraction is heuristic in every
available library.

The asymmetry that governs the rest of this pipeline governs here too: under a fail-closed gate a
missed fact costs a check that did not run, while a fabricated one costs an operator who cannot ship
correct work. An operator converting a spreadsheet in Excel sees the merged cells with their own
eyes and decides what the table means. A converter would decide silently, at scale, in a fact
inventory that downstream treats as ground truth.

The work is also not ours to do well. Exporting a sheet as a Markdown table is a two-minute
operation in software the operator already has open; matching that quality from a library is weeks
of edge cases for a source class that arrives a few times a year.

## Decision

Neither `.doc` nor `.xlsx`/`.xls` is converted by this pipeline. Both are **recognised** as their
own `SourceFormat` (`word-legacy`, `spreadsheet`), marked unsupported, and reported with a remedy
that names the next step in the operator's own hands.

Recognition is the entire point, because the outcome is identical either way — a `.xlsx` that falls
through to `UNKNOWN` is refused just as firmly. What differs is whether the refusal can be acted on.
That was the whole value of the 0.37.0 change for `.doc` (`docs/RELEASE_NOTES_0.37.0.md:40-45`):
nothing new became supported; a silent failure became a loud one that names the next move. A format
that is refused without a remedy leaves the operator holding a file and no next step, which is how a
one-minute problem becomes a support thread.

The remedy is one decision stored once, in `manifest/formats.py`, and read by all four sites that
report the refusal: the preparation-readiness warning, the coverage warning, the score finding, and
the `preprocess` passthrough line. The preparation warning also became per-source rather than one
joined line — two refused formats have two different next steps, so a single sentence covering both
is necessarily wrong about one of them. Its previous text said "convert unsupported inputs during
preprocess", which was worse than an unhelpful remedy: it named an action this pipeline does not
perform, since `preprocess` copies both formats byte-for-byte.

Two languages are kept side by side because `validate/` reports in Chinese by earlier decision while
`preparation/` and `score/` write their own findings in English — not because score reports are
English, since `score/evaluate.py` passes validation findings through with their Chinese remedy
intact, so both languages already coexist in one report. Unifying them is a separate decision. The
wording deliberately ends at "put it back in `sources/` and preprocess again" rather than naming a
run-level action, because the passthrough line is printed before any run directory exists and the
mandatory order starts at preprocess — so the same sentence is true in all four places.

**The spreadsheet remedy does not mention CSV**, though the originating issue proposed it. `.csv` is
not in the extension table either, so it lands in exactly the same unsupported state — advising it
would send the operator in a circle. Source facts are read only out of Markdown, so a Markdown table
is the only export that actually reaches the gate.

## Considered options

- **Building the converters** recovers content without operator effort, but feeds guessed structure
  into a fail-closed gate. This is the same reasoning ADR 0007 applies to flattened HTML, and the
  same conclusion.
- **Leaving `.xlsx` in `UNKNOWN`** costs nothing to implement and refuses the file just as
  effectively, but cannot name a remedy, because at that point the pipeline genuinely does not know
  what it is looking at. The two lines in the extension table buy the difference between "not
  supported" and "not supported, here is what to do".
- **Routing spreadsheets through the supplementary-carrier path** (ADR 0010) instead: that path
  handles a *carrier* whose content a human has already excerpted into Markdown, which is the same
  motion this remedy asks for. If a spreadsheet's content must enter the pipeline as evidence rather
  than as documentation, it goes in as a supplementary note with a sidecar — `authority:
  supplementary`, not on a par with a formal document. That composes with this decision rather than
  competing with it.

## Consequences

Adding a format here is two lines and a remedy, so the cost of extending the same treatment to the
next unreadable-but-recognisable format is near zero — and that is deliberate, because the failure
mode being guarded against is a format that is refused with nothing to say.

An operator with a spreadsheet still has work to do, and the pipeline is now explicit that the work
is theirs. That is the honest position: the alternative is not "less work", it is the same work done
worse by a machine that cannot see the merged cells.

One migration consequence is worth stating plainly, because its error message does not name the
cause. `source_risk/inspect.py`'s `source_binding_digest` hashes each source's `source_format.value`,
so a corpus containing `.xls`/`.xlsx` that was risk-scanned before this change no longer matches the
rebuilt manifest, and `assemble --source-quality` refuses the run with a source-binding mismatch.
That is fail-closed and correct — the package genuinely changed how it is described — and re-running
`inspect-source-risk` resolves it, but an operator hitting it will not guess why.

`docs/PRODUCT_EXTENSION_ROADMAP.md` and `docs/DESIGN_DECISIONS.md` keep their statements of fact and
link here for the reasoning, rather than restating the trade-off in three places.

**Falsified if:** either format stops being an explicit, remedied refusal. Concretely, this decision
no longer holds when `loop_apidoc/manifest/formats.py` maps `.doc`, `.xls` or `.xlsx` to a supported
format or drops their remedies; when any of the four reporting sites stops reading them —
`loop_apidoc/preparation/assess.py`, `loop_apidoc/validate/coverage.py`,
`loop_apidoc/score/evaluate.py`, `loop_apidoc/cli.py` (the `preprocess` passthrough line lives there,
not in the preprocess module) — and hardcodes its own wording instead; or when
`loop_apidoc/agentcli/preprocess.py` converts either format instead of passing it through.

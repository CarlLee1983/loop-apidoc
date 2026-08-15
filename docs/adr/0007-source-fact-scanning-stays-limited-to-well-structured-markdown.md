---
status: accepted
---

# Source-fact scanning stays limited to well-structured Markdown, and the cost is disclosed

The semantic completeness gate compares an extraction against facts read mechanically out of the
sources. Those facts come from one place: a Markdown scan that recognises endpoint declarations,
parameter tables whose first header cell is name-like, and fenced example blocks. An HTML source
never reaches that scan at all, and a source produced by flattening HTML into a single line of
text reaches it and yields nothing. In both cases the gate has nothing to compare, so it passes
silently.

A third shape hides inside the same class and matters just as much: a source whose Markdown
structure is intact — headings, GFM tables, the lot — but whose endpoints are not written as
`METHOD /path`. `benchmarks/tappay-backend` documents every operation as a full URL inside a code
comment, and the scan reads nothing from it. The failure there is the recognizer's, not the
source's, and no amount of re-running preprocessing will change it.

The scan is deliberately not widened to cover them. Structure is what makes a fact mechanical;
guessing structure out of a prose dump manufactures facts, and under a fail-closed gate a false
fact blocks a correct extraction. The asymmetry is decisive — a missed fact costs a check that
did not run, a fabricated one costs an operator who cannot ship correct work.

What is fixed instead is the visibility of that limit. Every run now projects, per manifest
source, how many facts were scanned and how many of them matched the extraction by endpoint
identity, and `validate/fact_coverage.py` turns a source with zero facts, or with facts that
matched nothing, into a warning-severity `SOURCE_FACTS_UNSCANNED` issue. `verify-extraction`
forecasts the same projection before a run directory exists.

The severity is fixed at warning, not error. A legitimate prose-only source with no parameter
tables lands in the zero-fact class, and failing it would be reading "could not be measured" as
"is wrong" — the same confusion the scan itself refuses to make. It is scored, though, under
source grounding: two runs of the same product should differ in score when one of them had more
sources the gate never judged.

## Considered options

- Failing a run whose sources all scan to zero facts would make the limit impossible to ignore,
  but it fails correct work: a provider that documents everything in prose has produced a
  legitimate source, and the pipeline would be refusing it for being unmeasurable.
- Widening the scan with heuristics for flattened text (treating repeated `word type
  description` runs as a parameter table) would recover some coverage, but it invents structure
  that is not in the bytes and would feed a fail-closed gate with guesses.
- Leaving the limit documented only in the module docstring, a pinned test, and the 0.14.0
  release notes — the state before this decision — keeps the code honest but not the product:
  the operator holding the run directory is precisely the person who cannot see any of those.
- Reusing `SOURCE_UNVERIFIED` for the warning would have avoided a new code, but that code's
  remedy is to re-read the source and fill the JSON. Applied to a flattened dump, that remedy
  is an infinite loop: there is nothing in the text to find. The remedy here is to re-run
  preprocessing along a path that preserves tables (`normalize-html-snapshot`, `preprocess`),
  which is a different action taken by a different actor.

## Consequences

Nine of the thirteen benchmark cases now carry this warning permanently, and that is the intended
reading: those runs were never judged by the gate, and the reports said nothing about it. The
0.36.0 release notes list which cases and how many sources each. They are not all the same
problem — some sources are genuinely flattened, others are well-formed Markdown the recognizer
does not understand — which is why the issue's remedy text enumerates the causes instead of
asserting one.

The score cost is real and worth stating plainly: a warning costs 12 points in its category and
`source_grounding` carries 20% of the total, so a case like `cybersource-payments` with 24 such
warnings floors that category at 0 and loses the full 20 points. Runs gated on an absolute
`--min-score` threshold will need that threshold revisited; run status and exit codes are
unaffected.

A warning that is always present for a given corpus does teach people to ignore it (the concern
ADR 0006 weighs), and that cost is accepted here because the alternative is worse: the
information it carries is not "you omitted something" but "this run's central invariant went
unchecked for these sources", which is exactly what an operator must not infer from silence.

The zero-match class also gives the second-order benefit of naming a source whose facts exist but
line up with nothing the extraction claims — usually a missed endpoint, occasionally a
misparsed table.

**Falsified if:** source facts stop being limited to well-structured Markdown, or the limit stops
being disclosed. Concretely, this decision no longer holds when `loop_apidoc/source_facts/collect.py`
admits a source format beyond Markdown into the scan, or when `loop_apidoc/validate/fact_coverage.py`
stops reporting sources the gate could not judge.

# loop-apidoc 0.37.0 release notes

Release date: 2026-08-16

## Summary

Truthful source handling: table structure, unclosed fences, scanner divergences, and honest format claims

## Changed

This release is the follow-up wave to 0.36.0's `SOURCE_FACTS_UNSCANNED`. Making the
source-fact gate's blind spots visible exposed what was hiding behind them, and each item
below is one of those, fixed at the point where it silently produced or destroyed a fact.

- **HTML tables keep their structure.** `normalize-html-snapshot` previously flattened a
  nested table's rows into the enclosing table, ignored `colspan`/`rowspan` entirely, and
  always took the first row as the header. A misaligned parameter table then became a
  source fact the source never stated — and under the fail-closed completeness gate, a
  fabricated fact blocks a correct extraction. Tables are now expanded into a rectangular
  grid, a nested table renders as its own block, out-of-range or non-numeric spans count
  as 1, overlapping spans discard the whole table, and a multi-row `thead` merges into the
  single header row GFM allows. A spanning cell's text stays in its own column and the
  columns it covers are left blank, which is what keeps a group-title row ("Header",
  「支付類」) distinguishable from a parameter row downstream.
- **An unclosed fence is named instead of failing silently.** A closing fence carrying an
  info string (```` ```json ````) is not a close under CommonMark, so the scan treated
  everything after it as fence content — zero facts, no error. The strict rule stays
  (relaxing it leaks code samples into the fact inventory), but `SOURCE_FACTS_UNSCANNED`
  and the `verify-extraction` forecast now name the line where the fence opened. The
  warning also fires when a source is only *partly* unread, which is the more dangerous
  shape: the gate ran, judged what it could see, and the report looks clean. A fence that
  simply runs to end of input with no refused close is not reported — CommonMark closes it
  too, so nothing was lost. (ADR 0008)
- **The two Markdown scanners are separately governed, and their divergences are pinned.**
  `source_facts/markdown.py` and `markdown_drafts/markdown.py` disagree on nine shapes, and
  neither is uniformly the stricter one — each is looser exactly where its own job needs
  it. They must not be unified: a change made to improve draft output would silently move a
  fail-closed gate. A new test pins every row, so a divergence can only change deliberately.
  (ADR 0009)
- **`.doc` is no longer claimed as supported.** The manifest reported legacy binary Word as
  `supported: pending`, `preprocess` copied it through with "agent must read source format"
  — which an OLE compound file makes impossible — and only `inspect-source-risk`, two
  stages later, refused it. It is now detected as `word-legacy` and reported unsupported at
  the first stage, with a remedy that works: re-save as `.docx` or PDF. `.docx` is
  unaffected; it has a full preprocessing path.
- **A number is only an error code when the page says so.** The URL corpus registered any
  four- or five-digit run as an error-code entity: years, amounts, timeouts, ports. Across
  the benchmark corpus that is 761 matches of which 8% sit next to a word calling them a
  code. An entity now needs a cue (`error`/`code`/`錯誤`/`代碼`/`狀態`) within a tight
  window, and a year-shaped value never qualifies. These entities only feed related-page
  scoring, so precision is what is worth having.
- **Validation speaks one language.** `validate/coverage.py` and
  `validate/response_contract.py` each chose their own, so one report addressed the
  operator in two. All issue text is now `zh-TW`, and the rule is recorded in `AGENTS.md`
  rather than in one module's docstring, where only that module's readers would find it.

## Strategy impact

- [ ] None — <explain why no strategy document changed>
- [x] Updated — `docs/adr/0008-an-unclosed-fence-is-reported-not-guessed-shut.md`,
  `docs/adr/0009-the-two-markdown-scanners-stay-separate.md`

## Notes for operators

No benchmark expectation changed in this release, and no run's pass/fail or exit code
changes. The HTML table fix affects documents processed by `normalize-html-snapshot` from
now on; sources normalized before this release keep whatever structure they were given, so
re-normalizing a source is what applies the fix to it — and that will change its scanned
fact count.

## Validation

- `npm run tag:check`
- `uv run ruff check .`
- `uv run pytest --cov=loop_apidoc` (2227 passed)
- `uv run python scripts/quality_gate.py --strict-local` (13 cases, zero skips)
- `npm run docs:check`

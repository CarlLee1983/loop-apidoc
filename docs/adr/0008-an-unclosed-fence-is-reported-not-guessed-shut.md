---
status: accepted
---

# An unclosed fence is reported, not guessed shut

`source_facts/markdown.py` tracks fenced code blocks so that a JSON sample inside one never
becomes a source fact. Following CommonMark, a closing fence must carry no info string: a line
reading ```` ```json ```` opens a fence, it never closes one.

Some sources close their fences that way anyway — pairing ```` ```json ```` with ```` ```json ````
reads naturally to a human, and a renderer that is lenient about it will display the document
correctly. Under the strict rule the scan treats everything after that line as fence content, so
the rest of the document is never read: zero facts, no error, and a result identical to a source
that genuinely has no structure.

The strict rule stays. The alternative — accepting an info-string line as a close — is a guess
about which of two readings the author meant, and it is wrong in the case that costs the most: two
adjacent opening fences (a JSON request sample followed by a JSON response sample, each opened and
closed in the ordinary way, with a stray info string on one close) would be read as one open and
one close, putting the sample *between* them outside any fence. Its contents then become source
facts. A fabricated fact blocks a correct extraction under the fail-closed completeness gate,
which is the harm this project consistently refuses to risk (ADR 0007).

What changes is that the failure is no longer silent. `SourceFacts` records the line where such a
fence opened, the coverage projection carries that line, and the `SOURCE_FACTS_UNSCANNED` warning
(ADR 0007) names it: the operator is told which line to open instead of being handed three possible
causes to choose between. `verify-extraction` forecasts the same line before a run directory exists.

The record is made only when the scan saw a line that *looks* like a close and was refused — an
info string on the closing fence, or a marker that does not match the opening one. A fence that
simply runs to the end of the document without any such line is not reported: CommonMark closes an
unterminated fence at end of input, so every reader agrees with the scanner and nothing was lost by
the strict rule. Reporting it anyway would send an operator to fix a source that is not broken, and
the fact count after the "fix" would be unchanged.

The warning also fires when the source is only *partly* unread — facts before the fence matched the
extraction while everything after it went unread. That case is more dangerous than a wholly
unscanned source, not less: the gate ran, found nothing wrong with the part it could see, and the
report looks clean.

## Considered options

- Accepting an info-string line as a closing fence fixes the documents that pair their fences that
  way, but it is a guess, and the case it gets wrong leaks a code sample into the fact inventory.
  A missed fact costs a check that did not run; a fabricated one costs an operator who cannot ship
  correct work.
- Re-scanning leniently *only when* the strict scan ends inside a fence would bound the guess to
  documents the strict scan definitely failed on. It is tempting and still rejected: a source that
  is genuinely truncated mid-sample ends inside a fence too, and that is precisely when a lenient
  re-scan reads the truncated sample as prose.
- Failing the run on an unclosed fence would guarantee nobody ships an unread source, but a fence
  that never closes is a defect in the *source*, and the pipeline's answer to a defective source is
  to report it, not to refuse to produce the artifacts an operator needs in order to judge it.
- Leaving the limit undisclosed — the state before this decision — makes an unread document
  indistinguishable from an unstructured one, which is the exact confusion ADR 0007 exists to
  remove.

## Consequences

A source whose fences are mismatched still yields nothing after that line, and the operator has to
fix the source (or its acquisition path) before the gate can judge it. That is the accepted cost.

The two Markdown scanners now differ on this point deliberately: `markdown_drafts/markdown.py`
closes a fence on any line starting with the marker, info string or not, because its output is
non-authoritative draft material that a human reviews, and a leaked sample there costs a reviewer
one glance. `source_facts/markdown.py` feeds a fail-closed gate, where the same leak costs a
correct extraction. The divergence is catalogued in the scanner-divergence follow-up rather than
resolved by making one match the other.

No benchmark source currently trips this: a scan across all thirteen cases found zero
info-string closes and zero documents ending inside a fence. This decision is therefore about a
failure mode that is cheap to disclose and expensive to misread, not about a fire being put out.

**Falsified if:** a refused closing fence stops being reported, or the scan starts guessing fences
shut. Concretely, this decision no longer holds when `loop_apidoc/source_facts/markdown.py` treats a
line carrying an info string as a closing fence, or when `loop_apidoc/validate/fact_coverage.py`
stops naming the line where the unclosed fence opened.

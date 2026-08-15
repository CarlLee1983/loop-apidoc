---
status: accepted
---

# The documented error-code floor comes from source structure alone

A `collect_error_codes` directive asks for the provider's error codes exhaustively. Until now
nothing established how many codes the sources document, so the cheapest way to satisfy such a
directive was to report one code — an answer indistinguishable in the output from a genuine
sweep.

Where a supplier source presents an error-code table, the codes in it are now a **Documented
Error-Code Floor**: a deterministic lower bound an exhaustive answer must contain. Reporting
fewer is a `FOCUS_INCOMPLETE` validation issue naming the omitted codes and where each is
written down. Reporting more still passes. Where the sources present no such structure there is
no floor and no judgement — the floor is *absent*, which is not the same as zero.

Three parts of that design are deviations a later reader would otherwise correct.

**The floor is global and ignores the directive's own scope.** A directive's `text` is the
operator's own words and carries their intended scope, but the gate is deterministic and cannot
read prose. So a directive worded "collect the refund flow's error codes" is still judged
against every code the sources tabulate. This is deliberate: `collect_error_codes` means what
its name says, and an operator who wants a narrow claim has Expectation Directives, which name
one thing each. The asymmetry — `text` scopes the agent, not the floor — is documented in the
agent-facing focus reference so it surprises nobody twice.

**The floor unions across sources, while the neighbouring endpoint index intersects.** Reading
the two side by side, the inconsistency looks like an oversight. It is not. The endpoint
intersection exists because several sources describing *one endpoint* are competing accounts of
the same thing, and the richest account would widen the requirement past what an extraction was
right to ignore. Error-code tables in different documents are usually *different code sets*
rather than competing accounts, so intersecting would collapse the floor to near-nothing. Stale
documents cannot inflate it either: fact collection reads only manifest sources in the pending
processing state, so duplicate, ignored, and unsupported sources never reach the union.

**The general source-fact gate deliberately does not consume the floor.** The fact exists and
that gate can see it, but only focus directives are judged against it. Requiring every
documented code to appear in the typed catalogue on *every* run would change the verdict of
runs nobody directed, and it deserves its own trade-off discussion rather than arriving as a
side effect of this one. That discussion has since happened and settled on keeping it this way
— see [ADR 0006](0006-requiring-exhaustive-error-codes-stays-a-directive.md).

## Considered options

- Letting the requester declare the expected codes in `focus.json` would be perfectly
  deterministic and need no recognizer at all, but it replaces "the sources document this" with
  "the operator asserts this", which contradicts the Normative Contract's rule that supplier
  sources are the sole authority — and it would let an Expectation Directive satisfy itself.
- Deriving the floor from the URL corpus's error-code entities would reuse material the
  pipeline already produces, but that material is the product of a `\b[1-9]\d{3,4}\b` scan of
  prose, so prices, timestamps and order ids all qualify; the entities carry no line numbers, no
  provenance, and no manifest binding. A test bars both the focus package and the source-fact
  package from reading them.
- Deriving the floor from the extraction's own `inventory.errors[]` would be trivial, but that
  list is what the answer is being judged against — the floor would be a function of the answer
  and could never disagree with it.
- Scanning for error codes inside the focus package instead of the source-fact scanner would
  leave the existing package untouched, but it creates a second table-recognition
  implementation that will drift from the first, and the focus package's loader is by contract
  that package's only read exit.
- Adding a scope field to `FocusDirective` so a directive could narrow its own floor would
  remove the asymmetry above, but the directive contract states that `kind` is the sole
  determinant of severity and `intent` the sole determinant of anchor type, with no override
  fields; this would open the first of them.
- Treating a shortfall as a gate violation rather than a validation issue would fail it earlier,
  but a short answer is well formed — every code in it is real and cited — so the fault is
  substantive, not structural, and a Coverage Directive would become a hard failure in defiance
  of its own `kind`.

## Consequences

Recognition must stay strict, because the asymmetry of costs is severe: a real error-code table
going unrecognised reproduces the behaviour that existed before this decision, while a
misrecognised table produces a false fact, and a false fact blocks a correct extraction. That is
why generic headers (`代碼`, `code`, `status code`) are honoured only when an enclosing heading
is itself an error section, why one malformed data row discards a whole table rather than
lowering the floor silently, and why the scanner stays silent on sources it cannot read
structurally.

One consequence of that vocabulary is worth stating rather than discovering: an HTTP status
table under an error heading is promoted into the floor. Where a provider documents its failures
only as HTTP statuses that is arguably correct; where it also has provider-specific codes it will
over-demand. Narrowing it further is a decision, not a patch.

The floor covers Markdown sources only, because that is all the source-fact scanner reads. A
PDF- or Word-only integration gets no floor, exactly as it gets no parameter-table facts today —
the pre-existing scope limit of that package, not a new one.

Adding `FOCUS_INCOMPLETE` to the scoring exclusion list touches
`loop_apidoc/score/evaluate.py`, which ADR 0004's falsification condition names. That edit keeps
focus outcomes out of the weighted categories, so it *preserves* ADR 0004 rather than falsifying
it; the boundary was crossed deliberately and reinforced.

`loop_apidoc/focus/codes.py` remains what it was — the anchor vocabulary that resolves a
reported code against the typed catalogue. It is deliberately not the floor's source, and it is
not part of this decision's boundary list for that reason.

**Falsified if:** the floor stops deriving from structure the supplier sources themselves
present. Concretely, this decision no longer holds when `loop_apidoc/source_facts/markdown.py`
recognises an error code outside a table whose own header declares that column to be error
codes; when `loop_apidoc/source_facts/models.py` builds the floor from anything other than
scanned per-source facts, or narrows the union to an intersection; or when
`loop_apidoc/validate/focus.py` derives the omitted set from the extraction's own
`inventory.errors[]`, from the URL corpus entities, or from a directive's `text`.

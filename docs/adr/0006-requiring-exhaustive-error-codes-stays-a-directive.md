---
status: accepted
---

# Requiring exhaustive error codes stays something a requester asks for

The documented error-code floor (ADR 0005) is deterministic and already computed on every run:
`source_facts/gate.py` receives the same `FactIndex` that carries it. Extending that gate to
require every documented code on every run — no directive needed — would be a small change and
a materially stronger completeness guarantee.

It is deliberately not made. The floor binds only when a `collect_error_codes` focus directive
asks it to.

The reason is that the existing semantic completeness gate is safe because it can scope itself,
and the floor cannot. Parameter facts hang off an endpoint, so the gate speaks only about
endpoints the extraction actually contains and stays silent otherwise — "no match, no
judgement" is what stops it from demanding things nobody claimed to build. Error codes are
tabulated at document level; supplier sources treat them as one shared catalogue, which is why
this very gate already reads `inventory.errors[]` as a *suppressor* so a per-endpoint error
table repeated through a document does not fire per endpoint. There is no handle to scope the
requirement with.

Unscoped, the requirement lands on work that is entirely legitimate. An integration
implementing three of a provider's forty operations is a normal thing to build, and its
extraction has no reason to carry the forty-item global error table. Making that fail — or warn
— would be the pipeline demanding something no one asserted was needed.

And the assertion already has a home. `collect_error_codes` *is* the sentence "this integration
cannot ship without all of them", written by the person entitled to say it, at the cost of one
line in a JSON file. The asymmetry that prompted this question is therefore not a gap in the
check; it is the check being addressed to the party who can answer for it.

## Considered options

- Making the shortfall a blocking violation in the shared extraction gate would match how
  documented parameters are already treated, but the identical substantive fact would then hard
  fail with no directive present while merely warning when a Coverage Directive is attached —
  incoherent in an obvious direction, since it punishes the operator who did not ask and
  forgives the one who did.
- Emitting it as a warning-severity validation issue on every run would avoid failing correct
  partial integrations while still surfacing the information, but a partial integration would
  then carry a warning listing every code it does not implement, on every run, forever. A
  warning that is always present teaches people to ignore warnings, which costs more than the
  information is worth.
- Scoping the requirement to codes the extraction's own operations could raise would restore
  the humility the parameter gate has, but it needs a code→operation link the sources usually
  do not state; deriving one would be inference, which this project refuses at exactly this
  boundary.
- Applying the floor only when the extraction claims to document every operation the sources
  describe would scope it honestly, but nothing in the extraction makes that claim today, and
  inventing a completeness flag for the extraction to self-declare would put the judgement back
  in the hands of the party being judged.

## Consequences

A run without `--focus` is not judged against the floor, and an extraction can omit documented
error codes without the pipeline objecting. That is the accepted cost: the check exists and is
reachable, but reaching it is the requester's decision, as it is for every other focus
directive.

The facts are still computed on every run, whether or not anything consumes them. That is not
waste to be optimised away — the recognizer runs inside the same Markdown scan that already
produces parameter facts, and a later decision to consume them should not have to rebuild the
substrate.

`docs/PRODUCT_EXTENSION_ROADMAP.md` previously carried this as deferred work. It now points
here, because "deferred" and "decided against" are different states and a roadmap that only
expresses the first will quietly re-propose the second.

**Falsified if:** requiring exhaustive error codes stops being something a requester asks for.
Concretely, this decision no longer holds when `loop_apidoc/source_facts/gate.py` judges an
extraction against `FactIndex.documented_error_codes()`, or when any other gate outside the
focus path makes a documented error code a requirement without a directive naming it.

# Focus directive examples

Copy one of these next to your run inputs, edit it, and pass it with `--focus`.

They are **examples, not presets**. There is deliberately no `--focus-preset` flag: a
preset shipped with the package would assert on your behalf that a provider documents
particular operations, which is an inference this project refuses to make and which is
wrong for some providers. Whether a directive applies to your supplier is your judgement,
and copying the file is how that judgement gets recorded as yours.

## The two kinds

An **Expectation Directive** (`"kind": "expectation"`) is an existence claim: you are
asserting that the supplier's sources document this. It is falsified — not satisfied —
when no source states it, and a falsified expectation fails validation.

A **Coverage Directive** (`"kind": "coverage"`) names a scope of attention to sweep
exhaustively. Reporting that no source states it is a complete answer, not a failure.

Severity follows from `kind` alone. If you want a non-blocking outcome, write a Coverage
Directive — there is no override flag.

## The answer you get back

The extraction agent writes `focus-response.json` into the extraction directory, answering
every directive exactly once, with one of two outcomes. `satisfied` carries anchors, each
pinned to an exact source fragment — a filename alone is not accepted. `not_found` carries
every readable source that was searched.

There is no third outcome. The agent cannot declare a directive inapplicable.

## What is enforced today

The pipeline currently checks the *shape* of the answer: every directive is answered exactly
once, an anchor resolves to an endpoint the extraction actually contains, its anchor type
agrees with the directive's intent, and its evidence materializes from a manifest source with
a matching digest. Any of those failing stops the run before a run directory exists.

A falsified Expectation Directive then fails validation as a `FOCUS_UNMET` error — the run's
artifacts are still written, so you can read the guide, the OpenAPI document, and the answer's
searched-source list before deciding whether to gather better sources or re-run the
extraction. A Coverage Directive coming back empty is a warning and blocks nothing.

A `not_found` answer must account for every supported, readable source in the manifest —
listing one and declaring the thing absent is refused, because the claim being made is that it
is in none of them. Sources the manifest records as unreadable are not required (nothing can
search what it cannot read) and are tolerated if listed.

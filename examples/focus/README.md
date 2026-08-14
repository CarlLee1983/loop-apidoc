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

---
status: accepted
---

# Focus directives never enter comparable artifacts

A run can now carry requester-authored focus directives — Coverage Directives naming a
scope to sweep, Expectation Directives claiming a specific operation, field, or error code
is documented. They steer subagent attention during extraction and are checked
deterministically afterwards, so a directive changes what the pipeline *looks at* and what
it *reports*. It must not change what the pipeline *concludes*.

Directives are therefore confined to the run directory. They are excluded from
`provenance.json`, from the score, and from every Foundry-governed asset. Two runs over the
same sources with different directives must produce byte-identical provenance and an
identical score; only their focus material may differ.

The rule binds every artifact the feature produces, whenever it lands. Today that is the
`focus.json` input and the agent's `focus-response.json`; the `FOCUS_UNMET` validation
issues and the `focus/focus-report.*` pair arrive with the tickets that route semantic
outcomes and write the report, and are covered by this decision on arrival rather than by a
later one.

The reason is that this project's whole claim is that supplier sources are the sole
authority for what a contract says. The moment a directive is visible in provenance, a
claim's recorded support depends on who asked rather than on what the source states, and
"the source documents this" quietly becomes "someone asked us to look for this and we found
something". Scores stop being comparable across runs, and a Foundry approval starts binding
one requester's priorities into a governed asset. A directive that is falsified is loud —
that is its whole value — but it is loud in validation, which is a statement about this run,
not in provenance, which is a statement about the sources.

## Considered options

- Recording on each claim that a directive prompted its extraction would help a reviewer see
  why an obscure field was picked up, but it makes provenance a function of the request, so
  the same sources reviewed twice would produce two different provenance files with no
  source-level difference to justify the divergence.
- Scoring a run higher when its directives are satisfied would reward thorough extraction,
  but the score is the project's cross-run quality signal; a requester could then raise a
  score by writing easier directives, which inverts what the number means.
- Publishing satisfied directives into the Foundry asset would let a downstream consumer see
  the integration concerns the contract was built for, but it binds run-time intent into a
  governed artifact that is supposed to describe the provider, and an approval would then
  cover material no supplier source authorises.

## Consequences

Focus reporting has to be self-contained: everything a reviewer needs in order to judge
whether a directive was honestly answered has to live in the run's own focus material,
because nothing downstream carries it. Reproducing a run's contract does not require its `focus.json`, which
is the point — the file is an input to the process, not a part of the result. The cost is
that a genuinely useful audit trail ("this field exists in the contract because someone
asked us to hunt for it") is available only inside the run, and a consumer reading only the
governed asset cannot recover it.

**Falsified if:** a directive becomes visible in any artifact that is compared across runs.
Concretely, this decision no longer holds when `loop_apidoc/generate/provenance.py` reads a
directive, response, or focus report; when `loop_apidoc/score/evaluate.py` takes focus
outcomes into its weighted categories; or when anything under `loop_apidoc/foundry/`
persists, binds, or approves focus material as part of a governed asset.

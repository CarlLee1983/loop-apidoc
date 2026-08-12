---
status: accepted
---

# Measure coverage on a platform-independent denominator

The governed asset store reaches for a syscall that only one operating system provides.
Publishing an asset must rename a staged directory onto its final name and fail when
that name already exists, which is `renameatx_np(RENAME_EXCL)` on Darwin and
`renameat2(RENAME_NOREPLACE)` on Linux; resolving a pinned directory descriptor back to
a pathname is `fcntl(F_GETPATH)` on Darwin and `/proc/self/fd/<n>` on Linux. Each pair is
written as a `sys.platform` branch in `loop_apidoc/foundry/store.py`, so on any one host
the branch belonging to the other platform cannot execute.

Coverage measured with those branches in the denominator therefore scores the same tree
differently depending on where it runs. That is not a property of the tree, and the
project's single `fail_under` threshold cannot be true on both platforms at once: the
tree that scored 92.53% on macOS scored 92.45% on Linux CI and failed a 92.5% gate.
Both `sys.platform` guards are excluded from measurement in `pyproject.toml`, so the
gate compares one denominator everywhere and a threshold means the same thing on a
developer's machine as it does in CI.

Excluding a branch removes it from the numerator too, so this decision buys comparability
by giving up the gate's opinion about platform-specific code. That code keeps its own
tests; what it loses is the aggregate percentage's claim to cover it. The exclusion is
deliberately written against the two `sys.platform` guard lines rather than a whole
module, so a new untested helper in `store.py` still moves the number.

## Considered options

- Lowering `fail_under` until Linux passed would restore a green gate immediately but
  would weaken the threshold for every module to accommodate a measurement artifact in
  one of them, and would need lowering again whenever the platform-specific surface grew.
- Leaving the branches measured and writing tests until Linux cleared the threshold would
  keep the strictest gate, but the deficit is code that cannot run on the host doing the
  measuring, so the debt is permanent and grows with each new platform branch — every
  future change would have to pay for it out of unrelated modules.
- Running the gate on both platforms and taking the lower score would measure honestly
  but doubles CI cost to answer a question neither run can answer alone.

## Consequences

A single `fail_under` in `pyproject.toml` stays meaningful, and a coverage number quoted
from a local run is comparable to the CI one. Platform-specific publication code must
carry its own explicit tests, because the aggregate gate no longer accounts for it; a
regression there will surface as a failing behavioral test, not as a coverage drop. The
exclusion list is a boundary, not a convenience: adding a pattern to it removes real code
from the gate's view, so it stays limited to guards whose alternative branch is
unreachable on the measuring host.

**Falsified if:** the exclusion stops being limited to platform-unreachable branches, or
the gate stops being a single comparable threshold. Concretely, this decision no longer
holds when `exclude_also` in `pyproject.toml` names a pattern that is not a `sys.platform`
guard, when `fail_under` is lowered to accommodate a platform difference rather than a
deliberate change in the coverage bar, or when a `sys.platform` branch in
`loop_apidoc/foundry/store.py` loses the behavioral tests in
`tests/foundry/test_store.py` that the aggregate gate no longer provides.

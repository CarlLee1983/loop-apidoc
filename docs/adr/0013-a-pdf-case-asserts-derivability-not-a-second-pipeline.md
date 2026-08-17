---
status: accepted
---

# A PDF case asserts that its Markdown is derivable, rather than running a second pipeline from the PDF

Two of the thirteen benchmark cases name a PDF as their source, but neither one's `sources/`
directory has ever held a PDF: both hold the converted Markdown. The `preprocess` step —
pymupdf4llm for PDF, the OOXML normalizer for `.docx` — therefore sat outside every harness run,
including `--strict-local`. Read cold that looks like the PDF path is source-backed when only the
half after conversion is (#111).

The obvious reading of the gap is "make the case start from the PDF". It is the wrong one, and the
reason is the pipeline's own mandatory order.

## Context

`preprocess` writes its Markdown into a separate `--out` directory, and the manifest is built over
*that* directory, not over the original. A PDF is an unscannable blocker for `inspect-source-risk`,
so a run that began at the PDF would have to convert before it could build a manifest at all. A
case's `sources/` directory is, by construction, the post-`preprocess` state — that is what it is
supposed to hold. Nothing about the committed layout is wrong.

What was missing is narrower and entirely checkable: nothing asserted that the local Markdown a case
feeds the harness is what the recorded PDF actually produces. The `ecpay-creditcard-pdf` case records an official URL
and a SHA-256 in its `notes.md`, but no test ever fetched, hashed, or re-converted anything. A
pymupdf4llm upgrade that changed table flattening would move every evidence line range in the case,
and the failure would surface as a pile of stale `fragment_digest` errors with no indication that a
dependency, not the extraction, was the cause.

That failure mode is not hypothetical: it is exactly what happened to `rsg-game-transfer-wallet`
when its normalizer changed and its raw HTML had been left in a temporary directory (#110). The
difference is that a PDF case can be protected cheaply, because the original is content-addressed
and, for `ecpay`, still published at a stable URL.

## Decision

A PDF-derived case commits a `source-derivation.json` descriptor binding three things: the original
PDF (case-relative path, official URL, capture date, SHA-256), the derived Markdown (case-relative
path, SHA-256), and the conversion tool by name. A source-backed test re-runs `preprocess` over the
original and asserts the produced Markdown is byte-identical to the local one the case feeds the
harness. The original PDF lives under the case's gitignored `raw/`, for the same copyright reason
`sources/` is gitignored.

**What enters the repository is the digest, not the document.** Both `raw/` and `sources/` are
gitignored, so neither the PDF nor its Markdown is in the tree; the descriptor's
`derived_markdown.sha256` is the only tracked anchor, and it is what makes the two local files
checkable at all. Two assertions follow from that split, and they have different preconditions: the
Markdown's digest is checked wherever that file exists, which is every machine that can run a
source-backed case, while the re-conversion needs the original as well. Reserving both for a machine
that happens to have `raw/` would waste the anchor the repository actually carries.

**The descriptor does not pin a tool version.** `uv.lock` already pins pymupdf4llm exactly, and CI
resolves through it, so a second version statement in thirteen descriptors would be a copy that can
disagree with the authority. What the lane adds is the missing half: the lock says which version
runs, and this test says what that version must produce. A lock bump that changes the conversion now
fails loudly, in one named test, instead of silently invalidating a case's evidence.

**This lane grants no new evidence strength.** A PDF case was source-backed before and is
source-backed now; what changed is that one previously unexercised step is exercised. Nothing in
this record licenses describing `.docx` or GitBook as validated — neither has a real source at all,
which is a different and unfixed gap (#99).

Only `ecpay-creditcard-pdf` declares a descriptor today. `jili-legacy-gaming-pdf`'s source is a
supplier delivery with no public URL; it joins the lane when the operator supplies that file, and
until then the case keeps exactly the evidence strength it already had.

## Considered options

**Run the case from the PDF.** Rejected: it inverts the mandatory order. The manifest and the
risk gate must see the converted Markdown, so the run would convert first anyway — the only thing
gained over the descriptor is a longer test, and the thing lost is that `sources/` stops meaning
"the exact package the manifest binds".

**Commit the PDF.** Rejected for the same reason `sources/` is gitignored: the originals are
operator-provided and may be copyrighted. Content-addressing plus a recorded URL gets reproducibility
without redistribution.

**Pin pymupdf4llm in the descriptor.** Rejected: two statements of the same fact, one of which is
not the one the resolver reads.

**Accept the gap and document it.** Rejected here, though it is the right answer for `.docx` and
GitBook: those have no real source to convert, so there is nothing to assert. `ecpay` has a byte-
identical original still available at its recorded URL, so the cheap check exists and a note saying
"unverified" would be a choice not to run it.

## Consequences

`scripts/quality_gate.py` carries a reviewed inventory of the cases in this lane, with the same
exact-set-parity rule as `REQUIRED_BENCHMARK_CASES` and `SANITIZED_BENCHMARK_CASES`: a descriptor
that is added or removed without an intentional matching update fails. `--strict-local` names a
missing original before it runs pytest, matching how it already reports missing source-quality
packages.

Each layer skips when its own input is absent, like every other source-backed assertion: the digest
check skips without the Markdown, the re-conversion skips without the original. CI has neither, so
it is unaffected. The guarantee is a local-operator one, which is where a dependency bump would be
noticed first.

A conversion drift is not a defect to be suppressed. When it happens, the fix is to re-derive the
case's evidence against the new Markdown and record what moved — the procedure `rsg` established in
#110 — never to relax the assertion.

**Falsified if:** the derivability assertion stops running or stops binding the recorded original.
Concretely, this decision no longer holds when `tests/test_benchmarks.py` drops the re-conversion
test or compares anything weaker than byte equality, or stops checking the Markdown digest wherever
that file exists; when `scripts/quality_gate.py`'s PDF-derived inventory loses exact-set parity with
the tracked descriptors — `benchmarks/ecpay-creditcard-pdf/source-derivation.json` today — or
`--strict-local` stops reporting a missing original; or when a descriptor starts carrying a
pymupdf4llm version of its own, at which point `uv.lock` is no longer the single authority for which
converter runs.

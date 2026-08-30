---
status: accepted
---

# A leaked third-party document is purged from history by the repository owner, and the gate never does it

Root `work/` — the local pipeline scratch directory — was tracked on `main` for five weeks. The
0.41 hygiene slices removed it from the current tree and built a gate so it cannot return (#149,
#150, #151). Removing it from *history* is a different act with different authority, and this
record fixes who performs it, on what evidence, and what the gate's role is not.

## Context

429 files under `work/` were tracked. The obvious reading was that they are regenerable clutter and
their removal from the tree closes the matter. Three findings made that reading wrong, each
established by looking rather than inferred.

**The cached pages were access-controlled.** Eleven of the files were URL-corpus caches of a
supplier's hosted documentation site. The corpus metadata records no cookie, authorization, token,
or key, which was first read as evidence of an anonymous fetch of a public site. That inference was
wrong: the authentication is embedded in the page, not in the metadata. Each cached page carries a
signed HS256 site token scoped to organization and site — expired 2026-07-23, `sub` a
48-character internal identifier rather than a person, so no credential rotation is warranted, but
its presence establishes that the pages were rendered under access control rather than fetched
anonymously.

**The derived artifacts carry the same document.** Purging only the eleven caches would have been
theatre. 192 of the 429 files carry the supplier's site or API identifiers, and the majority are not
caches: `endpoints/ep*.json`, the extraction answers, and the per-operation request and response
example pairs are the *extracted* form of the same access-controlled document — more usable to
someone seeking the API than the raw HTML is.

**Removal from the tree does not remove reachability.** A force-push rewrites refs; it does not
delete objects. After the rewrite, blob `b8984c3b…` still returned HTTP 200 from the API, and
pre-rewrite commits still resolved. The SHAs are not obscure: they are printed on the public pull
request pages of the very slices that did the cleanup. GitHub also rejected `refs/pull/*` during the
mirror push (`deny updating a hidden ref`), so those refs still point at pre-rewrite commits — a
live ref, not a merely-unreclaimed object.

**The supplier is deliberately unnamed in this record.** Naming them here would publish, in a
permanent and search-indexed file on the default branch, both who they are and that their material
leaked — a wider disclosure than the buried blobs this purge removed, and one the record does not
need: every finding, the evidence strength, and the falsification condition read identically without
it. The identity is known to the repository owner, who decided against notifying the supplier;
that decision is recorded in the consequences below rather than implied by this omission.

## Decision

**The purge scope is the whole `work/` path, not the cache files.** The unit is the directory the
material entered through, because the derivatives are the same disclosure in a more usable form.
All 429 files are local artifacts; none had any claim to be in history.

**A history rewrite is the repository owner's decision, and only the owner performs it.** The
quality gate detects a violation and refuses the commit. It never rewrites history, never
force-pushes, and its failure message says so, because a contributor who reads "this must not be
committed" must not conclude that purging history is theirs to do. For a root in
`REPOSITORY_HYGIENE_DISCLOSURE_ROOTS` the message routes the decision to the owner explicitly and
tells the reporter not to quote the contents.

**Asking the host to garbage-collect is part of the purge, not an optional follow-up.** Until it
runs, the material is retrievable by anyone who reads a SHA off a pull request page, which is the
same exposure the purge was performed to end.

## Considered options

**Purge only the eleven cache files.** Rejected. Identical cost — the same full rewrite, the same
53 tags and 44 releases — while leaving 181 files carrying the same document in structured form.

**Do not purge; rely on removal from the current tree.** This was the initial recommendation, and it
rested on the exposure being nil because the content was publicly available from the vendor anyway.
The embedded site token falsified that premise. Once the source is access-controlled, a public
repository offers what the vendor does not, and the marginal exposure is the whole of it.

**Make the repository private.** Rejected as disproportionate: it trades the project's openness for
a problem that a bounded rewrite solves, and it does nothing about clones already taken.

**Have the agent perform the rewrite unprompted.** Rejected, and the reason is the point of this
record. The rewrite is irreversible, outward-facing, and rests on a judgement about supplier
agreements that the code cannot make. The gate's correct behaviour on discovering a leak is to fail
loudly and name the paths — never to act.

## Consequences

Every commit from 2026-07-21 onward has a new SHA; `main` is 794 commits where it was 795, one
commit having become empty and been pruned. The 53 tags and 44 releases survived the rewrite, and
the `main` tree SHA is unchanged, so no working-tree content moved.

Local branches predating the rewrite still carry the purged files — eight of nine in the pre-purge
checkout, 423–429 files each. Pushing one would restore to the remote exactly what was removed.
They are preserved outside the working checkout rather than deleted, because they also hold
unpublished work, and that trade is deliberate: the risk is a push nobody intended, which is visible
and recoverable, against losing commits that exist nowhere else.

A full mirror backup taken before the rewrite is the only route back, and it necessarily still
contains everything removed. It is therefore itself material to keep off any public host and to
delete once the host's garbage collection is confirmed.

**The supplier was not notified.** The owner considered a disclosure notice and decided against
it on 2026-08-30. Recording the decision matters because anonymising the record and declining to
notify look identical from outside, and they are not the same choice: this record omits the name to
avoid publishing a leak the supplier has not been told about, not because the supplier already
knows. Anyone later reasoning about the residual risk, or drafting a supplier communication, should
start from that fact rather than assume prior contact.

**Open residual: the garbage-collection request was submitted to GitHub Support on 2026-08-30 and
has not yet been actioned.** The rewrite is done and a fresh clone is clean, but old objects remain
reachable — not merely unreclaimed: `refs/pull/*` are live refs pointing at pre-rewrite commits, so
ordinary collection would never reach them, and fetching `refs/pull/149/head` still returns the full
removed tree. This record does not describe a closed matter until that fetch comes back empty, and
saying otherwise in a release note or a supplier communication would be false.

**Falsified if:** the split between detection and purge stops holding. Concretely, this decision no
longer holds when `scripts/quality_gate.py` gains any code that rewrites history, deletes remote
refs, or force-pushes, rather than reporting paths and exiting non-zero; when
`REPOSITORY_HYGIENE_DISCLOSURE_ROOTS` stops routing the purge decision to the repository owner in
the failure message that `tests/test_quality_gate.py` pins; or when a hygiene failure is closed by a
rewrite without a recorded owner decision and a host garbage-collection request.

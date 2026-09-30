# Stop the no-replace collision test from leaving directories in the process cwd

## Goal

Running the test suite must leave nothing behind in the process's current
working directory. Today every full `uv run pytest` run (including the one inside
`make verify`) leaves one empty directory named like
`..tappay-backend-20260702-120000-<hex>-cleanup-<hex>` in the cwd, usually the
repository root; the owner has already deleted 114 of them by hand.

The only source is
`tests/foundry/test_approve.py::test_real_no_replace_collision_preserves_foreign_empty_asset_root`.
Its mock `foreign_root_then_exclusive_rename` calls `asset_root.mkdir()` on every
`_rename_noreplace` call and ignores `parent_fd`. Cleanup in
`remove_owned_entry_relative` (`loop_apidoc/foundry/descriptor_namespace.py`,
the call at lines 354-356) passes the relative path `Path(quarantine)` together
with `parent_fd`, so the mock creates an empty directory with the quarantine
name relative to the cwd.

* Fix the mock in that test so it simulates the foreign asset root only where
  the product would see it (inside the directory `parent_fd` refers to, or at
  the absolute asset root path), and never creates anything relative to the
  process cwd.
* The test keeps proving that approval fails with
  `asset root publication failed` when a destination appears between the
  existence check and the rename, and is strengthened to prove that destination
  is not replaced: today it only writes a `sentinel` into the foreign root after
  the call, which shows the directory exists but not that it is still the empty
  foreign root.

## Out of Scope

* Everything under `loop_apidoc/`, in particular the tombstone retention in
  `remove_owned_entry_relative`: keeping the quarantine entry inside the
  `parent_fd` directory is deliberate (see its docstring) and is not this
  problem.
* Every other test, including `tests/foundry/test_importer.py` and
  `tests/foundry/test_feedback.py` (run alone, they leave nothing in the cwd),
  and the other tests in `tests/foundry/test_approve.py`.
* Test fixtures, `conftest.py`, pytest configuration, `Makefile`, and
  `.github/workflows/`.
* Removing directories that earlier runs already left in any checkout.
* Dependency changes, version bumps, releases, tags, pushes, or merges.

## Acceptance Criteria

1. With `REPO` set to the repository root and `d=$(mktemp -d)`, running
   `(cd "$d" && uv run --project "$REPO" pytest -p no:cacheprovider --rootdir "$REPO" "$REPO/tests/foundry/test_approve.py::test_real_no_replace_collision_preserves_foreign_empty_asset_root")`
   exits 0, and afterwards `ls -A "$d"` prints nothing.
2. The test still wraps `approve.approve_candidate(...)` in
   `pytest.raises(FoundryInputError, match="asset root publication failed")`.
   After that block, and before anything is written into it, the test asserts
   that the foreign root
   `paths.asset_dir(tmp_path, "tappay-backend", "tappay-backend-20260702-120000")`
   is a directory that exists and that `list(foreign_root.iterdir()) == []`.
3. In a checkout where `find . -maxdepth 1 -name '.*-cleanup-*'` prints nothing,
   `make verify` exits 0 and the same `find` still prints nothing afterwards.
4. `git diff --name-status main...HEAD` lists only
   `M tests/foundry/test_approve.py`, plus this Story file
   (`specs/stories/approve-test-cwd-residue.md`) if it is not already on `main`.

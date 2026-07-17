# Repeatable Release Workflow Design

## Goal

Make loop-apidoc releases repeatable by accepting a semantic version once,
synchronizing all release metadata, validating it, and creating the matching
remote tag through Tagsmith without manually inspecting remote tags.

## Scope

- Add `scripts/release.py` with `prepare` and `tag` subcommands.
- Keep commit creation explicit and manual.
- Use the committed `.tagsmith.json` policy and Tagsmith for tag creation.
- Keep the current version locations synchronized: `pyproject.toml`,
  `loop_apidoc/__init__.py`, `.claude-plugin/plugin.json`, `uv.lock`, both
  READMEs, `docs/introduction.html`, and `tests/test_plugin_manifest.py`.

## Workflow

1. `prepare --version X.Y.Z --summary TEXT` validates strict SemVer, requires a
   version greater than the current package version, updates every version
   location, refreshes `uv.lock`, and creates `docs/RELEASE_NOTES_X.Y.Z.md`.
   It refuses to overwrite existing release notes or modify a dirty worktree.
2. The maintainer fills in the release notes as needed, runs validation, and
   commits the resulting release metadata.
3. `tag --message TEXT [--dry-run]` reads the package version, requires a clean
   worktree, fetches tags from `origin`, and invokes Tagsmith with
   `--set-version X.Y.Z --push`. Tagsmith owns format, ordering, duplicate, and
   remote-push protection.

## Error Handling

- Invalid, unchanged, or downgraded versions fail before writes.
- A pre-existing release-note path, missing `origin`, failed lock refresh, or
  mismatched metadata fails with a nonzero exit and leaves no partial release
  note.
- Tagging never guesses a version; it uses the version recorded in
  `pyproject.toml` and therefore cannot create a different tag by bump level.

## Testing

- Unit tests use a temporary repository fixture to prove `prepare` synchronizes
  the version files and writes the expected notes.
- Failure tests prove `prepare` refuses a dirty worktree, an existing note, and
  a non-increasing version without changing files.
- Tag tests mock subprocess calls and verify the sequence is `git fetch --tags
  origin` followed by `npx tagsmith create --set-version <package-version>
  --push`.
- Existing full lint, pytest with coverage, quality gate, Tagsmith policy check,
  and release command dry-run remain required.

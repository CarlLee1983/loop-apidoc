# Manifest Single-File Sources Design

**Issue:** #16 — Support passing a single file path to `manifest --sources`

## Goal

Allow `loop-apidoc manifest --sources <file>` to create a manifest for exactly
that file. Existing directory behaviour must remain unchanged.

## Scope

This change applies only to the `manifest` command. Other commands continue to
require a source directory because they consume a manifest-relative source tree
or process multiple source artifacts.

## Design

The CLI accepts an existing readable file or directory for `--sources`.

- When `--sources` is a directory, it calls `build_manifest` exactly as it does
  today, including all default and user-supplied exclusions.
- When it is a file, the CLI sets the manifest root to the file's parent
  directory. It appends exclusion patterns for every sibling path except the
  selected file, then calls the existing directory-based `build_manifest`.
- As a result, `Manifest.sources_root` is the selected file's parent and
  `local_sources` contains only the selected file, whose relative path is its
  filename (or its path relative to that parent).

The builder and scanner remain directory-only APIs. This retains their current
meaning: they scan a root tree and derive POSIX relative paths from that root.
The CLI owns the user-facing path normalization.

## Error Handling

Typer continues to reject nonexistent and unreadable paths before the command
runs. A selected file is handled as above; no special inference is made about
file format, filenames, URLs, or sibling content.

## Tests

Add CLI-level regression tests for:

1. A single source file produces a successful manifest whose root is the
   parent directory and whose only local source is the selected file.
2. A source directory retains its current complete scan behaviour.
3. A nonexistent source path remains rejected.

No new scanner or builder tests are needed because their input contract and
behaviour do not change.

## Documentation

Update the English and Traditional-Chinese README manifest command examples to
state that `--sources` accepts a source directory or one source file.

## Non-goals

- Adding `--include` or `--source-file` glob filtering (issue #18).
- Extending single-file acceptance to `assemble`, `verify-extraction`,
  `preprocess`, or other commands.
- Changing manifest statuses, source hashing, URL probing, or exclusion rules.

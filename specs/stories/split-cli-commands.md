# Split loop_apidoc/cli.py into a commands package, keeping every command name

## Goal

`loop_apidoc/cli.py` is 1,383 lines and defines 28 top-level commands in one module.
Move the command functions into a new package, `loop_apidoc/commands/`, with one module
per group:

| Module | Commands |
| --- | --- |
| `acquisition.py` | `manifest`, `catalog-url`, `select-url`, `cache-url-pages`, `cache-url-entry`, `related-url-pages`, `cache-gitbook-llms`, `snapshot-openapi-url`, `import-supplementary-note`, `import-rendered-url`, `normalize-html-snapshot` |
| `drafts.py` | `extract-markdown-drafts`, `scaffold-extraction` |
| `freshness.py` | `record-fingerprint`, `check-freshness`, `check-freshness-batch` |
| `governance.py` | `governance-scan`, `governance-review-plan` |
| `source_quality.py` | `inspect-source-risk`, `assess-sources` |
| `extraction.py` | `verify-extraction`, `assemble`, `preprocess` |
| `runs.py` | `validate`, `diff`, `score`, `evaluate`, `review` |

`cli.py` keeps `app`, the `foundry` and `feedback` sub-apps, the version callback, and
`main`. It registers every command function on `app` under the command's current name
and in the current order. The command modules hold plain functions and do not import
`loop_apidoc.cli`.

The commands stay top-level: no group prefix, no renamed command, no changed option.
Typer sub-apps are therefore not used for them. Command modules keep their
function-local imports, because tests monkeypatch the imported modules
(for example `loop_apidoc.url_corpus.cache_catalog_pages`).

ADR 0012, 0016, and 0017 guard behaviour by naming `loop_apidoc/cli.py`. The
`preprocess` passthrough line and the `--architecture-mode` default move to
`commands/extraction.py`, so those path markers move with the code, and the decisions
do not change.

## Out of Scope

- Any change to a command's name, options, defaults, help text, output, or exit code.
- `loop_apidoc/foundry/cli.py`, `loop_apidoc/feedback/cli.py`, and the `pyproject.toml`
  entry point `loop_apidoc.cli:main`.
- Moving command logic into the domain packages; the functions move as they are.
- In ADRs 0012, 0016, and 0017, anything other than the path markers named in criteria
  7-9.
- Every other `AGENTS.md` section, and other modules over 800 lines.
- Test changes. No test file is edited.

## Acceptance Criteria

1. `wc -l` reports at most 800 lines for `loop_apidoc/cli.py` and every module in
   `loop_apidoc/commands/`.
2. Every top-level function defined in `git show 6fefe7b:loop_apidoc/cli.py` is defined
   exactly once across `loop_apidoc/cli.py` and `loop_apidoc/commands/*.py`. A Python
   `ast` script over those files shows this, and it is included in the completion
   report.
3. `registered_cli_commands()` from `tests/cli_commands_support.py` returns the same set
   at `HEAD` as at `6fefe7b`.
4. For `uv run loop-apidoc --help` and for `uv run loop-apidoc <command> --help` for
   every command in that set, the output at `HEAD` is byte-identical to the output at
   `6fefe7b`. A script runs both trees and compares them, and its summary is in the
   completion report.
5. `git grep -n 'loop_apidoc.cli' -- loop_apidoc/commands/` prints nothing.
6. `git diff --name-status main...HEAD -- tests/` prints nothing, and
   `uv run pytest -q` passes.
7. In ADR 0012's `**Falsified if:**` paragraph, the reporting site
   `loop_apidoc/cli.py` and its parenthetical about the `preprocess` passthrough line now
   name `loop_apidoc/commands/extraction.py`.
8. In ADR 0016's `**Falsified if:**` paragraph, the condition about changing the
   `--architecture-mode` default names `loop_apidoc/commands/extraction.py` in place of
   `loop_apidoc/cli.py`.
9. In ADR 0017's `**Falsified if:**` paragraph, the condition about exposing a command or
   option names both `loop_apidoc/cli.py` and `loop_apidoc/commands/`.
10. `git diff main...HEAD -- docs/adr/` changes only the lines that criteria 7-9 require.
    The ADR 0012, 0016, and 0017 rows of `docs/ARCHITECTURE.md`'s `## 決策邊界` satisfy
    `tests/docs/test_adr_boundary_list.py`.
11. The package table under `### 套件職責表` in `docs/ARCHITECTURE.md` has a row for
    `loop_apidoc/commands/` that names its seven modules. Apart from that row and the
    `## 決策邊界` rows in criterion 10, `docs/ARCHITECTURE.md` does not change.
12. `scripts/quality_gate.py`'s `FILE_IO_EXIT_MODULES` drops `loop_apidoc/cli.py` if it
    no longer writes, and lists every `loop_apidoc/commands/` module that does. The
    `AGENTS.md` **File-I/O exits** paragraph states the new writer count, and its
    sentence about what `cli.py` writes names the modules that now write those outputs.
    `git diff main...HEAD -- AGENTS.md` touches only that paragraph.
13. `git diff --name-status main...HEAD` lists only `M loop_apidoc/cli.py`,
    `A loop_apidoc/commands/*.py` (including `__init__.py`), `M scripts/quality_gate.py`,
    `M AGENTS.md`, `M docs/ARCHITECTURE.md`, the three ADRs, and this Story file
    (`specs/stories/split-cli-commands.md`).
14. `make verify` exits 0.

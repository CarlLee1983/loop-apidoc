# Move the package responsibility table from AGENTS.md to docs/ARCHITECTURE.md

## Goal

`AGENTS.md` is loaded into every agent session, and at commit `165516d` its
`## Package boundaries` table (lines 146-181, 36 lines, 35,403 bytes) is reference
material about what each package owns, not an operating rule for agents. Move that
table verbatim into `docs/ARCHITECTURE.md` under `## 套件邊界`, and leave a link in its
place, so the per-session cost of `AGENTS.md` drops by roughly 45% while the facts stay
in one place. The `**File-I/O exits**` paragraphs that follow the table stay in
`AGENTS.md`: tests in `tests/docs/` pin them there.

## Out of Scope

- The `**File-I/O exits**` paragraph and the paragraph after it (from `**File-I/O exits**`
  up to `## Correction & fail-closed classification`).
- Every other `AGENTS.md` section, including `## Benchmark harness contract` and
  `## Repository hygiene`, which tests and `scripts/quality_gate.py` read from `AGENTS.md`.
- Translating the table into Traditional Chinese, or rewording any row.
- Any change to existing `docs/ARCHITECTURE.md` text; the table is only inserted.
- Changes to tests, `scripts/`, the HTML manuals, or `README*.md`.

## Acceptance Criteria

1. `sed -n '/^## Package boundaries/,/^## Correction/p' AGENTS.md | grep -c '^| '`
   prints `0`.
2. `python3 -c "import subprocess,pathlib; t=''.join(subprocess.run(['git','show','165516d:AGENTS.md'],capture_output=True,text=True).stdout.splitlines(True)[145:181]); a=pathlib.Path('docs/ARCHITECTURE.md').read_text(); i=a.find(t); print(i!=-1 and a.rfind('## 套件邊界',0,i)!=-1 and a.find('## 資料流與關鍵 seam')>i)"`
   prints `True`. This checks that the 36 table lines appear byte-identical and contiguous,
   after `## 套件邊界` and before `## 資料流與關鍵 seam`.
3. The `## Package boundaries` section of `AGENTS.md` contains a Markdown link whose
   target is `docs/ARCHITECTURE.md` (an anchor suffix is allowed).
4. `diff <(git show 165516d:AGENTS.md | sed -n '/^\*\*File-I\/O exits\*\*/,$p') <(sed -n '/^\*\*File-I\/O exits\*\*/,$p' AGENTS.md)`
   prints nothing.
5. `diff <(git show 165516d:AGENTS.md | sed -n '1,/^## Package boundaries/p') <(sed -n '1,/^## Package boundaries/p' AGENTS.md)`
   prints nothing.
6. `diff <(git show 165516d:docs/ARCHITECTURE.md) docs/ARCHITECTURE.md | grep '^<'`
   prints nothing (lines were only added).
7. `wc -c < AGENTS.md` prints a number no greater than `44500`.
8. `git diff --name-status main...HEAD` lists only `M AGENTS.md`,
   `M docs/ARCHITECTURE.md`, and this Story file
   (`specs/stories/agents-md-package-table-to-architecture.md`).
9. `make verify` exits 0.

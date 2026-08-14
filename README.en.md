# takeout_handler

[한국어](README.md) | English

A unified pipeline that converts ChatGPT / Gemini takeout exports into
Obsidian-compatible markdown. Each vendor's raw export format is completely
different, so parsing logic is split per vendor, but shared logic — code-fence
safety, frontmatter assembly, callout formatting — lives in `common/` and is
reused by both.

## Usage

1. Drop the raw zip a vendor gave you **as-is, without unzipping it** into one
   of the locations below (already-unzipped content also works — see "What
   real vendor exports actually look like" below).

   ```
   data/
   ├── chatgpt/   # ChatGPT's Data export zip as-is, or its unzipped contents
   └── gemini/    # Google Takeout zip as-is, or its unzipped contents
   ```

   If `run.py` can't find the files it needs in a vendor's folder, it
   automatically unzips any `*.zip` in that folder in place and looks again
   (`common/zip_extract.py`). If it's split into multiple part-zips like
   Google Takeout does, just drop them all in the same folder — they extract
   and merge naturally regardless of order. Original zip files are never
   deleted.

   **What real vendor exports actually look like** (once unzipped):
   - **ChatGPT** (the zip from "Settings → Data controls → Export"): usually
     not wrapped in a folder — `conversations.json`, `chat.html`,
     `file_*.dat`, etc. sit right at the top level of the archive. Depending
     on your unzip tool it may end up wrapped in one extra folder, but that's
     fine too since discovery is recursive.
   - **Gemini** (the zip from Google Takeout with only "Gemini Apps"
     selected): always wrapped in at least one layer like
     `Takeout/<service name>/`, with `My Activity.html` and attached media
     files sitting side by side inside it. Just drop the whole `Takeout/`
     folder into `data/gemini/` (no need to dig into subfolders yourself).

2. Run it.

   ```bash
   python run.py
   ```

   Only vendors whose presence is detected under `data/` are automatically
   picked and run. To run a specific vendor only, pass `--vendor chatgpt` or
   `--vendor gemini`. Add `--dry-run` to preview parsing results (session
   count, skip count, attachment resolve success/failure counts) in the
   console without creating any actual files.

   If you don't want to move the raw export into `data/<vendor>/` (e.g. you
   want to use a zip that's still sitting in your Downloads folder as-is),
   you can point directly at its location with `--input` — no real path is
   ever hardcoded anywhere in the code, and you can point at wherever you
   want on each run:

   ```bash
   python run.py --vendor gemini --input "gemini=C:\Users\me\Downloads\takeout.zip"
   ```

   Pass a folder and it's used as the source as-is (nothing is
   copied/moved); pass a `.zip` file and the original is left untouched
   while only its contents are extracted into `data/<vendor>/`.

3. Results are generated under `result/<vendor>/*.md` (+
   `result/<vendor>/Attachments/`).

4. Once you've reviewed them, run with `--publish` to apply them to your
   actual Obsidian vault (see "Configuration" below). Conversion (step 2)
   and applying to the vault (step 4) are kept separate because writing to
   your real PKM store is hard to undo, so you get a chance to review
   `result/` first.

   ```bash
   python run.py --publish
   ```

## Configuration (config.json)

Three paths — where your raw takeout lives, where converted markdown goes,
and where your actual Obsidian vault is — are managed via `config.json`. It's
auto-created with default values in the project root on first run (see
`config.example.json` for its shape). It contains personal paths, so it's
`.gitignore`d.

```json
{
  "takeout_paths": { "chatgpt": "", "gemini": "" },
  "markdown_output_dir": "result",
  "obsidian_vault_dir": "",
  "vault_subdirs": { "chatgpt": "ChatGPT", "gemini": "Gemini" }
}
```

**Priority: CLI flag > config.json > built-in default.** If you set nothing,
it uses the defaults (source is `data/<vendor>/`, output is `result/`, vault
is unset). Use a CLI flag to override for a single run, or edit
`config.json` directly if you want to keep using the same location every
time.

| Path | config.json key | CLI override | Default |
|---|---|---|---|
| Raw takeout source | `takeout_paths.<vendor>` | `--input VENDOR=PATH` | `data/<vendor>/` |
| Markdown output | `markdown_output_dir` | `--output-dir PATH` | `result/` |
| Obsidian vault | `obsidian_vault_dir` | `--vault-dir PATH` (with `--publish`) | unset (no publishing) |

When applying to the vault with `--publish`, a per-vendor subfolder is
auto-created using the names configured in `vault_subdirs`
(`<vault>/ChatGPT/`, `<vault>/Gemini/`). It's **simple mirroring** — upserts
are based purely on the `vault_dir/<vendor_subdir>/<filename>` location, so
if you move or rename a note inside your vault, that move isn't tracked; if
that session's content changes later, a new note may be created at the
original location rather than wherever you moved it.

### Exit codes

- `0`: Completed normally.
- `1`: No vendor ran at all (nothing found under `data/<vendor>/`).
- `2`: Some vendor only partially succeeded (e.g. one of several
  `conversations-*.json` files was corrupted and failed to parse) — check
  the `[warning]`/`⚠️` logs in the console. If you're calling this pipeline
  from an automation script, make sure to check the exit code.

## Output format

One markdown note per session (conversation). Frontmatter carries
`title`/`session_id`/`url`/`date`/`turns_count`/`content_hash`/`tags`, and
the body lists turns as `> [!question]- User (...)` /
`> [!tip]- <Vendor> (...)` callouts. Image/file attachments are copied into
`Attachments/` and embedded with `![[...]]` where possible.

Immediately before each callout there's an HTML comment shaped like
`<!-- turn: {"turn_index": 0, "role": "user", "parent_turn_index": null,
"has_attachment": false} -->`. It's invisible in Obsidian's preview, but lets
a RAG chunking pipeline read QA pairs, session boundaries, and attachment
context directly, without needing to interpret callout syntax
(`[!question]` vs `[!tip]`) or rely on ordering heuristics like "up to the
next question."
- `parent_turn_index`: which question (turn_index) this answer belongs to.
  Question turns are always `null` (the start of a new turn window). Even
  when one question's answer is split across multiple turns (this does
  happen — a long response getting split into several messages), they all
  point to the same `parent_turn_index`.
- `has_attachment`: whether an attachment block immediately follows this
  turn.

## Requirements

The runtime pipeline itself uses only the standard library (Python 3.10+).
No external packages needed. To run the tests, `pip install -r
requirements-dev.txt` (adds only pytest).

## Structure

```
common/                  # Logic shared by both vendors
├── markdown_safety.py     # code-fence safety net
├── text.py                 # first_sentence / yaml_quote / sanitize_filename / format_callout
├── session_markdown.py    # frontmatter + callout markdown assembly, content_hash compute/extract
├── attachment_cache.py    # shared attachment resolver skeleton (caching, dry-run copy, tallying)
├── attachment_types.py    # attachment extension classification (embeddability etc, shared by both vendors)
├── zip_extract.py          # extracts *.zip in data/<vendor>/ in place (includes zip-slip defense)
├── fs_discovery.py         # filters archive-tool junk paths like __MACOSX, handles candidate ambiguity
├── upsert.py                # content_hash-comparison-based upsert writes (for result/)
├── publish.py                # result/ -> real vault mirroring (for --publish, reuses upsert)
└── config.py                  # config.json loader (creates with defaults if missing)
vendors/
├── base.py               # vendor module interface contract (Protocol) + runtime validation + auto-discovery
├── chatgpt.py             # conversations*.json tree parsing + .dat attachment recovery
└── gemini.py               # "My Activity.html" block parsing + local attachment matching
run.py                    # CLI: config loading + path priority resolution + vendor execution + publishing
config.example.json       # example config.json shape (the real config.json is .gitignore'd)
tests/                    # pytest -- pure functions in common/ + vendor parsing logic (tree branch
                          # selection, KST parsing, etc) + config/publish unit tests
```

## Development

```bash
pip install -r requirements-dev.txt
pytest
```

`tests/` is split into 4 layers:

| Directory | What it guarantees | Run |
|---|---|---|
| `tests/unit/` | Individually verifies pure functions in `common/` and vendor parser core logic (`_active_branch_nodes`, `_parse_kst`, etc) with synthetic data | `pytest tests/unit` |
| `tests/regression/` | Reproduces bugs that actually happened in past issues (#11 Gemini nested attachments, #13 `__MACOSX` ordering, #16 CRLF) via the exact path they occurred, to pin them down | `pytest -m regression` |
| `tests/integration/` | Verifies the full CLI wiring end to end: argparse → `resolve_source` → `run_vendor` → `detect`/`convert` → upsert/publish (synthetic fixtures; never touches the real `data/`/`config.json`) | `pytest -m integration` |
| `tests/smoke/` | The shallowest, fastest check — just confirms imports don't break and the CLI at least starts without crashing | `pytest -m smoke` |

Full-pipeline verification against real, large-scale takeout data (byte-diff
against prior output) isn't included in the automated tests — since it's
personal data that can't be committed, it's re-run and compared manually
whenever a regression is suspected.

`run.main()` unconditionally reads the project's real `config.json` (creating
it if missing), and falls back to `data/<vendor>/` (a real path that may
contain personal data) if none is set. The `_isolate_real_project_paths`
autouse fixture in `tests/conftest.py` automatically isolates both of these
paths to temp paths for every test, so forgetting this while writing a new
test still keeps real project files safe — but this is only a safety net
that makes mistakes harmless, not a license to skip being explicit; CLI-level
tests should still be written with `--input`/`--output-dir`/`--vault-dir`
explicitly pointed at temp paths.

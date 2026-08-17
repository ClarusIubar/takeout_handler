# takeout_handler

[한국어](README.md) | English

A unified pipeline that converts ChatGPT / Gemini / Claude takeout exports
into Obsidian-compatible markdown. Each vendor's raw export format is
completely different, so parsing logic is split per vendor, but shared logic
— code-fence safety, frontmatter assembly, callout formatting — lives in
`common/` and is reused by all of them.

## Usage

1. Drop the raw zip a vendor gave you **as-is, without unzipping it** into one
   of the locations below (already-unzipped content also works — see "What
   real vendor exports actually look like" below).

   ```
   data/
   ├── chatgpt/   # ChatGPT's Data export zip as-is, or its unzipped contents
   ├── gemini/    # Google Takeout zip as-is, or its unzipped contents
   └── claude/    # Claude's (Anthropic) data export zip as-is, or its unzipped contents
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
   - **Claude** (the zip from "Settings → Account → Export data"): the top
     level of the archive has `conversations.json` (all conversations that
     aren't attached to a project, as one array), `design_chats/` (one file
     per conversation that *is* attached to a project), `projects/` (project
     metadata, when present), and so on. If your account has a lot of data
     this can come split into multiple parts, e.g.
     `data-...-batch-0000.zip` — **only a single part is supported right
     now**. Extracting several parts into the same folder would make later
     parts silently overwrite the earlier parts' `conversations.json`/
     `design_chats/`, losing conversations, so if you have multiple parts
     you need to process each one separately.

2. Run it.

   ```bash
   python run.py
   ```

   Only vendors whose presence is detected under `data/` are automatically
   picked and run. To run a specific vendor only, pass `--vendor chatgpt`,
   `--vendor gemini`, or `--vendor claude`. Add `--dry-run` to preview
   parsing results (session count, skip count, attachment resolve
   success/failure counts) in the console without creating any actual files.

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
   `result/<vendor>/Attachments/`). Claude is the exception: conversations
   attached to a project are generated under
   `result/claude/<project name>/*.md`, one subfolder per project, while
   conversations that aren't attached to a project go straight into
   `result/claude/*.md` like the other vendors.

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
  "takeout_paths": { "chatgpt": "", "gemini": "", "claude": "" },
  "markdown_output_dir": "result",
  "obsidian_vault_dir": "",
  "vault_subdirs": { "chatgpt": "ChatGPT", "gemini": "Gemini", "claude": "Claude" }
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
(`<vault>/ChatGPT/`, `<vault>/Gemini/`, `<vault>/Claude/`). It's **simple
mirroring** — upserts are based purely on the
`vault_dir/<vendor_subdir>/<filename>` location (for Claude project
conversations, `vault_dir/<vendor_subdir>/<project name>/<filename>`), so
if you move or rename a note inside your vault, that move isn't tracked; if
that session's content changes later, a new note may be created at the
original location rather than wherever you moved it. For the same reason,
if a Claude project gets renamed later, a new subfolder is created and the
old subfolder's file becomes orphaned.

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

Filenames are based on `session_id`, not `title` — Gemini, unlike ChatGPT,
doesn't provide a per-conversation title (see the wiki's
[Output Format](https://github.com/ClarusIubar/takeout_handler/wiki/Output-Format-en)
for the design reasoning).

**Out of scope for Claude**: `memories.json` (memory feature summaries),
`login_history.json`, `users.json` (account info), and the `docs` field
inside `projects/*.json` (project knowledge files) aren't conversations, so
none of them get converted. This export never contains actual attachment
bytes (only reference filenames), so attachments always show up as a
"missing" notice.

## Requirements

The runtime pipeline itself uses only the standard library (Python 3.10+).
No external packages needed. To run the tests, `pip install -r
requirements-dev.txt` (adds only pytest).

## Structure

```
common/                  # Logic shared across vendors
├── markdown_safety.py     # code-fence safety net
├── text.py                 # first_sentence / yaml_quote / sanitize_filename / format_callout
├── session_markdown.py    # frontmatter + callout markdown assembly, content_hash compute/extract
├── attachment_cache.py    # shared attachment resolver skeleton (caching, dry-run copy, tallying)
├── attachment_types.py    # attachment extension classification (embeddability etc, shared across vendors)
├── zip_extract.py          # extracts *.zip in data/<vendor>/ in place (includes zip-slip defense)
├── fs_discovery.py         # filters archive-tool junk paths like __MACOSX, handles candidate ambiguity
├── upsert.py                # content_hash-comparison-based upsert writes (for result/)
├── publish.py                # result/ -> real vault mirroring (for --publish, reuses upsert,
│                             #   recursively mirrors result_dir subfolders)
└── config.py                  # config.json loader (creates with defaults if missing)
vendors/
├── base.py               # vendor module interface contract (Protocol) + runtime validation + auto-discovery
├── chatgpt.py             # conversations*.json tree parsing + .dat attachment recovery
├── gemini.py               # "My Activity.html" block parsing + local attachment matching
└── claude.py               # parses conversations.json (non-project chats) + design_chats/*.json
                            #   (project-attached agentic chats, a different schema)
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

`tests/` is split into 4 layers — `unit`/`regression`/`integration`/`smoke` —
and each can be run on its own, e.g. `pytest -m smoke`. See the wiki's
[Development](https://github.com/ClarusIubar/takeout_handler/wiki/Development-en)
page for how each layer is organized and how test isolation works.

Full-pipeline verification against real, large-scale takeout data (byte-diff
against prior output) isn't included in the automated tests — since it's
personal data that can't be committed, it's re-run and compared manually
whenever a regression is suspected.

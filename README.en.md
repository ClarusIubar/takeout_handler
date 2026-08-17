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

Filenames are based on `session_id`, not `title` — Gemini, unlike ChatGPT,
doesn't provide a per-conversation title (see the wiki's
[Output Format](https://github.com/ClarusIubar/takeout_handler/wiki/Output-Format-en)
for the design reasoning).

## MCP server (optional)

`mcp_server/` exposes an [MCP](https://modelcontextprotocol.io) server so
Claude (or any MCP client) can query sessions already rendered into
`result/` (or a `--publish`ed vault) directly. It only reads what's already
there — it never touches `vendors/`/`common/`, and it's a separate flow from
`python run.py`'s convert/publish steps.

```bash
pip install -e .[mcp]   # or: pip install -r requirements-mcp.txt
python -m mcp_server    # add --source vault to query the vault instead
```

Tools it provides: `list_sessions`, `search_sessions` (plain substring match
over titles/turn text), `get_session` (fetch one session in full),
`sync_takeout` (re-run the conversion — only updates `result/`, the sole
write tool, and never touches the vault). No auth or remote transport
(stdio only, runs as a local process).

**Claude Desktop** (`claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "takeout-handler": {
      "command": "python",
      "args": ["-m", "mcp_server"],
      "cwd": "/path/to/takeout_handler"
    }
  }
}
```

**Claude Code**:
```bash
claude mcp add takeout-handler -- python -m mcp_server
```
(run from the repo directory, or pass `cwd` pointing at it)

## Tool-usage eval (eval/, optional)

`eval/` holds a harness that checks whether a real LLM correctly picks the
right one of the 4 MCP tools for natural-language requests. It deliberately
targets a low-reasoning model served locally via LM Studio (`gemma-4-12b-it`)
rather than a frontier/cloud model — if a weak model can use the tools
correctly, that's a far more trustworthy signal about interface quality than
a frontier model succeeding, since raw inference power can paper over
badly-designed tool descriptions/schemas in a way that doesn't generalize.

```bash
pip install -e .[mcp]           # eval reuses mcp_server as-is
python -m eval.harness          # requires LM Studio running locally at http://localhost:1234
```

**Entirely separate from `pytest`** — LLM output is non-deterministic and a
local LM Studio server has to actually be running, so this lives outside
`tests/` (in `eval/`) and isn't wired into CI. Only the deterministic grading
logic (pure functions) is unit-tested, in `tests/unit/test_eval_*.py`. See
[eval/README.md](eval/README.md) for the task list and fixture design
rationale.

All 14 tasks above use synthetic fixtures. To try the same methodology
interactively against your own real `result/` data, use `python -m
eval.manual_probe` (no automated grading, nothing written to disk). See the
"실제 데이터 수동 점검" section in [eval/README.md](eval/README.md) for
details.

## Requirements

The runtime pipeline itself uses only the standard library (Python 3.10+).
No external packages needed. To run the tests, `pip install -r
requirements-dev.txt` (adds only pytest).

The MCP server feature (`mcp_server/`, see below) is the one exception — it
needs the `mcp` SDK. Skip it entirely if you don't use that feature. `pip
install -e .[mcp]` or `pip install -r requirements-mcp.txt`.

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
├── config.py                  # config.json loader (creates with defaults if missing)
└── session_reader.py            # inverse of session_markdown.py -- rendered .md -> SessionRecord (for mcp_server)
vendors/
├── base.py               # vendor module interface contract (Protocol) + runtime validation + auto-discovery
├── chatgpt.py             # conversations*.json tree parsing + .dat attachment recovery
└── gemini.py               # "My Activity.html" block parsing + local attachment matching
mcp_server/               # MCP server (optional, see above) -- read-only over result/vault
├── config.py               # CLI flag / config.json path resolution
├── index.py                 # builds an in-memory query index from rendered .md files
├── pipeline.py               # for sync_takeout -- reuses run.py:run_vendor()
├── server.py                  # tool/resource registration
└── __main__.py                  # python -m mcp_server entry point
eval/                     # tool-usage eval (optional, see above) -- unrelated to pytest
├── lm_studio_client.py     # LM Studio (OpenAI-compatible) client
├── fixtures.py               # synthetic session data for the eval
├── tasks.py                    # eval task definitions
├── harness.py                    # core loop + `python -m eval.harness` entry point
└── report.py                       # console summary table + JSON report
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

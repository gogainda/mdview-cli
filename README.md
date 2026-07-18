# mdv — preview Markdown files from your terminal

`mdv` renders a Markdown file the way it should look — headings, tables, code,
Mermaid diagrams — and opens it in your browser. One command, no account, no
configuration.

```bash
uv tool install mdview-cli    # or: pipx install mdview-cli, pip install mdview-cli
mdv notes.md
```

Homebrew users:

```bash
brew install gogainda/tap/mdview-cli
```

That's the whole workflow: `mdv FILE.md` publishes the file to
[mdview.io](https://mdview.io), opens the rendered page, and prints a link you
can send to anyone. Anonymous previews last 30 days and take files up to 2 MB.

## Two ways to preview

**Shareable preview (default).** `mdv FILE.md` is shorthand for `mdv preview
FILE.md`. The title comes from the first `#` heading, or pass your own:

```bash
mdv notes.md
mdv preview notes.md --title "Design notes"
mdv preview notes.md --json     # print the share URLs as JSON, don't open a browser
```

**Local-only preview.** `mdv open` uploads nothing: it packs the file into the
URL itself and rendering happens entirely in your browser. Use it for drafts
that shouldn't leave your machine.

```bash
mdv open notes.md
```

## Iterating on one document

Previews are throwaway: every run mints a new link. When you keep working on
the same file — a spec, an architecture doc, a report — you want the opposite:
one stable URL whose content follows your edits, and a check that every
revision still renders cleanly.

That's `mdv sync`. It needs a free mdview.io CLI token because it manages
saved documents in your account:

```bash
mdv keys set          # paste your CLI token once (or set MDVIEW_TOKEN in CI)
mdv sync spec.md      # first run creates the document and prints its share URL
```

Edit the file and run `mdv sync spec.md` again: same URL, new content. After
every sync, mdv checks the document in the PDF renderer:

- exit `0` — every Mermaid diagram renders; safe to share or export
- exit `1` — something broke; each failing diagram is listed with its error

which makes `mdv sync` usable as a CI or pre-commit gate for your docs. Around
it:

```bash
mdv verify spec.md    # re-run the render check without uploading anything
mdv fix spec.md       # let mdview repair broken Mermaid (your file is backed up first)
mdv export spec.md    # render to spec.pdf
mdv list              # all saved documents with their URLs
mdv unlink spec.md    # forget the file↔document link; the document stays online
```

`mdv fix` rewrites the local file with the repaired Markdown, keeping a
timestamped backup, then re-syncs and re-verifies.

## Reference

| Command | Token | What it does |
|---|---|---|
| `mdv FILE.md` / `mdv preview` | no | Publish anonymously, open the rendered page (30-day link) |
| `mdv open` | no | Render locally in the browser; nothing is uploaded |
| `mdv sync` | yes | Update a saved document, keep its URL, verify rendering |
| `mdv verify` | yes | Re-check rendering of a synced document |
| `mdv fix` | yes | Repair broken Mermaid diagrams, with a local backup |
| `mdv export` | yes | Export a synced document to PDF |
| `mdv list` | yes | List saved documents |
| `mdv unlink` | no | Remove the local file↔document association |
| `mdv keys set/list/path/unset` | — | Manage the stored CLI token |

Exit codes: `0` success, `1` document doesn't render cleanly, `2` usage error,
`3` mdview.io error.

Environment: `MDVIEW_TOKEN` supplies the token without storing it (ideal for
CI); `MDVIEW_BASE_URL` points the CLI at another server.

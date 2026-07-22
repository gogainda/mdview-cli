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

Set up a free mdview.io CLI token once, then it's one command per iteration:

```bash
mdv keys set          # once (or set MDVIEW_TOKEN in CI)
mdv sync spec.md      # publish this revision, verify it, auto-repair broken diagrams
```

While you iterate, the document lives at its **private** `/p/` page — only
you, signed in, can see it, and the URL stays the same forever. Every sync
shows the fixed, renderable version there. Broken Mermaid diagrams are
repaired automatically and the fix is written back into your file (the
original is kept as a timestamped backup); only documents that can't be
repaired exit `1`.

When — and only when — you decide to publish, make it public; and grab a PDF
at any point:

```bash
mdv share spec.md               # mint the public /s/ link (from then on it follows your syncs)
mdv share spec.md --slug my-doc # …or with a custom /s/my-doc slug
mdv export spec.md              # render the current revision to spec.pdf
```

Or do both steps at once — sync, auto-repair, and share in one call:

```bash
mdv publish spec.md --slug my-doc   # sync + repair + share, atomically
```

Useful around the loop:

```bash
mdv sync spec.md --no-fix     # fast sync: skip auto-repair, just report failures
mdv export spec.md --no-sync  # PDF of the last synced revision; local edits stay private
mdv list                      # all saved documents with their URLs
mdv status spec.md            # document ID, public state, last sync, local edits pending?
mdv unlink spec.md            # forget the file↔document link; the document stays online
```

Nothing is public until you run `mdv share`. After that, the public page
serves the last synced revision — mid-edit local changes still stay private
until you sync. `mdv fix FILE --local` repairs a file in place without
creating a saved document (free accounts share the daily Quick Fix limit;
Pro is unlimited).

### Example session

A real session, working on a doc whose Mermaid diagrams start out broken:

```console
$ mdv sync spec.md                 # iterate — the broken flowchart is auto-repaired (~30s)
Document: 8be0be9198400443
Private: https://mdview.io/p/8be0be9198400443
Renderable: yes (1 diagrams, 0 tables)

$ vim spec.md                      # …add two sections, each with a (broken) diagram…
$ mdv sync spec.md                 # same doc, all three diagrams repaired and verified
Document: 8be0be9198400443
Private: https://mdview.io/p/8be0be9198400443
Renderable: yes (3 diagrams, 0 tables)

$ mdv share spec.md                # happy with it — make it public
https://mdview.io/s/9a2b8fb1

$ mdv export spec.md               # …and hand over a PDF
PDF: spec.pdf
```

Two commands did all the work: `mdv sync` after every editing round, and
`mdv share` once at the end. The fixes were written back into `spec.md`
(originals in timestamped backups, so you can review what the repair
changed — worth a glance before sharing, since a repair is guaranteed to
render but not to read your mind), the private URL never changed, and the
public link didn't exist until it was asked for.

**When this flow fits:** a document that lives longer than one paste — specs,
architecture docs, reports, runbooks, agent-written docs you refine over
hours or days. Use it when reviewers follow one link that must always show
the latest good revision, when a PDF has to be producible at any moment, or
in CI as a docs gate (`mdv sync --no-fix` exits `1` on broken diagrams
without editing anything). For a one-off snapshot, `mdv preview` is enough;
for reading a local file without uploading it, use `mdv open`.

## Reference

| Command | Token | What it does |
|---|---|---|
| `mdv FILE.md` / `mdv preview` | no | Publish anonymously, open the rendered page (30-day link) |
| `mdv open` | no | Render locally in the browser; nothing is uploaded |
| `mdv sync` | yes | Update a saved document at its private /p/ URL, verify + auto-repair |
| `mdv share` | yes | Make a synced document public at its /s/ URL, optionally with `--slug` |
| `mdv publish` | yes | Sync + auto-repair + share in one call |
| `mdv verify` | yes | Re-check rendering of a synced document |
| `mdv fix` | yes | Repair broken Mermaid diagrams, with a local backup |
| `mdv export` | yes | Export a synced document to PDF |
| `mdv list` | yes | List saved documents |
| `mdv status` | yes | Show a synced document's ID, public state, slug, and whether local edits are unsynced |
| `mdv unlink` | no | Remove the local file↔document association |
| `mdv keys set/list/path/unset` | — | Manage the stored CLI token |

Exit codes: `0` success, `1` document doesn't render cleanly, `2` usage error,
`3` mdview.io error.

Environment: `MDVIEW_TOKEN` supplies the token without storing it (ideal for
CI); `MDVIEW_BASE_URL` points the CLI at another server.

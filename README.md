# mdv

`mdv` opens Markdown in mdview.io and can keep an evolving file attached to one
stable document while checking every revision in the PDF renderer.

## Quick start — no token required

```bash
uv tool install mdview-cli
mdv open architecture.md
```

Opening a local file does not upload it and does not require an account, token,
or configuration.

## Verify every revision

Saved-document commands require a mdview.io CLI token because they update your
documents between runs. Configure it once, then sync the same file after every
edit:

```bash
mdv keys set
mdv sync architecture.md
```

Edit the file and run `mdv sync architecture.md` again. The share URL stays the
same. Exit status `0` means every Mermaid diagram rendered; status `1` means the
document needs attention.

```bash
mdv fix architecture.md
mdv export architecture.md
```

`open` is token-free. `sync`, `verify`, `fix`, `export`, and `list` use a token
to access Saved documents. In CI, set `MDVIEW_TOKEN` instead of storing it.
`MDVIEW_BASE_URL` overrides the service URL for development.

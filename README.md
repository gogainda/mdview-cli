# mdv

`mdv` keeps one Markdown file attached to one stable mdview.io document and
checks every revision in the same renderer used for PDF export.

```bash
uv tool install mdview-cli
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

Set `MDVIEW_TOKEN` instead of storing a token in CI. `MDVIEW_BASE_URL` overrides
the service URL for development.

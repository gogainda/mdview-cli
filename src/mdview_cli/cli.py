import base64
import functools
import io
import json
import os
import re
import shutil
import tempfile
import webbrowser
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import click

from .api import ApiError, MdviewApi
from .config import base_url, data_dir, get_token, keys_path, remove_token, save_token
from .state import DocumentState


class ServiceError(click.ClickException):
    exit_code = 3


def service_errors(command):
    @functools.wraps(command)
    def wrapper(*args, **kwargs):
        try:
            return command(*args, **kwargs)
        except ApiError as error:
            raise ServiceError(str(error)) from error

    return wrapper


def atomic_write(path: Path, data):
    binary = isinstance(data, bytes)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb" if binary else "w", encoding=None if binary else "utf-8") as stream:
            stream.write(data)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def api_for_token(token=None):
    credential = token or get_token()
    if not credential:
        raise click.UsageError("No CLI token. Run 'mdv keys set' or set MDVIEW_TOKEN.")
    return MdviewApi(base_url(), credential)


def title_for(path: Path, markdown: str, explicit=None) -> str:
    if explicit:
        return explicit
    match = re.search(r"^#\s+(.+?)\s*$", markdown, re.MULTILINE)
    return match.group(1) if match else path.stem


def share_id(body):
    return body.get("customSlug") or body.get("custom_slug") or body.get("shortId") or body.get("short_id")


def share_url(share):
    return f"{base_url()}/s/{share}"


def verdict(report) -> bool:
    if "renderable" in report:
        return bool(report["renderable"])
    return bool(report.get("known")) and int(report.get("diagrams", {}).get("failing", 0)) == 0


def result_payload(document_id, share, report, created=False):
    return {
        "document_id": document_id,
        "created": created,
        "share_url": share_url(share) if share else None,
        "renderable": verdict(report),
        "diagrams": report.get("diagrams", {}),
        "tables": report.get("tables", {}),
        "failures": report.get("failures", []),
    }


def print_result(payload, as_json=False, *, check=True):
    if as_json:
        click.echo(json.dumps(payload, separators=(",", ":")))
    else:
        click.echo(f"Document: {payload['document_id']}")
        if payload.get("share_url"):
            click.echo(f"Share: {payload['share_url']}")
        diagrams = payload.get("diagrams") or {}
        failures = payload.get("failures") or []
        failing = int(diagrams.get("failing", len(failures)) or 0)
        total = int(diagrams.get("total", 0) or 0)
        if payload["renderable"]:
            click.secho(f"Renderable: yes ({total} diagrams, {payload.get('tables', {}).get('total', 0)} tables)", fg="green")
        else:
            click.secho(f"Renderable: no ({failing} of {total} diagrams failed)", fg="red", err=True)
            for failure in failures:
                index = failure.get("index", "?")
                error = failure.get("error") or failure.get("message") or "render failed"
                click.echo(f"  Diagram {index}: {error}", err=True)
            click.echo("Run 'mdv fix FILE' to repair the diagrams.", err=True)
    if check and not payload["renderable"]:
        raise click.exceptions.Exit(1)


def sync_file(path: Path, *, api=None, state=None, title=None, document_id=None, share=True, verify=True):
    if not path.is_file():
        raise click.UsageError(f"File not found: {path}")
    markdown = path.read_text(encoding="utf-8")
    api = api or api_for_token()
    state = state or DocumentState()
    association = state.get(base_url(), path)
    document_id = document_id or (association and association["document_id"])
    existing_share = association and association["share_id"]
    updated_at = association and association["updated_at"]
    created = document_id is None
    doc_title = title_for(path, markdown, title)
    if created:
        created_body = api.create(doc_title, markdown)
        document_id = created_body["id"]
        updated_at = created_body.get("updated_at")
    else:
        try:
            updated = api.update(document_id, doc_title, markdown, updated_at)
            updated_at = updated.get("updated_at")
        except ApiError as error:
            if error.status_code != 404 or document_id != (association and association["document_id"]):
                raise
            created_body = api.create(doc_title, markdown)
            document_id = created_body["id"]
            updated_at = created_body.get("updated_at")
            existing_share = None
            created = True
    if share and not existing_share:
        existing_share = share_id(api.share(document_id))
    state.put(base_url(), path, document_id, existing_share, updated_at)
    report = api.verify(document_id) if verify else {"renderable": True, "diagrams": {}, "tables": {}}
    return result_payload(document_id, existing_share, report, created)


class MdvGroup(click.Group):
    """Treat `mdv FILE` as shorthand for `mdv preview FILE`."""

    def resolve_command(self, ctx, args):
        argument = args[0]
        if self.get_command(ctx, argument) is None and (
            Path(argument).is_file() or argument.endswith((".md", ".markdown"))
        ):
            return "preview", self.commands["preview"], args
        return super().resolve_command(ctx, args)


@click.group(cls=MdvGroup)
@click.version_option()
def cli():
    """Iterate on Markdown and verify every revision with mdview.io.

    Running `mdv FILE.md` previews the file (same as `mdv preview FILE.md`).
    """


@cli.group()
def keys():
    """Manage the mdview.io CLI token."""


@keys.command("set")
def keys_set():
    token = click.prompt("CLI token", hide_input=True).strip()
    if not token.startswith("mdv1_"):
        raise click.UsageError("CLI tokens start with mdv1_.")
    try:
        api_for_token(token).documents()
    except ApiError as error:
        raise ServiceError(f"Token validation failed: {error}") from error
    save_token(token)
    click.echo(f"Token saved to {keys_path()}")


@keys.command("path")
def keys_path_command():
    click.echo(keys_path())


@keys.command("unset")
def keys_unset():
    click.echo("Token removed." if remove_token() else "No stored token.")


@keys.command("list")
def keys_list():
    click.echo("default" if get_token() else "No token configured.")


@cli.command("sync")
@click.argument("file", type=click.Path(path_type=Path))
@click.option("--title")
@click.option("--id", "document_id")
@click.option("--no-share", is_flag=True)
@click.option("--json", "as_json", is_flag=True)
@service_errors
def sync_command(file, title, document_id, no_share, as_json):
    """Update FILE, preserve its URL, and verify PDF rendering."""
    payload = sync_file(file, title=title, document_id=document_id, share=not no_share)
    print_result(payload, as_json)


@cli.command("verify")
@click.argument("file", required=False, type=click.Path(path_type=Path))
@click.option("--id", "document_id")
@click.option("--status", is_flag=True)
@click.option("--json", "as_json", is_flag=True)
@service_errors
def verify_command(file, document_id, status, as_json):
    association = DocumentState().get(base_url(), file) if file else None
    document_id = document_id or (association and association["document_id"])
    if not document_id:
        raise click.UsageError("Provide an associated FILE or --id.")
    report = api_for_token().verify(document_id, status=status)
    payload = result_payload(document_id, association and association["share_id"], report)
    print_result(payload, as_json)


@cli.command("fix")
@click.argument("file", type=click.Path(path_type=Path))
@click.option("--json", "as_json", is_flag=True)
@service_errors
def fix_command(file, as_json):
    api = api_for_token()
    state = DocumentState()
    initial = sync_file(file, api=api, state=state, verify=False)
    repaired = api.fix(initial["document_id"])
    markdown = repaired.get("markdown")
    if markdown is None:
        raise ServiceError("The repair response did not include Markdown.")
    backup_dir = data_dir() / "backups" / initial["document_id"]
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup = backup_dir / f"{stamp}-{file.name}"
    shutil.copy2(file, backup)
    atomic_write(file, markdown)
    payload = sync_file(file, api=api, state=state)
    payload["backup"] = str(backup)
    payload["fixed"] = repaired.get("diagrams", {}).get("fixed", 0)
    print_result(payload, as_json)


@cli.command("export")
@click.argument("file", type=click.Path(path_type=Path))
@click.option("-o", "--output", type=click.Path(path_type=Path))
@click.option("--force", is_flag=True)
@service_errors
def export_command(file, output, force):
    api = api_for_token()
    payload = sync_file(file, api=api)
    print_result(payload, check=False)
    if not payload["renderable"] and not force:
        raise click.ClickException("Document is not Renderable; use --force to export anyway.")
    output = output or file.with_suffix(".pdf")
    pdf = api.export_pdf(payload["document_id"])
    output.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(output, pdf)
    click.echo(f"PDF: {output}")


@cli.command("list")
@click.option("--json", "as_json", is_flag=True)
@service_errors
def list_command(as_json):
    documents = api_for_token().documents()
    if as_json:
        click.echo(json.dumps(documents, separators=(",", ":")))
    else:
        for document in documents:
            sid = share_id(document)
            suffix = f"  {share_url(sid)}" if sid else ""
            click.echo(f"{document.get('id')}  {document.get('title', 'Untitled')}{suffix}")


@cli.command("unlink")
@click.argument("file", type=click.Path(path_type=Path))
def unlink_command(file):
    removed = DocumentState().unlink(base_url(), file)
    click.echo("Association removed; remote document was not deleted." if removed else "No association found.")


@cli.command("preview")
@click.argument("file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--title")
@click.option("--json", "as_json", is_flag=True)
@service_errors
def preview_command(file, title, as_json):
    """Publish FILE anonymously and open its temporary mdview page."""
    markdown = file.read_text(encoding="utf-8")
    body = MdviewApi(base_url()).publish(title_for(file, markdown, title), markdown)
    url = body.get("shareUrl") or body.get("viewerUrl")
    if not url:
        sid = share_id(body)
        url = share_url(sid) if sid else None
    if not url:
        raise ServiceError("The publish response did not include a share URL.")
    if as_json:
        click.echo(json.dumps(body, separators=(",", ":")))
    else:
        click.echo(f"Preview: {url}")
        webbrowser.open(url)


@cli.command("open")
@click.argument("file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
def open_command(file):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.write(file, arcname=file.name)
    payload = base64.b64encode(buffer.getvalue()).decode("ascii")
    url = f"{base_url()}/#mvd=zip:{payload}"
    webbrowser.open(url)
    click.echo(f"Opened {file}")

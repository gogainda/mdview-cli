import json
from pathlib import Path

from click.testing import CliRunner

from mdview_cli.api import ApiError
from mdview_cli.cli import cli


class FakeApi:
    def __init__(self, renderable=True):
        self.renderable = renderable
        self.created = 0
        self.updated = 0
        self.verified = 0
        self.shared = 0
        self.missing_on_update = False
        self.slug_calls = []

    def create(self, title, content):
        self.created += 1
        return {"id": "doc123", "updated_at": "one"}

    def update(self, document_id, title, content, updated_at=None):
        self.updated += 1
        if self.missing_on_update:
            self.missing_on_update = False
            raise ApiError("Document not found", 404)
        return {"ok": True, "updated_at": "two"}

    def share(self, document_id):
        self.shared += 1
        return {"shortId": "share123"}

    def set_slug(self, document_id, slug):
        self.slug_calls.append((document_id, slug))
        return {"customSlug": slug}

    def documents(self):
        return [{"id": "doc123", "title": "Doc", "customSlug": "share123"}]

    def verify(self, document_id, status=False):
        self.verified += 1
        return {
            "renderable": self.renderable,
            "diagrams": {
                "total": 1,
                "failing": 0 if self.renderable else 1,
            },
            "tables": {"total": 2},
            "failures": [] if self.renderable else [{"index": 0, "error": "Parse error"}],
        }

    def fix(self, document_id):
        self.renderable = True
        return {"markdown": "# Fixed\n\n```mermaid\ngraph TD; A-->B\n```\n", "diagrams": {"fixed": 1}}

    def export_pdf(self, document_id):
        return b"%PDF-1.4 rendered"

    def fix_markdown(self, content):
        return {
            "renderable": True,
            "markdown": "# Fixed locally\n",
            "diagrams": {"total": 1, "failing_before": 1, "fixed": 1, "remaining": 0},
        }


def configure(monkeypatch, tmp_path, api):
    monkeypatch.setenv("MDVIEW_TOKEN", "mdv1_test")
    monkeypatch.setenv("MDVIEW_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("MDVIEW_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr("mdview_cli.cli.api_for_token", lambda token=None: api)


def test_sync_creates_once_then_updates_and_always_verifies(monkeypatch, tmp_path):
    api = FakeApi()
    configure(monkeypatch, tmp_path, api)
    document = tmp_path / "architecture.md"
    document.write_text("# Architecture\n", encoding="utf-8")
    runner = CliRunner()

    first = runner.invoke(cli, ["sync", str(document)])
    document.write_text("# Architecture\n\nSecond revision.\n", encoding="utf-8")
    second = runner.invoke(cli, ["sync", str(document)])

    assert first.exit_code == 0
    assert second.exit_code == 0
    assert "https://mdview.io/p/doc123" in second.output
    assert api.created == 1
    assert api.updated == 1
    assert api.verified == 2
    assert api.shared == 0


def test_sync_reports_broken_diagram_and_exits_one_when_repair_unavailable(monkeypatch, tmp_path):
    api = FakeApi(renderable=False)

    def quota_exhausted(document_id):
        raise ApiError("Daily Quick Fix limit reached. Upgrade to Pro for unlimited fixes.", 402)

    api.fix = quota_exhausted
    configure(monkeypatch, tmp_path, api)
    document = tmp_path / "broken.md"
    document.write_text("# Broken\n", encoding="utf-8")

    result = CliRunner().invoke(cli, ["sync", str(document)])

    assert result.exit_code == 1
    assert "Auto-repair unavailable" in result.output
    assert "Diagram 0: Parse error" in result.output


def test_sync_recreates_a_deleted_associated_document(monkeypatch, tmp_path):
    api = FakeApi()
    configure(monkeypatch, tmp_path, api)
    document = tmp_path / "doc.md"
    document.write_text("# Doc\n", encoding="utf-8")
    runner = CliRunner()
    assert runner.invoke(cli, ["sync", str(document)]).exit_code == 0
    api.missing_on_update = True

    result = runner.invoke(cli, ["sync", str(document), "--json"])

    assert result.exit_code == 0
    assert json.loads(result.output)["created"] is True
    assert api.created == 2


def test_sync_json_is_machine_readable(monkeypatch, tmp_path):
    api = FakeApi()
    configure(monkeypatch, tmp_path, api)
    document = tmp_path / "doc.md"
    document.write_text("# Doc\n", encoding="utf-8")

    result = CliRunner().invoke(cli, ["sync", str(document), "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["document_id"] == "doc123"
    assert payload["renderable"] is True


def test_preview_publishes_anonymously_and_opens_share_url(monkeypatch, tmp_path):
    calls = {}

    class FakePublisher:
        def __init__(self, base_url, token=None, timeout=75):
            calls["token"] = token

        def publish(self, title, content):
            calls["title"] = title
            calls["content"] = content
            return {"shareUrl": "https://mdview.io/s/tmp123"}

    opened = []
    monkeypatch.setattr("mdview_cli.cli.MdviewApi", FakePublisher)
    monkeypatch.setattr("mdview_cli.cli.webbrowser.open", opened.append)
    document = tmp_path / "notes.md"
    document.write_text("# Notes\n\nBody.\n", encoding="utf-8")

    result = CliRunner().invoke(cli, ["preview", str(document)])

    assert result.exit_code == 0
    assert "https://mdview.io/s/tmp123" in result.output
    assert calls["token"] is None
    assert calls["title"] == "Notes"
    assert opened == ["https://mdview.io/s/tmp123"]


def test_bare_file_argument_defaults_to_preview(monkeypatch, tmp_path):
    class FakePublisher:
        def __init__(self, base_url, token=None, timeout=75):
            pass

        def publish(self, title, content):
            return {"shareUrl": "https://mdview.io/s/tmp123"}

    monkeypatch.setattr("mdview_cli.cli.MdviewApi", FakePublisher)
    monkeypatch.setattr("mdview_cli.cli.webbrowser.open", lambda url: None)
    document = tmp_path / "notes.md"
    document.write_text("# Notes\n", encoding="utf-8")

    result = CliRunner().invoke(cli, [str(document)])

    assert result.exit_code == 0
    assert "https://mdview.io/s/tmp123" in result.output


def test_unknown_command_still_errors(tmp_path):
    result = CliRunner().invoke(cli, ["snyc"])

    assert result.exit_code == 2
    assert "No such command" in result.output


def test_share_publishes_on_request_and_sync_stays_private_until_then(monkeypatch, tmp_path):
    api = FakeApi()
    configure(monkeypatch, tmp_path, api)
    document = tmp_path / "doc.md"
    document.write_text("# Doc\n", encoding="utf-8")
    runner = CliRunner()
    assert runner.invoke(cli, ["sync", str(document)]).exit_code == 0
    assert api.shared == 0

    shared = runner.invoke(cli, ["share", str(document)])
    resynced = runner.invoke(cli, ["sync", str(document)])

    assert shared.exit_code == 0
    assert shared.output.strip() == "https://mdview.io/s/share123"
    assert api.shared == 1
    assert "Share: https://mdview.io/s/share123" in resynced.output


def test_sync_no_fix_skips_repair_and_exits_one(monkeypatch, tmp_path):
    api = FakeApi(renderable=False)
    configure(monkeypatch, tmp_path, api)
    document = tmp_path / "broken.md"
    original = "# Broken\n\n```mermaid\nnope\n```\n"
    document.write_text(original, encoding="utf-8")

    result = CliRunner().invoke(cli, ["sync", str(document), "--no-fix"])

    assert result.exit_code == 1
    assert "Diagram 0: Parse error" in result.output
    assert document.read_text(encoding="utf-8") == original


def test_sync_auto_repairs_broken_diagrams_and_exits_zero(monkeypatch, tmp_path):
    api = FakeApi(renderable=False)
    configure(monkeypatch, tmp_path, api)
    document = tmp_path / "broken.md"
    document.write_text("# Broken\n\n```mermaid\nnope\n```\n", encoding="utf-8")

    result = CliRunner().invoke(cli, ["sync", str(document)])

    assert result.exit_code == 0
    assert document.read_text(encoding="utf-8").startswith("# Fixed")
    assert "Renderable: yes" in result.output


def test_export_no_sync_exports_published_doc_without_uploading(monkeypatch, tmp_path):
    api = FakeApi()
    configure(monkeypatch, tmp_path, api)
    document = tmp_path / "doc.md"
    document.write_text("# Doc\n", encoding="utf-8")
    runner = CliRunner()
    assert runner.invoke(cli, ["sync", str(document)]).exit_code == 0
    document.write_text("# Broken WIP edit\n", encoding="utf-8")

    result = runner.invoke(cli, ["export", str(document), "--no-sync"])

    assert result.exit_code == 0
    assert (tmp_path / "doc.pdf").read_bytes() == b"%PDF-1.4 rendered"
    assert api.created == 1 and api.updated == 0


def test_fix_local_rewrites_file_without_syncing(monkeypatch, tmp_path):
    api = FakeApi()
    configure(monkeypatch, tmp_path, api)
    document = tmp_path / "broken.md"
    original = "# Broken\n\n```mermaid\nnope\n```\n"
    document.write_text(original, encoding="utf-8")

    result = CliRunner().invoke(cli, ["fix", str(document), "--local", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["fixed"] == 1
    assert document.read_text(encoding="utf-8") == "# Fixed locally\n"
    assert Path(payload["backup"]).read_text(encoding="utf-8") == original
    assert api.created == 0
    assert api.updated == 0
    assert api.verified == 0


def test_share_accepts_custom_slug_and_json(monkeypatch, tmp_path):
    api = FakeApi()
    configure(monkeypatch, tmp_path, api)
    document = tmp_path / "doc.md"
    document.write_text("# Doc\n", encoding="utf-8")
    runner = CliRunner()
    assert runner.invoke(cli, ["sync", str(document)]).exit_code == 0

    result = runner.invoke(cli, ["share", str(document), "--slug", "my-slug", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["slug"] == "my-slug"
    assert payload["share_url"] == "https://mdview.io/s/my-slug"
    assert api.slug_calls == [("doc123", "my-slug")]


def test_publish_syncs_and_shares_with_slug_in_one_step(monkeypatch, tmp_path):
    api = FakeApi()
    configure(monkeypatch, tmp_path, api)
    document = tmp_path / "doc.md"
    document.write_text("# Doc\n", encoding="utf-8")

    result = CliRunner().invoke(cli, ["publish", str(document), "--slug", "my-slug", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["share_url"] == "https://mdview.io/s/my-slug"
    assert api.created == 1
    assert api.shared == 1
    assert api.slug_calls == [("doc123", "my-slug")]


def test_publish_repairs_broken_diagrams_before_sharing(monkeypatch, tmp_path):
    api = FakeApi(renderable=False)
    configure(monkeypatch, tmp_path, api)
    document = tmp_path / "broken.md"
    document.write_text("# Broken\n\n```mermaid\nnope\n```\n", encoding="utf-8")

    result = CliRunner().invoke(cli, ["publish", str(document), "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["renderable"] is True
    assert payload["share_url"] == "https://mdview.io/s/share123"
    assert document.read_text(encoding="utf-8").startswith("# Fixed")


def test_status_reports_unlinked_file(monkeypatch, tmp_path):
    api = FakeApi()
    configure(monkeypatch, tmp_path, api)
    document = tmp_path / "doc.md"
    document.write_text("# Doc\n", encoding="utf-8")

    result = CliRunner().invoke(cli, ["status", str(document), "--json"])

    assert result.exit_code == 0
    assert json.loads(result.output) == {"file": str(document), "linked": False}


def test_status_reconciles_share_state_from_server_and_detects_dirty_file(monkeypatch, tmp_path):
    api = FakeApi()
    configure(monkeypatch, tmp_path, api)
    document = tmp_path / "doc.md"
    document.write_text("# Doc\n", encoding="utf-8")
    runner = CliRunner()
    assert runner.invoke(cli, ["sync", str(document)]).exit_code == 0

    clean = runner.invoke(cli, ["status", str(document), "--json"])
    document.write_text("# Doc\n\nEdited locally.\n", encoding="utf-8")
    dirty = runner.invoke(cli, ["status", str(document), "--json"])

    clean_payload = json.loads(clean.output)
    dirty_payload = json.loads(dirty.output)
    assert clean_payload["published"] is True
    assert clean_payload["share_url"] == "https://mdview.io/s/share123"
    assert clean_payload["dirty"] is False
    assert dirty_payload["dirty"] is True


def test_fix_backs_up_rewrites_resyncs_and_verifies(monkeypatch, tmp_path):
    api = FakeApi(renderable=False)
    configure(monkeypatch, tmp_path, api)
    document = tmp_path / "broken.md"
    original = "# Broken\n\n```mermaid\nnope\n```\n"
    document.write_text(original, encoding="utf-8")

    result = CliRunner().invoke(cli, ["fix", str(document), "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert document.read_text(encoding="utf-8").startswith("# Fixed")
    assert Path(payload["backup"]).read_text(encoding="utf-8") == original
    assert api.updated == 1
    assert api.verified == 1

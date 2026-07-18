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
        self.missing_on_update = False

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
        return {"shortId": "share123"}

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
    assert "https://mdview.io/s/share123" in second.output
    assert api.created == 1
    assert api.updated == 1
    assert api.verified == 2


def test_sync_reports_broken_diagram_and_exits_one(monkeypatch, tmp_path):
    api = FakeApi(renderable=False)
    configure(monkeypatch, tmp_path, api)
    document = tmp_path / "broken.md"
    document.write_text("# Broken\n", encoding="utf-8")

    result = CliRunner().invoke(cli, ["sync", str(document)])

    assert result.exit_code == 1
    assert "Diagram 0: Parse error" in result.output
    assert "mdv fix FILE" in result.output


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

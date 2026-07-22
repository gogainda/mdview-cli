import pytest

from mdview_cli.api import ApiError, MdviewApi


class FakeResponse:
    def __init__(self, status_code, body):
        self.status_code = status_code
        self.is_error = status_code >= 400
        self._body = body
        self.reason_phrase = "error"

    def json(self):
        return self._body


def make_api(monkeypatch, responses):
    api = MdviewApi("https://mdview.io", token="mdv1_test")
    calls = []

    def fake_request(method, path, **kwargs):
        calls.append((method, path))
        return responses[len(calls) - 1]

    monkeypatch.setattr(api.client, "request", fake_request)
    monkeypatch.setattr("mdview_cli.api.time.sleep", lambda seconds: None)
    return api, calls


def test_retries_on_busy_then_succeeds(monkeypatch):
    responses = [
        FakeResponse(409, {"error": "export_busy"}),
        FakeResponse(409, {"error": "export_busy"}),
        FakeResponse(200, {"ok": True}),
    ]
    api, calls = make_api(monkeypatch, responses)

    result = api.request("GET", "/api/documents/doc123/export/pdf")

    assert result.json() == {"ok": True}
    assert len(calls) == 3


def test_gives_up_after_bounded_retries(monkeypatch):
    responses = [FakeResponse(409, {"error": "export_busy"}) for _ in range(10)]
    api, calls = make_api(monkeypatch, responses)

    with pytest.raises(ApiError, match="export_busy"):
        api.request("GET", "/api/documents/doc123/export/pdf")

    assert len(calls) == 4


def test_does_not_retry_non_busy_errors(monkeypatch):
    responses = [FakeResponse(404, {"error": "not_found"})]
    api, calls = make_api(monkeypatch, responses)

    with pytest.raises(ApiError, match="not_found"):
        api.request("GET", "/api/documents/doc123")

    assert len(calls) == 1

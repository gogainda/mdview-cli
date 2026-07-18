import httpx


class ApiError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class MdviewApi:
    def __init__(self, base_url: str, token: str, timeout: float = 75):
        self.base_url = base_url.rstrip("/")
        self.client = httpx.Client(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=timeout,
        )

    def request(self, method: str, path: str, **kwargs):
        try:
            response = self.client.request(method, path, **kwargs)
        except httpx.HTTPError as error:
            raise ApiError(f"Could not reach mdview.io: {error}") from error
        if response.is_error:
            try:
                body = response.json()
                message = body.get("message") or body.get("error") or response.reason_phrase
            except ValueError:
                message = response.reason_phrase
            raise ApiError(str(message), response.status_code)
        return response

    def validate(self):
        self.request("GET", "/api/documents")

    def create(self, title, content):
        return self.request("POST", "/api/documents", json={"title": title, "content": content}).json()

    def update(self, document_id, title, content, updated_at=None):
        body = {"title": title, "content": content}
        if updated_at:
            body["clientUpdatedAt"] = updated_at
        return self.request("PUT", f"/api/documents/{document_id}", json=body).json()

    def share(self, document_id):
        return self.request("POST", f"/api/documents/{document_id}/share", json={}).json()

    def verify(self, document_id, status=False):
        suffix = "/status" if status else ""
        return self.request("GET", f"/api/documents/{document_id}/verify{suffix}").json()

    def fix(self, document_id):
        return self.request("POST", f"/api/documents/{document_id}/fix/diagrams", json={}).json()

    def export_pdf(self, document_id):
        return self.request("GET", f"/api/documents/{document_id}/export/pdf").content

    def documents(self):
        return self.request("GET", "/api/documents").json()

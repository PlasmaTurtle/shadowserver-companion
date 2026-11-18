"""Explicit launcher authentication for local synthetic test clients."""

from fastapi.testclient import TestClient as StarletteTestClient


class TestClient(StarletteTestClient):
    __test__ = False

    def __init__(self, app, **kwargs):
        kwargs.setdefault("base_url", "http://127.0.0.1")
        super().__init__(app, **kwargs)

    def __enter__(self):
        value = super().__enter__()
        authenticate(value, self.app)
        return value


def authenticate(client, app):
    response = client.post(
        "/api/session/exchange",
        headers={
            "X-Workbench-Launch": app.state.sessions.issue_launch(),
            "Origin": "http://127.0.0.1",
        },
    )
    assert response.status_code == 200, response.text
    client.headers["X-Workbench-Token"] = client.get("/api/bootstrap").json()["token"]
    return client

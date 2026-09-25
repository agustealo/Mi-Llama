from fastapi import FastAPI
from fastapi.testclient import TestClient

from mi_llama.workspace import attach_workspace


def test_workspace_mount_preserves_existing_routes() -> None:
    app = FastAPI()

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ready"}

    attach_workspace(app)
    client = TestClient(app)

    response = client.get("/")
    assert response.status_code == 200
    assert "Mi-Llama Workspace" in response.text
    assert client.get("/health").json() == {"status": "ready"}

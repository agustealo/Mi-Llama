from uuid import UUID

from fastapi import FastAPI
from fastapi.testclient import TestClient

from mi_llama.main import require_access_token
from mi_llama.research_structure.routes import register_research_structure_routes
from mi_llama.writing_structure.routes import register_writing_structure_routes

PROJECT_ID = UUID("11111111-1111-1111-1111-111111111111")


class ResearchListRepository:
    async def list_research_questions(self, *, access_token: str, project_id: UUID) -> list[object]:
        assert access_token == "jwt"
        assert project_id == PROJECT_ID
        return []


class WritingListRepository:
    async def list_outline_nodes(self, *, access_token: str, project_id: UUID) -> list[object]:
        assert access_token == "jwt"
        assert project_id == PROJECT_ID
        return []


def test_research_route_binds_injected_bearer_dependency() -> None:
    app = FastAPI()
    register_research_structure_routes(
        app=app,
        repository=ResearchListRepository(),  # type: ignore[arg-type]
        research=None,
        access_token_dependency=require_access_token,
    )

    response = TestClient(app).get(
        f"/api/projects/{PROJECT_ID}/research/questions",
        headers={"Authorization": "Bearer jwt"},
    )

    assert response.status_code == 200, response.text
    assert response.json() == []


def test_writing_route_binds_injected_bearer_dependency() -> None:
    app = FastAPI()
    register_writing_structure_routes(
        app=app,
        repository=WritingListRepository(),  # type: ignore[arg-type]
        access_token_dependency=require_access_token,
    )

    response = TestClient(app).get(
        f"/api/projects/{PROJECT_ID}/writing/outline",
        headers={"Authorization": "Bearer jwt"},
    )

    assert response.status_code == 200, response.text
    assert response.json() == []

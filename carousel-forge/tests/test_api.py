"""API 표면 — 미구현 엔드포인트는 빈 응답이 아니라 501을 낸다."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

from apps.api.deps import get_session
from apps.api.main import app


@pytest.fixture
def client(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'api.db'}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)

    def override():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_healthz_reports_platform_spec_freshness(client):
    body = client.get("/healthz").json()
    assert body["status"] == "ok"
    assert body["platforms_stale"] is False


def test_platforms_endpoint_serves_the_config(client):
    body = client.get("/platforms").json()
    assert body["instagram"]["canvas"] == {"width": 1080, "height": 1350, "ratio": "4:5"}
    assert body["xiaohongshu"]["title_max_chars"] == 20


def test_account_round_trip(client):
    created = client.post(
        "/accounts",
        json={"handle": "deskreset", "display_name": "Desk Reset", "platform": "instagram"},
    )
    assert created.status_code == 201, created.text
    assert created.json()["default_language"] == "ko"
    assert client.get("/accounts").json()[0]["handle"] == "deskreset"


def test_duplicate_handle_is_rejected(client):
    payload = {"handle": "dup", "display_name": "Dup", "platform": "instagram"}
    assert client.post("/accounts", json=payload).status_code == 201
    assert client.post("/accounts", json=payload).status_code == 409


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("post", "/topics/ingest"),
        ("post", "/carousels"),
        ("post", "/carousels/x/regenerate"),
        ("post", "/carousels/x/localize"),
        ("get", "/exports/x/zip"),
        ("post", "/library/x/remix"),
    ],
)
def test_unbuilt_endpoints_return_501_with_the_milestone(client, method, path):
    response = getattr(client, method)(path)
    assert response.status_code == 501
    assert "구현 예정" in response.json()["detail"]


def test_missing_export_is_404_not_501(client):
    assert client.get("/exports/nope/manifest").status_code == 404


def test_implemented_endpoints_no_longer_return_501(client):
    """M3가 붙은 뒤 /styles/extract는 501이 아니다 — 없는 계정에 404를 낸다."""
    response = client.post(
        "/styles/extract", json={"account_id": "nope", "name": "x", "screenshots": ["a.png"]}
    )
    assert response.status_code == 404

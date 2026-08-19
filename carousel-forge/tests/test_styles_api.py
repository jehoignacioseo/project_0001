"""/styles — 승인 관문이 실제로 막는가.

추출된 DNA가 사람 승인 없이 활성화되면 이 관문은 없는 것과 같다.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

from apps.api.deps import get_session
from apps.api.main import app
from apps.api.models import Account, StyleDNA

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr("apps.api.routers.styles.STORAGE_DIR", tmp_path / "storage")
    engine = create_engine(
        f"sqlite:///{tmp_path / 'styles.db'}", connect_args={"check_same_thread": False}
    )
    SQLModel.metadata.create_all(engine)

    def override():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override
    with TestClient(app) as c:
        c.engine = engine
        yield c
    app.dependency_overrides.clear()


def _account(client) -> str:
    return client.post(
        "/accounts",
        json={"handle": "bench", "display_name": "Bench", "platform": "instagram"},
    ).json()["id"]


def _style(client, *, confidence: float = 0.7, active: bool = False) -> str:
    dna = json.loads((FIXTURES / "style_dna_benchmark.json").read_text(encoding="utf-8"))
    with Session(client.engine) as session:
        record = StyleDNA(
            account_id=_account(client),
            name="benchmark",
            version=1,
            source_type="screenshots",
            source_refs=[],
            dna=dna,
            confidence_score=confidence,
            is_active=active,
        )
        session.add(record)
        session.commit()
        session.refresh(record)
        return record.id


def test_extract_rejects_an_unknown_account(client):
    response = client.post(
        "/styles/extract",
        json={"account_id": "nope", "name": "x", "screenshots": ["a.png"]},
    )
    assert response.status_code == 404


def test_extract_rejects_missing_files(client):
    account_id = _account(client)
    response = client.post(
        "/styles/extract",
        json={"account_id": account_id, "name": "x", "screenshots": ["/없는/파일.png"]},
    )
    assert response.status_code == 400
    assert "찾을 수 없다" in response.json()["detail"]


def test_activation_requires_a_verification_render(client, tmp_path):
    """검증 렌더를 보지 않고 승인하면 관문이 의미가 없다."""
    style_id = _style(client)
    response = client.post(f"/styles/{style_id}/activate", json={"approved": True})
    assert response.status_code == 409
    assert "검증 렌더 없이" in response.json()["detail"]

    with Session(client.engine) as session:
        assert session.get(StyleDNA, style_id).is_active is False


def test_rejecting_keeps_it_inactive(client):
    style_id = _style(client)
    response = client.post(f"/styles/{style_id}/activate", json={"approved": False})
    assert response.status_code == 200
    assert response.json()["is_active"] is False


def test_approval_activates_and_retires_the_previous_dna(client, tmp_path):
    style_id = _style(client)
    # 검증 렌더가 있었던 것으로 만든다 (렌더 자체는 M1 테스트가 검증한다)
    preview = tmp_path / "storage" / "styles" / style_id
    preview.mkdir(parents=True)
    (preview / "comparison.png").write_bytes(b"\x89PNG\r\n\x1a\n")

    with Session(client.engine) as session:
        record = session.get(StyleDNA, style_id)
        account_id = record.account_id
        older = StyleDNA(
            account_id=account_id, name="old", version=0, source_type="manual",
            source_refs=[], dna=record.dna, confidence_score=0.5, is_active=True,
        )
        session.add(older)
        session.commit()
        older_id = older.id

    response = client.post(f"/styles/{style_id}/activate", json={"approved": True})
    assert response.status_code == 200
    body = response.json()
    assert body["is_active"] is True
    assert older_id in body["deactivated"]

    with Session(client.engine) as session:
        # 이전 버전은 내려가되 삭제되지 않는다 — 버전은 남는다
        assert session.get(StyleDNA, older_id).is_active is False
        assert session.get(StyleDNA, older_id) is not None
        assert session.get(Account, account_id).active_style_dna_id == style_id


def test_low_confidence_is_surfaced_on_activation(client, tmp_path):
    style_id = _style(client, confidence=0.4)
    preview = tmp_path / "storage" / "styles" / style_id
    preview.mkdir(parents=True)
    (preview / "comparison.png").write_bytes(b"\x89PNG\r\n\x1a\n")

    body = client.post(f"/styles/{style_id}/activate", json={"approved": True}).json()
    assert body["is_active"] is True
    assert "신뢰도" in body["message"]


def test_preview_image_404s_before_it_is_built(client):
    style_id = _style(client)
    response = client.get(f"/styles/{style_id}/preview.png")
    assert response.status_code == 404
    assert "아직 없다" in response.json()["detail"]

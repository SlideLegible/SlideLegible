"""End-to-end API test with rendering disabled."""

from __future__ import annotations

import time
from collections.abc import Iterator
from typing import Any

import decks
import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("SLIDELEGIBLE_RENDERER", "none")
    from slidelegible_web.app import app

    with TestClient(app) as c:
        yield c


def _wait(client: TestClient, job_id: str) -> dict[str, Any]:
    for _ in range(200):
        job = client.get(f"/api/v1/jobs/{job_id}").json()
        if job["status"] in ("completed", "failed"):
            return dict(job)
        time.sleep(0.05)
    raise AssertionError("job did not finish")


def test_full_flow(client: TestClient) -> None:
    caps = client.get("/api/v1/capabilities").json()
    assert caps["renderer"] is None
    assert {p["name"] for p in caps["policies"]} == {"comfortable", "projector", "strict_aaa"}

    files = {"file": ("demo.pptx", decks.deck_basic(), "application/octet-stream")}
    upload = client.post("/api/v1/presentations", files=files).json()
    assert upload["slides"] == 1

    job = client.post(
        f"/api/v1/presentations/{upload['id']}/analysis", json={"policy": "projector"}
    ).json()
    done = _wait(client, job["job_id"])
    assert done["status"] == "completed", done
    analysis = client.get(f"/api/v1/analyses/{done['result']['analysis_id']}").json()
    report = analysis["report"]
    assert report["policy"]["name"] == "projector"
    suggestions = report["plan"]["suggestions"]
    assert suggestions
    assert analysis["proposed"]["applied"] == [s["id"] for s in suggestions]

    first = suggestions[0]["id"]
    job = client.post(
        f"/api/v1/analyses/{analysis['id']}/corrections", json={"suggestion_ids": [first]}
    ).json()
    done = _wait(client, job["job_id"])
    correction = done["result"]["correction"]
    assert correction["applied"] == [first]

    pptx = client.get(f"/api/v1/artifacts/{correction['pptx_artifact']}")
    assert pptx.status_code == 200 and pptx.content[:2] == b"PK"
    html = client.get(f"/api/v1/corrections/{correction['id']}/report?lang=en")
    assert html.status_code == 200 and "readability report" in html.text
    zh = client.get(f"/api/v1/corrections/{correction['id']}/report?lang=zh-TW")
    assert "可讀性報告" in zh.text


def test_invalid_upload(client: TestClient) -> None:
    files = {"file": ("x.pptx", b"hello", "application/octet-stream")}
    response = client.post("/api/v1/presentations", files=files)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "not_a_zip"


def test_unknown_ids(client: TestClient) -> None:
    assert client.get("/api/v1/jobs/nope").status_code == 404
    assert client.get("/api/v1/artifacts/nope").status_code == 404

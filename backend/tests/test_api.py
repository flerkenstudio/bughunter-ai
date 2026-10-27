"""Backend contract tests, including the full failure-to-verification loop."""
from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app.security import UnsafeTargetError, validate_patch
from backend.app.targets import free_port

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture()
def client(tmp_path):
    port = free_port()
    from backend.app.config import Settings

    settings = Settings(
        repo_root=REPO_ROOT,
        db_path=tmp_path / "bughunter.db",
        artifact_dir=tmp_path / "artifacts",
        demo_dir=REPO_ROOT / "demo-store",
        demo_port=port,
        default_run_timeout_seconds=120,
    )
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client, settings


def test_health_and_seeded_project(client):
    test_client, _ = client
    health = test_client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    projects = test_client.get("/api/projects")
    assert projects.status_code == 200
    assert len(projects.json()) == 1
    assert projects.json()[0]["name"].startswith("Nimbus")


def test_rejects_unsafe_target_scheme_and_credentials(client):
    test_client, _ = client
    for url in ["file:///etc/passwd", "http://user:pass@example.com"]:
        response = test_client.post(
            "/api/projects", json={"name": "Unsafe", "base_url": url, "description": ""}
        )
        assert response.status_code == 400, url


def test_rejects_unknown_scope(client):
    test_client, _ = client
    project = test_client.get("/api/projects").json()[0]
    response = test_client.post(
        "/api/runs",
        json={"project_id": project["id"], "scope": ["admin"], "mode": "reproduce"},
    )
    assert response.status_code == 400


def test_patch_path_validation():
    safe = (
        "--- a/demo-store/checkout.js\n+++ b/demo-store/checkout.js\n"
        "@@ -1 +1 @@\n-a\n+b\n"
    )
    assert validate_patch(safe) == ["demo-store/checkout.js"]

    with pytest.raises(UnsafeTargetError):
        validate_patch("--- a/../secrets.env\n+++ b/../secrets.env\n@@ -1 +1 @@\n-a\n+b\n")

    with pytest.raises(UnsafeTargetError):
        validate_patch("--- a/frontend/.env\n+++ b/frontend/.env\n@@ -1 +1 @@\n-a\n+b\n")


def _wait_for_terminal(test_client: TestClient, run_id: str, timeout: float = 180.0) -> dict:
    deadline = time.time() + timeout
    last: dict = {}
    while time.time() < deadline:
        last = test_client.get(f"/api/runs/{run_id}/live").json()
        if not last["active"]:
            return last
        time.sleep(1.0)
    raise AssertionError(f"run did not finish in {timeout}s: {last}")


def test_seeded_bug_reproduced_and_patch_verified(client):
    test_client, _ = client
    project = test_client.get("/api/projects").json()[0]

    start = test_client.post(
        "/api/runs",
        json={
            "project_id": project["id"],
            "scope": ["checkout"],
            "mode": "reproduce",
            "max_duration_seconds": 120,
        },
    )
    assert start.status_code == 202, start.text
    run_id = start.json()["id"]

    live = _wait_for_terminal(test_client, run_id)
    run = live["run"]
    assert run["status"] == "completed", run
    assert run["target_revision"], "the tested revision must be recorded"

    bugs = live["bugs"]
    assert len(bugs) == 1, bugs
    bug = bugs[0]
    assert bug["severity"] in {"high", "critical"}
    assert bug["reproduction_steps"], bug
    assert any(artifact["type"] == "screenshot" for artifact in bug["evidence"]), bug["evidence"]
    assert any(artifact["type"] == "trace" for artifact in bug["evidence"]), bug["evidence"]
    assert any(artifact["type"] == "console_log" for artifact in bug["evidence"])

    tests = live["tests"]
    by_attempt: dict[int, dict[str, str]] = {}
    for test in tests:
        by_attempt.setdefault(test["attempt"], {})[test["test_key"]] = test["status"]
    assert by_attempt[1]["checkout_discount_total"] == "failed"
    assert by_attempt[2]["checkout_discount_total"] == "failed"
    assert by_attempt[1]["checkout_healthy_path"] == "passed"

    patches = bug["patches"]
    assert len(patches) == 1, patches
    assert patches[0]["verification_status"] == "unverified"

    verify = test_client.post(f"/api/patches/{patches[0]['id']}/verify")
    assert verify.status_code == 200, verify.text
    payload = verify.json()
    assert payload["verification_status"] == "verified", payload
    assert payload["all_passed"] is True
    statuses = {test["test_key"]: test["status"] for test in payload["tests"]}
    assert statuses["checkout_discount_total"] == "passed"
    assert statuses["checkout_healthy_path"] == "passed"
    assert all(status == "passed" for status in statuses.values())

    # Verification rows must persist so a reload still shows what passed.
    persisted = test_client.get(f"/api/bugs/{bug['id']}").json()
    saved_tests = persisted["patches"][0]["verification_tests"]
    assert saved_tests and len(saved_tests) == 4, saved_tests
    assert {row["status"] for row in saved_tests} == {"passed"}

    # Verification evidence must be persisted and hash-addressed.
    run_artifacts = test_client.get(f"/api/runs/{run_id}/artifacts").json()
    assert any("verification" in artifact["label"] for artifact in run_artifacts)
    assert all(len(artifact["sha256"]) == 64 for artifact in run_artifacts)

def test_suite_that_never_ran_is_failed_not_completed(client, monkeypatch):
    """A browser suite that produces no results must never be reported as a pass."""
    test_client, _ = client
    import backend.app.orchestrator as orchestrator_module
    from backend.app.runner.playwright_runner import SuiteResult, TestResult

    def fake_run_tests(**kwargs):
        return SuiteResult(
            results=[
                TestResult(test_key=key, name=key, status="not_run", failure_message="did not execute")
                for key in kwargs["test_keys"]
            ],
            output_tail="pytest exited with code 4; junit written: False",
            timed_out=False,
            duration_ms=12,
        )

    monkeypatch.setattr(orchestrator_module, "run_tests", fake_run_tests)
    project = test_client.get("/api/projects").json()[0]
    start = test_client.post(
        "/api/runs",
        json={"project_id": project["id"], "scope": ["checkout"], "mode": "reproduce"},
    )
    assert start.status_code == 202, start.text
    live = _wait_for_terminal(test_client, start.json()["id"])

    assert live["run"]["status"] == "failed"
    assert live["run"]["error_kind"] == "runner_error"
    assert "did not execute" in live["run"]["error_message"]
    assert live["bugs"] == []


def test_target_policy_blocks_private_and_metadata(client):
    test_client, _ = client
    blocked = [
        "http://10.0.0.5",
        "http://192.168.1.10:8080",
        "http://169.254.169.254/latest/meta-data",
        "ftp://example.com/file",
    ]
    for url in blocked:
        response = test_client.post(
            "/api/projects", json={"name": "Blocked", "base_url": url, "description": ""}
        )
        assert response.status_code == 400, url

    # A public IP literal is a valid target and needs no DNS.
    allowed = test_client.post(
        "/api/projects",
        json={"name": "Public", "base_url": "http://93.184.216.34", "description": ""},
    )
    assert allowed.status_code == 201, allowed.text
    assert allowed.json()["target_kind"] == "external"


def test_external_target_rejects_demo_scope(client):
    test_client, _ = client
    project = test_client.post(
        "/api/projects",
        json={"name": "Public", "base_url": "http://93.184.216.34", "description": ""},
    ).json()

    rejected = test_client.post(
        "/api/runs",
        json={"project_id": project["id"], "scope": ["checkout"], "mode": "reproduce"},
    )
    assert rejected.status_code == 400
    assert "probe" in rejected.json()["detail"]


def test_probe_pack_passes_on_demo_store(client):
    """The generic pack must run against a plain URL and report no bugs."""
    test_client, _ = client
    project = test_client.get("/api/projects").json()[0]
    assert project["target_kind"] == "demo"

    start = test_client.post(
        "/api/runs",
        json={"project_id": project["id"], "scope": ["probe"], "mode": "reproduce"},
    )
    assert start.status_code == 202, start.text
    live = _wait_for_terminal(test_client, start.json()["id"], timeout=240)

    assert live["run"]["status"] == "completed", live["run"]
    assert live["run"]["summary"]["tests_total"] == 8
    assert live["run"]["summary"]["passed"] == 8
    assert live["run"]["summary"]["failed"] == 0
    assert live["bugs"] == []
    assert live["run"]["target_revision"].startswith("fingerprint:")

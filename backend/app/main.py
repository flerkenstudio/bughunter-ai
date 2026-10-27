"""FastAPI application: the API surface described in the project blueprint."""
from __future__ import annotations

import mimetypes
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from . import repository
from .catalog import SCOPES, TESTS
from .config import Settings, get_settings
from .db import init_db
from .orchestrator import ACTIVE_STATES, PatchVerifier, RunOrchestrator
from .schemas import (
    BugOut,
    HealthOut,
    PatchCreate,
    PatchOut,
    ProjectCreate,
    ProjectOut,
    RunCreate,
    RunOut,
    TestCaseOut,
    VerifyOut,
)
from .security import (
    LOOPBACK_HOSTS,
    UnsafeTargetError,
    validate_scope,
    validate_target,
)
from .targets import health_status, stop_all

API_VERSION = "0.1.0"


DEMO_ONLY_SCOPES = {"login", "checkout", "cart"}


def _project_out(project: dict[str, Any]) -> dict[str, Any]:
    host = (urlparse(project["base_url"]).hostname or "").lower()
    return {**project, "target_kind": "demo" if host in LOOPBACK_HOSTS else "external"}


def _run_out(run: dict[str, Any]) -> dict[str, Any]:
    keys = set(RunOut.model_fields)
    return {key: run.get(key) for key in keys}


def _artifact_out(artifact: dict[str, Any]) -> dict[str, Any]:
    payload = dict(artifact)
    payload["download_url"] = f"/api/artifacts/{artifact['id']}"
    return payload


def _bug_out(conn, bug: dict[str, Any]) -> dict[str, Any]:
    payload = dict(bug)
    order = {"screenshot": 0, "trace": 1, "console_log": 2}
    evidence = [
        _artifact_out(artifact)
        for artifact in repository.list_artifacts(conn, bug["run_id"])
        if artifact.get("bug_id") == bug["id"]
    ]
    payload["evidence"] = sorted(evidence, key=lambda item: order.get(item["type"], 3))
    payload["patches"] = repository.list_patches_for_bug(conn, bug["id"])
    return payload


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        init_db(config.db_path)
        seed_url = f"http://127.0.0.1:{config.demo_port}"
        with repository.session(config.db_path) as conn:
            existing = [
                project for project in repository.list_projects(conn) if project["base_url"] == seed_url
            ]
            if not existing:
                repository.create_project(
                    conn,
                    name="Nimbus Supply (demo)",
                    base_url=seed_url,
                    description="Bundled demo storefront with a deliberately seeded checkout bug.",
                )
        app.state.orchestrator = RunOrchestrator(config)
        app.state.verifier = PatchVerifier(config)
        yield
        stop_all()

    app = FastAPI(title="BugHunter AI", version=API_VERSION, lifespan=lifespan)
    app.state.settings = config
    app.state.orchestrator = RunOrchestrator(config)
    app.state.verifier = PatchVerifier(config)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(UnsafeTargetError)
    async def _unsafe_target(_: Request, exc: UnsafeTargetError):
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=400, content={"detail": str(exc)})

    # ---------------------------------------------------------------- health
    @app.get("/api/health", response_model=HealthOut)
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "version": API_VERSION,
            "ai_provider": app.state.orchestrator.provider.name,
            "demo_target": health_status("http://127.0.0.1:8090") or "not-running",
        }

    @app.get("/api/catalog")
    def catalog() -> dict[str, Any]:
        return {
            "scopes": list(SCOPES),
            "tests": [spec.to_dict() for spec in TESTS.values()],
        }

    # ---------------------------------------------------------------- projects
    @app.post("/api/projects", response_model=ProjectOut, status_code=201)
    def create_project(payload: ProjectCreate) -> dict[str, Any]:
        validate_target(payload.base_url, config)
        with repository.session(config.db_path) as conn:
            project = repository.create_project(
                conn,
                name=payload.name,
                base_url=payload.base_url,
                description=payload.description,
            )
            return _project_out(project)

    @app.get("/api/projects", response_model=list[ProjectOut])
    def list_projects() -> list[dict[str, Any]]:
        with repository.session(config.db_path) as conn:
            return [_project_out(project) for project in repository.list_projects(conn)]

    @app.get("/api/projects/{project_id}/memories")
    def list_memories(project_id: str) -> list[dict[str, Any]]:
        with repository.session(config.db_path) as conn:
            return repository.list_memories(conn, project_id)

    # ---------------------------------------------------------------- runs
    @app.post("/api/runs", response_model=RunOut, status_code=202)
    def start_run(payload: RunCreate) -> dict[str, Any]:
        with repository.session(config.db_path) as conn:
            project = repository.get_project(conn, payload.project_id)
            if project is None:
                raise HTTPException(status_code=404, detail="project not found")
            validate_scope(payload.scope)
            target = validate_target(project["base_url"], config)
            if not target.is_demo:
                wrong = [area for area in payload.scope if area in DEMO_ONLY_SCOPES]
                if wrong:
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            f"scope {wrong} only applies to the bundled demo target; "
                            "use ['probe'] for an external URL"
                        ),
                    )
            run = repository.create_run(
                conn,
                project_id=project["id"],
                scope=payload.scope,
                mode=payload.mode,
                max_duration_seconds=payload.max_duration_seconds,
            )
            run = repository.get_run(conn, run["id"]) or run
        app.state.orchestrator.dispatch(run["id"])
        return _run_out(run)

    @app.get("/api/runs", response_model=list[RunOut])
    def list_runs(limit: int = 50) -> list[dict[str, Any]]:
        with repository.session(config.db_path) as conn:
            return [_run_out(run) for run in repository.list_runs(conn, limit=min(limit, 200))]

    @app.get("/api/runs/{run_id}", response_model=RunOut)
    def get_run(run_id: str) -> dict[str, Any]:
        with repository.session(config.db_path) as conn:
            run = repository.get_run(conn, run_id)
            if run is None:
                raise HTTPException(status_code=404, detail="run not found")
            return _run_out(run)

    @app.get("/api/runs/{run_id}/tests", response_model=list[TestCaseOut])
    def get_run_tests(run_id: str) -> list[dict[str, Any]]:
        with repository.session(config.db_path) as conn:
            if repository.get_run(conn, run_id) is None:
                raise HTTPException(status_code=404, detail="run not found")
            return repository.list_tests(conn, run_id)

    @app.get("/api/runs/{run_id}/bugs", response_model=list[BugOut])
    def get_run_bugs(run_id: str) -> list[dict[str, Any]]:
        with repository.session(config.db_path) as conn:
            if repository.get_run(conn, run_id) is None:
                raise HTTPException(status_code=404, detail="run not found")
            return [_bug_out(conn, bug) for bug in repository.list_bugs(conn, run_id)]

    @app.get("/api/runs/{run_id}/artifacts")
    def get_run_artifacts(run_id: str) -> list[dict[str, Any]]:
        with repository.session(config.db_path) as conn:
            if repository.get_run(conn, run_id) is None:
                raise HTTPException(status_code=404, detail="run not found")
            return [_artifact_out(artifact) for artifact in repository.list_artifacts(conn, run_id)]

    @app.get("/api/runs/{run_id}/live")
    def run_live(run_id: str) -> dict[str, Any]:
        """Compact polling payload for the dashboard."""
        with repository.session(config.db_path) as conn:
            run = repository.get_run(conn, run_id)
            if run is None:
                raise HTTPException(status_code=404, detail="run not found")
            tests = repository.list_tests(conn, run_id)
            bugs = [_bug_out(conn, bug) for bug in repository.list_bugs(conn, run_id)]
            return {
                "run": _run_out(run),
                "active": run["status"] in ACTIVE_STATES,
                "tests": tests,
                "bugs": bugs,
            }

    # ---------------------------------------------------------------- bugs and patches
    @app.get("/api/bugs/{bug_id}", response_model=BugOut)
    def get_bug(bug_id: str) -> dict[str, Any]:
        with repository.session(config.db_path) as conn:
            bug = repository.get_bug(conn, bug_id)
            if bug is None:
                raise HTTPException(status_code=404, detail="bug not found")
            return _bug_out(conn, bug)

    @app.post("/api/bugs/{bug_id}/patches", response_model=PatchOut, status_code=201)
    def propose_patch(bug_id: str, payload: PatchCreate) -> dict[str, Any]:
        from .security import validate_patch

        validate_patch(payload.diff)
        with repository.session(config.db_path) as conn:
            bug = repository.get_bug(conn, bug_id)
            if bug is None:
                raise HTTPException(status_code=404, detail="bug not found")
            patch = repository.create_patch(
                conn,
                bug_id=bug_id,
                diff=payload.diff,
                summary=payload.summary,
                source="manual",
            )
            return patch

    @app.get("/api/patches/{patch_id}", response_model=PatchOut)
    def get_patch(patch_id: str) -> dict[str, Any]:
        with repository.session(config.db_path) as conn:
            patch = repository.get_patch(conn, patch_id)
            if patch is None:
                raise HTTPException(status_code=404, detail="patch not found")
            return patch

    @app.post("/api/patches/{patch_id}/verify", response_model=VerifyOut)
    def verify_patch(patch_id: str) -> dict[str, Any]:
        try:
            return app.state.verifier.verify(patch_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except UnsafeTargetError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    # ---------------------------------------------------------------- artifacts
    @app.get("/api/artifacts/{artifact_id}")
    def download_artifact(artifact_id: str) -> FileResponse:
        with repository.session(config.db_path) as conn:
            artifact = repository.get_artifact(conn, artifact_id)
            if artifact is None:
                raise HTTPException(status_code=404, detail="artifact not found")
        path = Path(artifact["storage_path"]).resolve()
        root = config.artifact_dir.resolve()
        if not path.is_file() or not path.is_relative_to(root):
            raise HTTPException(status_code=404, detail="artifact file missing")
        media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        return FileResponse(path, media_type=media_type, filename=path.name)

    # ---------------------------------------------------------------- frontend bundle
    dist = config.repo_root / "frontend" / "dist"
    if dist.is_dir():
        app.mount("/app", StaticFiles(directory=str(dist), html=True), name="dashboard")

        @app.get("/", include_in_schema=False)
        def root() -> RedirectResponse:
            return RedirectResponse(url="/app/")

    return app


app = create_app()
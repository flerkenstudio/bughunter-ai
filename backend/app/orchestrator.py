"""Run orchestration: plan -> execute -> reproduce -> analyze -> persist.

Invariants enforced here:
* a bug exists only after the failure reproduced in a second execution;
* a test that did not run is never counted as a pass;
* infrastructure failures never become application bugs;
* patches are verified only by re-running tests in an isolated checkout.
"""
from __future__ import annotations

import hashlib
import shutil
import subprocess
import tempfile
import threading
import time
import traceback
from pathlib import Path
from typing import Any

from . import artifacts, repository
from .ai.provider import Analysis, build_provider
from .catalog import REGRESSION_TESTS, tests_for_scope
from .config import Settings
from .runner.playwright_runner import SuiteResult, TestResult, run_tests
from .security import (
    DEMO_TARGET_MARKER,
    UnsafeTargetError,
    TargetIdentityError,
    TargetUnavailableError,
    probe_target,
    validate_patch,
    validate_target,
)
from .targets import (
    free_port,
    health_status,
    start_demo_server,
    start_managed_server,
    stop_server,
    wait_for_health,
)

TERMINAL_STATES = {"completed", "failed", "cancelled", "timed_out", "inconclusive"}

ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "queued": {"planning", "failed", "cancelled"},
    "planning": {"running", "failed", "cancelled", "timed_out"},
    "running": {"reproducing", "completed", "inconclusive", "failed", "cancelled", "timed_out"},
    "reproducing": {"analyzing", "inconclusive", "failed", "cancelled", "timed_out"},
    "analyzing": {"completed", "inconclusive", "failed", "cancelled", "timed_out"},
    "patching": {"verifying", "failed", "cancelled"},
    "verifying": {"completed", "failed", "cancelled", "timed_out"},
}

ACTIVE_STATES = {"queued", "planning", "running", "reproducing", "analyzing", "patching", "verifying"}


class InvalidTransition(RuntimeError):
    pass


def demo_tree_revision(repo_root: Path) -> str:
    """Content fingerprint of the target, used when git has no commit yet."""
    digest = hashlib.sha256()
    for path in sorted((repo_root / "demo-store").rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        digest.update(path.relative_to(repo_root).as_posix().encode())
        digest.update(path.read_bytes())
    return "fingerprint:" + digest.hexdigest()[:16]


def git_revision(repo_root: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return demo_tree_revision(repo_root)
    if result.returncode != 0:
        return demo_tree_revision(repo_root)
    return result.stdout.strip() or demo_tree_revision(repo_root)


class Transition:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._lock = threading.Lock()

    def move(self, conn, run_id: str, status: str, **fields: Any) -> None:
        with self._lock:
            run = repository.get_run(conn, run_id)
            if run is None:
                raise InvalidTransition(f"run {run_id} not found")
            current = run["status"]
            if current != status and status not in ALLOWED_TRANSITIONS.get(current, set()):
                raise InvalidTransition(f"{current} -> {status} is not allowed")
            payload = {"status": status, **fields}
            if status in TERMINAL_STATES and "finished_at" not in payload:
                payload["finished_at"] = repository.utc_now()
            repository.update_run(conn, run_id, **payload)


class RunOrchestrator:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.provider = build_provider(settings)

    # ------------------------------------------------------------------ dispatch
    def dispatch(self, run_id: str) -> None:
        thread = threading.Thread(target=self._safe_execute, args=(run_id,), daemon=True)
        thread.start()

    def _safe_execute(self, run_id: str) -> None:
        try:
            self.execute(run_id)
        except Exception:  # noqa: BLE001 - terminal state must be recorded
            detail = traceback.format_exc(limit=5)[-3000:]
            try:
                with repository.session(self.settings.db_path) as conn:
                    Transition(self.settings).move(
                        conn,
                        run_id,
                        "failed",
                        error_kind="internal_error",
                        error_message=detail,
                        finished_at=repository.utc_now(),
                    )
            except Exception:
                pass

    # ------------------------------------------------------------------ main flow
    def execute(self, run_id: str) -> None:
        started = time.monotonic()
        transition = Transition(self.settings)

        with repository.session(self.settings.db_path) as conn:
            run = repository.get_run(conn, run_id)
            if run is None:
                return
            project = repository.get_project(conn, run["project_id"])
            if project is None:
                transition.move(conn, run_id, "failed", error_message="project missing")
                return
            repository.update_run(
                conn,
                run_id,
                status="planning",
                started_at=repository.utc_now(),
            )

        # ---- target preflight: unreachable targets are infrastructure, not bugs
        base_url = project["base_url"]
        try:
            target = validate_target(base_url, self.settings)
            if target.is_demo and health_status(base_url) != DEMO_TARGET_MARKER:
                if target.port == self.settings.demo_port:
                    start_managed_server(
                        self.settings.demo_dir,
                        self.settings.demo_port,
                        self.settings.repo_root / "data" / "logs" / "demo-run.log",
                    )
                else:
                    raise TargetUnavailableError(
                        f"no demo store is listening on {base_url}; register the running demo target"
                    )
            probe_target(target, self.settings)
            # The tested revision only exists for the local demo checkout.
            revision = (
                git_revision(self.settings.repo_root)
                if target.is_demo
                else f"external:{target.host}"
            )
        except (TargetUnavailableError, TargetIdentityError, ValueError) as exc:
            with repository.session(self.settings.db_path) as conn:
                transition.move(
                    conn,
                    run_id,
                    "failed",
                    error_kind="infrastructure",
                    error_message=str(exc)[:2000],
                    summary={
                        "tests_total": 0,
                        "passed": 0,
                        "failed": 0,
                        "confirmed_bugs": 0,
                        "duration_ms": 0,
                    },
                )
                repository.add_memory(
                    conn,
                    project_id=project["id"],
                    run_id=run_id,
                    summary=f"Run {run_id[:8]} did not start: target rejected or unreachable ({exc}).",
                )
            return

        requested_seconds = int(
            run.get("max_duration_seconds") or self.settings.default_run_timeout_seconds
        )
        plan = self.provider.create_plan(
            scope=run["scope"] or [],
            mode=run["mode"],
            project_name=project["name"],
            max_seconds=requested_seconds,
        )
        max_seconds = min(
            int(plan.limits.get("max_duration_seconds", self.settings.default_run_timeout_seconds)),
            self.settings.max_run_timeout_seconds,
        )

        test_keys = [spec.key for spec in tests_for_scope(run["scope"] or [])]
        evidence_root = self.settings.artifact_dir / run_id

        with repository.session(self.settings.db_path) as conn:
            repository.update_run(
                conn, run_id, plan=plan.to_dict(), target_revision=revision
            )
            transition.move(conn, run_id, "running")

        suite = run_tests(
            test_keys=test_keys,
            base_url=base_url,
            evidence_dir=evidence_root / "attempt-1",
            repo_root=self.settings.repo_root,
            timeout_seconds=max_seconds,
        )
        first_cases = self._persist_attempt(
            run_id=run_id,
            suite=suite,
            attempt=1,
            run_dir=evidence_root / "attempt-1",
        )

        if suite.timed_out:
            with repository.session(self.settings.db_path) as conn:
                transition.move(
                    conn,
                    run_id,
                    "timed_out",
                    error_kind="timeout",
                    error_message=f"test suite exceeded {max_seconds}s",
                    summary=self._summary(suite, [], 0),
                )
            return

        # A suite that never executed is an infrastructure failure, never a pass.
        not_run = [result for result in suite.results if result.status == "not_run"]
        if not_run:
            with repository.session(self.settings.db_path) as conn:
                transition.move(
                    conn,
                    run_id,
                    "failed",
                    error_kind="runner_error",
                    error_message=(
                        "the browser suite did not execute: "
                        + suite.output_tail[-1500:]
                    ),
                    summary=self._summary(suite, [], 0),
                )
            return

        failed_results = [r for r in suite.results if r.status in {"failed", "error"}]
        if not failed_results:
            self._complete_clean(
                run_id=run_id,
                project_id=project["id"],
                suite=suite,
                started=started,
            )
            return

        # ---- reproduce: a single failing execution is not yet a confirmed bug
        with repository.session(self.settings.db_path) as conn:
            transition.move(conn, run_id, "reproducing")

        repro_suite = run_tests(
            test_keys=[result.test_key for result in failed_results],
            base_url=base_url,
            evidence_dir=evidence_root / "attempt-2",
            repo_root=self.settings.repo_root,
            timeout_seconds=max_seconds,
        )
        second_cases = self._persist_attempt(
            run_id=run_id,
            suite=repro_suite,
            attempt=2,
            run_dir=evidence_root / "attempt-2",
        )

        if repro_suite.timed_out:
            with repository.session(self.settings.db_path) as conn:
                transition.move(
                    conn,
                    run_id,
                    "timed_out",
                    error_kind="timeout",
                    error_message="reproduction run timed out",
                    summary=self._summary(suite, [], 0),
                )
            return

        repro_not_run = [
            result for result in repro_suite.results if result.status == "not_run"
        ]
        if repro_not_run:
            with repository.session(self.settings.db_path) as conn:
                transition.move(
                    conn,
                    run_id,
                    "failed",
                    error_kind="runner_error",
                    error_message=(
                        "reproduction suite did not execute: "
                        + repro_suite.output_tail[-1500:]
                    ),
                    summary=self._summary(suite, [], 0),
                )
            return

        second_by_key = {result.test_key: result for result in repro_suite.results}
        confirmed = [
            result
            for result in failed_results
            if second_by_key.get(result.test_key) is not None
            and second_by_key[result.test_key].status in {"failed", "error"}
        ]
        not_reproduced = [
            result.test_key
            for result in failed_results
            if result.test_key not in {item.test_key for item in confirmed}
        ]

        if not confirmed:
            with repository.session(self.settings.db_path) as conn:
                transition.move(
                    conn,
                    run_id,
                    "inconclusive",
                    summary=self._summary(suite, [], 0, not_reproduced=not_reproduced),
                    error_kind="not_reproduced",
                    error_message="failures did not repeat on the second execution",
                )
                repository.add_memory(
                    conn,
                    project_id=project["id"],
                    run_id=run_id,
                    summary=(
                        f"Run {run_id[:8]}: {', '.join(not_reproduced)} failed once but did not "
                        "reproduce; no bug reported."
                    ),
                )
            return

        # ---- analyze: explanation is attached to reproduced evidence only
        with repository.session(self.settings.db_path) as conn:
            transition.move(conn, run_id, "analyzing")

        analyses = self.provider.analyze(
            failures=confirmed,
            repo_root=self.settings.repo_root,
            output_tail=suite.output_tail,
            scope=run["scope"] or [],
        )
        analysis_by_key = {analysis.test_key: analysis for analysis in analyses}

        patch_ids, bug_ids = self._create_bugs_and_patches(
            run_id=run_id,
            confirmed=confirmed,
            analysis_by_key=analysis_by_key,
            first_cases=first_cases,
            second_cases=second_cases,
        )

        duration_ms = int((time.monotonic() - started) * 1000)
        with repository.session(self.settings.db_path) as conn:
            transition.move(
                conn,
                run_id,
                "completed",
                summary=self._summary(
                    suite,
                    confirmed,
                    duration_ms,
                    not_reproduced=not_reproduced,
                    patch_ids=patch_ids,
                ),
            )
            repository.add_memory(
                conn,
                project_id=project["id"],
                run_id=run_id,
                summary=(
                    f"Run {run_id[:8]} on {project['name']}: {len(confirmed)} confirmed bug(s) "
                    f"reproduced twice, {len(patch_ids)} patch proposal(s)."
                ),
            )

    # ------------------------------------------------------------------ helpers
    def _persist_attempt(
        self,
        *,
        run_id: str,
        suite: SuiteResult,
        attempt: int,
        run_dir: Path,
    ) -> dict[str, dict[str, Any]]:
        cases: dict[str, dict[str, Any]] = {}
        with repository.session(self.settings.db_path) as conn:
            for result in suite.results:
                case = repository.add_test_case(
                    conn,
                    run_id=run_id,
                    test_key=result.test_key,
                    name=result.name,
                    status=result.status,
                    duration_ms=result.duration_ms,
                    failure_message=result.failure_message,
                    attempt=attempt,
                )
                cases[result.test_key] = case
                for path in result.evidence:
                    if path.is_file():
                        artifacts.record_file(
                            conn,
                            run_id=run_id,
                            path=path,
                            label=f"attempt {attempt}: {result.test_key} / {path.name}",
                            test_case_id=case["id"],
                        )
            output_path = run_dir / "pytest-output.txt"
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(suite.output_tail, encoding="utf-8")
            artifacts.record_file(
                conn,
                run_id=run_id,
                path=output_path,
                label=f"attempt {attempt}: pytest output",
            )
        return cases

    def _create_bugs_and_patches(
        self,
        *,
        run_id: str,
        confirmed: list[TestResult],
        analysis_by_key: dict[str, Analysis],
        first_cases: dict[str, dict[str, Any]],
        second_cases: dict[str, dict[str, Any]],
    ) -> tuple[list[str], list[str]]:
        patch_ids: list[str] = []
        bug_ids: list[str] = []
        with repository.session(self.settings.db_path) as conn:
            existing_artifacts = repository.list_artifacts(conn, run_id)
            for result in confirmed:
                case = first_cases.get(result.test_key)
                analysis = analysis_by_key.get(result.test_key)
                if analysis is None:
                    analysis = Analysis(
                        test_key=result.test_key,
                        title=f"{result.test_key} failed",
                        severity="medium",
                        summary=result.failure_message or "assertion failed",
                        root_cause="Reproduced failure without an explanation.",
                        reproduction_steps=[],
                    )
                bug = repository.create_bug(
                    conn,
                    run_id=run_id,
                    test_case_id=case["id"] if case else None,
                    title=analysis.title,
                    severity=analysis.severity,
                    description=analysis.summary,
                    root_cause=analysis.root_cause,
                    reproduction_steps=analysis.reproduction_steps,
                )
                bug_ids.append(bug["id"])

                related_case_ids = {
                    item["id"]
                    for item in (first_cases.get(result.test_key), second_cases.get(result.test_key))
                    if item
                }
                artifact_ids = [
                    artifact["id"]
                    for artifact in existing_artifacts
                    if artifact.get("test_case_id") in related_case_ids
                ]
                if artifact_ids:
                    repository.attach_artifacts_to_bug(conn, artifact_ids, bug["id"])

                if analysis.patch_diff:
                    patch = repository.create_patch(
                        conn,
                        bug_id=bug["id"],
                        diff=analysis.patch_diff,
                        summary=analysis.patch_summary,
                        source=analysis.source,
                    )
                    patch_ids.append(patch["id"])
        return patch_ids, bug_ids

    def _complete_clean(
        self, *, run_id: str, project_id: str, suite: SuiteResult, started: float
    ) -> None:
        duration_ms = int((time.monotonic() - started) * 1000)
        with repository.session(self.settings.db_path) as conn:
            Transition(self.settings).move(
                conn, run_id, "completed", summary=self._summary(suite, [], duration_ms)
            )
            repository.add_memory(
                conn,
                project_id=project_id,
                run_id=run_id,
                summary=f"Run {run_id[:8]}: all selected tests passed, no bugs reported.",
            )

    def _summary(
        self,
        suite: SuiteResult,
        confirmed: list[TestResult],
        duration_ms: int,
        *,
        not_reproduced: list[str] | None = None,
        patch_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        passed = sum(1 for result in suite.results if result.status == "passed")
        failed = sum(1 for result in suite.results if result.status in {"failed", "error"})
        not_run = sum(1 for result in suite.results if result.status == "not_run")
        return {
            "tests_total": len(suite.results),
            "passed": passed,
            "failed": failed,
            "not_run": not_run,
            "confirmed_bugs": len(confirmed),
            "not_reproduced": not_reproduced or [],
            "patch_ids": patch_ids or [],
            "duration_ms": duration_ms,
            "provider": self.provider.name,
        }


class PatchVerifier:
    """Apply a proposed patch in isolation, then prove it with the same tests."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._lock = threading.Lock()

    def verify(self, patch_id: str) -> dict[str, Any]:
        with repository.session(self.settings.db_path) as conn:
            patch = repository.get_patch(conn, patch_id)
            if patch is None:
                raise LookupError("patch not found")
            bug = repository.get_bug(conn, patch["bug_id"])
            if bug is None:
                raise LookupError("bug not found")
            run = repository.get_run(conn, bug["run_id"])
            if run is None:
                raise LookupError("run not found")
            project = repository.get_project(conn, run["project_id"])
            if project is None:
                raise LookupError("project not found")
            test_case = repository.get_test(conn, bug["test_case_id"]) if bug["test_case_id"] else None

        target = validate_target(project["base_url"], self.settings)
        if not target.is_demo:
            raise UnsafeTargetError(
                "patch verification is only available for the bundled demo target: the "
                "proposed change has to be applied to a checkout of this repository"
            )

        validate_patch(patch["diff"])

        failing_key = test_case["test_key"] if test_case else None
        test_keys = list(dict.fromkeys([*([failing_key] if failing_key else []), *REGRESSION_TESTS]))

        # Keep the checkout outside the repository: git apply resolves relative
        # paths against the repository root when cwd is inside it, which would
        # patch the wrong files. A system-temp checkout is also fully disposable.
        sandbox = Path(tempfile.mkdtemp(prefix=f"bughunter-verify-{patch_id[:8]}-"))
        workspace = sandbox / "checkout"
        worktree_created = False
        server = None
        evidence_dir = self.settings.artifact_dir / run["id"] / f"verification-{patch_id[:8]}"
        revision = git_revision(self.settings.repo_root)

        try:
            add = subprocess.run(
                ["git", "worktree", "add", "--detach", str(workspace), "HEAD"],
                cwd=str(self.settings.repo_root),
                capture_output=True,
                text=True,
                timeout=60,
            )
            if add.returncode == 0:
                worktree_created = True
            else:
                shutil.copytree(
                    self.settings.repo_root,
                    workspace,
                    ignore=shutil.ignore_patterns("data", ".git", "__pycache__", "node_modules", ".venv"),
                )

            # git on Windows mangles LF patches piped through stdin; applying a
            # patch file keeps the diff byte-exact.
            patch_file = sandbox / "proposed.diff"
            patch_file.write_text(patch["diff"], encoding="utf-8", newline="\n")
            apply = subprocess.run(
                ["git", "apply", "--whitespace=nowarn", str(patch_file)],
                cwd=str(workspace),
                capture_output=True,
                text=True,
                timeout=60,
            )
            if apply.returncode != 0:
                return self._finish(
                    patch_id=patch_id,
                    run_id=run["id"],
                    status="error",
                    message="patch did not apply to the tested revision",
                    output=(apply.stderr or apply.stdout or "")[-4000:],
                    tests=[],
                    revision=revision,
                )

            demo_dir = workspace / "demo-store"
            port = free_port()
            server = start_demo_server(
                demo_dir,
                port,
                self.settings.repo_root / "data" / "logs" / f"verify-{patch_id[:8]}.log",
            )
            if not wait_for_health(server.base_url, timeout=20):
                return self._finish(
                    patch_id=patch_id,
                    run_id=run["id"],
                    status="error",
                    message="patched demo store did not start",
                    output="health check timed out",
                    tests=[],
                    revision=revision,
                )

            suite = run_tests(
                test_keys=test_keys,
                base_url=server.base_url,
                evidence_dir=evidence_dir,
                repo_root=workspace,
                timeout_seconds=min(self.settings.default_run_timeout_seconds, 300),
            )
            with repository.session(self.settings.db_path) as conn:
                for path in evidence_dir.glob("*"):
                    if path.is_file():
                        artifacts.record_file(
                            conn,
                            run_id=run["id"],
                            path=path,
                            label=f"verification {patch_id[:8]}: {path.name}",
                        )

            all_passed = bool(suite.results) and all(
                result.status == "passed" for result in suite.results
            )
            status = "verified" if all_passed else "failed"
            message = (
                "patched checkout passes the failing test and the regression suite"
                if all_passed
                else "verification tests did not all pass on the patched checkout"
            )
            return self._finish(
                patch_id=patch_id,
                run_id=run["id"],
                status=status,
                message=message,
                output=suite.output_tail,
                tests=suite.results,
                revision=revision,
            )
        finally:
            stop_server(server)
            if worktree_created:
                subprocess.run(
                    ["git", "worktree", "remove", "--force", str(workspace)],
                    cwd=str(self.settings.repo_root),
                    capture_output=True,
                    text=True,
                )
            shutil.rmtree(sandbox, ignore_errors=True)

    def _finish(
        self,
        *,
        patch_id: str,
        run_id: str,
        status: str,
        message: str,
        output: str,
        tests: list[TestResult],
        revision: str | None,
    ) -> dict[str, Any]:
        verification_status = {"verified": "verified", "failed": "failed", "error": "error"}[status]
        patch_status = {
            "verified": "verified",
            "failed": "verification_failed",
            "error": "proposed",
        }[status]
        test_rows = [
            {
                "test_key": result.test_key,
                "name": result.name,
                "status": result.status,
                "duration_ms": result.duration_ms,
                "failure_message": result.failure_message,
            }
            for result in tests
        ]
        with repository.session(self.settings.db_path) as conn:
            repository.update_patch(
                conn,
                patch_id,
                verification_status=verification_status,
                status=patch_status,
                verification_output=output[-6000:],
                verification_tests=test_rows,
                revision=revision,
                verified_at=repository.utc_now() if status == "verified" else None,
            )
        return {
            "patch_id": patch_id,
            "verification_status": verification_status,
            "all_passed": status == "verified",
            "tests": [
                {
                    "test_key": result.test_key,
                    "name": result.name,
                    "status": result.status,
                    "duration_ms": result.duration_ms,
                    "failure_message": result.failure_message,
                }
                for result in tests
            ],
            "revision": revision,
            "output_tail": output[-4000:],
            "message": message,
        }
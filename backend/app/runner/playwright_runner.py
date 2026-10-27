"""Run the Playwright suite and turn JUnit output into structured results."""
from __future__ import annotations

import os
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from ..catalog import test_by_key

OUTPUT_TAIL_CHARS = 4000
MESSAGE_LIMIT = 6000


@dataclass
class TestResult:
    test_key: str
    name: str
    status: str
    duration_ms: int = 0
    failure_message: str | None = None
    evidence: list[Path] = field(default_factory=list)


@dataclass
class SuiteResult:
    results: list[TestResult]
    output_tail: str
    timed_out: bool
    duration_ms: int

    @property
    def all_passed(self) -> bool:
        return bool(self.results) and all(result.status == "passed" for result in self.results)

    @property
    def failed_keys(self) -> list[str]:
        return [result.test_key for result in self.results if result.status in {"failed", "error"}]


def _evidence_for(evidence_dir: Path, function_name: str) -> list[Path]:
    if not evidence_dir.exists():
        return []
    return sorted(
        path
        for path in evidence_dir.glob(f"{function_name}.*")
        if path.is_file() and path.suffix != ".py"
    )


def _parse_junit(xml_path: Path) -> dict[str, tuple[str, int, str | None]]:
    parsed: dict[str, tuple[str, int, str | None]] = {}
    if not xml_path.exists():
        return parsed
    try:
        root = ET.parse(xml_path).getroot()
    except ET.ParseError:
        return parsed

    for case in root.iter("testcase"):
        name = case.get("name") or ""
        duration_ms = int(float(case.get("time") or 0) * 1000)
        status = "passed"
        message: str | None = None
        for child in case:
            if child.tag in {"failure", "error"}:
                status = "failed" if child.tag == "failure" else "error"
                message = (child.get("message") or child.text or "").strip()[:MESSAGE_LIMIT]
                break
            if child.tag == "skipped":
                status = "skipped"
                message = (child.get("message") or "").strip()[:MESSAGE_LIMIT] or None
                break
        parsed[name] = (status, duration_ms, message)
    return parsed


def run_tests(
    *,
    test_keys: list[str],
    base_url: str,
    evidence_dir: Path,
    repo_root: Path,
    timeout_seconds: int,
) -> SuiteResult:
    specs = [spec for spec in (test_by_key(key) for key in test_keys) if spec is not None]
    if not specs:
        return SuiteResult(results=[], output_tail="no tests selected", timed_out=False, duration_ms=0)

    evidence_dir.mkdir(parents=True, exist_ok=True)
    xml_path = evidence_dir / "junit.xml"
    expression = " or ".join(spec.function for spec in specs)
    # Specs live in more than one file now (demo journeys and the generic probe pack).
    suite_files = sorted({spec.file for spec in specs})

    env = os.environ.copy()
    env.update(
        {
            "BASE_URL": base_url,
            "EVIDENCE_DIR": str(evidence_dir),
            "HEADLESS": env.get("HEADLESS", "1"),
            "PYTHONIOENCODING": "utf-8",
        }
    )

    command = [
        sys.executable,
        "-m",
        "pytest",
        *suite_files,
        "-q",
        "-p",
        "no:cacheprovider",
        "-k",
        expression,
        f"--junitxml={xml_path}",
        "-o",
        "junit_family=xunit1",
    ]

    started = time.monotonic()
    timed_out = False
    returncode: int | None = None
    try:
        completed = subprocess.run(
            command,
            cwd=str(repo_root),
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
        )
        returncode = completed.returncode
        output = (completed.stdout or "") + (completed.stderr or "")
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        stdout = exc.stdout.decode("utf-8", "replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = exc.stderr.decode("utf-8", "replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        output = f"Test suite timed out after {timeout_seconds}s\n{stdout}{stderr}"
    except OSError as exc:
        output = f"failed to start pytest: {exc}"
    duration_ms = int((time.monotonic() - started) * 1000)

    parsed = _parse_junit(xml_path)
    if not parsed:
        output = (
            output
            + f"\n[runner] pytest exited with code {returncode}; "
            + f"junit written: {xml_path.exists()}; command: {' '.join(command)}"
        )
    results: list[TestResult] = []
    for spec in specs:
        status, case_duration, message = parsed.get(
            spec.function, ("not_run", 0, "test did not execute")
        )
        if timed_out:
            status, message = "not_run", "test did not complete before the run timeout"
        results.append(
            TestResult(
                test_key=spec.key,
                name=spec.name,
                status=status,
                duration_ms=case_duration,
                failure_message=message,
                evidence=_evidence_for(evidence_dir, spec.function),
            )
        )

    return SuiteResult(
        results=results,
        output_tail=output[-OUTPUT_TAIL_CHARS:],
        timed_out=timed_out,
        duration_ms=duration_ms,
    )
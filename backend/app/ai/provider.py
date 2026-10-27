"""Planner and analyst adapters.

Two rules shape this module:

1. An AI explanation is not evidence. The provider only explains failures that
   the runner already observed; it never creates a bug on its own.
2. A model never gets secrets or cookies, and its plan is clamped to the
   catalog, so a bad completion cannot widen the blast radius of a run.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol

import httpx
from pydantic import BaseModel, ConfigDict, Field

from ..catalog import (
    REPRODUCTION_STEPS,
    TESTS,
    TestSpec,
    build_demo_fix,
    test_by_key,
    tests_for_scope,
)
from ..config import Settings
from ..runner.playwright_runner import TestResult
from ..security import UnsafeTargetError, validate_patch

Severity = Literal["critical", "high", "medium", "low", "info"]


@dataclass
class Plan:
    objective: str
    scope: list[str]
    tests: list[dict[str, Any]]
    limits: dict[str, Any]
    source: str
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "objective": self.objective,
            "scope": self.scope,
            "tests": self.tests,
            "limits": self.limits,
            "source": self.source,
            "notes": self.notes,
        }


@dataclass
class Analysis:
    test_key: str
    title: str
    severity: Severity
    summary: str
    root_cause: str
    reproduction_steps: list[str]
    patch_diff: str | None = None
    patch_summary: str = ""
    source: str = "rule-based"

    def to_dict(self) -> dict[str, Any]:
        return {
            "test_key": self.test_key,
            "title": self.title,
            "severity": self.severity,
            "summary": self.summary,
            "root_cause": self.root_cause,
            "reproduction_steps": self.reproduction_steps,
            "patch_diff": self.patch_diff,
            "patch_summary": self.patch_summary,
            "source": self.source,
        }


class ModelBug(BaseModel):
    model_config = ConfigDict(extra="ignore")

    test_key: str
    title: str = Field(min_length=6, max_length=160)
    severity: Severity = "medium"
    root_cause: str = Field(min_length=10)
    reproduction_steps: list[str] = Field(default_factory=list)
    patch_diff: str | None = None
    patch_summary: str = ""


class ModelResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    bugs: list[ModelBug] = Field(default_factory=list)


class QAProvider(Protocol):
    name: str

    def create_plan(self, *, scope: list[str], mode: str, project_name: str, max_seconds: int) -> Plan: ...

    def analyze(
        self, *, failures: list[TestResult], repo_root: Path, output_tail: str, scope: list[str]
    ) -> list[Analysis]: ...


def trim_failure_message(message: str, limit: int = 600) -> str:
    """Keep the human-readable assertion line, not the whole locator call log."""
    for marker in ("\nCall log:", "\nAria snapshot:", "\nassert ", "\nE   "):
        message = message.split(marker)[0]
    message = message.strip()
    return message if len(message) <= limit else message[:limit].rstrip() + "…"


DEFAULT_TITLES = {
    "checkout_discount_total": "SAVE10 discount is shown but not removed from the charged total",
    "checkout_healthy_path": "Checkout total is wrong without a promo code",
    "login_valid_credentials": "Valid demo credentials fail to sign in",
    "cart_badge_updates": "Cart badge does not reflect added items",
}


class DeterministicProvider:
    """Rule-based planner and analyst used by default and as the LLM fallback."""

    name = "deterministic"

    def create_plan(
        self, *, scope: list[str], mode: str, project_name: str, max_seconds: int
    ) -> Plan:
        specs = tests_for_scope(scope)
        return Plan(
            objective=(
                f"Verify {', '.join(scope)} flows on {project_name} in '{mode}' mode, then "
                "reproduce every failure before reporting it."
            ),
            scope=list(scope),
            tests=[
                {
                    "key": spec.key,
                    "name": spec.name,
                    "scope": spec.scope,
                    "description": spec.description,
                }
                for spec in specs
            ],
            limits={
                "max_duration_seconds": max_seconds,
                "browser": "chromium",
                "headless": True,
                "max_tests": len(specs),
                "targets": 1,
            },
            source=self.name,
            notes="Bounded by the in-repo test catalog; no free-form test generation.",
        )

    def analyze(
        self, *, failures: list[TestResult], repo_root: Path, output_tail: str, scope: list[str]
    ) -> list[Analysis]:
        demo_fix = build_demo_fix(repo_root) if "checkout" in scope else None
        analyses: list[Analysis] = []
        for failure in failures:
            spec = test_by_key(failure.test_key)
            severity: Severity = (spec.severity_hint if spec else "medium")  # type: ignore[assignment]
            steps = list(REPRODUCTION_STEPS.get(failure.test_key, []))
            message = failure.failure_message or "the test failed without a captured message"
            if not steps:
                steps = [
                    f"Run browser test {failure.test_key} against the demo store.",
                    "Observe the failing assertion recorded in the run evidence.",
                ]

            patch_diff = None
            patch_summary = ""
            root_cause = ""
            if failure.test_key == "checkout_discount_total" and demo_fix is not None:
                root_cause = demo_fix.root_cause
                patch_diff = demo_fix.diff
                patch_summary = demo_fix.summary
            elif spec is not None and spec.scope == "probe":
                first_line = trim_failure_message(message, limit=220)
                root_cause = (
                    "The generic site probe observed this on the live page: "
                    f"{first_line} The screenshot, console log and trace captured during "
                    "this check are attached as evidence; no repository patch is proposed "
                    "for a target we do not control."
                )
            elif failure.test_key == "checkout_healthy_path":
                root_cause = (
                    "The no-promo checkout path failed, which means pricing changed for carts "
                    "without a discount. Inspect computeOrderTotals() before proposing a patch."
                )
            else:
                root_cause = (
                    "The browser assertion failed on this revision. The captured screenshot, "
                    "console log and assertion message are the evidence to investigate."
                )

            analyses.append(
                Analysis(
                    test_key=failure.test_key,
                    title=(
                        spec.name
                        if spec is not None and spec.scope == "probe"
                        else DEFAULT_TITLES.get(failure.test_key, f"{failure.test_key} failed")
                    ),
                    severity=severity,
                    summary=trim_failure_message(message),
                    root_cause=root_cause,
                    reproduction_steps=steps,
                    patch_diff=patch_diff,
                    patch_summary=patch_summary,
                    source=self.name,
                )
            )
        return analyses


class OpenAICompatibleProvider:
    """Adapter for any OpenAI-compatible chat completions endpoint.

    Falls back to the deterministic provider on transport errors or invalid
    completions, so a model outage never breaks a run.
    """

    name = "openai-compatible"

    def __init__(self, settings: Settings, fallback: DeterministicProvider) -> None:
        self._settings = settings
        self._fallback = fallback

    def create_plan(
        self, *, scope: list[str], mode: str, project_name: str, max_seconds: int
    ) -> Plan:
        plan = self._fallback.create_plan(
            scope=scope, mode=mode, project_name=project_name, max_seconds=max_seconds
        )
        plan.source = f"{self.name}+catalog"
        plan.notes = "Model requested; plan still clamped to the curated test catalog."
        return plan

    def _chat(self, payload: dict[str, Any]) -> dict[str, Any]:
        headers = {"Content-Type": "application/json"}
        if self._settings.ai_api_key:
            headers["Authorization"] = f"Bearer {self._settings.ai_api_key}"
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                f"{self._settings.ai_base_url}/chat/completions", headers=headers, json=payload
            )
            response.raise_for_status()
            return response.json()

    def analyze(
        self, *, failures: list[TestResult], repo_root: Path, output_tail: str, scope: list[str]
    ) -> list[Analysis]:
        fallback = self._fallback.analyze(
            failures=failures, repo_root=repo_root, output_tail=output_tail, scope=scope
        )
        if not failures:
            return fallback

        catalog_view = [
            {
                "test_key": failure.test_key,
                "test_name": failure.name,
                "status": failure.status,
                "assertion_message": (failure.failure_message or "")[:1500],
            }
            for failure in failures
        ]
        prompt = (
            "You are a QA analyst. Explain only the observed failures below. Do not invent "
            "bugs, do not claim a fix is verified, and return JSON shaped as "
            '{"bugs":[{"test_key","title","severity","root_cause","reproduction_steps",'
            '"patch_diff","patch_summary"}]}. Severity is one of critical, high, medium, low. '
            "patch_diff must be a unified diff inside demo-store/, backend/, tests/, frontend/ "
            "or docs/, or an empty string.\n\n"
            f"Failures:\n{json.dumps(catalog_view, indent=2)}\n\n"
            f"Runner output tail:\n{output_tail[-1500:]}"
        )
        try:
            payload = self._chat(
                {
                    "model": self._settings.ai_model,
                    "temperature": 0,
                    "messages": [
                        {"role": "system", "content": "Return only valid JSON."},
                        {"role": "user", "content": prompt},
                    ],
                }
            )
            content = payload["choices"][0]["message"]["content"]
            parsed = ModelResponse.model_validate_json(content)
        except Exception:
            return fallback

        by_key = {analysis.test_key: analysis for analysis in fallback}
        merged: list[Analysis] = []
        for bug in parsed.bugs:
            base = by_key.get(bug.test_key)
            if base is None:
                continue
            patch_diff = base.patch_diff
            patch_summary = base.patch_summary
            if bug.patch_diff:
                try:
                    validate_patch(bug.patch_diff)
                except UnsafeTargetError:
                    patch_diff = base.patch_diff
                else:
                    patch_diff = bug.patch_diff
                    patch_summary = bug.patch_summary or base.patch_summary
            merged.append(
                Analysis(
                    test_key=base.test_key,
                    title=bug.title,
                    severity=bug.severity,
                    summary=base.summary,
                    root_cause=bug.root_cause,
                    reproduction_steps=bug.reproduction_steps or base.reproduction_steps,
                    patch_diff=patch_diff,
                    patch_summary=patch_summary,
                    source=self.name,
                )
            )

        covered = {analysis.test_key for analysis in merged}
        merged.extend(analysis for analysis in fallback if analysis.test_key not in covered)
        return merged


def build_provider(settings: Settings) -> QAProvider:
    deterministic = DeterministicProvider()
    if settings.ai_enabled:
        return OpenAICompatibleProvider(settings, deterministic)
    return deterministic


def describe_tests(keys: list[str]) -> list[TestSpec]:
    return [spec for spec in (test_by_key(key) for key in keys) if spec is not None]


def catalog_keys() -> list[str]:
    return sorted(TESTS)
"""Typed request/response contracts. Pydantic validates everything crossing the API."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

RunStatus = Literal[
    "queued",
    "planning",
    "running",
    "reproducing",
    "analyzing",
    "patching",
    "verifying",
    "completed",
    "failed",
    "cancelled",
    "timed_out",
    "inconclusive",
]

TestCaseStatus = Literal["passed", "failed", "error", "skipped", "not_run"]
Severity = Literal["critical", "high", "medium", "low", "info"]
PatchStatus = Literal["proposed", "verified", "verification_failed", "rejected"]
VerificationStatus = Literal["unverified", "verified", "failed", "error"]


class ProjectCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=2, max_length=80)
    base_url: str = Field(min_length=8, max_length=300)
    description: str = Field(default="", max_length=500)

    @field_validator("base_url")
    @classmethod
    def _strip_trailing_slash(cls, value: str) -> str:
        return value.strip().rstrip("/")


class ProjectOut(BaseModel):
    id: str
    name: str
    base_url: str
    description: str
    created_at: str
    target_kind: str | None = None


class RunCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str = Field(min_length=1, max_length=64)
    scope: list[str] = Field(default_factory=lambda: ["login", "checkout"], min_length=1)
    mode: Literal["reproduce", "fix"] = "reproduce"
    max_duration_seconds: int = Field(default=120, ge=10, le=600)

    @field_validator("scope")
    @classmethod
    def _dedupe_scope(cls, value: list[str]) -> list[str]:
        unique = list(dict.fromkeys(scope.strip().lower() for scope in value))
        if not unique:
            raise ValueError("scope must contain at least one area")
        return unique


class RunOut(BaseModel):
    id: str
    project_id: str
    project_name: str | None = None
    status: RunStatus
    mode: str
    scope: list[str]
    plan: dict | None = None
    summary: dict | None = None
    error_kind: str | None = None
    error_message: str | None = None
    target_revision: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    created_at: str


class TestCaseOut(BaseModel):
    id: str
    run_id: str
    test_key: str
    name: str
    status: TestCaseStatus
    duration_ms: int
    failure_message: str | None = None
    attempt: int
    created_at: str


class BugOut(BaseModel):
    id: str
    run_id: str
    test_case_id: str | None = None
    title: str
    severity: Severity
    description: str
    root_cause: str
    reproduction_steps: list[str]
    status: str
    created_at: str
    evidence: list["ArtifactOut"] = Field(default_factory=list)
    patches: list["PatchOut"] = Field(default_factory=list)


class ArtifactOut(BaseModel):
    id: str
    run_id: str
    test_case_id: str | None = None
    bug_id: str | None = None
    type: str
    label: str
    storage_path: str
    sha256: str
    size_bytes: int
    created_at: str
    download_url: str


class PatchCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    diff: str = Field(min_length=10, max_length=100_000)
    summary: str = Field(default="", max_length=500)


class VerificationTestOut(BaseModel):
    test_key: str
    name: str
    status: TestCaseStatus
    duration_ms: int = 0
    failure_message: str | None = None


class PatchOut(BaseModel):
    id: str
    bug_id: str
    summary: str
    diff: str
    source: str
    status: PatchStatus
    verification_status: VerificationStatus
    verification_output: str | None = None
    verification_tests: list[VerificationTestOut] | None = None
    revision: str | None = None
    created_at: str
    verified_at: str | None = None


class VerifyOut(BaseModel):
    patch_id: str
    verification_status: VerificationStatus
    all_passed: bool
    tests: list[VerificationTestOut]
    revision: str | None = None
    output_tail: str = ""
    message: str


class HealthOut(BaseModel):
    status: str
    version: str
    ai_provider: str
    demo_target: str


BugOut.model_rebuild()
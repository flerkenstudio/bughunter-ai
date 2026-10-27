"""Runtime configuration, read once from the environment."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _split_csv(value: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in value.split(",") if part.strip())


@dataclass(frozen=True)
class Settings:
    repo_root: Path = REPO_ROOT
    db_path: Path = field(default_factory=lambda: REPO_ROOT / "data" / "bughunter.db")
    artifact_dir: Path = field(default_factory=lambda: REPO_ROOT / "data" / "artifacts")
    demo_dir: Path = field(default_factory=lambda: REPO_ROOT / "demo-store")
    demo_port: int = 8090
    allowed_ports: tuple[int, ...] = ()
    allowed_hosts: tuple[str, ...] = ()
    allow_external_targets: bool = True
    allow_private_targets: bool = False
    require_demo_target: bool = True
    default_run_timeout_seconds: int = 120
    max_run_timeout_seconds: int = 600
    ai_base_url: str = ""
    ai_api_key: str = ""
    ai_model: str = ""

    @classmethod
    def from_env(cls) -> "Settings":
        ports = _split_csv(os.environ.get("BUGHUNTER_ALLOWED_PORTS", ""))
        return cls(
            db_path=Path(os.environ.get("BUGHUNTER_DB", REPO_ROOT / "data" / "bughunter.db")),
            artifact_dir=Path(
                os.environ.get("BUGHUNTER_ARTIFACT_DIR", REPO_ROOT / "data" / "artifacts")
            ),
            demo_dir=Path(os.environ.get("BUGHUNTER_DEMO_DIR", REPO_ROOT / "demo-store")),
            demo_port=int(os.environ.get("BUGHUNTER_DEMO_PORT", "8090")),
            allowed_ports=tuple(int(port) for port in ports),
            allowed_hosts=tuple(
                host.lower() for host in _split_csv(os.environ.get("BUGHUNTER_ALLOWED_HOSTS", ""))
            ),
            allow_external_targets=os.environ.get("BUGHUNTER_ALLOW_EXTERNAL_TARGETS", "1") != "0",
            allow_private_targets=os.environ.get("BUGHUNTER_ALLOW_PRIVATE_TARGETS", "0") == "1",
            require_demo_target=os.environ.get("BUGHUNTER_REQUIRE_DEMO_TARGET", "1") != "0",
            default_run_timeout_seconds=int(os.environ.get("BUGHUNTER_RUN_TIMEOUT", "120")),
            max_run_timeout_seconds=int(os.environ.get("BUGHUNTER_MAX_RUN_TIMEOUT", "600")),
            ai_base_url=os.environ.get("BUGHUNTER_AI_BASE_URL", "").rstrip("/"),
            ai_api_key=os.environ.get("BUGHUNTER_AI_API_KEY", ""),
            ai_model=os.environ.get("BUGHUNTER_AI_MODEL", ""),
        )

    @property
    def ai_enabled(self) -> bool:
        return bool(self.ai_base_url and self.ai_model)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings.from_env()
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    settings.artifact_dir.mkdir(parents=True, exist_ok=True)
    return settings
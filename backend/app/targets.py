"""Lifecycle management for the local demo target."""
from __future__ import annotations

import socket
import subprocess
import sys
import threading
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from .config import Settings
from .security import DEMO_TARGET_MARKER

_START_LOCK = threading.Lock()
_SERVERS: dict[str, "RunningServer"] = {}


@dataclass
class RunningServer:
    base_url: str
    port: int
    directory: Path
    process: subprocess.Popen


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def health_status(base_url: str, timeout: float = 1.0) -> str | None:
    try:
        with urllib.request.urlopen(f"{base_url.rstrip('/')}/health", timeout=timeout) as response:
            if response.status != 200:
                return None
            return response.headers.get("X-Demo-Target")
    except Exception:
        return None


def wait_for_health(base_url: str, timeout: float = 20.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if health_status(base_url) == DEMO_TARGET_MARKER:
            return True
        time.sleep(0.15)
    return False


def _popen_kwargs() -> dict:
    kwargs: dict = {
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "stdin": subprocess.DEVNULL,
    }
    if sys.platform == "win32":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return kwargs


def start_demo_server(directory: Path, port: int, log_path: Path | None = None) -> RunningServer:
    server_script = directory / "server.py"
    if not server_script.exists():
        raise FileNotFoundError(f"demo server not found at {server_script}")

    stdout = subprocess.DEVNULL
    log_handle = None
    if log_path is not None:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_handle = log_path.open("w", encoding="utf-8")
        stdout = log_handle

    kwargs = _popen_kwargs()
    kwargs["stdout"] = stdout
    kwargs["stderr"] = subprocess.STDOUT if log_handle else subprocess.DEVNULL

    process = subprocess.Popen(
        [sys.executable, str(server_script), "--dir", str(directory), "--port", str(port)],
        cwd=str(directory),
        **kwargs,
    )
    base_url = f"http://127.0.0.1:{port}"
    if log_handle is not None:
        process._bughunter_log = log_handle  # type: ignore[attr-defined]
    if not wait_for_health(base_url):
        process.terminate()
        raise RuntimeError(f"demo server on port {port} did not become healthy")
    return RunningServer(base_url=base_url, port=port, directory=directory, process=process)


def start_managed_server(directory: Path, port: int, log_path: Path | None = None) -> RunningServer:
    """Start a demo server and register it so ``stop_all`` reaps it on shutdown."""
    with _START_LOCK:
        base_url = f"http://127.0.0.1:{port}"
        existing = _SERVERS.get(base_url)
        if existing and existing.process.poll() is None:
            return existing
        server = start_demo_server(directory, port, log_path)
        _SERVERS[base_url] = server
        return server


def ensure_project_target(base_url: str, settings: Settings) -> RunningServer | None:
    """Reuse a healthy demo store, otherwise start one for the configured port."""
    with _START_LOCK:
        marker = health_status(base_url)
        if marker == DEMO_TARGET_MARKER:
            return None
        if base_url in _SERVERS:
            server = _SERVERS[base_url]
            if server.process.poll() is None:
                return server

        port = settings.demo_port
        log_path = settings.repo_root / "data" / "logs" / f"demo-{port}.log"
        server = start_demo_server(settings.demo_dir, port, log_path)
        _SERVERS[base_url] = server
        return server


def stop_server(server: RunningServer | None) -> None:
    if server is None:
        return
    process = server.process
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
    log_handle = getattr(process, "_bughunter_log", None)
    if log_handle is not None:
        try:
            log_handle.close()
        except Exception:
            pass


def stop_all() -> None:
    with _START_LOCK:
        for server in list(_SERVERS.values()):
            stop_server(server)
        _SERVERS.clear()
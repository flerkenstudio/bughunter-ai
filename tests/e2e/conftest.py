"""Browser test harness.

The harness starts its own demo-store instance unless BASE_URL is supplied, so a
verification run can point the same tests at an isolated patched checkout, and a
probe run can point them at any registered target.
Every test writes a screenshot and a browser console log into EVIDENCE_DIR.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

REPO_ROOT = Path(__file__).resolve().parents[2]
DEMO_DIR = REPO_ROOT / "demo-store"

MAX_RECORDED_EVENTS = 200


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_health(url: str, timeout: float = 20.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url + "/health", timeout=1.0) as response:
                if response.status == 200:
                    return
        except Exception:
            time.sleep(0.15)
    raise RuntimeError(f"demo store did not become healthy at {url}")


@pytest.fixture(scope="session")
def base_url():
    supplied = os.environ.get("BASE_URL")
    if supplied:
        yield supplied.rstrip("/")
        return

    port = _free_port()
    url = f"http://127.0.0.1:{port}"
    proc = subprocess.Popen(
        [sys.executable, str(DEMO_DIR / "server.py"), "--dir", str(DEMO_DIR), "--port", str(port)],
        cwd=str(REPO_ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        _wait_for_health(url)
        yield url
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


@pytest.fixture(scope="session")
def playwright_browser():
    headless = os.environ.get("HEADLESS", "1") != "0"
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless)
        yield browser
        browser.close()


@pytest.fixture(scope="session")
def evidence_dir() -> Path:
    directory = Path(os.environ.get("EVIDENCE_DIR", str(REPO_ROOT / "data" / "evidence")))
    directory.mkdir(parents=True, exist_ok=True)
    return directory


@pytest.fixture
def browser_events() -> dict[str, list]:
    """Everything the browser saw, so a test can assert on it directly."""
    return {
        "console": [],  # {"type", "text"}
        "pageerrors": [],  # str
        "responses": [],  # {"url", "status", "resource_type"}
        "requestfailures": [],  # {"url", "failure"}
    }


def _record(events: dict[str, list], bucket: str, item: dict) -> None:
    if len(events[bucket]) < MAX_RECORDED_EVENTS:
        events[bucket].append(item)


@pytest.fixture
def page(request, playwright_browser, evidence_dir, browser_events):
    test_name = request.node.name
    context = playwright_browser.new_context(viewport={"width": 1280, "height": 900})
    context.tracing.start(screenshots=True, snapshots=True)
    page = context.new_page()
    page.set_default_timeout(15_000)

    page.on(
        "console",
        lambda message: _record(
            browser_events, "console", {"type": message.type, "text": message.text}
        ),
    )
    page.on("pageerror", lambda error: _record(browser_events, "pageerrors", {"text": str(error)}))
    page.on(
        "response",
        lambda response: _record(
            browser_events,
            "responses",
            {
                "url": response.url,
                "status": response.status,
                "resource_type": response.request.resource_type,
            },
        ),
    )
    page.on(
        "requestfailed",
        lambda failed: _record(
            browser_events,
            "requestfailures",
            {"url": failed.url, "failure": (failed.failure or "unknown")},
        ),
    )

    yield page

    try:
        if not page.is_closed():
            page.screenshot(path=str(evidence_dir / f"{test_name}.png"), full_page=True)
    except Exception:
        pass

    trace_path = evidence_dir / f"{test_name}.trace.zip"
    try:
        context.tracing.stop(path=str(trace_path))
    except Exception:
        pass

    log_payload = {
        "test": test_name,
        "url": page.url if not page.is_closed() else None,
        "console": browser_events["console"],
        "pageerrors": browser_events["pageerrors"],
        "responses": browser_events["responses"][-80:],
        "requestfailures": browser_events["requestfailures"],
    }
    (evidence_dir / f"{test_name}.console.json").write_text(
        json.dumps(log_payload, indent=2), encoding="utf-8"
    )
    context.close()
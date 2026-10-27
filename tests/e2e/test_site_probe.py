"""Generic site probe: systematic checks that work against any URL.

No demo-store selectors, no seeded knowledge. Each test navigates the registered
target once and asserts one property, so a failure produces focused evidence
(screenshot, console log, trace) and a precise message.
"""
from __future__ import annotations

from urllib.parse import urljoin, urlparse

from playwright.sync_api import Page

NAVIGATION_TIMEOUT_MS = 45_000
SETTLE_MS = 1_200
MAX_CHECKED_LINKS = 10
MOBILE_VIEWPORT = {"width": 390, "height": 844}
OVERFLOW_TOLERANCE_PX = 8

# Browsers request this on their own; a missing favicon is not a page defect.
IGNORED_REQUEST_SUFFIXES = ("/favicon.ico",)


def open_target(page: Page, base_url: str):
    page.set_default_navigation_timeout(NAVIGATION_TIMEOUT_MS)
    response = page.goto(base_url, wait_until="domcontentloaded")
    page.wait_for_timeout(SETTLE_MS)
    return response


def _ignored(url: str) -> bool:
    path = urlparse(url).path.lower()
    return any(path.endswith(suffix) for suffix in IGNORED_REQUEST_SUFFIXES)


def test_probe_page_loads(page: Page, base_url: str):
    """The document must respond below 400 and render content."""
    response = open_target(page, base_url)
    assert response is not None, f"no HTTP response for {base_url}"
    assert response.status < 400, (
        f"target returned HTTP {response.status} for {base_url}"
    )
    body = page.content()
    assert len(body.strip()) > 0, f"target returned an empty document at {base_url}"
    title = (page.title() or "").strip()
    assert title or "<body" in body, f"document at {base_url} produced no usable markup"


def test_probe_no_console_errors(page: Page, base_url: str, browser_events: dict):
    """Uncaught JavaScript errors are application defects, not noise."""
    open_target(page, base_url)
    page.wait_for_timeout(SETTLE_MS)

    errors = [item["text"] for item in browser_events["console"] if item["type"] == "error"]
    errors.extend(item["text"] for item in browser_events["pageerrors"])
    assert not errors, "console errors on load: " + " | ".join(errors[:3])


def test_probe_no_failed_requests(page: Page, base_url: str, browser_events: dict):
    """Subresources and API calls must not fail with 4xx or 5xx."""
    open_target(page, base_url)
    try:
        page.wait_for_load_state("networkidle", timeout=15_000)
    except Exception:
        pass  # busy pages never go idle; the responses captured so far still count

    failures = [
        f"{item['status']} {item['url']}"
        for item in browser_events["responses"]
        if item["status"] >= 400 and not _ignored(item["url"])
    ]
    failures.extend(
        f"failed {item['url']} ({item['failure']})"
        for item in browser_events["requestfailures"]
        if not _ignored(item["url"])
    )
    assert not failures, "failing requests: " + " | ".join(sorted(set(failures))[:5])


def test_probe_document_metadata(page: Page, base_url: str):
    """Title and meta description are required for search and accessibility."""
    open_target(page, base_url)

    title = (page.title() or "").strip()
    description = page.evaluate(
        "() => (document.querySelector('meta[name=\"description\"]')?.content || '').trim()"
    )
    assert title, f"document at {base_url} has no <title>"
    assert description, f"document at {base_url} has no meta description"


def test_probe_images_load(page: Page, base_url: str):
    """Every image must resolve to a real resource."""
    open_target(page, base_url)
    try:
        page.wait_for_load_state("load", timeout=10_000)
    except Exception:
        pass

    broken = page.evaluate(
        """() => Array.from(document.images)
            .filter((img) => img.complete && img.naturalWidth === 0)
            .map((img) => img.currentSrc || img.src)"""
    )
    assert not broken, "broken images: " + " | ".join(broken[:5])


def test_probe_links_respond(page: Page, base_url: str):
    """Internal links must not be dead."""
    open_target(page, base_url)

    origin = urlparse(base_url)
    hrefs = page.evaluate(
        """() => Array.from(document.querySelectorAll('a[href]')).map((a) => a.href)"""
    )
    targets: list[str] = []
    for href in hrefs:
        parsed = urlparse(href)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            continue
        if parsed.netloc != origin.netloc:
            continue
        clean = href.split("#")[0]
        if not clean or clean.rstrip("/") == base_url.rstrip("/"):
            continue
        if clean not in targets:
            targets.append(clean)
        if len(targets) >= MAX_CHECKED_LINKS:
            break

    if not targets:
        # A single-page site with no same-origin links has nothing to check here.
        return
    checked = 0
    broken: list[str] = []
    for url in targets:
        try:
            response = page.request.get(url, timeout=10_000, max_redirects=5)
        except Exception as exc:  # network-level failure is a broken link too
            broken.append(f"{url} ({exc.__class__.__name__})")
            continue
        checked += 1
        if response.status >= 400:
            broken.append(f"{response.status} {url}")
    assert not broken, f"broken internal links ({checked} checked): " + " | ".join(broken[:5])


def test_probe_form_controls_labelled(page: Page, base_url: str):
    """Accessible names are required for form controls."""
    open_target(page, base_url)

    unlabelled = page.evaluate(
        """() => {
            const selector = 'input, select, textarea';
            const skip = new Set(['hidden', 'submit', 'button', 'reset', 'image']);
            return Array.from(document.querySelectorAll(selector))
                .filter((el) => !skip.has((el.type || '').toLowerCase()))
                .filter((el) => !(
                    (el.id && document.querySelector(`label[for="${el.id}"]`)) ||
                    el.closest('label') ||
                    el.getAttribute('aria-label') ||
                    el.getAttribute('aria-labelledby') ||
                    el.getAttribute('title') ||
                    el.getAttribute('placeholder')
                ))
                .map((el) => `${el.tagName.toLowerCase()}[name=${el.name || '?'}] type=${el.type || '?'}`);
        }"""
    )
    assert not unlabelled, "unlabelled form controls: " + " | ".join(unlabelled[:5])


def test_probe_mobile_layout(page: Page, base_url: str):
    """A phone viewport must not produce horizontal overflow."""
    page.set_viewport_size(MOBILE_VIEWPORT)
    open_target(page, base_url)

    measurements = page.evaluate(
        """() => ({
            scrollWidth: document.documentElement.scrollWidth,
            innerWidth: window.innerWidth,
        })"""
    )
    overflow = measurements["scrollWidth"] - measurements["innerWidth"]
    assert overflow <= OVERFLOW_TOLERANCE_PX, (
        f"horizontal overflow of {overflow}px at 390px viewport "
        f"(scrollWidth {measurements['scrollWidth']} vs viewport {measurements['innerWidth']})"
    )


def _same_origin(base_url: str, href: str) -> bool:
    """Kept for readability in traces when debugging link checks."""
    return urlparse(urljoin(base_url, href)).netloc == urlparse(base_url).netloc
"""The bounded test catalog and demo-specific analysis knowledge.

Everything here is deliberately explicit: an AI plan may only select tests from
this catalog, which keeps runs reproducible and scoped.
"""
from __future__ import annotations

import difflib
from dataclasses import asdict, dataclass
from pathlib import Path


SCOPES: tuple[str, ...] = ("probe", "login", "checkout", "cart")

DEMO_FILE = "tests/e2e/test_store.py"
PROBE_FILE = "tests/e2e/test_site_probe.py"


@dataclass(frozen=True)
class TestSpec:
    key: str
    function: str
    file: str
    name: str
    scope: str
    description: str
    severity_hint: str

    def to_dict(self) -> dict:
        return asdict(self)


TESTS: dict[str, TestSpec] = {
    spec.key: spec
    for spec in [
        TestSpec(
            key="checkout_discount_total",
            file=DEMO_FILE,
            function="test_checkout_discount_total",
            name="Checkout applies the SAVE10 discount to the charged total",
            scope="checkout",
            description=(
                "Adds Pulse Headphones and Nimbus Bottle, applies SAVE10, and asserts the "
                "summary and confirmation charge $104.49."
            ),
            severity_hint="high",
        ),
        TestSpec(
            key="checkout_healthy_path",
            file=DEMO_FILE,
            function="test_checkout_without_promo_stays_correct",
            name="Checkout without a promo code charges the correct total",
            scope="checkout",
            description=(
                "Buys one Trail Pack with no promo code and asserts 64.00 + 6.99 shipping "
                "+ 5.12 tax = $76.11."
            ),
            severity_hint="medium",
        ),
        TestSpec(
            key="login_valid_credentials",
            file=DEMO_FILE,
            function="test_login_with_valid_credentials",
            name="Sign in with the demo account succeeds",
            scope="login",
            description=(
                "Signs in as demo@nimbus.dev and asserts the account panel shows the email "
                "and no error message."
            ),
            severity_hint="high",
        ),
        TestSpec(
            key="cart_badge_updates",
            file=DEMO_FILE,
            function="test_cart_badge_updates",
            name="Adding a product updates the cart badge",
            scope="cart",
            description="Adds the Aurora Mug and asserts the header cart count changes from 0 to 1.",
            severity_hint="medium",
        ),
        TestSpec(
            key="probe_page_loads",
            file=PROBE_FILE,
            function="test_probe_page_loads",
            name="Target page loads without an HTTP error",
            scope="probe",
            description=(
                "Navigates to the target URL and asserts the document responds below 400 "
                "instead of failing, timing out or erroring."
            ),
            severity_hint="critical",
        ),
        TestSpec(
            key="probe_no_console_errors",
            file=PROBE_FILE,
            function="test_probe_no_console_errors",
            name="Page produces no uncaught JavaScript errors",
            scope="probe",
            description=(
                "Loads the page and asserts the console reports no errors and no uncaught "
                "exceptions."
            ),
            severity_hint="high",
        ),
        TestSpec(
            key="probe_no_failed_requests",
            file=PROBE_FILE,
            function="test_probe_no_failed_requests",
            name="No subresource or API request fails with 4xx or 5xx",
            scope="probe",
            description=(
                "Watches network activity during load and fails on any 4xx or 5xx response, "
                "listing every failing URL."
            ),
            severity_hint="high",
        ),
        TestSpec(
            key="probe_document_metadata",
            file=PROBE_FILE,
            function="test_probe_document_metadata",
            name="Title and meta description are present",
            scope="probe",
            description=(
                "Asserts the document has a non-empty title and a meta description for search "
                "engines and assistive technology."
            ),
            severity_hint="medium",
        ),
        TestSpec(
            key="probe_images_load",
            file=PROBE_FILE,
            function="test_probe_images_load",
            name="Images load with real dimensions",
            scope="probe",
            description=(
                "Checks every image element resolves with a natural width above zero and lists "
                "the broken sources."
            ),
            severity_hint="medium",
        ),
        TestSpec(
            key="probe_links_respond",
            file=PROBE_FILE,
            function="test_probe_links_respond",
            name="Internal links respond without client or server errors",
            scope="probe",
            description="Follows up to ten same-origin links and fails on any response of 400 or above.",
            severity_hint="medium",
        ),
        TestSpec(
            key="probe_form_controls_labelled",
            file=PROBE_FILE,
            function="test_probe_form_controls_labelled",
            name="Form controls are labelled",
            scope="probe",
            description=(
                "Finds inputs, selects and textareas without an associated label, aria-label or "
                "placeholder."
            ),
            severity_hint="low",
        ),
        TestSpec(
            key="probe_mobile_layout",
            file=PROBE_FILE,
            function="test_probe_mobile_layout",
            name="Layout does not overflow a phone viewport",
            scope="probe",
            description=(
                "Reloads at 390x844 and asserts the document does not scroll horizontally "
                "beyond the viewport."
            ),
            severity_hint="low",
        ),
    ]
}

SCOPE_TESTS: dict[str, tuple[str, ...]] = {
    "probe": (
        "probe_page_loads",
        "probe_no_console_errors",
        "probe_no_failed_requests",
        "probe_document_metadata",
        "probe_images_load",
        "probe_links_respond",
        "probe_form_controls_labelled",
        "probe_mobile_layout",
    ),
    "login": ("login_valid_credentials",),
    "checkout": ("checkout_discount_total", "checkout_healthy_path"),
    "cart": ("cart_badge_updates",),
}

# Regression coverage run after a patch, even when the failing test is narrower.
REGRESSION_TESTS: tuple[str, ...] = (
    "checkout_healthy_path",
    "login_valid_credentials",
    "cart_badge_updates",
)


def tests_for_scope(scope: list[str]) -> list[TestSpec]:
    selected: list[TestSpec] = []
    for area in scope:
        for key in SCOPE_TESTS.get(area, ()):
            spec = TESTS.get(key)
            if spec and spec not in selected:
                selected.append(spec)
    return selected


def test_by_key(key: str) -> TestSpec | None:
    return TESTS.get(key)


BUGGY_LINE = "  const total = round2(subtotal + shipping + tax);"
FIXED_LINE = "  const total = round2(taxable + shipping + tax);"

ROOT_CAUSE_TOTAL = (
    "In demo-store/checkout.js, computeOrderTotals() subtracts the promo discount when "
    "computing taxable, but builds the final total from the undiscounted subtotal "
    "(total = subtotal + shipping + tax). The order summary renders a discount line, so "
    "the displayed discount is never actually removed from the amount charged: for a "
    "$107.50 cart with SAVE10 the UI charges $115.24 instead of $104.49."
)


@dataclass
class DemoFix:
    diff: str
    summary: str
    root_cause: str


def build_demo_fix(repo_root: Path) -> DemoFix | None:
    """Derive a one-line patch from the live checkout source.

    The patch is generated from the file that is actually on disk, so line numbers
    and context always match the revision under test.
    """
    path = repo_root / "demo-store" / "checkout.js"
    try:
        original = path.read_text(encoding="utf-8")
    except OSError:
        return None
    if BUGGY_LINE not in original:
        return None

    fixed = original.replace(BUGGY_LINE, FIXED_LINE, 1)
    diff = "".join(
        difflib.unified_diff(
            original.splitlines(keepends=True),
            fixed.splitlines(keepends=True),
            fromfile="a/demo-store/checkout.js",
            tofile="b/demo-store/checkout.js",
        )
    )
    return DemoFix(
        diff=diff,
        summary=(
            "Charge the discounted subtotal: build the order total from taxable "
            "instead of subtotal so the SAVE10 discount reaches the payment total."
        ),
        root_cause=ROOT_CAUSE_TOTAL,
    )


REPRODUCTION_STEPS: dict[str, list[str]] = {
    "checkout_discount_total": [
        "Open the demo store and add Pulse Headphones ($89.00) and Nimbus Bottle ($18.50).",
        "Go to checkout and enter promo code SAVE10, then apply it.",
        "The summary shows Discount -$10.75 and Shipping Free, but the Total reads $115.24.",
        "Expected total: $104.49 (96.75 taxable + 0.00 shipping + 7.74 tax).",
        "Place the order: the confirmation page charges the same inflated total.",
    ],
    "checkout_healthy_path": [
        "Add one Trail Pack ($64.00) and open checkout without a promo code.",
        "The summary should show 64.00 + 6.99 shipping + 5.12 tax = 76.11.",
    ],
    "login_valid_credentials": [
        "Open the account page and sign in with demo@nimbus.dev / demo1234.",
        "The account panel should appear with no error message.",
    ],
    "cart_badge_updates": [
        "Open the shop with a cart count of 0.",
        "Add the Aurora Mug and confirm the header badge reads 1.",
    ],
    "probe_page_loads": [
        "Open the target URL in Chromium and wait for the document response.",
        "Confirm the response status is below 400 and the page renders.",
        "The captured screenshot, console log and trace are the evidence for this check.",
    ],
    "probe_no_console_errors": [
        "Open the target URL and let every script run.",
        "Read the browser console for errors and uncaught exceptions.",
        "The console log artifact lists each message with its type.",
    ],
    "probe_no_failed_requests": [
        "Open the target URL and record every network response.",
        "List all responses with a 4xx or 5xx status.",
        "The failing URLs are reported in the assertion message.",
    ],
    "probe_document_metadata": [
        "Open the target URL and read the document head.",
        "Check the title is non-empty and a meta description is present.",
    ],
    "probe_images_load": [
        "Open the target URL and wait for images.",
        "Check every img element for a natural width above zero.",
        "Broken image sources are listed in the assertion message.",
    ],
    "probe_links_respond": [
        "Open the target URL and collect up to ten same-origin links.",
        "Request each link and record its status code.",
        "Links returning 400 or above are reported with their status.",
    ],
    "probe_form_controls_labelled": [
        "Open the target URL and enumerate form controls.",
        "Check each control for a label, aria-label, aria-labelledby, title or placeholder.",
        "Unlabelled controls are reported with their selector and name.",
    ],
    "probe_mobile_layout": [
        "Reload the target URL at a 390x844 phone viewport.",
        "Compare the document scroll width against the viewport width.",
        "A horizontal overflow wider than the viewport fails the check.",
    ],
}
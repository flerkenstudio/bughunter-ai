"""End-to-end journeys for the Nimbus Supply demo store.

These tests are the evidence source for BugHunter AI. Assertions state the
business rule, not the current implementation, so a correct patch turns the
failing test green and a wrong patch keeps it red.
"""
from playwright.sync_api import Page, expect


def _seed_cart(page: Page, base_url: str, skus: list[str]) -> None:
    page.goto(f"{base_url}/index.html")
    for sku in skus:
        page.get_by_test_id(f"add-{sku}").click()
    page.goto(f"{base_url}/checkout.html")


def test_checkout_discount_total(page: Page, base_url: str):
    """
    SAVE10 takes 10% off the subtotal, shipping is free above $75 after the
    discount, and 8% tax applies to the discounted subtotal:

        89.00 + 18.50 = 107.50 subtotal
        -10.75 discount  -> 96.75 taxable
        0.00 shipping (>= 75), 7.74 tax
        = 104.49 charged
    """
    _seed_cart(page, base_url, ["pulse-headphones", "nimbus-bottle"])

    page.get_by_test_id("promo-input").fill("SAVE10")
    page.get_by_test_id("apply-promo").click()

    expect(page.get_by_test_id("discount-row")).to_be_visible()
    expect(page.get_by_test_id("discount")).to_have_text("-$10.75")
    expect(page.get_by_test_id("shipping")).to_have_text("Free")
    expect(page.get_by_test_id("tax")).to_have_text("$7.74")
    expect(page.get_by_test_id("total")).to_have_text("$104.49")

    page.get_by_test_id("place-order").click()
    expect(page.get_by_test_id("order-total")).to_have_text("$104.49")


def test_checkout_without_promo_stays_correct(page: Page, base_url: str):
    """Healthy path: one Trail Pack, no promo. 64.00 + 6.99 shipping + 5.12 tax = 76.11."""
    _seed_cart(page, base_url, ["trail-pack"])

    expect(page.get_by_test_id("discount-row")).to_be_hidden()
    expect(page.get_by_test_id("subtotal")).to_have_text("$64.00")
    expect(page.get_by_test_id("shipping")).to_have_text("$6.99")
    expect(page.get_by_test_id("tax")).to_have_text("$5.12")
    expect(page.get_by_test_id("total")).to_have_text("$76.11")

    page.get_by_test_id("place-order").click()
    expect(page.get_by_test_id("order-total")).to_have_text("$76.11")


def test_login_with_valid_credentials(page: Page, base_url: str):
    page.goto(f"{base_url}/login.html")
    page.get_by_test_id("login-email").fill("demo@nimbus.dev")
    page.get_by_test_id("login-password").fill("demo1234")
    page.get_by_test_id("login-submit").click()

    expect(page.get_by_test_id("login-success")).to_be_visible()
    expect(page.get_by_test_id("account-email")).to_have_text("demo@nimbus.dev")
    expect(page.get_by_test_id("login-error")).to_be_hidden()


def test_cart_badge_updates(page: Page, base_url: str):
    page.goto(f"{base_url}/index.html")
    expect(page.get_by_test_id("cart-count")).to_have_text("0")

    page.get_by_test_id("add-aurora-mug").click()
    expect(page.get_by_test_id("cart-count")).to_have_text("1")
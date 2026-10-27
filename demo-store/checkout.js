/*
 * Checkout pricing for the Nimbus Supply demo store.
 *
 * Pricing rules (also documented in the storefront help panel):
 *   subtotal  = sum of line totals
 *   discount  = promo rate applied to subtotal (SAVE10 = 10%)
 *   taxable   = subtotal - discount
 *   shipping  = free when taxable >= 75, otherwise 6.99
 *   tax       = 8% of taxable, rounded to cents
 *   total     = taxable + shipping + tax
 */
const PROMO_CODES = { SAVE10: 0.1 };
const FREE_SHIPPING_THRESHOLD = 75;
const SHIPPING_FEE = 6.99;
const TAX_RATE = 0.08;
const PROMO_KEY = "nimbus.promo";

function round2(value) {
  return Math.round((value + Number.EPSILON) * 100) / 100;
}

function computeOrderTotals(lines, promoCode) {
  const subtotal = round2(lines.reduce((sum, line) => sum + line.lineTotal, 0));
  const rate = PROMO_CODES[promoCode] || 0;
  const discount = round2(subtotal * rate);
  const taxable = round2(subtotal - discount);
  const shipping = taxable >= FREE_SHIPPING_THRESHOLD ? 0 : SHIPPING_FEE;
  const tax = round2(taxable * TAX_RATE);
  const total = round2(subtotal + shipping + tax);

  return { subtotal, discount, taxable, shipping, tax, total, promoCode };
}

function setText(testId, value) {
  const node = document.querySelector(`[data-testid='${testId}']`);
  if (node) node.textContent = value;
}

function renderSummary(totals) {
  setText("subtotal", formatMoney(totals.subtotal));
  setText("shipping", totals.shipping === 0 ? "Free" : formatMoney(totals.shipping));
  setText("tax", formatMoney(totals.tax));
  setText("total", formatMoney(totals.total));

  const discountRow = document.querySelector("[data-testid='discount-row']");
  if (discountRow) {
    discountRow.hidden = totals.discount <= 0;
    setText("discount", "-" + formatMoney(totals.discount));
  }
}

function renderLines(lines) {
  const body = document.querySelector("[data-testid='cart-lines']");
  if (!body) return;
  body.innerHTML = "";
  lines.forEach((line) => {
    const row = document.createElement("div");
    row.className = "cart-line";
    row.dataset.sku = line.sku;
    row.innerHTML = `
      <span class="cart-line-name">${line.name}</span>
      <span class="cart-line-qty">x${line.qty}</span>
      <span class="cart-line-total">${formatMoney(line.lineTotal)}</span>
    `;
    body.appendChild(row);
  });
}

function currentPromo() {
  return sessionStorage.getItem(PROMO_KEY) || "";
}

function setPromoMessage(text, kind) {
  const node = document.querySelector("[data-testid='promo-message']");
  if (!node) return;
  node.textContent = text;
  node.dataset.kind = kind || "";
}

function initCheckout() {
  const lines = cartLines(readCart());
  const cartPanel = document.querySelector("[data-testid='checkout']");
  const emptyPanel = document.querySelector("[data-testid='empty-cart']");

  if (lines.length === 0) {
    if (cartPanel) cartPanel.hidden = true;
    if (emptyPanel) emptyPanel.hidden = false;
    return;
  }
  if (emptyPanel) emptyPanel.hidden = true;
  if (cartPanel) cartPanel.hidden = false;

  renderLines(lines);
  let promo = currentPromo();
  if (promo) {
    const input = document.querySelector("[data-testid='promo-input']");
    if (input) input.value = promo;
    setPromoMessage("SAVE10 applied: 10% off your subtotal.", "ok");
  }
  renderSummary(computeOrderTotals(lines, promo));

  const applyButton = document.querySelector("[data-testid='apply-promo']");
  if (applyButton) {
    applyButton.addEventListener("click", () => {
      const input = document.querySelector("[data-testid='promo-input']");
      const code = (input.value || "").trim().toUpperCase();
      if (!code) {
        sessionStorage.removeItem(PROMO_KEY);
        setPromoMessage("", "");
        renderSummary(computeOrderTotals(lines, ""));
        return;
      }
      if (!PROMO_CODES[code]) {
        setPromoMessage(`"${code}" is not a valid promo code.`, "error");
        return;
      }
      sessionStorage.setItem(PROMO_KEY, code);
      promo = code;
      setPromoMessage(`${code} applied: 10% off your subtotal.`, "ok");
      renderSummary(computeOrderTotals(lines, promo));
    });
  }

  const placeOrder = document.querySelector("[data-testid='place-order']");
  placeOrder.addEventListener("click", () => {
    const totals = computeOrderTotals(lines, currentPromo());
    localStorage.setItem(
      ORDER_KEY,
      JSON.stringify({
        reference: "NB-" + Date.now().toString().slice(-6),
        placedAt: new Date().toISOString(),
        lines,
        totals
      })
    );
    sessionStorage.removeItem(PROMO_KEY);
    writeCart({});
    window.location.href = "confirmation.html";
  });
}

document.addEventListener("DOMContentLoaded", initCheckout);
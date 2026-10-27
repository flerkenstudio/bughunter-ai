/*
 * Nimbus Supply demo storefront.
 *
 * This is the controlled target for BugHunter AI. It is intentionally small,
 * dependency-free and deterministic so a run can be reproduced byte-for-byte.
 */
const PRODUCTS = [
  { sku: "pulse-headphones", name: "Pulse Headphones", price: 89.0, blurb: "Closed-back wireless, 40h battery." },
  { sku: "nimbus-bottle", name: "Nimbus Bottle", price: 18.5, blurb: "Insulated steel, 750ml." },
  { sku: "trail-pack", name: "Trail Pack", price: 64.0, blurb: "22L daypack with laptop sleeve." },
  { sku: "aurora-mug", name: "Aurora Mug", price: 14.25, blurb: "Double-walled ceramic." }
];

const CART_KEY = "nimbus.cart";
const ORDER_KEY = "nimbus.lastOrder";

function readCart() {
  try {
    const raw = localStorage.getItem(CART_KEY);
    return raw ? JSON.parse(raw) : {};
  } catch (err) {
    return {};
  }
}

function writeCart(cart) {
  localStorage.setItem(CART_KEY, JSON.stringify(cart));
  updateCartBadge();
}

function addToCart(sku, qty) {
  const cart = readCart();
  cart[sku] = (cart[sku] || 0) + (qty || 1);
  writeCart(cart);
  return cart;
}

function cartLines(cart) {
  return Object.keys(cart)
    .map((sku) => {
      const product = PRODUCTS.find((p) => p.sku === sku);
      if (!product) return null;
      return { ...product, qty: cart[sku], lineTotal: product.price * cart[sku] };
    })
    .filter(Boolean);
}

function cartCount(cart) {
  return Object.values(cart).reduce((sum, qty) => sum + qty, 0);
}

function formatMoney(value) {
  return "$" + Number(value).toFixed(2);
}

function updateCartBadge() {
  const badge = document.querySelector("[data-testid='cart-count']");
  if (badge) badge.textContent = String(cartCount(readCart()));
}

document.addEventListener("DOMContentLoaded", () => {
  updateCartBadge();
  document.querySelectorAll("[data-add-to-cart]").forEach((button) => {
    button.addEventListener("click", () => {
      addToCart(button.dataset.addToCart, 1);
      button.textContent = "Added";
      button.classList.add("added");
      setTimeout(() => {
        button.textContent = "Add to cart";
        button.classList.remove("added");
      }, 900);
    });
  });
});
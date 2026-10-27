/* Demo-only credential check. Never use this pattern in a real application. */
const DEMO_ACCOUNT = { email: "demo@nimbus.dev", password: "demo1234" };

document.addEventListener("DOMContentLoaded", () => {
  const form = document.querySelector("[data-testid='login-form']");
  const errorBox = document.querySelector("[data-testid='login-error']");
  const successBox = document.querySelector("[data-testid='login-success']");

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const email = document.querySelector("[data-testid='login-email']").value.trim().toLowerCase();
    const password = document.querySelector("[data-testid='login-password']").value;

    if (email === DEMO_ACCOUNT.email && password === DEMO_ACCOUNT.password) {
      errorBox.hidden = true;
      successBox.hidden = false;
      document.querySelector("[data-testid='account-email']").textContent = email;
      form.hidden = true;
      return;
    }

    successBox.hidden = true;
    errorBox.textContent = "Incorrect email or password.";
    errorBox.hidden = false;
  });
});
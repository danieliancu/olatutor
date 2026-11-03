// "How it will work" step switcher. Without JavaScript, the steps simply stay readable as a list.
document.querySelectorAll("[data-steps]").forEach((root) => {
  const art = root.querySelector("[data-step-art]");
  const steps = root.querySelectorAll("[data-step]");
  steps.forEach((step) => {
    step.addEventListener("click", () => {
      art.dataset.state = step.dataset.step;
      steps.forEach((other) => {
        const active = other === step;
        other.classList.toggle("is-active", active);
        other.setAttribute("aria-pressed", String(active));
      });
    });
  });
});

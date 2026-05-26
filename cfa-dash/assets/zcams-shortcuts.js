/**
 * ZCAMS keyboard shortcuts (Alt + number jumps to workflow pages).
 */
(function () {
  const ROUTES = {
    "1": "/dashboard",
    "2": "/bls",
    "3": "/reviewed-bl",
    "4": "/invoices",
    "5": "/checkout",
  };

  document.addEventListener("keydown", function (event) {
    if (!event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) {
      return;
    }
    const route = ROUTES[event.key];
    if (!route) {
      return;
    }
    const onPublic = ["/login", "/onboarding", "/"].includes(window.location.pathname);
    if (onPublic) {
      return;
    }
    event.preventDefault();
    window.location.pathname = route;
  });

  document.addEventListener("keydown", function (event) {
    if (event.key !== "Escape") {
      return;
    }
    ["invoice-request-modal", "detach-zsad-modal"].forEach(function (modalId) {
      const modal = document.getElementById(modalId);
      if (!modal || modal.classList.contains("is-hidden")) {
        return;
      }
      const closeBtn = modal.querySelector(".modal-close");
      if (closeBtn) {
        closeBtn.click();
      }
    });
  });
})();

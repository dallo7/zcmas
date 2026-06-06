/**
 * ZCAMS modal keyboard helpers.
 */
(function () {
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

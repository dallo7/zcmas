(function () {
  function clearSessionNotices() {
    document.querySelectorAll(".notice").forEach(function (notice) {
      if (notice.parentNode) {
        notice.parentNode.removeChild(notice);
      }
    });
  }

  function boot() {
    if (window.location.search.indexOf("logout=1") !== -1) {
      clearSessionNotices();
    }

    document.addEventListener(
      "click",
      function (event) {
        const logoutLink = event.target.closest?.('a[href*="logout=1"]');
        if (logoutLink) {
          clearSessionNotices();
        }
      },
      true
    );

    window.addEventListener("pagehide", function () {
      if (window.location.search.indexOf("logout=1") !== -1) {
        clearSessionNotices();
      }
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();

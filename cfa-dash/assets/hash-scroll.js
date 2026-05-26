(function () {
  function scrollToHash() {
    if (!window.location.hash) {
      return;
    }
    var id = window.location.hash.slice(1);
    var target = document.getElementById(id);
    if (target) {
      window.setTimeout(function () {
        target.scrollIntoView({ block: "start", behavior: "smooth" });
      }, 80);
    }
  }

  function boot() {
    scrollToHash();
    window.addEventListener("hashchange", scrollToHash);

    var pageSlot = document.getElementById("page-slot");
    if (!pageSlot) {
      return;
    }
    new MutationObserver(scrollToHash).observe(pageSlot, { childList: true, subtree: true });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();

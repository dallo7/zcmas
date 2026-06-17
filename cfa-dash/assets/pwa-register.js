/* Register ZCAMS service worker for installable PWA shell. */
(function registerZcamsPwa() {
  if (!("serviceWorker" in navigator)) {
    return;
  }
  window.addEventListener("load", function onLoad() {
    navigator.serviceWorker.register("/sw.js", { scope: "/" }).catch(function noop() {});
  });
})();

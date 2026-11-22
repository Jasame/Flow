  /* ---------- boot ---------- */
  (async function boot() {
    if ('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js').catch(() => {});
    try { await refreshSession(); } catch (e) { /* offline guest */ }
    route();
    OUTBOX.flush();
  })();
})();

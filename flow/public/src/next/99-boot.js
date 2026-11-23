  /* ---------- boot ---------- */
  (async function boot() {
    wechatBar();
    if ('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js').catch(() => {});
    try { await refreshHome(); S.homeFresh = true; } catch (e) { /* offline: route() asks again and offers a retry */ }
    route();
    OUTBOX.flush();
  })();
})();

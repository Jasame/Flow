  /* ---------- boot ---------- */
  (async function boot() {
    wechatBar();
    if ('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js').catch(() => {});
    // The copy of the last 今日 kept on the phone (05-data.js): the page is drawn from it at once, then from the
    // server's answer, quietly, if anything changed. Offline, the copy stays on screen. The first visit waits.
    const snap = snapGet(), drawn = () => { SPLASH.done(); firstViewDrawn(); prefetchTabs(); keepTodayOffline(); };
    if (snap && snap.home && snap.home.session) {
      S.home = snap.home; S.user = snap.home.session.user || null; S.csrf = ''; DATA.fromSnap = true; S.homeFresh = true; setDueBadge();
      const drawnFor = location.hash;
      route().then(drawn);
      try { if (await refreshHome()) redrawQuietly(drawnFor); } catch (e) { DATA.ok(); }
      TIPS.load();  // 使用提示 this account put away, kept on the phone before a page needs them (08-tips.js)
    } else {
      try { await refreshHome(); S.homeFresh = true; } catch (e) { DATA.ok(); /* offline: route() asks again and offers a retry */ }
      TIPS.load();
      route().then(drawn);  // the opening time ends when the first page is drawn
    }
    OUTBOX.flush();
  })();
})();

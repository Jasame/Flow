  /* ---------- boot ---------- */
  // 从提醒邮件点进来 (r29): a mail's link carries ?from=remind&k=review|once|weekly. Counted per day and kind only
  // (/api/next/tap: no account, D2), then taken off the address so a link passed on or bookmarked does not carry it.
  function remindOpen() {
    const q = new URLSearchParams(location.search);
    if (q.get('from') !== 'remind') return;
    const keys = { review: 'remind-review', once: 'remind-once', weekly: 'remind-weekly' };  // flow_admin.TAP_LABEL
    const key = Object.prototype.hasOwnProperty.call(keys, q.get('k')) ? keys[q.get('k')] : 'remind-other';
    try { navigator.sendBeacon('/api/next/tap', JSON.stringify({ k: key })); } catch (x) { /* not counted */ }
    q.delete('from'); q.delete('k');
    const rest = q.toString();
    try { history.replaceState(null, '', location.pathname + (rest ? '?' + rest : '') + location.hash); } catch (x) { /* the address stays */ }
  }
  (async function boot() {
    remindOpen();
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

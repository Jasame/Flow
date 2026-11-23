  /* ---------- what this browser tells the site about the site itself (field_service.py) ---------- */
  // Page errors (a script that broke, a promise nobody caught, a picture or sound that did not load, a request that
  // failed, a sound the browser would not play) and, once per visit, how long until the first page was on screen and
  // where the time went. No account and no address go with them; each problem is sent once per visit, 20 at most.
  // The last few errors also go with a 问题反馈 report (ERRS).
  const FIELD = { q: [], seen: new Set(), sent: 0, firstView: null, openSent: false, t: 0 };
  const ERRS = [];
  function beacon(url, data) {
    const body = JSON.stringify(data);
    try { if (navigator.sendBeacon && navigator.sendBeacon(url, body)) return; } catch (e) { /* fall back to fetch */ }
    try { fetch(url, { method: 'POST', body, keepalive: true, credentials: 'same-origin', headers: { 'Content-Type': 'application/json' } }).catch(() => {}); } catch (e) { /* not counted */ }
  }
  function noteIssue(kind, message, source) {
    try {
      const page = location.hash.split('?')[0] || '#/', msg = String(message || '').slice(0, 200), src = String(source || '').slice(0, 120);
      if (kind === 'js' || kind === 'promise') { ERRS.push((msg + (src ? ' @ ' + src : '')).slice(0, 200)); if (ERRS.length > 5) ERRS.shift(); }
      const key = [kind, page, msg, src].join('|');
      if (!msg || FIELD.seen.has(key) || FIELD.sent + FIELD.q.length >= 20) return;
      FIELD.seen.add(key); FIELD.q.push({ kind, page, message: msg, source: src });
      clearTimeout(FIELD.t); FIELD.t = setTimeout(flushIssues, 5000);
    } catch (e) { /* the report must never break the page */ }
  }
  function flushIssues() {
    if (!FIELD.q.length) return;
    const items = FIELD.q.splice(0); FIELD.sent += items.length;
    beacon('/api/next/issues', { items, asset: ASSET, standalone: STANDALONE() });
  }
  // Script errors, and pictures, sounds and scripts that did not load: those do not bubble, hence the capture phase.
  addEventListener('error', e => {
    const t = e && e.target;
    if (t && t !== window && t.tagName) {
      const src = String(t.currentSrc || t.src || t.href || '').replace(location.origin, '').split('?')[0];
      if (src && !src.startsWith('blob:') && !src.startsWith('data:')) noteIssue('resource', `${t.tagName.toLowerCase()} 没加载出来：${src}`);
      return;
    }
    if (e && e.message) noteIssue('js', e.message, `${String(e.filename || '').split('/').pop().split('?')[0]}:${e.lineno || 0}`);
  }, true);
  addEventListener('unhandledrejection', e => { const r = e && e.reason; if (!(r && r.network)) noteIssue('promise', (r && r.message) || String(r)); });

  // Opening time: navigation timing (when the browser has it) and the moment the first page was drawn.
  function navTiming() {
    const n = performance.getEntriesByType && performance.getEntriesByType('navigation')[0];
    if (n) return n;
    const t = performance.timing; if (!t || !t.navigationStart) return null;  // older in-app browsers
    const o = {}; ['domainLookupStart', 'domainLookupEnd', 'connectStart', 'connectEnd', 'secureConnectionStart', 'requestStart', 'responseStart', 'responseEnd']
      .forEach(k => { o[k] = t[k] ? t[k] - t.navigationStart : 0; });
    return o;
  }
  function sendOpenTime() {
    if (FIELD.openSent) return; FIELD.openSent = true;
    try {
      const n = navTiming(); if (!n) return;
      const res = (performance.getEntriesByType && performance.getEntriesByType('resource')) || [];
      const first = re => res.filter(r => re.test(r.name)).sort((a, b) => a.startTime - b.startTime)[0];
      const home = first(/\/api\/next\/home/), js = first(/\/next\.js/), c = navigator.connection || {};
      const ms = x => (x == null || !isFinite(x) || x < 0 ? null : Math.round(x)), fv = FIELD.firstView;
      beacon('/api/next/opentime', {
        domain: location.host, first_view: ms(fv), waited: ms(performance.now()),
        dns: ms(n.domainLookupEnd - n.domainLookupStart), connect: ms(n.connectEnd - n.connectStart),
        tls: n.secureConnectionStart > 0 ? ms(n.connectEnd - n.secureConnectionStart) : null,
        ttfb: ms(n.responseStart - n.requestStart), html: ms(n.responseEnd - n.responseStart),
        scripts: js ? ms(js.responseEnd - n.responseEnd) : null, home_api: home ? ms(home.duration) : null,
        render: fv != null && home ? ms(fv - home.responseEnd) : null,
        repeat: !!(navigator.serviceWorker && navigator.serviceWorker.controller), standalone: STANDALONE(),
        net: c.effectiveType || '', tz: (Intl.DateTimeFormat().resolvedOptions().timeZone || '').slice(0, 40) });
    } catch (e) { /* not counted */ }
  }
  function firstViewDrawn() {
    if (FIELD.firstView != null) return;
    FIELD.firstView = performance.now();
    setTimeout(sendOpenTime, 1500);
  }
  // Leaving (or switching away): what is queued goes now; a visit that leaves before anything showed counts too.
  addEventListener('visibilitychange', () => { if (document.visibilityState === 'hidden') { flushIssues(); sendOpenTime(); } });
  addEventListener('pagehide', () => { flushIssues(); sendOpenTime(); });

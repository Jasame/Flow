  /* ---------- data: pages that show at once, preloading, one request per page at a time ---------- */
  // Three layers, so a page appears without waiting and the next one is often ready before it is tapped:
  // - In memory: GET answers are shared and kept two minutes (the site's lists of levels and goals a day), and a
  //   request in flight is shared too, so a page and a preload of it never fetch twice. Anything sent (a POST) may
  //   change them, so it empties this memory.
  // - On the phone (localStorage): the last 今日 and the last five materials, per account. The next visit draws the
  //   page from them at once while the fresh data loads, and draws it again, quietly, if anything changed. Signing
  //   out clears them; the session's CSRF token is never kept there (sending waits for the server's answer instead).
  // - Preloading: once the first page is on screen and the phone is idle, the data of the other tabs; when a finger
  //   touches a link, the data of the page it leads to. Nothing that changes data is preloaded (the review queue
  //   brings in today's new words, so it is fetched only on a touch of 复习). Not with Save-Data or on 2G, except on
  //   a touch: that page was asked for.
  const DATA = { mem: new Map(), ok: null, ready: null, fromSnap: false };
  DATA.ready = new Promise(ok => { DATA.ok = ok; });
  const KEEP_MS = [[/^\/api\/next\/meta$/, 864e5], [/./, 12e4]];
  const parseJSON = t => { try { return t ? JSON.parse(t) : {}; } catch (e) { return {}; } };
  function dataGet(path, quiet) {
    const now = Date.now(), e = DATA.mem.get(path);
    if (e && now - e.at < KEEP_MS.find(([re]) => re.test(path))[1]) return e.p.then(parseJSON);
    const p = request(path, undefined, quiet).then(x => x.t);
    DATA.mem.set(path, { at: now, p });
    p.catch(() => { const x = DATA.mem.get(path); if (x && x.p === p) DATA.mem.delete(path); });
    return p.then(parseJSON);
  }
  function dataForget() { for (const k of [...DATA.mem.keys()]) if (!/^\/api\/next\/meta$/.test(k)) DATA.mem.delete(k); }
  function prefetch(path) { if (path) dataGet(path, true).catch(() => {}); }
  const materialPath = id => '/api/next/material?id=' + encodeURIComponent(id) + (S.user ? '' : '&level=' + encodeURIComponent(level()));
  function libraryPath(f) {
    if (!f) { try { f = JSON.parse(sessionStorage.getItem('flow-next-lib') || 'null'); } catch (e) { f = null; } }
    f = f || { level: hasProfile() ? level() : '', theme: '', page: 1, featured: '1' };
    return `/api/next/library?level=${f.level}&theme=${f.theme}&page=${f.page}&featured=${f.featured}`;
  }

  // ---- the copy kept on the phone
  const SNAP = 'flow-snap';
  const snapOwner = () => (S.user ? 'u' + S.user.id : 'guest');
  function snapGet() { const s = load(SNAP); return s && s.v === 1 ? s : null; }
  function snapPut(fn) {
    try {
      const old = snapGet(), s = old && old.owner === snapOwner() ? old : { v: 1, owner: snapOwner(), mats: {} };
      fn(s); save(SNAP, s);
    } catch (e) { /* full or private mode: the next visit simply waits for the server */ }
  }
  function snapHome() {
    // S.home without the session's CSRF token (sending waits for the server's own answer)
    const h = JSON.parse(JSON.stringify(S.home || {}));
    if (h.session && h.session.user) delete h.session.user.csrf;
    snapPut(s => { s.home = h; s.at = Date.now(); });
  }
  function snapMaterial(path, m) {
    snapPut(s => {
      s.mats[path] = { at: Date.now(), m };
      Object.keys(s.mats).sort((a, b) => s.mats[b].at - s.mats[a].at).slice(5).forEach(k => delete s.mats[k]);
    });
  }
  function snapMaterialGet(path) { const s = snapGet(); return s && s.owner === snapOwner() && s.mats[path] ? s.mats[path].m : null; }
  function snapClear() { save(SNAP, null); DATA.mem.clear(); }

  // ---- preloading
  const idle = f => (window.requestIdleCallback ? requestIdleCallback(f, { timeout: 2500 }) : setTimeout(f, 900));
  function prefetchTabs() {
    if (PRELOAD.frugal()) return;
    idle(() => {
      if (S.user) { prefetch('/api/next/vocab'); prefetch('/api/next/cards?q=&page=1&f='); prefetch('/api/next/radar'); }
      if (!S.meta) prefetch('/api/next/meta');
      prefetch(libraryPath());
    });
  }
  // A link's page, and the data it will ask for first: fetched while the finger is still on the screen.
  const ROUTE_DATA = [
    [/^#\/m\/([^/?]+)/, m => [materialPath(decodeURIComponent(m[1]))]],
    [/^#\/cards\/?$/, () => (S.user ? ['/api/next/vocab', '/api/next/cards?q=&page=1&f='] : [])],
    [/^#\/review$/, () => (S.user ? ['/api/next/review'] : [])],
    [/^#\/library$/, () => [libraryPath()]],
    [/^#\/practice$/, () => (S.user ? ['/api/next/radar'] : [])],
    [/^#\/me$/, () => (S.meta ? [] : ['/api/next/meta'])],
    [/^#\/graph$/, () => ['/api/next/graph' + guestQuery(true)]],
    [/^#\/growth$/, () => (S.user ? ['/api/next/growth'] : [])],
    [/^#\/report$/, () => (S.user ? ['/api/next/report'] : [])],
    [/^#\/series\/([^/?]+)/, m => ['/api/next/series?id=' + encodeURIComponent(decodeURIComponent(m[1]))]],
  ];
  function prefetchFor(hash) {
    for (const [re, f] of ROUTE_DATA) { const m = hash.match(re); if (m) { f(m).forEach(prefetch); return; } }
  }
  addEventListener('pointerdown', e => {
    const a = e.target && e.target.closest && e.target.closest('a[href^="#/"]');
    if (a) prefetchFor(a.getAttribute('href'));
  }, { capture: true, passive: true });

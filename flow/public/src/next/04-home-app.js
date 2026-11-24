  /* ---------- 主屏 App (Safari 「添加到主屏幕」, r28): a way back, the keyboard, and the version after a long sleep ---------- */
  // Opened from the home screen there is no browser around the page: no back button, no swipe back, and the app may
  // stay in the background for days. html.home-app marks it (also the Android/desktop install, display-mode standalone).
  const HOME_APP = matchMedia('(display-mode: standalone)').matches || navigator.standalone === true;
  document.documentElement.classList.toggle('home-app', HOME_APP);

  // ---- 返回: in the top bar, in place of the logo, on every page but the four tabs and the first-visit page.
  // It goes to the page before when the app has one (the history kept here), else to the page's own tab (‹ 练习).
  const HIST = [location.hash || '#/'];
  const TAB_OF = { today: ['#/', '今日'], practice: ['#/practice', '练习'], cards: ['#/cards', '单词'], me: ['#/me', '我的'] };
  addEventListener('hashchange', () => {
    const h = location.hash || '#/';
    if (HIST.length > 1 && HIST[HIST.length - 2] === h) HIST.pop(); else if (HIST[HIST.length - 1] !== h) HIST.push(h);
    if (HIST.length > 50) HIST.splice(0, HIST.length - 50);
  });
  // Called by setNav (02-shell.js) on every page with the tab it belongs to.
  function homeBack(nav) {
    const btn = document.getElementById('backBtn'), brand = bar.querySelector('.brand');
    if (!btn) return;
    const h = location.hash.replace(/^#\/?/, '');
    const root = ['', 'practice', 'cards', 'me', 'welcome'].includes(h);
    const show = HOME_APP && !root;
    btn.hidden = !show; brand.hidden = show;
    if (!show) return;
    const tab = TAB_OF[nav] || TAB_OF.today, prev = HIST.length > 1;
    btn.querySelector('span').textContent = prev ? '返回' : tab[1];
    btn.setAttribute('aria-label', prev ? '返回上一页' : '返回' + tab[1]);
    btn.onclick = () => { if (HIST.length > 1) history.back(); else location.hash = tab[0]; };
  }

  // ---- 键盘: a field being typed in and its button stay above the keyboard. iOS lays fixed things (the bottom sheet)
  // against the whole screen and lets the keyboard cover them; visualViewport says how much of the screen is left.
  // --kb is the keyboard's height: the sheet stands on it, and the page gets that much room below to scroll into.
  if (window.visualViewport) {
    const vv = window.visualViewport, root = document.documentElement;
    const submitOf = el => {
      const s = el.dataset && el.dataset.submit;
      const named = s && document.querySelector(s);
      if (named) return named;
      if (el.form) { const b = el.form.querySelector('[type=submit], .btn.primary'); if (b) return b; }
      const box = el.closest('#sheetCard, form, section, .card, .stack') || el.parentElement;
      return [...box.querySelectorAll('button.primary, .btn.primary, button[type=submit]')].find(b => el.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING) || null;
    };
    const fit = () => {
      const kb = Math.max(0, Math.round(innerHeight - vv.height - vv.offsetTop));
      root.style.setProperty('--kb', kb + 'px');
      document.body.classList.toggle('kb-open', kb > 80);
      const el = document.activeElement;
      if (kb <= 80 || !el || !isTyping({ target: el })) return;
      const btn = submitOf(el), card = el.closest('#sheetCard');
      const r = el.getBoundingClientRect(), b = btn && btn.offsetParent !== null ? btn.getBoundingClientRect() : r;
      const top = vv.offsetTop + 8, bottom = vv.offsetTop + vv.height - 8;
      const over = Math.max(r.bottom, b.bottom) - bottom;
      const by = over > 0 ? Math.min(over, r.top - top) : r.top < top ? r.top - top : 0;  // never push the field's top out
      if (by) (card || window).scrollBy({ top: by, behavior: 'auto' });
    };
    let raf = 0;
    const later = () => { cancelAnimationFrame(raf); raf = requestAnimationFrame(fit); };
    vv.addEventListener('resize', later);
    vv.addEventListener('scroll', later);
    document.addEventListener('focusin', e => { if (isTyping(e)) setTimeout(fit, 320); });  // after iOS has moved things itself
  }

  // ---- 新版本: back in front (or when the service worker changes), ask the server which version it serves. A new one
  // is taken at once on a resting page (one of the four tabs, nothing being typed, no sheet, nothing playing); anywhere
  // else one line offers it, and it is taken on the next resting page. The new service worker (sw.js: skipWaiting,
  // claim) is given up to 4 s to take over first, so the reload gets the new page and files, not the cached ones.
  // A version tried once and still not running is only offered again, never reloaded into a loop.
  const MY_ASSET = ((document.querySelector('script[src*="/next.js"]') || {}).src || '').split('v=')[1] || '';
  let NEW_ASSET = '', checked = 0, swSwitched = false;
  async function checkVersion(force) {
    if (!MY_ASSET || MY_ASSET.startsWith('__') || (!force && Date.now() - checked < 30e3)) return;
    checked = Date.now();
    let v = null;
    try { v = await fetch('/api/version', { cache: 'no-store', credentials: 'same-origin' }).then(r => (r.ok ? r.json() : null)); } catch (e) { return; }
    if (!v || !v.asset || v.asset === MY_ASSET) return;
    NEW_ASSET = v.asset;
    try { const reg = navigator.serviceWorker && await navigator.serviceWorker.getRegistration(); if (reg) reg.update(); } catch (e) { /* no worker: the reload asks the server */ }
    updateWhenSafe();
  }
  function restingNow() {
    const h = location.hash.replace(/^#\/?/, '');
    return ['', 'practice', 'cards', 'me'].includes(h) && sheetEl.hidden && document.visibilityState === 'visible'
      && !isTyping({ target: document.activeElement }) && !document.body.classList.contains('playing');
  }
  function updateWhenSafe() {
    if (!NEW_ASSET) return;
    if (load('flow-update-tried') !== NEW_ASSET && restingNow()) { takeUpdate(); return; }
    updateBar();
  }
  async function takeUpdate() {
    save('flow-update-tried', NEW_ASSET);
    const sw = navigator.serviceWorker;
    // the new worker may have taken over already (then at once); otherwise wait for it, at most 4 s
    if (sw && sw.controller && !swSwitched) await new Promise(done => { sw.addEventListener('controllerchange', done, { once: true }); setTimeout(done, 4000); });
    location.reload();
  }
  function updateBar() {
    if (document.getElementById('updateBar') || load('flow-update-later') === NEW_ASSET + '|' + new Date().toDateString()) return;
    const box = document.createElement('div');
    box.className = 'update-bar'; box.id = 'updateBar'; box.setAttribute('role', 'status');
    box.innerHTML = '<button class="ub-go" type="button" data-tap="update-bar">有新版本，点一下更新</button><button class="ub-x" type="button" aria-label="今天先不更新">×</button>';
    document.body.appendChild(box);
    box.querySelector('.ub-go').onclick = e => { e.currentTarget.textContent = '正在更新…'; e.currentTarget.disabled = true; takeUpdate(); };
    box.querySelector('.ub-x').onclick = () => { save('flow-update-later', NEW_ASSET + '|' + new Date().toDateString()); box.remove(); };
  }
  // after a reload into the new version: said once
  if (MY_ASSET && load('flow-update-tried') === MY_ASSET) { save('flow-update-tried', null); setTimeout(() => toast('已更新到新版本'), 1200); }
  document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'visible') checkVersion(); });
  if (navigator.serviceWorker) navigator.serviceWorker.addEventListener('controllerchange', () => { swSwitched = true; checkVersion(true); });
  addEventListener('hashchange', () => setTimeout(updateWhenSafe, 300));  // a pending version is taken on the next resting page
  setTimeout(() => checkVersion(true), 4000);  // once after opening (the page itself may have come from the cache), off the first screen's way

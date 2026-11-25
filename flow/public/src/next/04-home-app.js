  /* ---------- 主屏 App (Safari 「添加到主屏幕」, r28): a way back, the keyboard, and the version after a long sleep ---------- */
  // Opened from the home screen there is no browser around the page: no back button, no swipe back, and the app may
  // stay in the background for days. html.home-app marks it (also the Android/desktop install, display-mode standalone).
  // The iOS app (语流 20, ios/: Flow in a WKWebView, its user agent ending in FlowiOS/<version>) has no browser around
  // the page either, but there navigator.standalone and display-mode are not standalone. It follows theme-color and the
  // keyboard itself (the web view ends at the keyboard), so the two iOS work-arounds below stay off in it.
  // The desktop app (语流 22: Windows and macOS, a native window around the site, its user agent ending in
  // FlowDesktop/<version> (Windows) or (macOS)) has no browser back either: 返回 is its way back (with ⌘[ / Alt+← in its
  // own menu). Any of Flow's apps also says so before the page's scripts: window.FlowApp ({platform: 'ios' | 'windows' |
  // 'macos' …}). The keyboard work-around is for iPhones and iPads only, so the desktop leaves it alone anyway.
  const IN_IOS_APP = /FlowiOS\//.test(navigator.userAgent);
  const IN_APP = /Flow(iOS|Android|Desktop)\//.test(navigator.userAgent) || !!window.FlowApp;  // as docs/native-bridge.md (#162) names them
  const HOME_APP = matchMedia('(display-mode: standalone)').matches || navigator.standalone === true || IN_APP;
  document.documentElement.classList.toggle('home-app', HOME_APP);

  // ---- 返回: in the top bar, in place of the logo, on every page but the four tabs and the first-visit page.
  // It goes to the page before when the app has one (the history kept here), else to the page's own tab (‹ 练习).
  const HIST = [location.hash || '#/'];
  const TAB_OF = { today: ['#/', '今日'], practice: ['#/practice', '练习'], cards: ['#/cards', '单词'], me: ['#/me', '我的'] };
  // The four tab pages; #/teach is a 老师账号's home (its first tab, 「班级」, #121), the same page as its #/.
  const TAB_PAGES = ['', 'practice', 'cards', 'me', 'teach'];
  // A page's tab as the tab bar shows it: a 老师账号's first tab says 班级, not 今日 (02-shell.js roleTabs)
  const tabOf = nav => {
    const a = document.querySelector(`.tabs [data-nav="${nav}"]`), t = TAB_OF[nav] || TAB_OF.today;
    return a ? [a.getAttribute('href') || t[0], ((a.querySelector('span') || {}).textContent || t[1]).trim()] : t;
  };
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
    const root = TAB_PAGES.includes(h) || h === 'welcome';
    const show = HOME_APP && !root;
    btn.hidden = !show; brand.hidden = show;
    if (!show) return;
    const tab = tabOf(TAB_OF[nav] ? nav : 'today'), prev = HIST.length > 1;
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
    // Client rects → the part of the screen in sight: before iOS 26 they are against the layout viewport, which the
    // visual one may have panned down by offsetTop; on iOS 26+ (27.2 in the simulator) they are against what is in
    // sight already, offsetTop says something else, and pageTop ≈ scrollY. scrollY − pageTop is right for both.
    const shift = () => scrollY - vv.pageTop;
    // the sticky top bar and the study steps under it: a field brought into sight must not end up under them
    const headLine = () => Math.max(0, ...[bar, document.querySelector('main .steps')].filter(x => x && x.offsetParent !== null && /sticky|fixed/.test(getComputedStyle(x).position))
      .map(x => x.getBoundingClientRect()).filter(r => r.top < 120).map(r => r.bottom + shift()));
    let kbSeen = 0;  // the keyboard's height the last time it was up (iPhone portrait: about half the screen)
    // Flow's apps make the page itself shorter for the keyboard (Android's WebView, the iOS app's web view that ends at
    // the keyboard; 语流 21, 20): nothing is covered, but a field near the end and its button (登录, 发送) are now below the
    // page's own end. The page's height without a keyboard, per width, tells that: shorter while typing = a keyboard.
    let tallest = innerHeight, wide = innerWidth;
    const fit = () => {
      const kb = Math.max(0, Math.round(innerHeight - vv.height - vv.offsetTop));
      root.style.setProperty('--kb', kb + 'px');  // where fixed things (the sheet) stand
      // Up or not from the screen part covered: on iOS 26+ innerHeight shrinks with the keyboard, so kb above is 0 there.
      const covered = Math.round(root.clientHeight - vv.height), up = covered > 80;
      if (up) kbSeen = covered;
      const el = document.activeElement, typing = !!el && isTyping({ target: el });
      if (innerWidth !== wide) { wide = innerWidth; tallest = innerHeight; }  // turned: its own height again
      if (!typing) tallest = Math.max(tallest, innerHeight);
      const shrunk = typing && tallest - innerHeight > 80;
      document.body.classList.toggle('kb-open', up || shrunk);
      if (!(up || shrunk) || !typing) return;
      const btn = submitOf(el), card = el.closest('#sheetCard'), s = shift();
      const r = el.getBoundingClientRect(), b = btn && btn.offsetParent !== null ? btn.getBoundingClientRect() : r;
      const top = (card ? 0 : headLine()) + 8, bottom = vv.height - 8;
      const fieldTop = r.top + s, over = Math.max(r.bottom, b.bottom) + s - bottom;
      const by = over > 0 ? Math.min(over, fieldTop - top) : fieldTop < top ? fieldTop - top : 0;  // never push the field's top out
      if (by) (card || window).scrollBy({ top: by, behavior: 'auto' });
    };
    // On iPhones and iPads the page moves first, at the tap: when a field near the end of the page is to come into
    // sight, iOS 26+ moves the whole web view without telling the page (scrollY stays, the client rects do not
    // change) and stops at the keyboard itself, so its ∧ ∨ ✓ bar covers the field and its button (对话, 导入文章 —
    // tools/ios_sim_check.py, 2026-11-25). With room below the page and the field and its button already where the
    // keyboard will leave them in sight, iOS has nothing to move; fit() above then corrects what is left.
    const IOS_KB = !IN_IOS_APP && (/iPhone|iPad|iPod/.test(navigator.userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1));
    const makeRoom = el => {
      if (!IOS_KB || el.closest('#sheetCard') || root.clientHeight - vv.height > 80) return;  // a sheet stands on the keyboard; up already: fit()
      document.body.classList.add('kb-room');
      const btn = submitOf(el), s = shift(), r = el.getBoundingClientRect(), b = btn && btn.offsetParent !== null ? btn.getBoundingClientRect() : r;
      const kbH = kbSeen || Math.round(root.clientHeight * (innerWidth > innerHeight ? 0.62 : 0.5));
      const fieldTop = r.top + s, by = Math.min(Math.max(r.bottom, b.bottom) + s - (root.clientHeight - kbH - 12), fieldTop - headLine() - 12);
      if (by > 4 || fieldTop < headLine()) window.scrollBy({ top: by, behavior: 'auto' });
    };
    let raf = 0;
    const later = () => { cancelAnimationFrame(raf); raf = requestAnimationFrame(fit); };
    vv.addEventListener('resize', later);
    vv.addEventListener('scroll', later);
    document.addEventListener('focusin', e => { if (!isTyping(e)) return; makeRoom(e.target); setTimeout(fit, 320); });  // fit after iOS has moved things itself
    document.addEventListener('focusout', () => setTimeout(() => { if (!isTyping({ target: document.activeElement })) document.body.classList.remove('kb-room'); }, 0));
  }

  // ---- 新版本: back in front (or when the service worker changes), ask the server which version it serves. A new one
  // is taken at once on a resting page (one of the four tabs, nothing typed, no sheet, nothing playing or recording); anywhere
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
  // Something playing or recording (the narration, a clip or the server/browser voice in 01-audio-offline.js, the
  // microphone in 70-learner.js, any <audio> on the page; read only): a reload would cut it off. The 今日 mini player,
  // 好句 and shadowing can all be going on a tab page.
  function audioBusy() {
    try {
      if (!NAR.audio.paused || !CLIP.audio.paused || MIC.busy()) return true;
      if (window.speechSynthesis && (speechSynthesis.speaking || speechSynthesis.pending)) return true;
    } catch (e) { return true; }
    return [...document.querySelectorAll('audio, video')].some(m => !m.paused);
  }
  function restingNow() {
    const h = location.hash.replace(/^#\/?/, '');
    return TAB_PAGES.includes(h) && sheetEl.hidden && document.visibilityState === 'visible'
      && !isTyping({ target: document.activeElement }) && !document.body.classList.contains('playing') && !audioBusy();
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

  // ---- 深色/浅色: an iPhone paints the strip under the status bar from the page when it loads and keeps it. A home-screen
  // app left open while the phone turns dark (or light) keeps a light strip on the dark page — a white band — until the
  // page loads again; going home and back does not change it, nor does a new theme-color (tools/ios_sim_check.py,
  // 2026-11-25). So a change of scheme is taken like a new version: a reload at once on a resting page, else on the next.
  if (navigator.standalone === true && window.matchMedia) {
    let schemeStale = false;
    const takeScheme = () => { if (schemeStale && restingNow()) { schemeStale = false; location.reload(); } };
    const mq = matchMedia('(prefers-color-scheme: dark)');
    const changed = () => { schemeStale = true; setTimeout(takeScheme, 300); };
    if (mq.addEventListener) mq.addEventListener('change', changed); else if (mq.addListener) mq.addListener(changed);
    document.addEventListener('visibilitychange', () => setTimeout(takeScheme, 300));
    addEventListener('hashchange', () => setTimeout(takeScheme, 300));
  }

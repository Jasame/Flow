  /* ---------- sheet ---------- */
  let sheetReturn = null;
  function openSheet(html, onMount) {
    if (sheetEl.hidden) sheetReturn = document.activeElement;
    sheetCard.innerHTML = '<div class="grab" aria-hidden="true"></div>' + html; sheetEl.hidden = false; document.body.classList.add('sheet-open');
    // A finger does not need a focused field (it would pop the keyboard up over the sheet); a keyboard user does.
    const f = sheetCard.querySelector(TOUCH ? '[autofocus]' : '[autofocus],input,button:not([data-close])');
    setTimeout(() => (f || sheetCard).focus({ preventScroll: true }), 30);
    if (onMount) onMount(sheetCard);
  }
  function closeSheet() {
    sheetEl.hidden = true; sheetCard.innerHTML = ''; sheetCard.style.transform = ''; document.body.classList.remove('sheet-open');
    if (sheetReturn && document.contains(sheetReturn) && sheetReturn.focus) sheetReturn.focus({ preventScroll: true });
    sheetReturn = null;
  }
  sheetEl.addEventListener('click', e => { if (e.target.closest('[data-close]')) closeSheet(); });
  document.addEventListener('keydown', e => {
    if (sheetEl.hidden) return;
    if (e.key === 'Escape') { e.preventDefault(); closeSheet(); return; }
    if (e.key !== 'Tab') return;
    const f = [...sheetCard.querySelectorAll('a[href],button:not([disabled]),input:not([disabled]),textarea:not([disabled]),select,[tabindex="0"]')].filter(x => x.offsetParent !== null);
    if (!f.length) return;
    if (!sheetCard.contains(document.activeElement)) { e.preventDefault(); f[0].focus(); return; }  // focus had slipped out
    if (e.shiftKey && (document.activeElement === f[0] || document.activeElement === sheetCard)) { e.preventDefault(); f[f.length - 1].focus(); }
    else if (!e.shiftKey && document.activeElement === f[f.length - 1]) { e.preventDefault(); f[0].focus(); }
  });
  // While a sheet is open, focus cannot wander into the page behind it (e.g. Tab pressed while it was still loading).
  document.addEventListener('focusin', e => { if (!sheetEl.hidden && !sheetEl.contains(e.target)) sheetCard.focus({ preventScroll: true }); });
  (function sheetSwipe() {  // drag the sheet down to close it, like any phone sheet
    let y0 = null, dy = 0;
    sheetCard.addEventListener('touchstart', e => { y0 = sheetCard.scrollTop <= 0 && e.touches.length === 1 ? e.touches[0].clientY : null; dy = 0; }, { passive: true });
    sheetCard.addEventListener('touchmove', e => { if (y0 == null) return; dy = e.touches[0].clientY - y0; if (dy > 0) sheetCard.style.transform = `translateY(${dy}px)`; }, { passive: true });
    sheetCard.addEventListener('touchend', () => { if (y0 == null) return; y0 = null; if (dy > 90) closeSheet(); else sheetCard.style.transform = ''; });
  })();
  // On phones the bottom tabs step aside while typing, so the keyboard never covers the field and its button.
  document.addEventListener('focusin', e => { if (TOUCH && isTyping(e)) document.body.classList.add('typing'); });
  document.addEventListener('focusout', () => setTimeout(() => { if (!isTyping({ target: document.activeElement })) document.body.classList.remove('typing'); }, 80));
  // ⌘/Ctrl + Enter sends any writing box that says where its button is (data-submit).
  document.addEventListener('keydown', e => {
    if (e.key !== 'Enter' || !(e.metaKey || e.ctrlKey) || !e.target.dataset || !e.target.dataset.submit) return;
    const b = document.querySelector(e.target.dataset.submit); if (b && !b.disabled) { e.preventDefault(); b.click(); }
  });
  // Site-wide keys: ? lists the shortcuts, / jumps to the search box.
  document.addEventListener('keydown', e => {
    if (e.defaultPrevented || e.metaKey || e.ctrlKey || e.altKey || isTyping(e) || !sheetEl.hidden) return;
    if (e.key === '?') { e.preventDefault(); shortcutHelp(); }
    else if (e.key === '/') { const q = view.querySelector('input[type=search]'); if (q) { e.preventDefault(); q.focus(); } }
  });
  function shortcutHelp() {
    const rows = [['通用', [['?', '显示这张快捷键表'], ['/', '跳到搜索框'], ['Esc', '关闭弹窗'], ['⌘/Ctrl + ↵', '提交写作、复述、翻译']]],
      ['听', [['空格 / K', '播放或停止全文']]], ['读', [['Tab 进入正文，← →', '逐词移动'], ['↵', '查当前的词'], ['E', 'AI 讲解当前这句']]],
      ['复习', [['1 / 2 / 3', '认识 / 模糊 / 不认识'], ['↵ 或 空格', '下一个'], ['X', '其实记错了'], ['← →', '测词汇量：不认识 / 认识']]]];
    openSheet(`<div class="stack"><h2 class="h2" id="sheetTitle">键盘快捷键</h2>${rows.map(([t, ks]) => `<div class="stack-s"><div class="kicker">${t}</div><dl class="keys">${ks.map(([k, d]) => `<dt><kbd>${esc(k)}</kbd></dt><dd>${esc(d)}</dd>`).join('')}</dl></div>`).join('')}
      ${TOUCH ? '<p class="muted small">触屏：复习时左滑「不认识」、右滑「认识」；弹窗向下拖可以关闭。</p>' : ''}<button class="btn ghost" data-close>关闭</button></div>`);
  }

  /* ---------- session ---------- */
  // The home data carries the session too (who is signed in, the CSRF token): one request, not two in a row,
  // which on a line from mainland China to the server is about a second saved. Signed in, the server ignores the
  // guest's level and themes in the query, so asking before S.user is known gives the same answer.
  async function refreshHome() {
    S.home = await api('/api/next/home' + guestQuery(true));
    if (S.home.session) { S.user = S.home.session.user; S.csrf = S.user ? S.user.csrf : ''; }
    if (S.home.profile && S.home.profile.voice) { S.voice = S.home.profile.voice; save('flow-next-voice', S.voice); }
    const due = S.home.stats ? S.home.stats.due + S.home.stats.new : 0;
    const b = document.getElementById('dueBadge'); b.hidden = !due; b.textContent = due > 99 ? '99+' : due;
  }
  function needLogin(reason) { openLogin(reason); return false; }
  function openLogin(reason, tab) {
    tab = tab || 'pw';
    const tabs = [['pw', '密码登录'], ['code', '验证码登录'], ['reg', '注册']];
    openSheet(`<div class="stack">
      <div><h2 class="h2" id="sheetTitle">登录语流</h2>${reason ? `<p class="muted small">${esc(reason)}</p>` : ''}</div>
      <div class="seg" role="tablist">${tabs.map(([k, l]) => `<button role="tab" data-tab="${k}" aria-selected="${k === tab}">${l}</button>`).join('')}</div>
      <form id="authForm" class="stack" novalidate>${authFields(tab)}</form>
      <p class="err" id="authErr" role="alert"></p>
      <button class="btn ghost" data-close type="button">先不登录</button></div>`, card => {
      card.querySelectorAll('[data-tab]').forEach(b => b.onclick = () => openLogin(reason, b.dataset.tab));
      const form = card.querySelector('#authForm');
      const sendBtn = card.querySelector('[data-send]');
      if (sendBtn) sendBtn.onclick = async () => {
        const email = form.email.value.trim(); const err = card.querySelector('#authErr'); err.textContent = '';
        sendBtn.disabled = true;
        try { const r = await api('/api/auth/code', { email, purpose: tab === 'reg' ? 'register' : 'login' }); toast(r.message || '验证码已发送，请查看邮箱'); countdown(sendBtn); }
        catch (e) { err.textContent = e.message; sendBtn.disabled = false; }
      };
      form.onsubmit = async e => {
        e.preventDefault(); const err = card.querySelector('#authErr'); err.textContent = '';
        const btn = form.querySelector('[type=submit]'); btn.disabled = true;
        try {
          if (tab === 'pw') await api('/api/login', { username: form.username.value.trim(), password: form.password.value });
          else if (tab === 'code') await api('/api/login', { method: 'code', email: form.email.value.trim(), code: form.code.value.trim() });
          else await api('/api/register', { email: form.email.value.trim(), code: form.code.value.trim(), username: form.username.value.trim(), password: form.password.value });
          await afterLogin(); closeSheet(); toast('已登录'); route(true);
        } catch (x) { err.textContent = x.message; btn.disabled = false; }
      };
    });
  }
  function authFields(tab) {
    if (tab === 'pw') return `<label class="field">用户名或邮箱<input name="username" type="text" autocomplete="username" required></label>
      <label class="field">密码<input name="password" type="password" autocomplete="current-password" required></label>
      <button class="btn primary block" type="submit">登录</button>`;
    const codeRow = `<label class="field">邮箱<input name="email" type="email" autocomplete="email" inputmode="email" required></label>
      <div class="row"><label class="field grow">验证码<input name="code" type="text" inputmode="numeric" autocomplete="one-time-code" maxlength="6" required></label></div>
      <button class="btn small" type="button" data-send>发送验证码</button>`;
    if (tab === 'code') return codeRow + '<button class="btn primary block" type="submit">登录</button>';
    return codeRow + `<label class="field">用户名（3–40 个字符）<input name="username" type="text" autocomplete="username" required></label>
      <label class="field">密码（至少 10 位）<input name="password" type="password" autocomplete="new-password" minlength="10" required></label>
      <button class="btn primary block" type="submit">注册并登录</button>`;
  }
  function countdown(btn) { let n = 60; btn.textContent = `${n} 秒后可重发`; const t = setInterval(() => { n--; if (n <= 0) { clearInterval(t); btn.disabled = false; btn.textContent = '重新发送'; } else btn.textContent = `${n} 秒后可重发`; }, 1000); }
  async function afterLogin() {
    await refreshHome();
    if (!S.home.profile && S.guest && S.guest.level) { try { await api('/api/next/profile', S.guest); await refreshHome(); } catch (e) { /* keep guest */ } }
    const gt = load('flow-next-guest-test');  // a vocabulary test taken before signing in
    if (gt && gt.answers) { try { await api('/api/next/vocab/test', { answers: gt.answers }); save('flow-next-guest-test', null); } catch (e) { /* try next time */ } }
  }

  /* ---------- router ---------- */
  function setNav(name) { document.querySelectorAll('[data-nav]').forEach(a => a.dataset.nav === name ? a.setAttribute('aria-current', 'page') : a.removeAttribute('aria-current')); }
  function parts() { return location.hash.replace(/^#\/?/, '').split('/'); }
  async function route(keepScroll) {
    TTS.stop(); NAR.stop(); CLIP.stop(); MIC.stop(); MINI.hide(); hideSelbar(); view.ontouchstart = view.ontouchmove = view.ontouchend = null; document.body.classList.remove('reviewing'); bar.classList.remove('hide'); document.onselectionchange = null; document.onkeydown = null;
    const [name, a, b] = parts();
    const last = S.lastRoute.split('/');
    const sameMaterial = name === 'm' && last[0] === 'm' && last[1] === a && !!view.querySelector('#pane');
    S.lastRoute = parts().join('/');
    if (!sameMaterial) view.innerHTML = skeleton();
    let fresh = S.homeFresh; S.homeFresh = false;  // home data fetched just before this page: today() need not ask again
    try {
      if (!S.home) { await refreshHome(); fresh = true; }
      if (name === 'welcome') { setNav(''); await welcome(a === 'edit'); }
      // Only the personalised home needs the level questions first; everything else works for a new guest too.
      else if (!hasProfile() && !['me', 'vocab', 'sounds', 'library', 'graph', 'm', 'cards', 'import', 'report', 'review'].includes(name)) { location.replace('#/welcome'); return; }
      else if (name === 'm' && a) { setNav('today'); await study(decodeURIComponent(a), b || 'listen', sameMaterial); }
      else if (name === 'graph') { setNav('graph'); await (a ? nodeView(decodeURIComponent(a)) : graphView()); }
      else if (name === 'cards') { setNav('cards'); await vocabView('', 1, a || ''); }
      else if (name === 'import') { setNav('today'); await importView(); }
      else if (name === 'sounds') { setNav('me'); await soundsView(a ? decodeURIComponent(a) : ''); }
      else if (name === 'report') { setNav('me'); await reportView(); }
      else if (name === 'vocab') { setNav('cards'); await (a === 'plan' ? planView() : a === 'test' ? vocabTest() : vocabView()); }
      else if (name === 'review') { setNav('cards'); await reviewView(); }
      else if (name === 'library') { setNav('today'); await libraryView(); }
      else if (name === 'me') { setNav('me'); await meView(); }
      else { setNav('today'); await today(fresh); }
      if (!sameMaterial && name !== 'welcome') enter(view);
      if (!sameMaterial) { const h = view.querySelector('h1'); announce(h ? h.textContent : document.title); }
    } catch (e) {
      view.innerHTML = `<div class="empty"><div class="big">⚠︎</div><p>${esc(e.message)}</p><button class="btn" id="retry">重试</button></div>`;
      document.getElementById('retry').onclick = () => route();
    } finally { if (!keepScroll && !sameMaterial) view.focus({ preventScroll: true }); }
  }
  window.addEventListener('hashchange', () => {
    const [name, a] = parts(), last = S.lastRoute.split('/');
    if (!(name === 'm' && last[0] === 'm' && last[1] === a)) window.scrollTo(0, 0);
    route();
  });
  // Focus mode: while reading, the top bar slides away on scroll down and comes back on scroll up.
  let lastY = 0;
  window.addEventListener('scroll', () => {
    const y = window.scrollY, reading = /^#\/m\//.test(location.hash);
    bar.classList.toggle('hide', reading && y > 140 && y > lastY + 2);
    if (y < lastY - 2) bar.classList.remove('hide');
    lastY = y;
  }, { passive: true });


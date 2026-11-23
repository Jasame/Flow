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
  /* ---------- sign in, sign up, a forgotten password ---------- */
  // With mail configured (production), sign-up, code login and a forgotten password use an emailed 6-digit code;
  // without it only username + password is offered, as the server then accepts.
  async function mailOn() {
    if (S.home && S.home.session && 'mail' in S.home.session) return !!S.home.session.mail;  // carried by the home data
    if (S.mail == null) { try { S.mail = !!(await api('/api/health')).mail; } catch (e) { return true; } }
    return S.mail;
  }
  // An account without an email cannot reset a forgotten password by itself: say so on 今日 until it binds one
  // (or the learner says 以后再说, which waits 14 days).
  function mailNudgeHTML() {
    const u = S.user, mail = S.home && S.home.session && S.home.session.mail;
    if (!u || u.email_bound !== false || !mail || Date.now() - (load('flow-next-mail-nudge') || 0) < 14 * 864e5) return '';
    return `<div class="card sunk section mail-nudge stack-s" id="mailNudge"><b>还没有绑定邮箱</b>
      <span class="small">忘记密码时，绑定了邮箱就能自己用验证码找回；没绑定的话只能请老师或管理员帮忙重设。</span>
      <div class="row"><button class="btn small primary" id="mnBind" type="button" data-tap="notice-mail">绑定邮箱</button><button class="btn small ghost" id="mnLater" type="button">以后再说</button></div></div>`;
  }
  // A few entry points are counted, how many taps a day and nothing about who, so the operator console can compare
  // the weeks before and after a release (flow_admin.TAP_LABEL lists them). Best effort: a lost count does not matter.
  document.addEventListener('click', e => {
    const t = e.target.closest && e.target.closest('[data-tap]'); if (!t) return;
    const fold = t.tagName === 'SUMMARY' && t.parentElement; if (fold && fold.open) return;
    try { navigator.sendBeacon('/api/next/tap', JSON.stringify({ k: t.dataset.tap })); } catch (x) { /* not counted */ }
  }, true);
  // In WeChat's built-in browser: a slim bar, under the top bar, on opening the page in the phone's browser, where every
  // sound plays and the app can be put on the home screen. Closed, it stays away for a week.
  function wechatBar() {
    if (!WECHAT || Date.now() - (load('flow-wx-bar') || 0) < 7 * 864e5) return;
    const ios = /iPhone|iPad|iPod/i.test(navigator.userAgent);
    const el = document.createElement('div'); el.className = 'wx-bar'; el.setAttribute('role', 'note');
    el.innerHTML = `<span>微信里部分声音和安装功能用不了。点右上角「···」，选「${ios ? '在默认浏览器中打开' : '在浏览器打开'}」，可以听全部音频，还能把语流装到桌面。</span>
      <button type="button" class="wx-x" aria-label="关闭提示">×</button>`;
    el.querySelector('.wx-x').onclick = () => { save('flow-wx-bar', Date.now()); el.remove(); };
    document.getElementById('bar').after(el);
  }
  function bindMailNudge(after) {
    const b = document.getElementById('mnBind'), l = document.getElementById('mnLater');
    if (b) b.onclick = () => bindEmailSheet('');
    if (l) l.onclick = () => { save('flow-next-mail-nudge', Date.now()); if (after) after(); else { const n = document.getElementById('mailNudge'); if (n) n.remove(); } };
  }
  const USERNAME_OK = /^[^\s@<>"'\\/]{2,40}$/;
  function pwField(label, name, auto, hint) {
    return `<label class="field">${label}<span class="pw-wrap"><input name="${name}" type="password" autocomplete="${auto}" ${auto === 'new-password' ? 'minlength="10"' : ''} required>
      <button class="pw-eye" type="button" aria-label="显示密码" aria-pressed="false" data-eye>${ICON.eye}</button></span>${hint ? `<span class="hint">${hint}</span>` : ''}</label>`;
  }
  function bindEyes(card) {
    card.querySelectorAll('[data-eye]').forEach(b => b.onclick = () => {
      const i = b.previousElementSibling, show = i.type === 'password';
      i.type = show ? 'text' : 'password'; b.setAttribute('aria-pressed', String(show)); b.setAttribute('aria-label', show ? '隐藏密码' : '显示密码'); i.focus();
    });
  }
  function fieldError(form, err, x) {  // the message under the form, and the field it is about marked and focused
    err.textContent = x.message;
    form.querySelectorAll('[aria-invalid]').forEach(i => i.removeAttribute('aria-invalid'));
    const f = x.field && form.elements[x.field]; if (f) { f.setAttribute('aria-invalid', 'true'); f.focus(); }
  }
  async function openLogin(reason, tab) {
    const mail = await mailOn();
    tab = tab || 'pw'; if (!mail && (tab === 'code' || tab === 'reset')) tab = 'pw';
    const tabs = mail ? [['pw', '密码登录'], ['code', '验证码登录'], ['reg', '注册']] : [['pw', '密码登录'], ['reg', '注册']];
    const reset = tab === 'reset';
    openSheet(`<div class="stack auth">
      <div><h2 class="h2" id="sheetTitle">${reset ? '找回密码' : tab === 'reg' ? '注册语流' : '登录语流'}</h2>${reason ? `<p class="muted small">${esc(reason)}</p>` : ''}</div>
      ${reset ? '<p class="small">填绑定的邮箱，收到验证码后设一个新密码。设好就直接登录，其他手机和电脑上的登录会退出。</p>'
        : `<div class="seg" role="tablist" aria-label="登录方式">${tabs.map(([k, l]) => `<button role="tab" data-tab="${k}" aria-selected="${k === tab}">${l}</button>`).join('')}</div>`}
      <form id="authForm" class="stack" novalidate>${authFields(tab, mail)}</form>
      <p class="err" id="authErr" role="alert"></p>
      ${reset ? '<button class="btn ghost" type="button" data-tab="pw">返回登录</button>' : '<button class="btn ghost" data-close type="button">先不登录</button>'}</div>`, card => {
      card.querySelectorAll('[data-tab]').forEach(b => b.onclick = () => openLogin(reason, b.dataset.tab));
      bindEyes(card);
      const form = card.querySelector('#authForm'), err = card.querySelector('#authErr');
      const sendBtn = card.querySelector('[data-send]');
      if (sendBtn) sendBtn.onclick = async () => {
        err.textContent = ''; sendBtn.disabled = true;
        try {
          const r = await api('/api/auth/code', { email: form.email.value.trim(), purpose: { reg: 'register', code: 'login', reset: 'reset' }[tab] });
          toast(r.message || '验证码已发送，请查看邮箱'); countdown(sendBtn); form.code.focus();
        } catch (x) { fieldError(form, err, { message: x.message, field: x.field || 'email' }); sendBtn.disabled = false; }
      };
      form.onsubmit = async e => {
        e.preventDefault(); err.textContent = '';
        const v = n => (form.elements[n] ? form.elements[n].value : '');
        // the checks the server would make, said at once and without a round trip
        if (tab === 'reg' && !USERNAME_OK.test(v('username').trim())) return fieldError(form, err, { message: '用户名需 2–40 个字符，不能有空格和 @', field: 'username' });
        if ((tab === 'reg' || tab === 'reset') && v('password').length < 10) return fieldError(form, err, { message: '密码至少 10 位', field: 'password' });
        if ((tab === 'code' || tab === 'reset' || (tab === 'reg' && mail)) && !/^\d{6}$/.test(v('code').trim())) return fieldError(form, err, { message: '请输入邮件里的 6 位验证码', field: 'code' });
        const btn = form.querySelector('[type=submit]'); btn.disabled = true;
        try {
          let r;
          if (tab === 'pw') r = await api('/api/login', { username: v('username').trim(), password: v('password') });
          else if (tab === 'code') r = await api('/api/login', { method: 'code', email: v('email').trim(), code: v('code').trim() });
          else if (reset) r = await api('/api/auth/reset', { email: v('email').trim(), code: v('code').trim(), password: v('password') });
          else r = await api('/api/register', { email: v('email').trim(), code: v('code').trim(), username: v('username').trim(), password: v('password') });
          await afterLogin(); closeSheet();
          const name = (S.user && S.user.username) || r.username || '';
          toast(reset ? '密码已重设，已经登录' : tab === 'reg' ? `注册成功，欢迎你${name ? '，' + name : ''}` : `欢迎回来${name ? '，' + name : ''}`);
          route(true);
        } catch (x) { fieldError(form, err, x); btn.disabled = false; }
      };
    });
  }
  function authFields(tab, mail) {
    const email = '<label class="field">邮箱<input name="email" type="email" autocomplete="email" inputmode="email" autocapitalize="off" spellcheck="false" required></label>';
    const code = `<div class="code-row"><label class="field">验证码<input name="code" type="text" inputmode="numeric" autocomplete="one-time-code" maxlength="6" pattern="\\d{6}" required></label>
      <button class="btn small" type="button" data-send>发送验证码</button></div><span class="hint">验证码 10 分钟内有效。收不到就看看垃圾邮件，60 秒后可以重发。</span>`;
    if (tab === 'pw') return `<label class="field">用户名或邮箱<input name="username" type="text" autocomplete="username" autocapitalize="off" spellcheck="false" required></label>
      ${pwField('密码', 'password', 'current-password')}
      <div class="auth-links">${mail ? '<button class="link small" type="button" data-tab="reset">忘记密码？</button>' : '<span class="tiny muted">忘记密码：请联系老师或管理员重设。</span>'}</div>
      <button class="btn primary block" type="submit">登录</button>`;
    if (tab === 'code') return email + code + '<button class="btn primary block" type="submit">登录</button>';
    if (tab === 'reset') return email + code + pwField('新密码', 'password', 'new-password', '至少 10 位，最好是一句只有你知道的话') + '<button class="btn primary block" type="submit">设置新密码并登录</button>';
    return (mail ? email + code : '') + `<label class="field">用户名<input name="username" type="text" autocomplete="username" autocapitalize="off" spellcheck="false" maxlength="40" required>
        <span class="hint">2–40 个字符，可以用中文，不能有空格和 @。登录时用户名和邮箱都可以用。</span></label>
      ${pwField('密码', 'password', 'new-password', '至少 10 位，最好是一句只有你知道的话')}
      ${mail ? '' : '<span class="hint">注册后可以在「我的」里绑定邮箱，忘记密码时用它找回。</span>'}
      <button class="btn primary block" type="submit">注册并登录</button>`;
  }
  // An older password-reset email links to /#reset=<token>: set the new password here, then sign in with it.
  function resetByLink(token) {
    openSheet(`<div class="stack"><h2 class="h2" id="sheetTitle">设置新密码</h2><p class="small">链接 30 分钟内有效。设好以后，用新密码登录；其他设备上的登录会退出。</p>
      <form id="rlForm" class="stack" novalidate>${pwField('新密码', 'password', 'new-password', '至少 10 位')}<button class="btn primary block" type="submit">保存新密码</button></form>
      <p class="err" id="rlErr" role="alert"></p><button class="btn ghost" data-close type="button">取消</button></div>`, card => {
      bindEyes(card);
      const form = card.querySelector('#rlForm'), err = card.querySelector('#rlErr');
      form.onsubmit = async e => {
        e.preventDefault(); err.textContent = '';
        if (form.password.value.length < 10) return fieldError(form, err, { message: '密码至少 10 位', field: 'password' });
        const b = form.querySelector('[type=submit]'); b.disabled = true;
        try { await api('/api/recovery/reset', { token, password: form.password.value }); toast('密码已重设'); openLogin('密码已重设，请用新密码登录。', 'pw'); }
        catch (x) { fieldError(form, err, x); b.disabled = false; }
      };
    });
  }
  function countdown(btn) { let n = 60; btn.textContent = `${n} 秒后可重发`; const t = setInterval(() => { n--; if (n <= 0) { clearInterval(t); btn.disabled = false; btn.textContent = '重新发送'; } else btn.textContent = `${n} 秒后可重发`; }, 1000); }
  async function afterLogin() {
    await refreshHome();
    if (!S.home.profile && S.guest && S.guest.level) { try { await api('/api/next/profile', S.guest); await refreshHome(); } catch (e) { /* keep guest */ } }
    const gt = load('flow-next-guest-test');  // a vocabulary test taken before signing in
    if (gt && gt.answers) { try { await api('/api/next/vocab/test', { answers: gt.answers }); save('flow-next-guest-test', null); } catch (e) { /* try next time */ } }
  }

  /* ---------- the tab bar's place ---------- */
  // On phones the tabs are fixed to the bottom, outside the sticky top bar: iOS Safari moves a fixed element along
  // with a sticky ancestor, and inside the bar the tabs slid up the screen on a long page. On wide screens they are a
  // row of links in the top bar.
  const WIDE = matchMedia('(min-width:760px)');
  function placeTabs() {
    const t = document.querySelector('.tabs'), bar = document.getElementById('bar');
    if (!t || !bar) return;
    if (WIDE.matches && t.parentElement !== bar) bar.appendChild(t);
    else if (!WIDE.matches && t.parentElement === bar) bar.after(t);
  }
  placeTabs();
  if (WIDE.addEventListener) WIDE.addEventListener('change', placeTabs); else if (WIDE.addListener) WIDE.addListener(placeTabs);

  /* ---------- router ---------- */
  function setNav(name) { document.querySelectorAll('[data-nav]').forEach(a => a.dataset.nav === name ? a.setAttribute('aria-current', 'page') : a.removeAttribute('aria-current')); }
  function parts() { return location.hash.replace(/^#\/?/, '').split('/'); }
  async function route(keepScroll) {
    if (/^#reset=/.test(location.hash)) {  // an older password-reset email
      const token = decodeURIComponent(location.hash.slice(7)); history.replaceState(null, '', location.pathname + location.search + '#/');
      setTimeout(() => resetByLink(token), 0);
    }
    TTS.stop(); NAR.stop(); CLIP.stop(); MIC.stop(); MINI.hide(); hideSelbar(); view.ontouchstart = view.ontouchmove = view.ontouchend = null; document.body.classList.remove('reviewing'); bar.classList.remove('hide'); document.onselectionchange = null; document.onkeydown = null;
    const [name, a, b] = parts();
    const last = S.lastRoute.split('/');
    const sameMaterial = name === 'm' && last[0] === 'm' && last[1] === a && !!view.querySelector('#pane');
    S.prevRoute = S.lastRoute; S.lastRoute = parts().join('/');  // 问题反馈 says which page it came from
    if (!sameMaterial) view.innerHTML = skeleton();
    let fresh = S.homeFresh; S.homeFresh = false;  // home data fetched just before this page: today() need not ask again
    try {
      if (!S.home) { await refreshHome(); fresh = true; }
      if (name === 'welcome') { setNav(''); await welcome(a === 'edit'); }
      // Only the personalised home needs the level questions first; everything else works for a new guest too.
      else if (!hasProfile() && !['me', 'vocab', 'sounds', 'library', 'graph', 'm', 'cards', 'import', 'report', 'review', 'placement', 'exam', 'series', 'mix', 'easy', 'words', 'speak', 'growth', 'radar', 'practice', 'guide', 'feedback'].includes(name)) { location.replace('#/welcome'); return; }
      else if (name === 'placement') { setNav('practice'); await placementView(); }
      else if (name === 'exam') { setNav('practice'); await examView(a); }
      else if (name === 'series') { setNav('today'); await seriesView(decodeURIComponent(a || '')); }
      else if (name === 'easy') { setNav('practice'); await (a ? easyRead(decodeURIComponent(a)) : easyView()); }
      else if (name === 'words' && a === 'confuse') { setNav('cards'); await (b ? confuseRound(decodeURIComponent(b)) : confuseView()); }
      else if (name === 'speak') { setNav('practice'); await (a ? speakScene(decodeURIComponent(a)) : speakView()); }
      else if (name === 'radar') { setNav('practice'); await (a === 'goals' ? radarGoals() : a === 'test' && (b === 'reading' || b === 'listening') ? assessComprehension(b) : a === 'test' && (b === 'speaking' || b === 'writing') ? assessJudged(b) : a === 'test' ? radarTests() : radarView()); }
      else if (name === 'growth') { setNav('me'); await growthView(a ? decodeURIComponent(a) : ''); }
      else if (name === 'mix') { setNav('practice'); await mixView(a === 'pair' || a === 'topic' ? a : 'due', b ? decodeURIComponent(b) : ''); }
      else if (name === 'm' && a) { setNav('today'); await study(decodeURIComponent(a), b || 'listen', sameMaterial); }
      else if (name === 'graph') { setNav('practice'); await (a ? nodeView(decodeURIComponent(a)) : graphView()); }
      else if (name === 'cards') { setNav('cards'); await vocabView('', 1, a || ''); }
      else if (name === 'import') { setNav('practice'); await importView(); }
      else if (name === 'sounds') { setNav('practice'); await soundsView(a ? decodeURIComponent(a) : ''); }
      else if (name === 'report') { setNav('me'); await reportView(); }
      else if (name === 'vocab') { setNav('cards'); await (a === 'plan' ? planView() : a === 'test' ? vocabTest() : vocabView()); }
      else if (name === 'review') { setNav('cards'); await reviewView(); }
      else if (name === 'library') { setNav('practice'); await libraryView(); }
      else if (name === 'practice') { setNav('practice'); await practiceView(); }
      else if (name === 'guide') { setNav('practice'); await guideView(a ? decodeURIComponent(a) : ''); }
      else if (name === 'me') { setNav('me'); await meView(); }
      else if (name === 'feedback') { setNav('me'); await feedbackView(); }
      else { setNav('today'); await today(fresh); }
      if (!sameMaterial && name !== 'welcome') enter(view);
      if (!sameMaterial) { const h = view.querySelector('h1'); announce(h ? h.textContent : document.title); }
    } catch (e) {
      view.innerHTML = `<div class="empty"><div class="big">⚠︎</div><p>${esc(e.message)}</p><button class="btn" id="retry">重试</button><p class="small"><a class="link" href="#/feedback">反馈这个问题</a></p></div>`;
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


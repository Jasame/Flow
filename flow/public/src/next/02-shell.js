  /* ---------- sheet ---------- */
  let sheetReturn = null;
  // Screen readers read the page in Chinese (lang="zh-CN"); English on it (a text, a question, a word, an example)
  // gets lang="en" as it appears, so it is read with an English voice. An element is marked when all of its text is
  // English; one that mixes both is left as it is (VoiceOver and TalkBack still switch for the Latin letters).
  // In English mode (00-i18n.js) the other way round: the page is lang="en" and Chinese on it (a meaning, a translation)
  // gets lang="zh-CN" (and data-lz, taken off again if the text is put into English later).
  const HAN = /[\u3400-\u9fff\uf900-\ufaff]/, LATIN2 = /[A-Za-z]{2}/;  // Chinese characters (not the full-width punctuation)
  function markEnglish(root) {
    const en = uiLang() === 'en', want = en ? HAN : LATIN2, other = en ? LATIN2 : HAN;
    const w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT), seen = new Set(); let n;
    while ((n = w.nextNode())) {
      const el = n.parentElement;
      if (!el || seen.has(el) || !want.test(n.nodeValue)) continue;
      seen.add(el);
      const own = el.closest('[lang]');
      if (own && own !== document.documentElement) continue;  // it says its language already
      if (!other.test(el.textContent) && !/^(SCRIPT|STYLE|TEXTAREA|OPTION)$/.test(el.tagName)) {
        if (en) { el.lang = 'zh-CN'; el.setAttribute('data-lz', ''); } else el.lang = 'en';
      }
    }
  }
  const EN_NEW = new Set(); let enFrame = 0;
  new MutationObserver(ms => {
    for (const m of ms) for (const x of m.addedNodes) { const e = x.nodeType === 1 ? x : x.parentElement; if (e) EN_NEW.add(e); }
    if (EN_NEW.size && !enFrame) enFrame = requestAnimationFrame(() => { enFrame = 0; EN_NEW.forEach(e => { if (e.isConnected) markEnglish(e); }); EN_NEW.clear(); });
  }).observe(document.body, { childList: true, subtree: true });
  function openSheet(html, onMount) {
    if (sheetEl.hidden) sheetReturn = document.activeElement;
    sheetCard.innerHTML = '<div class="grab" aria-hidden="true"></div>' + html; sheetEl.hidden = false; document.body.classList.add('sheet-open');
    // A finger does not need a focused field (it would pop the keyboard up over the sheet); a keyboard user does.
    const f = sheetCard.querySelector(TOUCH ? '[autofocus]' : '[autofocus],input,button:not([data-close])');
    setTimeout(() => (f || sheetCard).focus({ preventScroll: true }), 30);
    if (onMount) onMount(sheetCard);
  }
  // Closing slides the sheet down and fades it (0.16 s; B9's design audit, 2026-11-25), from wherever a finger let it
  // go. The sheet itself is closed at once (everything that asks whether one is open, focus, a sheet opened right after);
  // what moves is a copy of it, without ids, that nothing can reach and a screen reader does not see.
  function sheetGhost() {
    if (REDUCED || sheetEl.hidden || !sheetCard.firstChild) return;
    const g = sheetEl.cloneNode(true), c = g.querySelector('.sheet-card');
    g.removeAttribute('id'); g.querySelectorAll('[id]').forEach(x => x.removeAttribute('id'));
    g.classList.add('sheet-ghost'); g.setAttribute('aria-hidden', 'true'); g.inert = true;
    document.body.appendChild(g); if (c) c.scrollTop = sheetCard.scrollTop;
    setTimeout(() => g.remove(), 200);
  }
  function closeSheet() {
    sheetGhost();
    sheetEl.hidden = true; sheetCard.innerHTML = ''; sheetCard.style.transform = ''; document.body.classList.remove('sheet-open');
    if (sheetReturn && document.contains(sheetReturn) && sheetReturn.focus) sheetReturn.focus({ preventScroll: true });
    sheetReturn = null;
  }
  const sheetLocked = () => !!sheetCard.querySelector('[data-lock]');  // a sheet that waits for an answer (askAgeOnce)
  sheetEl.addEventListener('click', e => { const c = e.target.closest('[data-close]'); if (c && (!sheetLocked() || sheetCard.contains(c))) closeSheet(); });
  document.addEventListener('keydown', e => {
    if (sheetEl.hidden) return;
    if (e.key === 'Escape') { e.preventDefault(); if (!sheetLocked()) closeSheet(); return; }
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
    sheetCard.addEventListener('touchend', () => { if (y0 == null) return; y0 = null; if (dy > 90 && !sheetLocked()) closeSheet(); else sheetCard.style.transform = ''; });
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
      ['听', [['空格 / K', '播放、暂停或继续全文']]], ['读', [['Tab 进入正文，← →', '逐词移动'], ['↵', '查当前的词'], ['E', 'AI 讲解当前这句']]],
      ['复习', [['← ↓ →', '正面：不认识 / 模糊 / 认识（「认识」放在左边时左右反过来）'], ['← ↓ →', '翻面：记错了 / 模糊 / 没错'], ['1 / 2 / 3', '从左到右的按钮'], ['↵ 或 空格', '翻面：加了框的那个（正面选的那一个）'], ['E', '太简单，以后不用再背'], ['X', '其实记错了'],
        ['← →', '测词汇量：默认不认识 / 认识（「认识」放在左边时反过来）']]]];  // 「认识」放在 (50-words.js KNOW): by place on screen
    openSheet(`<div class="stack"><h2 class="h2" id="sheetTitle">键盘快捷键</h2>${rows.map(([t, ks]) => `<div class="stack-s"><div class="kicker">${t}</div><dl class="keys">${ks.map(([k, d]) => `<dt><kbd>${esc(k)}</kbd></dt><dd>${esc(d)}</dd>`).join('')}</dl></div>`).join('')}
      ${TOUCH ? '<p class="muted small">触屏：复习时左滑「不认识」、右滑「认识」；弹窗向下拖可以关闭。</p>' : ''}<button class="btn ghost" data-close>关闭</button></div>`);
  }

  /* ---------- session ---------- */
  // The home data carries the session too (who is signed in, the CSRF token): one request, not two in a row,
  // which on a line from mainland China to the server is about a second saved. Signed in, the server ignores the
  // guest's level and themes in the query, so asking before S.user is known gives the same answer.
  // The home data: who is signed in, today's plan and counts. Kept on the phone for the next visit (05-data.js).
  // Says whether anything changed since the copy the page was drawn from.
  async function refreshHome() {
    const before = S.home ? JSON.stringify(S.home) : '';
    S.home = await api('/api/next/home' + guestQuery(true));
    if (S.home.session) { S.user = S.home.session.user; S.csrf = S.user ? S.user.csrf : ''; setTimeout(askAgeOnce, 400); }
    roleTabs();
    S.homeFromSnap = false; DATA.ok();
    const changed = before !== JSON.stringify(S.home);
    if (changed) snapHome();
    if (S.home.profile && S.home.profile.voice) { S.voice = S.home.profile.voice; save('flow-next-voice', S.voice); }
    if (S.user && S.home.profile) accentFromAccount(S.home.profile);  // 主题色 kept with the account (07-accent.js)
    if (S.user && S.home.profile) langFromAccount(S.home.profile);  // and 界面语言 (07-lang.js)
    setDueBadge();
    return changed;
  }
  // 底栏 「练习」「单词」: a small ink dot when something waits, never a number (the user, 2026-11-26: 少数字，角标给人压力;
  // B9); a screen reader still hears how many, in the tab's own name: 「单词，有 10 项」
  function tabCount(id, n, name, what) {
    const b = document.getElementById(id); if (!b) return;
    b.hidden = !n; b.textContent = '';
    const a = b.closest('a'); if (a) { if (n) a.setAttribute('aria-label', `${name}，有 ${n} 项${what || ''}`); else a.removeAttribute('aria-label'); }
  }
  function setDueBadge() {
    const st = S.home && S.home.stats, due = st ? st.due + st.new : 0, other = st ? st.other_due || 0 : 0;
    tabCount('dueBadge', due, '单词');
    tabCount('otherBadge', other, '练习');  // the mistakes, patterns and sentences due again (练习 → 复习, 49-practice.js)
    tabCount('radarBadge', st ? st.radar_due || 0 : 0, '能力', '该测了');  // 底栏「能力」: skills due to be measured (48-radar.js)
  }
  // The page drawn again with fresher data, without the loading skeleton or the entrance animation, and only when it
  // would not take anything from the learner (a sheet open, typing in a field, another page by now, a whole text being
  // read or paused, a sound or a recording going: a redraw stops them — 语流 07's iPhone run, 2026-11-25: 播放全文 tapped
  // right after opening an article, the fresher 今日 came in and the reading was gone, as if read to its end).
  function redrawQuietly(drawnFor) {
    if (location.hash !== drawnFor || !sheetEl.hidden || (document.activeElement && /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName))) return;
    if (LONG.r || audioBusy()) return;
    S.homeFresh = true; route(true, true);
  }
  function needLogin(reason) { openLogin(reason); return false; }
  /* ---------- sign in, sign up, a forgotten password ---------- */
  // With mail configured (production), sign-up, code login and a forgotten password use an emailed 6-digit code;
  // without it only username + password is offered, as the server then accepts.
  async function mailOn() {
    if (S.home && S.home.session && 'mail' in S.home.session) return !!S.home.session.mail;  // carried by the home data
    if (S.mail == null) { try { const h = await api('/api/health'); S.mail = !!h.mail; S.inviteOnly = !!h.invite; } catch (e) { return true; } }
    return S.mail;
  }
  // 内测版 (FLOW_SIGNUP_INVITE_ONLY, beta_invites.py): a new 学生账号 needs an invite code; 语流's sign-up asks for none
  async function inviteOn() {
    if (S.home && S.home.session && 'invite' in S.home.session) return !!S.home.session.invite;
    if (S.inviteOnly == null) await mailOn();
    return !!S.inviteOnly;
  }
  // An account without an email cannot reset a forgotten password by itself: say so on 今日 until it binds one
  // (or the learner says 以后再说, which waits 14 days).
  function mailNudgeHTML() {
    const u = S.user, mail = S.home && S.home.session && S.home.session.mail;
    if (!u || u.email_bound !== false || !mail || Date.now() - (load('flow-next-mail-nudge') || 0) < 14 * 864e5) return '';
    // one line, put away with ✕ (以后再说: 14 days), not a card with two buttons (学优秀 UI 第一批, the user's pick 2026-11-25)
    return `<div class="mail-nudge mail-line" id="mailNudge" role="note"><span>绑定邮箱，忘记密码时可以自己找回</span>
      <button class="link small" id="mnBind" type="button" data-tap="notice-mail">去绑定</button><button class="mn-x" id="mnLater" type="button" aria-label="以后再说，14 天后再提醒">✕</button></div>`;
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
    if (!WECHAT) return;
    const ios = /iPhone|iPad|iPod/i.test(navigator.userAgent), menu = ios ? '在默认浏览器中打开' : '在浏览器打开';
    // The first visit in WeChat: an arrow to the ··· menu, the two steps, and a way to copy the address instead.
    if (!load('flow-wx-guide')) {
      save('flow-wx-guide', Date.now());
      const g = document.createElement('div'); g.className = 'wx-guide'; g.setAttribute('role', 'dialog'); g.setAttribute('aria-label', '在浏览器里打开');
      g.innerHTML = `<svg class="wx-arrow" viewBox="0 0 120 120" aria-hidden="true"><path d="M20 110 C 40 60, 70 40, 104 16" /><path d="M86 14 L106 14 L102 34" /></svg>
        <div class="wx-steps"><b>在浏览器里打开，用起来更顺</b>
          <ol><li>点右上角的「···」</li><li>选「${menu}」</li></ol>
          <span class="small">在浏览器里可以听全部录音、用浏览器朗读，还能把语流放到手机桌面。</span>
          <div class="row"><button class="btn" type="button" id="wxCopy">复制网址</button><button class="btn primary" type="button" id="wxStay">先在微信里看看</button></div></div>`;
      document.body.appendChild(g);
      g.querySelector('#wxStay').onclick = () => g.remove();
      g.querySelector('#wxCopy').onclick = async () => {
        const url = location.origin + '/';
        try { await navigator.clipboard.writeText(url); toast('网址已复制，到浏览器里粘贴打开'); } catch (e) { toast('长按复制：' + url); }
      };
    }
    if (Date.now() - (load('flow-wx-bar') || 0) < 7 * 864e5) return;
    const el = document.createElement('div'); el.className = 'wx-bar'; el.setAttribute('role', 'note');
    el.innerHTML = `<span>微信里部分声音和安装功能用不了。点右上角「···」，选「${menu}」，可以听全部音频，还能把语流装到桌面。</span>
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
    const f = x.field && form.elements[x.field]; if (f && f.setAttribute) { f.setAttribute('aria-invalid', 'true'); f.focus(); } else if (f && f[0]) f[0].focus();  // a radio group: its first
  }
  // opts.teacher: the token of a 老师注册链接 (teacher_service.py): only the sign-up, no 年龄段, and the account is a teacher's.
  async function openLogin(reason, tab, opts) {
    // 安卓 App 的基本模式（1.0.4 起：没同意《用户协议》《隐私和数据》）：登录、注册、验证码都会被 App 拦下（403 app-consent）。
    // 先请 App 再问一次同意（它等学员答完才回 'agreed' 或 'basic'）：同意了就接着打开这个框，还是不同意就不打开，
    // 免得填完才被拦（C2，docs/native-bridge.md §10）
    if (window.FlowApp && FlowApp.has && FlowApp.has('privacy')) {
      let st = null; try { st = await FlowApp.call('privacy.state'); } catch (e) { /* the app could not say: as in a browser */ }
      if (st && st.state === 'basic') {
        let r = null; try { r = await FlowApp.call('privacy.ask'); } catch (e) { /* no answer: as not agreed */ }
        if (r !== 'agreed') return;
      }
    }
    const mail = await mailOn(), teacher = opts && opts.teacher, invite = !teacher && await inviteOn();
    tab = teacher ? 'reg' : tab || 'pw'; if (!mail && (tab === 'code' || tab === 'reset')) tab = 'pw';
    // 注册 and 登录 side by side, one level (the owner on WeChat, 2026-11-25: 「注册一般和登录是一级的」); 密码 or 验证码 is
    // a choice inside 登录, a link under its form
    const tabs = [['reg', '注册', 'reg'], ['pw', '登录', 'pw code']];
    const reset = tab === 'reset';
    openSheet(`<div class="stack auth">
      <div><h2 class="h2" id="sheetTitle">${teacher ? '注册老师账号' : reset ? '找回密码' : tab === 'reg' ? '注册语流' : '登录语流'}</h2>${reason ? `<p class="muted small">${esc(reason)}</p>` : ''}</div>
      ${teacher ? '' : reset ? '<p class="small">填绑定的邮箱，收到验证码后设一个新密码。设好就直接登录，其他手机和电脑上的登录会退出。</p>'
        : `<div class="seg two" role="tablist" aria-label="注册或登录">${tabs.map(([k, l, on]) => `<button role="tab" type="button" data-tab="${k}" aria-selected="${on.split(' ').includes(tab)}">${l}</button>`).join('')}</div>`}
      <form id="authForm" class="stack" novalidate>${authFields(tab, mail, teacher, invite)}</form>
      <p class="err" id="authErr" role="alert"></p>
      ${reset ? '<button class="btn ghost" type="button" data-tab="pw">返回登录</button>' : `<button class="btn ghost" data-close type="button">${tab === 'reg' && !teacher ? '先不注册' : '先不登录'}</button>`}</div>`, card => {
      card.querySelectorAll('[data-tab]').forEach(b => b.onclick = () => openLogin(reason, b.dataset.tab));
      bindEyes(card);
      if (tab === 'reg' && !teacher) bindAge(card, false);
      const form = card.querySelector('#authForm'), err = card.querySelector('#authErr');
      const sendBtn = card.querySelector('[data-send]');
      if (sendBtn) sendBtn.onclick = async () => {
        err.textContent = ''; sendBtn.disabled = true;
        try {
          // from a class invite link (82-class.js joinRoute): the class's own code allowance, not this network's (auth_service)
          const r = await api('/api/auth/code', { email: form.email.value.trim(), purpose: { reg: 'register', code: 'login', reset: 'reset' }[tab], ...(tab === 'reg' && S.invite ? { class: S.invite } : {}), ...(tab === 'reg' && invite ? { invite: form.invite.value.trim() } : {}) });
          toast(r.message || '验证码已发送，请查看邮箱'); countdown(sendBtn); form.code.focus();
        } catch (x) { fieldError(form, err, { message: x.message, field: x.field || 'email' }); sendBtn.disabled = false; }
      };
      form.onsubmit = async e => {
        e.preventDefault(); err.textContent = '';
        const v = n => (form.elements[n] ? form.elements[n].value : '');
        // the checks the server would make, said at once and without a round trip
        if (tab === 'reg' && invite && !v('invite').trim()) return fieldError(form, err, { message: '内测版要凭邀请码注册，请填写收到的邀请码', field: 'invite' });
        if (tab === 'reg' && !USERNAME_OK.test(v('username').trim())) return fieldError(form, err, { message: '用户名需 2–40 个字符，不能有空格和 @', field: 'username' });
        if ((tab === 'reg' || tab === 'reset') && v('password').length < 10) return fieldError(form, err, { message: '密码至少 10 位', field: 'password' });
        if ((tab === 'code' || tab === 'reset' || (tab === 'reg' && mail)) && !/^\d{6}$/.test(v('code').trim())) return fieldError(form, err, { message: '请输入邮件里的 6 位验证码', field: 'code' });
        const ag = teacher ? {} : readAge(form), agp = tab === 'reg' && !teacher ? ageProblem(ag, true, false) : '';
        if (agp) return fieldError(form, err, { message: agp, field: ag.age ? 'guardian' : 'age' });
        if (tab === 'reg' && !form.consent.checked) return fieldError(form, err, { message: '请先勾选同意：数据存放在香港，以及《用户协议》和《隐私和数据》', field: 'consent' });
        const btn = form.querySelector('[type=submit]'); btn.disabled = true;
        try {
          let r;
          if (tab === 'pw') r = await api('/api/login', { username: v('username').trim(), password: v('password') });
          else if (tab === 'code') r = await api('/api/login', { method: 'code', email: v('email').trim(), code: v('code').trim() });
          else if (reset) r = await api('/api/auth/reset', { email: v('email').trim(), code: v('code').trim(), password: v('password') });
          else r = await api('/api/register', teacher ? { email: v('email').trim(), code: v('code').trim(), username: v('username').trim(), password: v('password'), teacher, storage: true, terms: true }
            : { email: v('email').trim(), code: v('code').trim(), username: v('username').trim(), password: v('password'), age: ag.age, guardian: ag.guardian, storage: true, terms: true, ...(invite ? { invite: v('invite').trim() } : {}) });
          await afterLogin(); closeSheet();
          const name = (S.user && S.user.username) || r.username || '';
          toast(reset ? '密码已重设，已经登录' : teacher ? `老师账号注册好了，欢迎你${name ? '，' + name : ''}` : tab === 'reg' ? `注册成功，欢迎你${name ? '，' + name : ''}` : `欢迎回来${name ? '，' + name : ''}`);
          route(true);
        } catch (x) { fieldError(form, err, x); btn.disabled = false; }
      };
    });
  }
  function authFields(tab, mail, teacher, invite) {
    const email = '<label class="field">邮箱<input name="email" type="email" autocomplete="email" inputmode="email" autocapitalize="off" spellcheck="false" required></label>';
    const code = `<div class="code-row"><label class="field">验证码<input name="code" type="text" inputmode="numeric" autocomplete="one-time-code" maxlength="6" pattern="\\d{6}" required></label>
      <button class="btn small" type="button" data-send>发送验证码</button></div><span class="hint">验证码 10 分钟内有效。收不到就看看垃圾邮件，60 秒后可以重发。</span>`;
    if (tab === 'pw') return `<label class="field">用户名或邮箱<input name="username" type="text" autocomplete="username" autocapitalize="off" spellcheck="false" required></label>
      ${pwField('密码', 'password', 'current-password')}
      <div class="auth-links">${mail ? '<button class="link small" type="button" data-tab="code">用邮箱验证码登录</button><button class="link small" type="button" data-tab="reset">忘记密码？</button>' : '<span class="tiny muted">忘记密码：请联系老师或管理员重设。</span>'}</div>
      <button class="btn primary block" type="submit">登录</button>`;
    if (tab === 'code') return email + code + '<div class="auth-links"><button class="link small" type="button" data-tab="pw">用密码登录</button></div><button class="btn primary block" type="submit">登录</button>';
    if (tab === 'reset') return email + code + pwField('新密码', 'password', 'new-password', '至少 10 位，最好是一句只有你知道的话') + '<button class="btn primary block" type="submit">设置新密码并登录</button>';
    const inv = invite ? '<label class="field">邀请码<input name="invite" type="text" autocomplete="off" autocapitalize="characters" spellcheck="false" maxlength="12" required>'
      + '<span class="hint">内测版要凭邀请码注册。字母不分大小写，横线可以不写。</span></label>' : '';
    return inv + (mail ? email + code : '') + `<label class="field">用户名<input name="username" type="text" autocomplete="username" autocapitalize="off" spellcheck="false" maxlength="40" required>
        <span class="hint">2–40 个字符，可以用中文，不能有空格和 @。登录时用户名和邮箱都可以用。</span></label>
      ${pwField('密码', 'password', 'new-password', '至少 10 位，最好是一句只有你知道的话')}
      ${mail ? '' : '<span class="hint">注册后可以在「我的」里绑定邮箱，忘记密码时用它找回。</span>'}
      ${teacher ? '' : ageFields('', false)}
      ${consentField()}
      <button class="btn primary block" type="submit">${teacher ? '注册老师账号并登录' : '注册并登录'}</button>`;
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

  /* ---------- 字号和行距 (81-me.js): set before anything is drawn ---------- */
  const TEXT = Object.assign({ size: 'm', lh: 'n' }, load('flow-next-text') || {});
  function applyText() { document.documentElement.dataset.size = TEXT.size; document.documentElement.dataset.lh = TEXT.lh; }
  applyText();

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

  // A 老师账号's first tab is its classes (#/ is the teacher page, 82-class.js); everyone else's is 今日.
  function roleTabs() { const t = document.querySelector('[data-nav="today"] span'); if (t) t.textContent = S.user && S.user.teacher ? '班级' : '今日'; }

  /* ---------- router ---------- */
  function setNav(name) { document.querySelectorAll('[data-nav]').forEach(a => a.dataset.nav === name ? a.setAttribute('aria-current', 'page') : a.removeAttribute('aria-current')); homeBack(name); }
  function parts() { return location.hash.replace(/^#\/?/, '').split('/'); }
  // Coming to a page already seen: 返回 (the page's own line, the browser's, the phone's), a tab tapped again (the
  // user, 2026-11-26: 从一个页面返回到另外一个页面的时候，整个页面就会稍微抖动一下……可以知道是刷新了，但是没必要抖动).
  // Such a page gets no skeleton in between and does not rise: the page left stays on screen until the one come to is
  // drawn, and the scroll moves in that same frame: to where the page was left when this is the way back to the page
  // before, else to the top. Meanwhile #view says data-busy="again": taps on the page left do nothing, and if the data
  // takes long it goes pale (after 0.4 s, 20-motion-graph.css); still no skeleton, so nothing jumps. A page opened for
  // the first time is drawn as before (skeleton, then the rise). The tests wait for both to be gone (ui_test.py settle).
  const SEEN = new Map();  // route → how far down it was when it was left
  let landing = null;      // from hashchange, for the route() it starts: { again, y }
  let routeTurn = 0;       // a route() still waiting for its data when the next page is asked for leaves the page alone
  try { history.scrollRestoration = 'manual'; } catch (e) { /* a browser without it puts the scroll back itself */ }
  async function route(keepScroll, quiet) {
    if (/^#reset=/.test(location.hash)) {  // an older password-reset email
      const token = decodeURIComponent(location.hash.slice(7)); history.replaceState(null, '', location.pathname + location.search + '#/');
      setTimeout(() => resetByLink(token), 0);
    }
    LONG.stop(); TTS.stop(); NAR.stop(); CLIP.stop(); MIC.stop(); MINI.undock(); MINI.hide(); hideSelbar(); swipeOff(); document.body.classList.remove('reviewing', 'onboarding'); bar.classList.remove('hide'); document.onselectionchange = null; document.onkeydown = null;
    const [name, a, b] = parts();
    if (name === 'about') { location.replace('/about'); return; }  // 认识语流 is its own page (the guide links here)
    const last = S.lastRoute.split('/');
    const sameMaterial = name === 'm' && last[0] === 'm' && last[1] === a && !!view.querySelector('#pane');
    S.prevRoute = S.lastRoute; S.lastRoute = parts().join('/');  // 问题反馈 says which page it came from
    const land = landing; landing = null;
    const again = !!land && land.again && !sameMaterial && !quiet;
    if (!quiet) { routeTurn++; view.removeAttribute('data-busy'); }
    const turn = routeTurn;
    if (again) { view.classList.remove('enter'); view.setAttribute('data-busy', 'again'); }  // 'enter' off: else what is drawn into it would rise
    else if (!sameMaterial && !quiet) view.innerHTML = skeleton();
    let fresh = S.homeFresh; S.homeFresh = false;  // home data fetched just before this page: today() need not ask again
    try {
      if (!S.home) { await refreshHome(); fresh = true; }
      // 认识语流's 「注册账号」 (/#/join): the first page with the sign-up sheet open over it; signed in, just the first page.
      if (name === 'join') { location.replace('#/'); if (!S.user) setTimeout(() => openLogin('', 'reg'), 0); return; }
      // 数据存放在香港 not agreed (an older account, or paused): that page first, every page but the guide (81-privacy.js)
      if (S.user && (S.user.storage !== 'ok' || S.user.terms !== 'ok') && name !== 'guide') { setNav(''); await storageView(); }
      // 选方向和目标 is the first-time page: a guest lands on it (no goals yet), and when it signs in there (「已有账号？
      // 登录」, or 认识语流's 「免费开始学」 → the sign-in sheet over it) to an account that has its goals, 今日 follows instead
      // of the questions again (the owner, 2026-11-26: an older account was asked again after signing in from a link)
      else if (name === 'welcome' && a !== 'edit' && S.user && S.home && S.home.profile) { location.replace('#/'); return; }
      else if (name === 'welcome') { setNav(''); await welcome(a === 'edit'); }
      // 老师模式 (82-class.js): #/teacher/<token> is a 老师注册链接; a teacher account's home is its classes
      else if (name === 'teacher') { setNav(''); await teacherSignup(decodeURIComponent(a || '')); }
      else if (name === 'teach' || (name === '' && S.user && S.user.teacher)) { setNav('today'); await teachHome(); }
      // Only the personalised home needs the level questions first; everything else works for a new guest too.
      else if (!hasProfile() && !['me', 'vocab', 'sounds', 'library', 'graph', 'm', 'cards', 'import', 'report', 'review', 'placement', 'exam', 'series', 'mix', 'easy', 'words', 'speak', 'growth', 'radar', 'practice', 'guide', 'feedback', 'weekly-off', 'invite', 'class', 'updates'].includes(name)) { location.replace('#/welcome'); return; }
      else if (name === 'placement') { setNav('practice'); await placementView(); }
      else if (name === 'exam') { setNav('practice'); await (b ? examTypeView(a, decodeURIComponent(b)) : examView(a)); }
      else if (name === 'series') { setNav('today'); await seriesView(decodeURIComponent(a || '')); }
      else if (name === 'easy') { setNav('practice'); await (a ? easyRead(decodeURIComponent(a)) : easyView()); }
      else if (name === 'words' && a === 'confuse') { setNav('cards'); await (b ? confuseRound(decodeURIComponent(b)) : confuseView()); }
      else if (name === 'speak') { setNav('practice'); await (a === 'ielts' ? (b ? ieltsPractice(decodeURIComponent(b)) : ieltsView()) : a ? speakScene(decodeURIComponent(a)) : speakView()); }
      else if (name === 'radar') { setNav('radar'); await (a === 'goals' ? radarGoals() : a === 'test' && (b === 'reading' || b === 'listening') ? assessComprehension(b) : a === 'test' && (b === 'speaking' || b === 'writing') ? assessJudged(b) : a === 'test' ? radarTests() : radarView()); }
      else if (name === 'growth') { setNav('me'); await growthView(a ? decodeURIComponent(a) : ''); }
      else if (name === 'two') { setNav('today'); await twoView(decodeURIComponent(a || '')); }  // 听两句、答一句 (26-two-lines.js)
      else if (name === 'mix') { setNav('practice'); await mixView(a === 'pair' || a === 'topic' || a === 'exam' || a === 'more' ? a : 'due', b ? decodeURIComponent(b) : ''); }
      else if (name === 'm' && a) { setNav('today'); await study(decodeURIComponent(a), b || 'listen', sameMaterial); }
      else if (name === 'graph') { setNav('practice'); await (a ? nodeView(decodeURIComponent(a)) : graphView()); }
      else if (name === 'cards' && a === 'mistake') { setNav('practice'); await mistakeView(); }  // 错题本: 练习 → 复习
      // #/cards/find/<词>: the words list with that word searched (the iPhone's system search opens a word this way, 语流 C1)
      // (a 「/」 left unencoded, as in borrow / lend, is still part of the word)
      else if (name === 'cards' && a === 'find') { setNav('cards'); await vocabView(parts().slice(2).map(x => decodeURIComponent(x)).join('/').slice(0, 80), 1, ''); const sf = document.getElementById('sf'); if (sf) sf.scrollIntoView({ block: 'start' }); }
      else if (name === 'cards') { setNav('cards'); await vocabView('', 1, a || ''); }
      else if (name === 'import') { setNav('practice'); await importView(); }
      else if (name === 'sounds') { setNav('practice'); await soundsView(a ? decodeURIComponent(a) : ''); }
      else if (name === 'report') { setNav('me'); await reportView(); }
      else if (name === 'today') { setNav('today'); todayEditView(); }  // 调整顺序 (#/today/edit, 13-today-views.js)
      else if (name === 'weekly-off') { setNav('me'); await weeklyOffView(decodeURIComponent(a || '')); }  // the link in the Sunday mail
      else if (name === 'vocab') { setNav('cards'); await (a === 'plan' ? planView() : a === 'test' ? vocabTest() : vocabView()); }
      else if (name === 'review') { setNav(a === 'other' ? 'practice' : 'cards'); await reviewView(a === 'more', a === 'other' ? 'other' : 'words'); }
      else if (name === 'library') { setNav('practice'); await libraryView(); }
      else if (name === 'practice') { setNav('practice'); await practiceView(); }
      else if (name === 'guide') { setNav('practice'); await guideView(a ? decodeURIComponent(a) : ''); }
      else if (name === 'me') { setNav('me'); await meView(a); }  // #/me/account, #/me/help: that fold open
      else if (name === 'invite') { setNav('me'); await joinRoute(decodeURIComponent(a || '')); }
      else if (name === 'class' && a) { setNav(S.user && S.user.teacher ? 'today' : 'me'); await classView(decodeURIComponent(a)); }
      else if (name === 'feedback') { setNav('me'); await feedbackView(); }
      else if (name === 'updates') { setNav('me'); await updatesView(); }  // 更新记录 (83-updates.js)
      else { setNav('today'); await today(fresh); }
      if (again) { if (turn === routeTurn) window.scrollTo(0, land.y); }
      else if (!sameMaterial && name !== 'welcome' && !quiet) enter(view);
      if (!sameMaterial && !quiet) { const h = view.querySelector('h1'); announce(h ? h.textContent : document.title); }
      homeBackLink();  // 主屏 App: the page's own 「← 上一级」 line gives way to the top bar's 返回 (04-home-app.js)
      if (!quiet) tourMaybe();  // 新手引导: 今日 (or 我的班级) the first time a new account opens it (08-tour.js)
    } catch (e) {
      if (again && turn === routeTurn) window.scrollTo(0, 0);
      const kept = e.network ? OFF.list() : [];  // offline: what can still be studied
      view.innerHTML = `<div class="empty"><div class="big">⚠︎</div><p>${esc(e.message)}</p><button class="btn" id="retry">重试</button>
        ${kept.length ? `<p class="small">没网时，这些已存到本机的材料还能学：</p><div class="mlist">${kept.map(k => mrow(k, null, '', '')).join('')}</div>` : ''}
        <p class="small"><a class="link" href="#/feedback">反馈这个问题</a></p></div>`;
      // an older front end than the server's may be what failed: a new version first (04-home-app.js), then the page again
      document.getElementById('retry').onclick = async ev => { ev.currentTarget.disabled = true; if (!(await retryOrUpdate())) route(); };
      errorPageUpdate();
    } finally { if (again && turn === routeTurn) view.removeAttribute('data-busy'); if (!keepScroll && !sameMaterial && !quiet) view.focus({ preventScroll: true }); }
  }
  // How the page changed (the Navigation API where there is one; else a longer history means a link, and a back or a
  // redirect cannot be told apart, so neither closes a sheet)
  const NAV = { type: '', len: history.length };
  if (window.navigation && navigation.addEventListener) navigation.addEventListener('navigate', e => { NAV.type = e.navigationType || ''; });
  window.addEventListener('hashchange', () => {
    const [name, a] = parts(), last = S.lastRoute.split('/'), to = parts().join('/');
    const inMaterial = name === 'm' && last[0] === 'm' && last[1] === a;
    // The way back to the page before: the browser says so (traverse), or the page come to is the one before the page
    // being left (04-home-app.js's HIST: its own listener runs after this one, so here it still ends with that page).
    const back = NAV.type === 'traverse' || (HIST.length > 1 && HIST[HIST.length - 2] === (location.hash || '#/'));
    SEEN.set(S.lastRoute, window.scrollY);
    const again = !inMaterial && SEEN.has(to);
    landing = { again, y: back && again ? SEEN.get(to) : 0 };
    if (!inMaterial && !again) window.scrollTo(0, 0);
    // another page the learner went to (a link, 返回, the browser's or the phone's back): a sheet of the page left closes
    // with it (one waiting for an answer stays). The app's own redirects (location.replace: #/join → #/ → #/welcome) keep
    // the sheet a route opened on the way (#/join's 注册). A tip the page left showed is put away, one said on the way
    // here (「已保存」) stays.
    const redirect = NAV.type ? NAV.type === 'replace' : history.length === NAV.len; NAV.type = ''; NAV.len = history.length;
    if (!redirect && !sheetEl.hidden && !sheetLocked()) closeSheet();
    if (Date.now() - (toast.at || 0) > 400) toastEl.classList.remove('show');
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


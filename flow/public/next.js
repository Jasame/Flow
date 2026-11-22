'use strict';
/* Flow Next — one learning loop: listen → read → check → use it → review what you saved. See NEXT.md. */
(function () {
  const view = document.getElementById('view');
  const sheetEl = document.getElementById('sheet');
  const sheetCard = document.getElementById('sheetCard');
  const toastEl = document.getElementById('toast');
  const S = { user: null, csrf: '', meta: null, home: null, guest: load('flow-next-guest') };
  const STEP = { listen: '听', read: '读', check: '理解', output: '用出来' };
  const STEPS = Object.keys(STEP);

  /* ---------- utilities ---------- */
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])); }
  function load(k) { try { return JSON.parse(localStorage.getItem(k) || 'null'); } catch (e) { return null; } }
  function save(k, v) { try { v == null ? localStorage.removeItem(k) : localStorage.setItem(k, JSON.stringify(v)); } catch (e) { /* private mode */ } }
  function rid(prefix) { return prefix + '-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 10); }
  function toast(msg) { toastEl.textContent = msg; toastEl.classList.add('show'); clearTimeout(toast.t); toast.t = setTimeout(() => toastEl.classList.remove('show'), 2400); }
  async function api(path, body) {
    const opt = { credentials: 'same-origin', headers: {} };
    if (body !== undefined) { opt.method = 'POST'; opt.headers['Content-Type'] = 'application/json'; if (S.csrf) opt.headers['X-CSRF-Token'] = S.csrf; opt.body = JSON.stringify(body); }
    const r = await fetch(path, opt);
    const j = await r.json().catch(() => ({}));
    if (!r.ok) { const e = new Error(j.error || ('请求失败（' + r.status + '）')); e.status = r.status; throw e; }
    return j;
  }
  const ICON = {
    play: '<svg viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>',
    pause: '<svg viewBox="0 0 24 24"><path d="M8 5v14M16 5v14"/></svg>',
    speak: '<svg viewBox="0 0 24 24"><path d="M4 10v4h4l5 4V6L8 10zM16 9a4 4 0 0 1 0 6M18.5 6.5a8 8 0 0 1 0 11"/></svg>',
    eye: '<svg viewBox="0 0 24 24"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/></svg>',
    star: '<svg viewBox="0 0 24 24"><path d="m12 3 2.8 5.8 6.2.9-4.5 4.4 1 6.2L12 17.4l-5.5 2.9 1-6.2L3 9.7l6.2-.9z"/></svg>',
    trash: '<svg viewBox="0 0 24 24"><path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13"/></svg>',
  };
  function level() { return (S.home && S.home.level) || (S.user && S.home && S.home.profile && S.home.profile.level) || (S.guest && S.guest.level) || 'B1'; }
  function hasProfile() { return S.user ? !!(S.home && S.home.profile) || !!(S.guest && S.guest.level) : !!(S.guest && S.guest.level); }

  /* ---------- speech ---------- */
  const TTS = {
    ok: 'speechSynthesis' in window, rate: Number(load('flow-next-rate')) || 1, voice: null, token: 0,
    pick() {
      if (!this.ok) return null;
      const vs = speechSynthesis.getVoices().filter(v => /^en[-_]/i.test(v.lang));
      const pref = ['Samantha', 'Google US English', 'Microsoft Aria', 'Microsoft Jenny', 'Karen', 'Daniel', 'Google UK English Female'];
      this.voice = pref.map(n => vs.find(v => v.name.includes(n))).find(Boolean) || vs.find(v => /en-US/i.test(v.lang)) || vs[0] || null;
      return this.voice;
    },
    say(text, onend) {
      if (!this.ok) { toast('这个浏览器不支持朗读'); return; }
      speechSynthesis.cancel();
      const u = new SpeechSynthesisUtterance(text);
      u.lang = 'en-US'; u.rate = this.rate; const v = this.voice || this.pick(); if (v) u.voice = v;
      const t = ++this.token;
      u.onend = () => { if (t === this.token && onend) onend(); };
      speechSynthesis.speak(u);
    },
    stop() { this.token++; if (this.ok) speechSynthesis.cancel(); },
  };
  if (TTS.ok) speechSynthesis.onvoiceschanged = () => TTS.pick();

  /* ---------- sheet ---------- */
  function openSheet(html, onMount) {
    sheetCard.innerHTML = html; sheetEl.hidden = false;
    const f = sheetCard.querySelector('[autofocus],input,button'); if (f) setTimeout(() => f.focus(), 30);
    if (onMount) onMount(sheetCard);
  }
  function closeSheet() { sheetEl.hidden = true; sheetCard.innerHTML = ''; }
  sheetEl.addEventListener('click', e => { if (e.target.closest('[data-close]')) closeSheet(); });
  document.addEventListener('keydown', e => { if (e.key === 'Escape' && !sheetEl.hidden) closeSheet(); });

  /* ---------- session ---------- */
  async function refreshSession() {
    const s = await api('/api/session');
    S.user = s.user; S.csrf = s.user ? s.user.csrf : '';
  }
  async function refreshHome() {
    const g = S.guest || {};
    const q = S.user ? '' : '?level=' + encodeURIComponent(g.level || 'B1') + (g.themes && g.themes.length ? '&themes=' + encodeURIComponent(g.themes.join(',')) : '');
    S.home = await api('/api/next/home' + q);
    const due = S.home.stats ? S.home.stats.due : 0;
    const b = document.getElementById('dueBadge'); b.hidden = !due; b.textContent = due > 99 ? '99+' : due;
  }
  function needLogin(reason) {
    openLogin(reason);
    return false;
  }
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
          await afterLogin(); closeSheet(); toast('已登录'); route();
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
    await refreshSession(); await refreshHome();
    if (!S.home.profile && S.guest && S.guest.level) {
      try { await api('/api/next/profile', S.guest); await refreshHome(); } catch (e) { /* keep guest */ }
    }
  }

  /* ---------- router ---------- */
  function setNav(name) { document.querySelectorAll('[data-nav]').forEach(a => a.dataset.nav === name ? a.setAttribute('aria-current', 'page') : a.removeAttribute('aria-current')); }
  async function route() {
    TTS.stop(); hideSelbar();
    const h = location.hash.replace(/^#\/?/, '');
    const [name, a, b] = h.split('/');
    try {
      if (!S.home) await refreshHome();
      if (name === 'welcome') { setNav(''); return welcome(a === 'edit'); }
      if (!hasProfile() && name !== 'me') { location.replace('#/welcome'); return; }
      if (name === 'm' && a) { setNav('today'); return study(decodeURIComponent(a), b || 'listen'); }
      if (name === 'cards') { setNav('cards'); return cardsView(); }
      if (name === 'review') { setNav('cards'); return reviewView(); }
      if (name === 'library') { setNav('today'); return libraryView(); }
      if (name === 'me') { setNav('me'); return meView(); }
      setNav('today'); return today();
    } catch (e) {
      view.innerHTML = `<div class="empty"><div class="big">⚠︎</div><p>${esc(e.message)}</p><button class="btn" id="retry">重试</button></div>`;
      document.getElementById('retry').onclick = route;
    } finally { view.focus({ preventScroll: true }); }
  }
  window.addEventListener('hashchange', () => { window.scrollTo(0, 0); route(); });

  /* ---------- welcome ---------- */
  async function welcome(edit) {
    if (!S.meta) S.meta = await api('/api/next/meta');
    const cur = (S.home && S.home.profile) || S.guest || {};
    const st = { step: 0, level: cur.level || '', goal: cur.goal || '', themes: (cur.themes || []).slice(), minutes: cur.minutes || 10 };
    const total = 4;
    function draw() {
      let body = '';
      if (st.step === 0) body = `<h1 class="h1">你能轻松读懂哪一句？</h1><p class="muted">选你不查词典也能读懂的最难一句。之后随时可以改。</p>
        <div class="choice">${S.meta.levels.map(l => `<button class="opt" data-v="${l.id}" aria-pressed="${st.level === l.id}"><div class="row between"><span class="l">${esc(l.label)}</span><span class="pill">${l.id}</span></div><div class="s">${esc(l.sample)}</div><div class="d">${esc(l.desc)}</div></button>`).join('')}</div>`;
      if (st.step === 1) body = `<h1 class="h1">你学英语主要为了什么？</h1><div class="choice">${S.meta.goals.map(g => `<button class="opt" data-v="${g.id}" aria-pressed="${st.goal === g.id}"><span class="l">${esc(g.label)}</span></button>`).join('')}</div>`;
      if (st.step === 2) body = `<h1 class="h1">你对哪些话题感兴趣？</h1><p class="muted">可以多选，不选就每天随机。</p><div class="chips">${S.meta.themes.map(t => `<button class="chip" data-t="${t.id}" aria-pressed="${st.themes.includes(t.id)}">${esc(t.label)}</button>`).join('')}</div>`;
      if (st.step === 3) body = `<h1 class="h1">每天想学多久？</h1><p class="muted">一篇材料大约 8–15 分钟。少一点但每天来，比偶尔学很久更有用。</p><div class="choice">${S.meta.minutes.map(m => `<button class="opt" data-v="${m}" aria-pressed="${st.minutes === m}"><span class="l">${m} 分钟</span></button>`).join('')}</div>`;
      const canNext = st.step === 0 ? !!st.level : st.step === 1 ? !!st.goal : true;
      view.innerHTML = `<div class="progress-line"><i id="wp"></i></div><div class="stack">${body}
        <div class="row between"><button class="btn ghost" id="wBack" ${st.step === 0 && !edit ? 'hidden' : ''}>${st.step === 0 ? '取消' : '上一步'}</button>
        <button class="btn primary" id="wNext" ${canNext ? '' : 'disabled'}>${st.step === total - 1 ? '开始学习' : '下一步'}</button></div></div>`;
      document.getElementById('wp').style.width = ((st.step + 1) / total * 100) + '%';
      view.querySelectorAll('.opt').forEach(b => b.onclick = () => {
        const v = b.dataset.v; if (st.step === 0) st.level = v; else if (st.step === 1) st.goal = v; else st.minutes = Number(v);
        draw(); if (st.step < 2) setTimeout(next, 160);
      });
      view.querySelectorAll('.chip').forEach(b => b.onclick = () => { const t = b.dataset.t; st.themes = st.themes.includes(t) ? st.themes.filter(x => x !== t) : st.themes.concat(t); draw(); });
      document.getElementById('wNext').onclick = next;
      document.getElementById('wBack').onclick = () => { if (st.step === 0) history.back(); else { st.step--; draw(); } };
    }
    async function next() {
      if (st.step < total - 1) { st.step++; draw(); return; }
      const prof = { level: st.level, goal: st.goal, themes: st.themes, minutes: st.minutes };
      S.guest = prof; save('flow-next-guest', prof);
      if (S.user) { try { await api('/api/next/profile', prof); } catch (e) { toast(e.message); } }
      await refreshHome(); location.hash = '#/';
    }
    draw();
  }

  /* ---------- today ---------- */
  function greeting() { const h = new Date().getHours(); return h < 5 ? '夜深了' : h < 11 ? '早上好' : h < 14 ? '中午好' : h < 18 ? '下午好' : '晚上好'; }
  function stepDots(steps) { return `<span class="steps-dots" aria-label="已完成 ${steps.length} / 4 步">${STEPS.map(s => `<i class="${steps.includes(s) ? 'on' : ''}"></i>`).join('')}</span>`; }
  function miniCard(m, tag) {
    return `<a class="card flat mini" href="#/m/${encodeURIComponent(m.id)}"><span class="t">${esc(m.title)}</span>
      <span class="meta">${tag ? `<span class="pill amber">${esc(tag)}</span>` : ''}<span class="pill">${m.level}</span></span>
      <span class="p">${esc(m.preview)}</span><span class="tiny muted">${esc(m.theme_label)} · ${m.words} 词 · 约 ${m.minutes} 分钟</span>${stepDots(m.steps)}</a>`;
  }
  async function today() {
    await refreshHome();
    const h = S.home, pick = h.today[0], st = h.stats;
    const name = S.user ? S.user.username : '';
    view.innerHTML = `<div class="hello"><span class="kicker">${greeting()}${name ? '，' + esc(name) : ''}</span>
        <h1 class="h1">今天学一篇，用上一句。</h1>
        <span class="muted small">按「${esc(h.level_label)}（${h.level}）」为你挑选 · <a class="link" href="#/welcome/edit">调整</a></span>
        ${st ? `<div class="week" aria-label="本周学习 ${st.week.filter(d => d.active).length} 天">${st.week.map(d => `<span class="${d.active ? 'on' : ''}" title="${d.day}"></span>`).join('')}</div>` : ''}</div>
      ${h.resume ? `<a class="card flat mini" href="#/m/${encodeURIComponent(h.resume.id)}/${nextStep(h.resume.steps)}"><span class="t">继续：${esc(h.resume.title)}</span><span class="pill green">继续</span><span class="p">${esc(h.resume.preview)}</span>${stepDots(h.resume.steps)}</a>` : ''}
      ${st && st.due ? `<div class="card section due"><div><div class="kicker">复习</div><div><b>${st.due}</b> 个你收藏的表达该复习了</div><div class="muted small">大约 ${Math.max(1, Math.round(st.due * 0.3))} 分钟</div></div><a class="btn primary" href="#/review">开始复习</a></div>` : ''}
      ${pick ? `<article class="card hero section"><div class="meta"><span class="pill green">今日推荐</span><span class="pill">${pick.level}</span><span class="pill">${esc(pick.theme_label)}</span></div>
        <h2 class="title">${esc(pick.title)}</h2><p class="preview">${esc(pick.preview)}</p>
        <div class="row between"><span class="muted small">${pick.words} 词 · 约 ${pick.minutes} 分钟 · 听、读、理解、用出来</span><a class="btn primary" href="#/m/${encodeURIComponent(pick.id)}">开始学习</a></div></article>` : '<div class="empty">今天没有可推荐的材料了。</div>'}
      ${h.news ? `<div class="section"><div class="section-head"><h2 class="h2">今日热点</h2><span class="muted tiny">联网检索后改写，未经人工审核</span></div>${miniCard(h.news, '热点')}</div>` : ''}
      <div class="section"><div class="section-head"><h2 class="h2">也可以选</h2><a class="link small" href="#/library">全部材料 →</a></div>
        <div class="grid-list">${h.today.slice(1).map(m => miniCard(m)).join('')}</div></div>
      ${S.user ? '' : `<div class="card sunk section"><div class="stack-s"><b>登录后，进度和收藏的表达会保存下来</b><span class="muted small">不登录也可以听、读和做理解题。</span><div><button class="btn small" id="loginCta">登录 / 注册</button></div></div></div>`}`;
    const cta = document.getElementById('loginCta'); if (cta) cta.onclick = () => openLogin();
  }
  function nextStep(steps) { return STEPS.find(s => !steps.includes(s)) || 'output'; }

  /* ---------- study ---------- */
  const SEL = { text: '', context: '' };
  let selbar = null;
  function hideSelbar() { if (selbar) { selbar.remove(); selbar = null; } }

  async function study(id, step) {
    const q = S.user ? '' : '&level=' + encodeURIComponent(level());
    const m = await api('/api/next/material?id=' + encodeURIComponent(id) + q);
    const local = load('flow-next-steps-' + id) || [];
    const done = new Set(m.steps.concat(local));
    const st = { m, step: STEPS.includes(step) ? step : 'listen', showOriginal: false, playing: -1, blind: false };

    function markStep(s) {
      if (done.has(s)) return;
      done.add(s); save('flow-next-steps-' + id, Array.from(done));
      if (S.user) api('/api/next/progress', { pack: id, step: s }).catch(() => {});
      const tab = view.querySelector(`[data-step="${s}"]`); if (tab && !tab.querySelector('.ok')) tab.insertAdjacentHTML('beforeend', '<span class="ok">✓</span>');
    }
    function go(s) { location.hash = `#/m/${encodeURIComponent(id)}/${s}`; }
    const lines = () => st.showOriginal && m.original ? m.original : m.sentences;

    view.innerHTML = `<div class="study-head"><span class="kicker">${esc(m.theme_label)} · ${m.level}${m.variant ? ' → ' + m.variant.level : ''}</span>
      <h1 class="h1">${esc(m.title)}</h1>
      <span class="muted tiny">${esc(m.source)}${m.provenance.length ? ' · 来源：' + m.provenance.map(p => `<a class="link" href="${esc(p.url)}" target="_blank" rel="noopener noreferrer">${esc(p.title)}</a>`).join('、') : ''}</span></div>
      <div class="steps" role="tablist">${STEPS.map(s => `<button role="tab" data-step="${s}" aria-selected="${s === st.step}">${STEP[s]}${done.has(s) ? '<span class="ok">✓</span>' : ''}</button>`).join('')}</div>
      <section id="pane"></section>`;
    view.querySelectorAll('[data-step]').forEach(b => b.onclick = () => go(b.dataset.step));
    const pane = view.querySelector('#pane');

    /* listen */
    function listen() {
      const ls = lines();
      pane.innerHTML = `<div class="player">
          <button class="btn primary" id="playAll">${ICON.play.replace('<svg', '<svg width="18" height="18" fill="currentColor"')}<span>播放全文</span></button>
          <div class="speed" role="group" aria-label="语速">${[0.75, 1, 1.25].map(r => `<button data-rate="${r}" aria-pressed="${TTS.rate === r}">${r}×</button>`).join('')}</div>
          <button class="icon-btn ${st.blind ? 'on' : ''}" id="blind" aria-pressed="${st.blind}" title="盲听：先只听不看" aria-label="盲听">${ICON.eye}</button>
        </div>
        ${TTS.ok ? '' : '<p class="err">这个浏览器不支持朗读，可以直接去「读」。</p>'}
        <p class="muted small">先盲听一遍，听不懂的句子单独点开反复听，再看原文。</p>
        <div class="lines">${ls.map((s, i) => `<div class="line" data-i="${i}"><button class="icon-btn" data-say="${i}" aria-label="播放第 ${i + 1} 句">${ICON.speak}</button><div class="txt ${st.blind ? 'blind' : ''}">${esc(s)}</div></div>`).join('')}</div>
        <div class="section row between"><span class="muted small">共 ${ls.length} 句</span><button class="btn" id="toRead">听完了，去读 →</button></div>`;
      const setNow = i => pane.querySelectorAll('.line').forEach(el => el.classList.toggle('now', Number(el.dataset.i) === i));
      const playFrom = i => {
        if (i >= ls.length) { st.playing = -1; setNow(-1); setBtn(false); markStep('listen'); return; }
        st.playing = i; setNow(i);
        const el = pane.querySelector(`.line[data-i="${i}"]`); if (el) el.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
        TTS.say(ls[i], () => playFrom(i + 1));
      };
      const setBtn = on => { const b = pane.querySelector('#playAll'); b.querySelector('span').textContent = on ? '停止' : '播放全文'; };
      pane.querySelector('#playAll').onclick = () => { if (st.playing >= 0) { TTS.stop(); st.playing = -1; setNow(-1); setBtn(false); } else { setBtn(true); playFrom(0); } };
      pane.querySelectorAll('[data-say]').forEach(b => b.onclick = () => { const i = Number(b.dataset.say); st.playing = -1; setBtn(false); setNow(i); TTS.say(ls[i], () => setNow(-1)); });
      pane.querySelectorAll('[data-rate]').forEach(b => b.onclick = () => { TTS.rate = Number(b.dataset.rate); save('flow-next-rate', TTS.rate); listen(); });
      pane.querySelector('#blind').onclick = () => { st.blind = !st.blind; listen(); };
      pane.querySelector('#toRead').onclick = () => { markStep('listen'); go('read'); };
    }

    /* read */
    function wordsHTML(sentence, si) {
      return sentence.split(/([A-Za-z]+(?:'[A-Za-z]+)?)/).map((part, k) => {
        if (k % 2 === 0) return esc(part);
        const key = part.toLowerCase();
        const isVocab = m.vocabulary.some(v => v.term.toLowerCase() === key || v.term.toLowerCase().split(' ').includes(key) && v.term.includes(' '));
        const cls = isVocab ? 'w vocab' : (m.hard[key] ? 'w hard' : 'w');
        return `<span class="${cls}" data-w="${esc(part)}" data-s="${si}">${esc(part)}</span>`;
      }).join('');
    }
    function read() {
      const ls = lines();
      const variantBar = m.variant ? `<div class="seg" role="tablist"><button data-ver="v" aria-selected="${!st.showOriginal}">适合我的版本（${m.variant.level}）</button><button data-ver="o" aria-selected="${st.showOriginal}">原文（${m.original_level}）</button><span></span></div>`
        : m.can_variant ? `<div class="card sunk row between"><span class="small">这篇原文是 ${m.original_level}，你选的是 ${m.user_level}。</span><button class="btn small" id="mkVar">改写成 ${m.user_level} 难度</button></div>` : '';
      pane.innerHTML = `${variantBar}
        <div class="legend"><span>本篇重点</span><span class="h">可能超出你的水平</span><span class="muted">点任意单词查词；选中一段文字可以收藏</span></div>
        <div class="text" id="reader">${ls.map((s, i) => `<span class="sent" data-si="${i}">${wordsHTML(s, i)}</span> `).join('')}</div>
        ${m.vocabulary.length ? `<div class="section"><h2 class="h2">本篇重点表达</h2><div class="vocab-list section">${m.vocabulary.map((v, i) => `<div class="vrow"><span class="term">${esc(v.term)}</span><button class="icon-btn" data-sv="${i}" aria-label="收藏 ${esc(v.term)}">${ICON.star}</button><span class="muted small">${esc(v.meaning)}</span><span class="ex">${esc(v.example || '')}</span></div>`).join('')}</div></div>` : ''}
        ${(m.variant && m.variant.notes.length) ? `<div class="section"><h2 class="h2">改写版新出现的表达</h2><div class="vocab-list section">${m.variant.notes.map((v, i) => `<div class="vrow"><span class="term">${esc(v.text)}</span><button class="icon-btn" data-sn="${i}" aria-label="收藏">${ICON.star}</button><span class="muted small">${esc(v.meaning)}</span></div>`).join('')}</div></div>` : ''}
        ${m.notes.length ? `<div class="section stack-s"><h2 class="h2">句子里的门道</h2>${m.notes.map(n => `<div class="note"><q>${esc(n.quote)}</q><div class="small muted">${esc(n.explanation)}</div></div>`).join('')}</div>` : ''}
        <div class="section row between"><span></span><button class="btn" id="toCheck">读完了，做理解题 →</button></div>`;
      pane.querySelectorAll('[data-ver]').forEach(b => b.onclick = () => { st.showOriginal = b.dataset.ver === 'o'; read(); });
      const mk = pane.querySelector('#mkVar');
      if (mk) mk.onclick = async () => {
        if (!S.user) return needLogin('登录后可以让 AI 把这篇改写成适合你的难度（每天的 AI 次数有上限）。');
        mk.disabled = true; mk.innerHTML = '<span class="spin"></span> 正在改写…';
        try { const r = await api('/api/next/variant', { pack: id, level: m.user_level, request_id: rid('nv') }); m.variant = { level: r.level, body: r.body, notes: r.notes }; m.original = m.sentences; m.sentences = splitSentences(r.body); m.can_variant = false; read(); toast(r.cached ? '已打开改写版' : '改写好了'); }
        catch (e) { toast(e.message); mk.disabled = false; mk.textContent = `改写成 ${m.user_level} 难度`; }
      };
      pane.querySelectorAll('.w').forEach(w => w.onclick = () => { if (!String(getSelection()).trim()) lookupSheet(w.dataset.w, ls[Number(w.dataset.s)], id); });
      pane.querySelectorAll('[data-sv]').forEach(b => b.onclick = () => { const v = m.vocabulary[Number(b.dataset.sv)]; saveCard({ text: v.term, meaning: v.meaning, context: findContext(v.term, ls) || v.example, pack: id }, b); });
      pane.querySelectorAll('[data-sn]').forEach(b => b.onclick = () => { const v = m.variant.notes[Number(b.dataset.sn)]; saveCard({ text: v.text, meaning: v.meaning, context: findContext(v.text, ls), pack: id }, b); });
      pane.querySelector('#toCheck').onclick = () => { markStep('read'); go('check'); };
    }

    /* check */
    function check() {
      if (!m.questions.length) { pane.innerHTML = '<div class="empty">这篇没有理解题。</div><div class="row between"><span></span><button class="btn primary" id="toOut">去用出来 →</button></div>'; pane.querySelector('#toOut').onclick = () => { markStep('check'); go('output'); }; return; }
      const answered = {};
      pane.innerHTML = `<div class="stack">${m.questions.map((q, i) => `<div class="card flat q" data-q="${i}"><div class="tiny muted">第 ${i + 1} / ${m.questions.length} 题</div><div class="prompt">${esc(q.prompt)}</div>
        ${q.options.map((o, j) => `<button class="ans" data-q="${i}" data-o="${j}"><span class="k">${'ABCD'[j]}</span><span>${esc(o)}</span></button>`).join('')}<div class="fb"></div></div>`).join('')}
        <div id="score"></div></div>`;
      pane.querySelectorAll('.ans').forEach(b => b.onclick = async () => {
        const i = Number(b.dataset.q), j = Number(b.dataset.o);
        if (answered[i] != null) return;
        answered[i] = j;
        const box = pane.querySelector(`.q[data-q="${i}"]`);
        box.querySelectorAll('.ans').forEach(x => x.disabled = true);
        try {
          const r = await api('/api/next/check', { pack: id, index: i, choice: j });
          answered[i] = r.correct;
          box.querySelector(`[data-o="${r.answer}"]`).classList.add('right');
          if (!r.correct) b.classList.add('wrong');
          box.querySelector('.fb').innerHTML = `<p class="small"><b>${r.correct ? '答对了。' : '再看看原文这句：'}</b></p>${r.evidence ? `<div class="evidence">${esc(r.evidence)}</div>` : ''}`;
          if (Object.keys(answered).length === m.questions.length) {
            const right = Object.values(answered).filter(Boolean).length;
            markStep('check');
            pane.querySelector('#score').innerHTML = `<div class="card sunk row between"><span><b>${right} / ${m.questions.length}</b> 题答对</span><button class="btn primary" id="toOut">去用出来 →</button></div>`;
            pane.querySelector('#toOut').onclick = () => go('output');
          }
        } catch (e) { toast(e.message); delete answered[i]; box.querySelectorAll('.ans').forEach(x => x.disabled = false); }
      });
    }

    /* output */
    function output() {
      const key = 'flow-next-draft-' + id;
      const draft = load(key) || '';
      pane.innerHTML = `<div class="stack"><div class="card flat task"><div class="kicker">用出来</div><b>${esc(m.task.prompt)}</b>
          ${m.task.model ? `<div class="model">${esc(m.task.model)} <button class="icon-btn" id="sayModel" aria-label="朗读参考句">${ICON.speak}</button></div>` : ''}
          ${m.task.hint ? `<div class="muted small">${esc(m.task.hint)}</div>` : ''}</div>
        <label class="field">你的英文<textarea id="ans" maxlength="600" placeholder="写一两句就好，写错没关系。">${esc(draft)}</textarea></label>
        <div class="row between"><span class="counter" id="cnt">${draft.length} / 600</span><button class="btn primary" id="go">让 AI 帮我改</button></div>
        <p class="err" id="outErr" role="alert"></p><div id="result"></div></div>`;
      const ta = pane.querySelector('#ans');
      ta.oninput = () => { save(key, ta.value); pane.querySelector('#cnt').textContent = ta.value.length + ' / 600'; };
      const sm = pane.querySelector('#sayModel'); if (sm) sm.onclick = () => TTS.say(m.task.model);
      pane.querySelector('#go').onclick = async () => {
        const text = ta.value.trim(), err = pane.querySelector('#outErr'); err.textContent = '';
        if (!/[A-Za-z]{2,}.*\s+.*[A-Za-z]/.test(text)) { err.textContent = '先用英文写一个短句。'; return; }
        if (!S.user) return needLogin('登录后 AI 会帮你改写，并给出三种更好的说法。');
        const btn = pane.querySelector('#go'); btn.disabled = true; btn.innerHTML = '<span class="spin"></span> 正在看你写的…';
        try {
          const r = await api('/api/next/rewrite', { pack: id, text, request_id: rid('nr') });
          markStep('output'); renderResult(r.result, text, r.remaining);
        } catch (e) { err.textContent = e.message; }
        btn.disabled = false; btn.textContent = '再改一次';
      };
    }
    function renderResult(r, yours, remaining) {
      const box = pane.querySelector('#result');
      const same = r.corrected.trim() === yours.trim();
      box.innerHTML = `<div class="result">
        <div class="card verdict ${esc(r.verdict)}"><span class="dot"></span><div>${esc(r.summary)}</div></div>
        <div class="card compare"><div class="kicker">${same ? '你写的已经是对的' : '改对之后'}</div>
          ${same ? '' : `<div class="yours">${esc(yours)}</div>`}<div class="fixed">${esc(r.corrected)} <button class="icon-btn" data-say-text="${esc(r.corrected)}" aria-label="朗读">${ICON.speak}</button></div>
          ${r.changes.length ? `<div>${r.changes.map(c => `<div class="change"><span class="ft"><del>${esc(c.from)}</del> → <ins>${esc(c.to)}</ins></span><span class="why">${esc(c.why)}</span></div>`).join('')}</div>` : ''}</div>
        <div class="stack-s"><h2 class="h2">还可以这样说</h2>${r.versions.map((v, i) => `<div class="version"><div class="row between"><span class="pill green">${esc(v.label)}</span><span class="row"><button class="icon-btn" data-say-text="${esc(v.text)}" aria-label="朗读">${ICON.speak}</button><button class="icon-btn" data-keep-v="${i}" aria-label="收藏这句">${ICON.star}</button></span></div><div class="v">${esc(v.text)}</div><div class="small muted">${esc(v.why)}</div></div>`).join('')}</div>
        ${r.keep ? `<div class="card sunk row between"><div><div class="kicker">值得收藏</div><b class="text">${esc(r.keep.text)}</b> <span class="muted small">${esc(r.keep.meaning)}</span></div><button class="btn small primary" id="keep">收藏</button></div>` : ''}
        <div class="card done-card"><div class="big">🌱</div><h2 class="h2">这篇完成了</h2><p class="muted small">${remaining != null ? '今天还可以用 AI ' + remaining + ' 次。' : ''}收藏的表达会在合适的时候出现在复习里。</p>
          <div class="row center"><a class="btn" href="#/cards">看表达库</a><a class="btn primary" href="#/">回到今日</a></div></div></div>`;
      box.querySelectorAll('[data-say-text]').forEach(b => b.onclick = () => TTS.say(b.dataset.sayText));
      box.querySelectorAll('[data-keep-v]').forEach(b => b.onclick = () => { const v = r.versions[Number(b.dataset.keepV)]; saveCard({ text: v.text, meaning: v.label + '：' + v.why, context: '', pack: id }, b); });
      const k = box.querySelector('#keep'); if (k) k.onclick = () => saveCard({ text: r.keep.text, meaning: r.keep.meaning, context: r.corrected, pack: id }, k);
      box.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
    ({ listen, read, check, output })[st.step]();

    // Selection → save a phrase (reading step).
    const onSel = () => {
      if (st.step !== 'read') return;
      const sel = getSelection(); const t = String(sel).replace(/\s+/g, ' ').trim();
      const reader = pane.querySelector('#reader');
      if (!t || t.length > 160 || !/[A-Za-z]/.test(t) || !reader || !reader.contains(sel.anchorNode)) { hideSelbar(); return; }
      const sentEl = sel.anchorNode.parentElement && sel.anchorNode.parentElement.closest('.sent');
      SEL.text = t; SEL.context = sentEl ? lines()[Number(sentEl.dataset.si)] : '';
      if (!selbar) { selbar = document.createElement('div'); selbar.className = 'selbar'; document.body.appendChild(selbar); }
      selbar.innerHTML = `<span>${esc(t)}</span><button type="button">收藏</button>`;
      selbar.querySelector('button').onclick = () => { saveCard({ text: SEL.text, context: SEL.context, pack: id }); sel.removeAllRanges(); hideSelbar(); };
    };
    document.onselectionchange = () => { clearTimeout(onSel.t); onSel.t = setTimeout(onSel, 250); };
  }
  function splitSentences(body) { return body.split(/(?<=[.!?]["”’]?)\s+/).map(s => s.trim()).filter(Boolean); }
  function findContext(term, ls) { const t = term.toLowerCase(); return ls.find(s => s.toLowerCase().includes(t)) || ''; }

  async function lookupSheet(word, sentence, pack) {
    openSheet(`<p class="loading"><span class="spin"></span></p>`);
    let e = null;
    try { e = (await api('/api/next/lookup?w=' + encodeURIComponent(word))).entry; } catch (x) { /* show fallback */ }
    const meaning = e ? e.meaning : '';
    openSheet(`<div class="stack">
      <div class="row between"><div><div class="word" id="sheetTitle">${esc(e ? e.word : word)}</div><div class="ph">${esc(e ? e.phonetic : '')}${e && e.lemma !== word.toLowerCase() ? ' · 原形 ' + esc(e.lemma) : ''}</div></div>
        <button class="icon-btn" id="sayW" aria-label="朗读">${ICON.speak}</button></div>
      <div class="mean">${e ? esc(meaning).replace(/；|;/g, '<br>') : '<span class="muted">词典里没有这个词，可以先收藏，复习时再查。</span>'}</div>
      ${e && e.example ? `<div class="small muted text">${esc(e.example)}</div>` : ''}
      <div class="card sunk small text">${esc(sentence)}</div>
      <div class="row"><button class="btn primary" id="saveW">${ICON.star.replace('<svg', '<svg width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.8"')}收藏这个词</button><button class="btn" id="saveS">收藏整句</button></div>
      <button class="btn ghost" data-close>关闭</button></div>`, card => {
      card.querySelector('#sayW').onclick = () => TTS.say(e ? e.word : word);
      card.querySelector('#saveW').onclick = () => saveCard({ text: e ? e.lemma : word, meaning, context: sentence, pack }).then(ok => ok && closeSheet());
      card.querySelector('#saveS').onclick = () => saveCard({ text: sentence, meaning: '', context: '', pack }).then(ok => ok && closeSheet());
    });
    TTS.say(e ? e.word : word);
  }
  async function saveCard(c, btn) {
    if (!S.user) { needLogin('登录后才能收藏表达，并在合适的时间提醒你复习。'); return false; }
    try {
      const r = await api('/api/next/cards', c);
      toast(r.existing ? '已经在表达库里了，已更新' : '已收藏到表达库');
      if (btn) btn.classList.add('on');
      return true;
    } catch (e) { toast(e.message); return false; }
  }

  /* ---------- cards ---------- */
  function highlight(ctx, text) {
    if (!ctx) return '';
    const i = ctx.toLowerCase().indexOf(text.toLowerCase());
    return i < 0 ? esc(ctx) : esc(ctx.slice(0, i)) + '<mark>' + esc(ctx.slice(i, i + text.length)) + '</mark>' + esc(ctx.slice(i + text.length));
  }
  async function cardsView(q, page) {
    if (!S.user) {
      view.innerHTML = `<h1 class="h1">表达库</h1><div class="empty"><div class="big">☆</div><p>读的时候点一下单词，或者选中一段话，就能收进表达库。<br>登录后，它们会按遗忘规律出现在复习里。</p><button class="btn primary" id="lg">登录 / 注册</button></div>`;
      document.getElementById('lg').onclick = () => openLogin(); return;
    }
    q = q || ''; page = page || 1;
    const [list, due] = await Promise.all([api('/api/next/cards?q=' + encodeURIComponent(q) + '&page=' + page), api('/api/next/review')]);
    const pages = Math.max(1, Math.ceil(list.total / list.per));
    view.innerHTML = `<div class="row between"><div><h1 class="h1">表达库</h1><span class="muted small">共 ${list.total} 个</span></div>
        ${due.due ? `<a class="btn primary" href="#/review">复习 ${due.due} 个</a>` : '<span class="pill green">今天的都复习完了</span>'}</div>
      <form class="searchrow" id="sf"><input type="search" name="q" placeholder="搜索单词、意思或原句" value="${esc(q)}"><button class="btn">搜索</button></form>
      ${list.items.length ? `<div class="grid-list">${list.items.map(c => `<div class="card flat xcard"><div class="row between"><span class="x">${esc(c.text)}</span>
          <span class="row"><button class="icon-btn" data-say="${esc(c.text)}" aria-label="朗读">${ICON.speak}</button><button class="icon-btn" data-del="${c.id}" aria-label="删除">${ICON.trash}</button></span></div>
          ${c.meaning ? `<div class="small">${esc(c.meaning)}</div>` : ''}${c.context ? `<div class="ctx">${highlight(c.context, c.text)}</div>` : ''}
          <div class="tiny muted">${c.reps ? `已复习 ${c.reps} 次 · ${dueText(c.due)}` : '还没复习过'}</div></div>`).join('')}</div>`
        : `<div class="empty"><div class="big">☆</div><p>${q ? '没有找到。' : '还没有收藏。学一篇材料时，点单词或选中一段话就能收藏。'}</p>${q ? '' : '<a class="btn primary" href="#/">去学今天的一篇</a>'}</div>`}
      ${pages > 1 ? `<div class="pager"><button class="btn small" id="pv" ${page <= 1 ? 'disabled' : ''}>上一页</button><span class="muted small">${page} / ${pages}</span><button class="btn small" id="nx" ${page >= pages ? 'disabled' : ''}>下一页</button></div>` : ''}`;
    document.getElementById('sf').onsubmit = e => { e.preventDefault(); cardsView(e.target.q.value.trim(), 1); };
    view.querySelectorAll('[data-say]').forEach(b => b.onclick = () => TTS.say(b.dataset.say));
    view.querySelectorAll('[data-del]').forEach(b => b.onclick = async () => { if (!confirm('从表达库删除这一条？')) return; try { await api('/api/next/cards/delete', { id: Number(b.dataset.del) }); cardsView(q, page); } catch (e) { toast(e.message); } });
    const pv = document.getElementById('pv'), nx = document.getElementById('nx');
    if (pv) pv.onclick = () => cardsView(q, page - 1); if (nx) nx.onclick = () => cardsView(q, page + 1);
  }
  function dueText(t) { const d = (t * 1000 - Date.now()) / 86400000; return d <= 0 ? '该复习了' : d < 1 ? '今天晚些时候复习' : `${Math.round(d)} 天后复习`; }

  /* ---------- review ---------- */
  async function reviewView() {
    if (!S.user) return needLogin('登录后才能复习你收藏的表达。');
    const q = await api('/api/next/review');
    const items = q.items; let i = 0; const tally = { again: 0, hard: 0, good: 0, easy: 0 };
    if (!items.length) { view.innerHTML = `<div class="empty"><div class="big">✓</div><p>现在没有要复习的表达。</p><a class="btn primary" href="#/">回到今日</a></div>`; return; }
    function show(revealed) {
      if (i >= items.length) {
        refreshHome().catch(() => {});
        view.innerHTML = `<div class="card done-card"><div class="big">🎉</div><h2 class="h2">复习完了 ${items.length} 个</h2><p class="muted small">记得 ${tally.good + tally.easy} · 模糊 ${tally.hard} · 忘了 ${tally.again}。忘了的会在 10 分钟后再出现一次。</p><div class="row center"><a class="btn" href="#/cards">表达库</a><a class="btn primary" href="#/">回到今日</a></div></div>`;
        return;
      }
      const c = items[i];
      const pos = c.context ? c.context.toLowerCase().indexOf(c.text.toLowerCase()) : -1;
      const front = pos >= 0
        ? `<div class="cloze">${esc(c.context.slice(0, pos))}<span class="gap ${revealed ? 'open' : ''}" aria-label="${revealed ? '' : '空格'}">${revealed ? esc(c.context.slice(pos, pos + c.text.length)) : '\u00a0'.repeat(Math.max(4, Math.min(c.text.length, 24)))}</span>${esc(c.context.slice(pos + c.text.length))}</div><div class="hint">${revealed ? '' : (c.meaning ? '提示：' + esc(c.meaning.slice(0, 60)) : '想想空里是什么')}</div>`
        : `<div class="hint">${c.meaning ? esc(c.meaning) : '回忆这个表达'}</div><div class="cloze">${revealed ? esc(c.text) : '<span class="gap">？</span>'}</div>`;
      view.innerHTML = `<div class="bar-progress"><i id="rp"></i></div><div class="review">${front}
        ${revealed ? `<div class="stack-s">${c.meaning && pos >= 0 ? `<div class="small">${esc(c.meaning)}</div>` : ''}<div><button class="icon-btn" id="say" aria-label="朗读">${ICON.speak}</button></div></div>
          <div class="rate"><button class="again" data-r="again">忘了<small>10 分钟后</small></button><button data-r="hard">模糊<small>明天</small></button><button class="good" data-r="good">记得<small>${c.reps === 0 ? '明天' : c.reps === 1 ? '3 天后' : '更久以后'}</small></button><button data-r="easy">很熟<small>更久以后</small></button></div>`
          : '<button class="btn primary block" id="reveal">显示答案</button>'}</div>
        <p class="muted tiny tc">${i + 1} / ${items.length}</p>`;
      document.getElementById('rp').style.width = (i / items.length * 100) + '%';
      const rv = document.getElementById('reveal'); if (rv) rv.onclick = () => { show(true); TTS.say(pos >= 0 ? c.context : c.text); };
      const say = document.getElementById('say'); if (say) say.onclick = () => TTS.say(pos >= 0 ? c.context : c.text);
      view.querySelectorAll('[data-r]').forEach(b => b.onclick = async () => {
        view.querySelectorAll('[data-r]').forEach(x => x.disabled = true);
        try { await api('/api/next/review', { id: c.id, rating: b.dataset.r }); tally[b.dataset.r]++; i++; show(false); }
        catch (e) { toast(e.message); view.querySelectorAll('[data-r]').forEach(x => x.disabled = false); }
      });
    }
    show(false);
  }

  /* ---------- library ---------- */
  async function libraryView(f) {
    f = f || { level: '', theme: '', page: 1 };
    const d = await api(`/api/next/library?level=${f.level}&theme=${f.theme}&page=${f.page}`);
    const pages = Math.max(1, Math.ceil(d.total / d.per));
    view.innerHTML = `<h1 class="h1">全部材料</h1><span class="muted small">${d.total} 篇</span>
      <div class="filters"><select id="fl" aria-label="难度"><option value="">全部难度</option>${['A2', 'B1', 'B2'].map(l => `<option ${f.level === l ? 'selected' : ''}>${l}</option>`).join('')}</select>
        <select id="ft" aria-label="话题"><option value="">全部话题</option>${Object.entries(d.themes).map(([k, v]) => `<option value="${k}" ${f.theme === k ? 'selected' : ''}>${esc(v)}</option>`).join('')}</select></div>
      <div class="grid-list">${d.items.map(m => miniCard(m, m.daily ? '热点' : '')).join('')}</div>
      ${pages > 1 ? `<div class="pager"><button class="btn small" id="pv" ${f.page <= 1 ? 'disabled' : ''}>上一页</button><span class="muted small">${f.page} / ${pages}</span><button class="btn small" id="nx" ${f.page >= pages ? 'disabled' : ''}>下一页</button></div>` : ''}`;
    document.getElementById('fl').onchange = e => libraryView({ ...f, level: e.target.value, page: 1 });
    document.getElementById('ft').onchange = e => libraryView({ ...f, theme: e.target.value, page: 1 });
    const pv = document.getElementById('pv'), nx = document.getElementById('nx');
    if (pv) pv.onclick = () => { scrollTo(0, 0); libraryView({ ...f, page: f.page - 1 }); };
    if (nx) nx.onclick = () => { scrollTo(0, 0); libraryView({ ...f, page: f.page + 1 }); };
  }

  /* ---------- me ---------- */
  async function meView() {
    if (!S.meta) S.meta = await api('/api/next/meta');
    const p = (S.home && S.home.profile) || S.guest || {};
    const lv = S.meta.levels.find(l => l.id === p.level), goal = S.meta.goals.find(g => g.id === p.goal);
    const themes = S.meta.themes.filter(t => (p.themes || []).includes(t.id)).map(t => t.label);
    const st = S.home && S.home.stats;
    view.innerHTML = `<h1 class="h1">${S.user ? esc(S.user.username) : '我的'}</h1>
      ${S.user ? '' : `<div class="card sunk section stack-s"><b>还没有登录</b><span class="muted small">登录后才能保存进度、收藏表达和使用 AI 改写。</span><div><button class="btn primary small" id="lg">登录 / 注册</button></div></div>`}
      ${st ? `<div class="stat-grid section"><div class="card flat stat"><b>${st.week.filter(d => d.active).length}</b><span class="tiny muted">本周学习天数</span></div><div class="card flat stat"><b>${st.materials_done}</b><span class="tiny muted">学完的材料</span></div><div class="card flat stat"><b>${st.cards}</b><span class="tiny muted">收藏的表达</span></div></div>` : ''}
      <div class="card flat section stack-s"><div class="row between"><b>学习设置</b><a class="link small" href="#/welcome/edit">修改</a></div>
        <div class="small">水平：${lv ? esc(lv.label) + '（' + lv.id + '）' : '未设置'}</div><div class="small">目标：${goal ? esc(goal.label) : '未设置'}</div>
        <div class="small">话题：${themes.length ? esc(themes.join('、')) : '随机'}</div><div class="small">每天：${p.minutes || 10} 分钟</div></div>
      <div class="card flat section list">
        <a href="/survey">参与匿名问卷：你想要什么样的英语学习网站 <span>→</span></a>
        <a href="/">回到经典版（私教、知识图谱、诊断）<span>→</span></a>
        ${S.user ? '<button id="out">退出登录 <span>→</span></button>' : ''}</div>
      <p class="muted tiny section">这是语流新版的试用版。学习记录与经典版共用同一个账号。</p>`;
    const lg = document.getElementById('lg'); if (lg) lg.onclick = () => openLogin();
    const out = document.getElementById('out');
    if (out) out.onclick = async () => { try { await api('/api/logout', {}); } catch (e) { /* ignore */ } S.user = null; S.csrf = ''; await refreshHome(); toast('已退出'); route(); };
  }

  /* ---------- boot ---------- */
  (async function boot() {
    try { await refreshSession(); } catch (e) { /* offline guest */ }
    route();
  })();
})();

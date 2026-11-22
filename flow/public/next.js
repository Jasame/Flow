'use strict';
/* Flow — one learning loop: listen → read → check → use it → review what you saved,
   steered by the knowledge graph (18 grammar nodes) and AI. See NEXT.md. */
(function () {
  const view = document.getElementById('view');
  const bar = document.getElementById('bar');
  const sheetEl = document.getElementById('sheet');
  const sheetCard = document.getElementById('sheetCard');
  const toastEl = document.getElementById('toast');
  const S = { user: null, csrf: '', meta: null, home: null, homeFresh: false, guest: load('flow-next-guest'), lastRoute: '', voice: load('flow-next-voice') || 'us-f' };
  const VOICE_LABELS = { 'us-f': '美音 · 女', 'us-m': '美音 · 男', 'uk-f': '英音 · 女', 'uk-m': '英音 · 男' };
  const STEP = { listen: '听', read: '读', check: '理解', output: '用出来' };
  const STEPS = Object.keys(STEP);
  const REDUCED = matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* ---------- utilities ---------- */
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])); }
  function load(k) { try { return JSON.parse(localStorage.getItem(k) || 'null'); } catch (e) { return null; } }
  function save(k, v) { try { v == null ? localStorage.removeItem(k) : localStorage.setItem(k, JSON.stringify(v)); } catch (e) { /* private mode */ } }
  function rid(prefix) { return prefix + '-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 10); }
  function toast(msg) { toastEl.textContent = msg; toastEl.classList.add('show'); clearTimeout(toast.t); toast.t = setTimeout(() => toastEl.classList.remove('show'), 2400); }
  async function api(path, body) {
    const opt = { credentials: 'same-origin', headers: {} };
    if (body !== undefined) { opt.method = 'POST'; opt.headers['Content-Type'] = 'application/json'; if (S.csrf) opt.headers['X-CSRF-Token'] = S.csrf; opt.body = JSON.stringify(body); }
    let r;
    try { r = await fetch(path, opt); } catch (x) { const e = new Error('网络连接失败，请检查网络'); e.network = true; throw e; }
    const j = await r.json().catch(() => ({}));
    if (!r.ok) { const e = new Error(j.error || ('请求失败（' + r.status + '）')); e.status = r.status; throw e; }
    return j;
  }
  const ICON = {
    play: '<svg viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>',
    speak: '<svg viewBox="0 0 24 24"><path d="M4 10v4h4l5 4V6L8 10zM16 9a4 4 0 0 1 0 6M18.5 6.5a8 8 0 0 1 0 11"/></svg>',
    eye: '<svg viewBox="0 0 24 24"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/></svg>',
    star: '<svg viewBox="0 0 24 24"><path d="m12 3 2.8 5.8 6.2.9-4.5 4.4 1 6.2L12 17.4l-5.5 2.9 1-6.2L3 9.7l6.2-.9z"/></svg>',
    trash: '<svg viewBox="0 0 24 24"><path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13"/></svg>',
    stop: '<svg viewBox="0 0 24 24"><rect x="6.5" y="6.5" width="11" height="11" rx="2"/></svg>',
  };
  const playIcon = (on, size) => (on ? ICON.stop : ICON.play).replace('<svg', `<svg width="${size || 18}" height="${size || 18}" fill="currentColor"`);
  const skeleton = () => '<div class="skeleton" aria-hidden="true"><i class="t"></i><i class="s"></i><i class="b"></i><i></i><i></i><i class="s"></i></div>';
  const doneRing = '<svg class="done-ring" viewBox="0 0 72 72" aria-hidden="true"><circle cx="36" cy="36" r="30"/><path d="M24 37l8 8 16-17"/></svg>';
  function level() { return (S.home && S.home.level) || (S.guest && S.guest.level) || 'B1'; }
  function hasProfile() { return S.user ? !!(S.home && S.home.profile) || !!(S.guest && S.guest.level) : !!(S.guest && S.guest.level); }
  function guestQuery(first) {
    if (S.user) return '';
    const g = S.guest || {};
    return (first ? '?' : '&') + 'level=' + encodeURIComponent(g.level || 'B1') + (g.themes && g.themes.length ? '&themes=' + encodeURIComponent(g.themes.join(',')) : '');
  }
  function enter(el) { if (!el) return; el.classList.remove('enter'); void el.offsetWidth; el.classList.add('enter'); }
  function nodeChip(n) { return `<a class="node-chip st st-${esc(n.status || 'untouched')}" href="#/graph/${encodeURIComponent(n.id || n.node)}">${esc(n.title)}</a>`; }
  // Input: coarse pointer = finger. Hover-only affordances and keyboard hints are adjusted for it.
  const TOUCH = matchMedia('(pointer: coarse)').matches;
  const isTyping = e => !!(e && e.target && e.target.closest && e.target.closest('input:not([type=checkbox]):not([type=radio]),textarea,select,[contenteditable]'));
  const srEl = document.getElementById('sr');
  function announce(t) { if (!srEl || !t) return; srEl.textContent = ''; setTimeout(() => { srEl.textContent = t; }, 40); }
  // Scroll so an element sits just below the sticky header (and the study step bar when there is one).
  function bringIntoView(el, smooth) {
    if (!el) return;
    const steps = view.querySelector('.steps');
    const off = bar.offsetHeight + (steps && !steps.contains(el) ? steps.offsetHeight : 0) + 10;
    scrollTo({ top: Math.max(0, el.getBoundingClientRect().top + scrollY - off), behavior: smooth === false || REDUCED ? 'auto' : 'smooth' });
  }

  /* ---------- speech (with word boundaries for read-along highlighting) ---------- */
  const TTS = {
    ok: 'speechSynthesis' in window, rate: Number(load('flow-next-rate')) || 1, voice: null, token: 0,
    pick() {
      if (!this.ok) return null;
      const vs = speechSynthesis.getVoices().filter(v => /^en[-_]/i.test(v.lang));
      const pref = ['Samantha', 'Google US English', 'Microsoft Aria', 'Microsoft Jenny', 'Karen', 'Daniel', 'Google UK English Female'];
      this.voice = pref.map(n => vs.find(v => v.name.includes(n))).find(Boolean) || vs.find(v => /en-US/i.test(v.lang)) || vs[0] || null;
      return this.voice;
    },
    say(text, onend, onword) {
      if (!this.ok) { toast('这个浏览器不支持朗读'); return; }
      speechSynthesis.cancel();
      const u = new SpeechSynthesisUtterance(text);
      u.lang = 'en-US'; u.rate = this.rate; const v = this.voice || this.pick(); if (v) u.voice = v;
      const t = ++this.token;
      if (onword) u.onboundary = e => { if (t === this.token && e.name !== 'sentence') onword(e.charIndex); };
      u.onend = () => { if (t === this.token && onend) onend(); };
      speechSynthesis.speak(u);
    },
    stop() { this.token++; if (this.ok) speechSynthesis.cancel(); },
  };
  if (TTS.ok) speechSynthesis.onvoiceschanged = () => TTS.pick();
  // Words of one sentence as spans that know their character offset, so boundary events can light them up.
  function wordSpans(sentence, cls, extra) {
    let html = '', off = 0;
    sentence.split(/([A-Za-z]+(?:'[A-Za-z]+)?)/).forEach((part, k) => {
      if (k % 2 === 0) html += esc(part);
      else html += `<span class="${cls(part)}" data-c="${off}" data-w="${esc(part)}"${extra || ''}>${esc(part)}</span>`;
      off += part.length;
    });
    return html;
  }
  function lightWord(container, charIndex) {
    let cur = null;
    container.querySelectorAll('[data-c]').forEach(el => { if (Number(el.dataset.c) <= charIndex) cur = el; });
    container.querySelectorAll('.cur').forEach(el => el.classList.remove('cur'));
    if (cur) cur.classList.add('cur');
  }

  /* ---------- narration: pre-generated Kokoro audio + timings (sentence exact, words estimated) ---------- */
  const NAR = {
    audio: new Audio(), meta: null, key: '', raf: 0, stopAt: null, onTick: null, onEnd: null,
    async load(id, voice, version) {
      const key = voice + '/' + id + '@' + version;
      if (this.key === key && this.meta) return true;
      this.stop(); this.meta = null; this.key = '';
      try {
        const r = await fetch(`/audio/${voice}/${encodeURIComponent(id)}.json?v=${version}`);
        if (!r.ok) return false;
        this.meta = await r.json(); this.key = key;
        this.audio.preload = 'auto'; this.audio.src = `/audio/${voice}/${encodeURIComponent(id)}.mp4?v=${version}`;
        return true;
      } catch (e) { return false; }
    },
    play(from, to, onTick, onEnd) {
      this.stopLoop(); this.stopAt = to; this.onTick = onTick; this.onEnd = onEnd;
      this.audio.playbackRate = TTS.rate; this.audio.preservesPitch = true;
      try { this.audio.currentTime = from; } catch (e) { /* not seekable yet */ }
      this.audio.play().catch(() => { toast('音频暂时无法播放，改用浏览器朗读'); this.finish(); });
      const loop = () => {
        const t = this.audio.currentTime;
        if (this.onTick) this.onTick(t);
        if ((this.stopAt != null && t >= this.stopAt) || this.audio.ended) { this.audio.pause(); this.finish(); return; }
        this.raf = requestAnimationFrame(loop);
      };
      this.raf = requestAnimationFrame(loop);
    },
    finish() { this.stopLoop(); const cb = this.onEnd; this.onEnd = null; this.onTick = null; if (cb) cb(); },
    stopLoop() { cancelAnimationFrame(this.raf); this.raf = 0; },
    stop() { this.stopLoop(); this.onEnd = null; this.onTick = null; try { this.audio.pause(); } catch (e) { /* ignore */ } },
    // -> [sentence index, char offset of the current word] at time t
    locate(t) {
      const ss = this.meta.sentences; let si = -1;
      for (let i = 0; i < ss.length; i++) { if (t >= ss[i].s - 0.02 && t < ss[i].e + 0.25) { si = i; break; } if (t < ss[i].s) break; }
      if (si < 0) return [-1, null];
      let wc = null; for (const w of ss[si].w) { if (t >= w[1]) wc = w[0]; else break; }
      return [si, wc];
    },
  };
  function lightAt(container, charOffset) {
    container.querySelectorAll('.cur').forEach(el => el.classList.remove('cur'));
    if (charOffset == null) return;
    const el = container.querySelector(`[data-c="${charOffset}"]`); if (el) el.classList.add('cur');
  }
  /* ---------- short clips: a word's pronunciation, or one sentence from a material's narration ---------- */
  const CLIP = {
    audio: new Audio(), raf: 0, metas: {}, want: null,
    accent() { return (S.voice || 'us-f').startsWith('uk') ? 'uk' : 'us'; },
    stop() { cancelAnimationFrame(this.raf); this.want = null; try { this.audio.pause(); } catch (e) { /* ignore */ } },
    play(src, from, to) {
      NAR.stop(); TTS.stop(); this.stop();
      const a = this.audio, want = this.want = { from, to };
      const go = () => {
        if (this.want !== want) return;
        try { a.currentTime = from; } catch (e) { /* not seekable yet */ }
        a.playbackRate = TTS.rate; a.play().catch(() => {});
        const loop = () => { if (this.want !== want) return; if (a.currentTime >= to || a.ended) { a.pause(); return; } this.raf = requestAnimationFrame(loop); };
        this.raf = requestAnimationFrame(loop);
      };
      if (a.getAttribute('src') !== src) { a.preload = 'auto'; a.setAttribute('src', src); a.addEventListener('loadedmetadata', go, { once: true }); a.load(); } else go();
    },
    // c: {text, audio: {us: [sprite, start, end], uk: [...]}}; falls back to the browser voice
    word(c) {
      const au = c.audio || {}, ac = au[this.accent()] ? this.accent() : au.us ? 'us' : au.uk ? 'uk' : null;
      if (!ac) { TTS.say(c.text); return; }
      const w = au[ac]; this.play(`/audio/words/${ac}/${w[0]}.mp4`, w[1], w[2]);
    },
    // ex: {pack, i, text, audio: narration version or 0}
    async sentence(ex) {
      if (!ex.audio) { TTS.say(ex.text); return; }
      const key = S.voice + '/' + ex.pack;
      try {
        if (!this.metas[key]) { const r = await fetch(`/audio/${S.voice}/${encodeURIComponent(ex.pack)}.json?v=${ex.audio}`); if (!r.ok) throw new Error('no timing'); this.metas[key] = await r.json(); }
        const s = this.metas[key].sentences[ex.i]; if (!s) throw new Error('no sentence');
        this.play(`/audio/${S.voice}/${encodeURIComponent(ex.pack)}.mp4?v=${ex.audio}`, s.s, s.e + 0.05);
      } catch (e) { TTS.say(ex.text); }
    },
  };
  /* ---------- mini player: while a whole text plays, a stop button stays on screen however far the text scrolls ---------- */
  const MINI = {
    el: null,
    show(label, onStop) {
      if (!this.el) { this.el = document.createElement('div'); this.el.className = 'mini-player'; this.el.setAttribute('role', 'region'); this.el.setAttribute('aria-label', '播放控制'); document.body.appendChild(this.el); }
      this.el.innerHTML = `<span class="eq" aria-hidden="true"><i></i><i></i><i></i></span><span class="lbl"></span><button type="button" class="stop">${playIcon(true, 15)}<span>停止</span></button>`;
      this.el.querySelector('.lbl').textContent = label;
      this.el.querySelector('.stop').onclick = () => { this.hide(); onStop(); };
      this.el.hidden = false; document.body.classList.add('playing');
    },
    update(label) { if (this.el && !this.el.hidden) this.el.querySelector('.lbl').textContent = label; },
    hide() { if (this.el) this.el.hidden = true; document.body.classList.remove('playing'); },
  };
  /* ---------- offline: reviews done without a connection are queued and synced with the time they happened ---------- */
  const OUTBOX = {
    key: 'flow-next-outbox',
    list() { return load(this.key) || []; },
    push(item) { const l = this.list(); l.push(item); save(this.key, l.slice(-500)); },
    async flush() {
      if (this.busy || !S.user || !navigator.onLine) return 0;
      this.busy = true; let sent = 0;
      try {
        let l = this.list();
        while (l.length) {
          const it = l[0];
          try { await api(it.path, it.body); } catch (e) { if (e.network) break; /* rejected (e.g. card deleted): drop it */ }
          l = this.list().slice(1); save(this.key, l); sent++;
        }
      } finally { this.busy = false; }
      if (sent) { toast(`已同步 ${sent} 条离线复习记录`); refreshHome().catch(() => {}); }
      return sent;
    },
  };
  window.addEventListener('online', () => OUTBOX.flush());
  // Ask the service worker to keep today's audio (word sprites, example narration) for weak or no network.
  function prefetchAudio(urls) {
    const list = [...new Set(urls)].filter(Boolean).slice(0, 40);
    if (list.length && navigator.serviceWorker && navigator.serviceWorker.controller) navigator.serviceWorker.controller.postMessage({ type: 'prefetch', urls: list });
  }
  let installPrompt = null;
  window.addEventListener('beforeinstallprompt', e => { e.preventDefault(); installPrompt = e; });

  // FSRS forgetting curve (same constants as fsrs.py): chance of recall t days after a review with stability s.
  const DECAY = -0.1542, FACTOR = Math.pow(0.9, 1 / DECAY) - 1;
  const recallAt = (s, t) => Math.pow(1 + FACTOR * Math.max(0, t) / s, DECAY);
  async function setVoice(v) {
    S.voice = v; save('flow-next-voice', v);
    if (S.user) { try { await api('/api/next/voice', { voice: v }); } catch (e) { /* keep local choice */ } }
  }
  function voiceChips(available) {
    return `<div class="voices" role="radiogroup" aria-label="朗读声音">${Object.entries(VOICE_LABELS).map(([k, l]) =>
      `<button class="chip small" role="radio" data-voice="${k}" aria-checked="${S.voice === k}" aria-pressed="${S.voice === k}" ${available && !available.includes(k) ? 'disabled' : ''}>${l}</button>`).join('')}</div>`;
  }

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

  /* ---------- welcome ---------- */
  async function welcome(edit) {
    if (!S.meta) S.meta = await api('/api/next/meta');
    const cur = (S.home && S.home.profile) || S.guest || {};
    const st = { step: 0, level: cur.level || '', goal: cur.goal || '', themes: (cur.themes || []).slice(), minutes: cur.minutes || 10 };
    const total = 4;
    function draw() {
      let body = '';
      if (st.step === 0) body = `<h1 class="h1">你能轻松读懂哪一句？</h1><p class="muted">选你不查词典也能读懂的最难一句。之后随时可以改。</p>
        <div class="choice opts four">${S.meta.levels.map(l => `<button class="opt" data-v="${l.id}" aria-pressed="${st.level === l.id}"><div class="row between"><span class="l">${esc(l.label)}</span><span class="pill">${l.id}</span></div><div class="s">${esc(l.sample)}</div><div class="d">${esc(l.desc)}</div></button>`).join('')}</div>`;
      if (st.step === 1) body = `<h1 class="h1">你学英语主要为了什么？</h1><div class="choice opts">${S.meta.goals.map(g => `<button class="opt" data-v="${g.id}" aria-pressed="${st.goal === g.id}"><span class="l">${esc(g.label)}</span></button>`).join('')}</div>`;
      if (st.step === 2) body = `<h1 class="h1">你对哪些话题感兴趣？</h1><p class="muted">可以多选，不选就每天随机。</p><div class="chips">${S.meta.themes.map(t => `<button class="chip" data-t="${t.id}" aria-pressed="${st.themes.includes(t.id)}">${esc(t.label)}</button>`).join('')}</div>`;
      if (st.step === 3) body = `<h1 class="h1">每天想学多久？</h1><p class="muted">5 分钟够复习单词再做一小步；一篇完整材料约 8–15 分钟，可以分两天学完。少一点但每天来，比偶尔学很久更有用。</p><div class="choice opts">${S.meta.minutes.map(m => `<button class="opt" data-v="${m}" aria-pressed="${st.minutes === m}"><span class="l">${m} 分钟</span></button>`).join('')}</div>`;
      const canNext = st.step === 0 ? !!st.level : st.step === 1 ? !!st.goal : true;
      const prevW = (st.step / total * 100);
      view.innerHTML = `<div class="progress-line"><i id="wp"></i></div><div class="stack" id="wbody">${body}
        <div class="row between wnav"><button class="btn ghost" id="wBack" ${st.step === 0 && !edit ? 'hidden' : ''}>${st.step === 0 ? '取消' : '上一步'}</button>
        <button class="btn primary" id="wNext" ${canNext ? '' : 'disabled'}>${st.step === total - 1 ? '开始学习' : '下一步'}</button></div></div>`;
      const wp = document.getElementById('wp'); wp.style.width = prevW + '%';
      requestAnimationFrame(() => requestAnimationFrame(() => { wp.style.width = ((st.step + 1) / total * 100) + '%'; }));
      enter(document.getElementById('wbody'));
      view.querySelectorAll('.opt').forEach(b => b.onclick = () => {
        const v = b.dataset.v; if (st.step === 0) st.level = v; else if (st.step === 1) st.goal = v; else st.minutes = Number(v);
        view.querySelectorAll('.opt').forEach(x => x.setAttribute('aria-pressed', String(x === b)));
        document.getElementById('wNext').disabled = false;
        if (st.step < 2) setTimeout(next, REDUCED ? 0 : 240);
      });
      view.querySelectorAll('.chip').forEach(b => b.onclick = () => { const t = b.dataset.t; st.themes = st.themes.includes(t) ? st.themes.filter(x => x !== t) : st.themes.concat(t); b.setAttribute('aria-pressed', String(st.themes.includes(t))); });
      document.getElementById('wNext').onclick = next;
      document.getElementById('wBack').onclick = () => { if (st.step === 0) history.back(); else { st.step--; draw(); } };
    }
    async function next() {
      if (st.step < total - 1) { st.step++; draw(); return; }
      const prof = { level: st.level, goal: st.goal, themes: st.themes, minutes: st.minutes };
      S.guest = prof; save('flow-next-guest', prof);
      if (S.user) { try { await api('/api/next/profile', prof); } catch (e) { toast(e.message); } }
      await refreshHome(); S.homeFresh = true; location.hash = '#/';
    }
    draw();
  }

  /* ---------- today ---------- */
  function greeting() { const h = new Date().getHours(); return h < 5 ? '夜深了' : h < 11 ? '早上好' : h < 14 ? '中午好' : h < 18 ? '下午好' : '晚上好'; }
  function stepDots(steps) { return `<span class="steps-dots" aria-label="已完成 ${steps.length} / 4 步">${STEPS.map(s => `<i class="${steps.includes(s) ? 'on' : ''}"></i>`).join('')}</span>`; }
  function reasonsHTML(m) { return m.reasons && m.reasons.length ? `<div class="reasons">${m.reasons.map(r => `<span class="reason">${esc(r)}</span>`).join('')}</div>` : ''; }
  function miniCard(m, tag) {
    return `<a class="card flat mini" href="#/m/${encodeURIComponent(m.id)}"><span class="t">${esc(m.title)}</span>
      <span class="meta">${m.featured ? '<span class="pill feat">精选</span>' : ''}${tag ? `<span class="pill amber">${esc(tag)}</span>` : ''}<span class="pill">${m.level}</span></span>
      <span class="p">${esc(m.preview)}</span><span class="tiny muted">${esc(m.theme_label)} · ${m.words} 词 · 约 ${m.minutes} 分钟</span>${m.steps.length ? stepDots(m.steps) : ''}${reasonsHTML(m)}</a>`;
  }
  async function today(fresh) {
    if (!fresh) await refreshHome();
    const h = S.home, pick = h.today[0], st = h.stats, g = h.graph;
    const name = S.user ? S.user.username : '';
    const gtotal = g ? g.total : 18, glit = g ? gtotal - g.untouched : 0;
    const path = S.user && h.path, weekN = st ? st.week.filter(d => d.active).length : 0;
    // One clear first action: the plan's next step (signed in), or today's article (guest).
    let top = '', readId = '';
    if (path) {
      const p = h.path, next = p.steps.find(s => !s.done), read = p.steps.find(s => s.key === 'read');
      readId = read ? decodeURIComponent(read.href.split('/')[2] || '') : '';
      const art = [pick, h.resume, ...h.today].find(m => m && m.id === readId);
      const label = s => s.key === 'read' && art ? '读今天这篇' : s.title;
      top = `<section class="today-plan" aria-labelledby="tpTitle">
        <div class="tp-head"><div><h1 class="h1" id="tpTitle">${next ? '今天的计划' : '今天的计划完成了'}</h1>
          <span class="muted small">${p.total} 步 · 约 ${p.minutes} 分钟 · 已完成 ${p.done} / ${p.total}</span></div>
          <span class="ring" data-p="${Math.round(p.done / Math.max(1, p.total) * 100)}" aria-hidden="true"><b>${p.done}/${p.total}</b></span></div>
        ${next ? `<a class="btn primary block go-next" href="${esc(next.href)}">开始：${esc(label(next))}<span aria-hidden="true">→</span></a>`
          : `<div class="tp-done">${doneRing}<span>都完成了。想多学一点，就再读一篇。</span></div><a class="btn primary block go-next" href="#/library">再学一篇<span aria-hidden="true">→</span></a>`}
        <div class="plist">${p.steps.map((s, k) => {
          const a = s.key === 'read' ? art : null;
          return `<a class="prow${s.done ? ' done' : ''}${s === next ? ' next' : ''}" href="${esc(s.href)}"><span class="num">${s.done ? '✓' : k + 1}</span>
            <span class="t"><b>${esc(a ? a.title : s.title)}</b><span class="muted tiny">${esc(a ? `今天这篇 · ${a.level} · ${a.theme_label} · 约 ${a.minutes} 分钟` : s.sub)}</span>${a ? `<span class="pv">${esc(a.preview)}</span>` : ''}</span>
            <span class="go" aria-hidden="true">›</span></a>`;
        }).join('')}</div></section>`;
    } else if (pick) {
      top = `<div class="hello"><h1 class="h1">今天学一篇，用上一句。</h1><span class="muted small">按「${esc(h.level_label)}（${h.level}）」为你挑选 · <a class="link" href="#/welcome/edit">调整</a></span></div>
        <article class="card hero"><div class="meta">${pick.featured ? '<span class="pill feat">精选</span>' : ''}<span class="pill green">今日推荐</span><span class="pill">${pick.level}</span><span class="pill">${esc(pick.theme_label)}</span></div>
        <h2 class="title">${esc(pick.title)}</h2>${pick.title_en ? `<div class="title-en">${esc(pick.title_en)}</div>` : ''}<p class="preview">${esc(pick.preview)}</p>${reasonsHTML(pick)}
        <span class="muted small">${pick.words} 词 · 约 ${pick.minutes} 分钟 · 听、读、理解、用出来</span>
        <a class="btn primary block go-next" href="#/m/${encodeURIComponent(pick.id)}">开始学习<span aria-hidden="true">→</span></a></article>`;
    } else top = '<div class="empty">今天没有可推荐的材料了。</div>';
    const more = h.today.filter(m => m.id !== readId && (!path ? m !== pick : true)).slice(0, 4);
    view.innerHTML = `<span class="kicker greet">${greeting()}${name ? `，<span class="nm">${esc(name)}</span>` : ''}</span>
      ${top}
      ${h.suggest && Date.now() - (load('flow-next-suggest-skip') || 0) > 7 * 864e5 ? suggestHTML(h.suggest) : ''}
      ${S.user && !path ? vocabHome(st) : ''}
      ${h.resume && h.resume.id !== readId ? `<a class="card flat mini section" href="#/m/${encodeURIComponent(h.resume.id)}/${nextStep(h.resume.steps)}"><span class="t">继续：${esc(h.resume.title)}</span><span class="pill green">继续</span><span class="p">${esc(h.resume.preview)}</span>${stepDots(h.resume.steps)}</a>` : ''}
      ${st ? `<div class="weekline section"><span class="small">本周学了 <b>${weekN}</b> 天</span><div class="week" aria-hidden="true">${st.week.map(d => `<span class="${d.active ? 'on' : ''}" title="${d.day}"></span>`).join('')}</div></div>` : ''}
      ${S.user ? '' : `<div class="card sunk section"><div class="stack-s"><b>登录后，进度和收藏的表达会保存下来</b><span class="muted small">不登录也可以听、读和做理解题。</span><div><button class="btn small" id="loginCta">登录 / 注册</button></div></div></div>`}
      ${h.news ? `<div class="section"><div class="section-head"><h2 class="h2">今日热点</h2><span class="muted tiny">联网检索后改写，未经人工审核</span></div>${miniCard(h.news, '热点')}</div>` : ''}
      <div class="section"><div class="section-head"><h2 class="h2">也可以选</h2><a class="link small" href="#/library">全部材料 →</a></div>
        ${path ? `<p class="muted tiny">按「${esc(h.level_label)}（${h.level}）」挑选 · <a class="link" href="#/welcome/edit">调整水平和话题</a></p>` : ''}
        <div class="grid-list">${more.map(m => miniCard(m)).join('')}</div></div>
      <a class="card flat section mini" href="#/graph"><span class="t">我的知识图谱</span><span class="pill green">${glit} / ${gtotal}</span>
        <span class="p">${g && g.watch && g.watch.length ? '写作中需要留意：' + g.watch.map(w => esc(w.title)).join('、') : '18 个语法知识点，读过、用过、做对过，都会在这里点亮。'}</span>
        ${g ? `<div class="gbar" aria-hidden="true">${['solid', 'used', 'met', 'watch'].map(k => `<i class="st st-${k}" data-w="${g[k] / gtotal * 100}"></i>`).join('')}</div>` : ''}</a>`;
    requestAnimationFrame(() => requestAnimationFrame(() => view.querySelectorAll('.gbar i').forEach(i => { i.style.width = i.dataset.w + '%'; })));
    const ring = view.querySelector('.ring'); if (ring) ring.style.setProperty('--p', ring.dataset.p + '%');  // CSP: no inline style attributes
    const cta = document.getElementById('loginCta'); if (cta) cta.onclick = () => openLogin();
    if (h.suggest) bindSuggest(h);
  }
  function vocabHome(st) {
    if (!st) return '';
    const n = st.due + st.new;
    if (!st.vocab_plan && !n) return `<a class="card flat section mini" href="#/cards"><span class="t">背单词</span><span class="pill">按遗忘曲线</span><span class="p">选一本词书，每天几个新词；例句来自你读的文章，还能听原文录音。</span></a>`;
    return `<div class="card section due"><div><div class="kicker">单词</div><div>${n ? `复习 <b>${st.due}</b> · 新词 <b>${st.new}</b>` : '今天的单词都完成了'}</div>
      <div class="muted small">${n ? `大约 ${st.minutes} 分钟` : '明天见'}</div></div>${n ? '<a class="btn primary" href="#/review">开始</a>' : '<a class="btn" href="#/cards">查看</a>'}</div>`;
  }
  function nextStep(steps) { return STEPS.find(s => !steps.includes(s)) || 'output'; }

  /* ---------- study ---------- */
  let selbar = null;
  function hideSelbar() { if (selbar) { selbar.remove(); selbar = null; } }
  const MAT = {}; // the material being studied: step changes reuse it instead of refetching and re-animating the header

  async function study(id, step, same) {
    let m = same && MAT[id];
    if (!m) { m = await api('/api/next/material?id=' + encodeURIComponent(id) + (S.user ? '' : '&level=' + encodeURIComponent(level()))); MAT[id] = m; }
    const done = new Set(m.steps.concat(load('flow-next-steps-' + id) || []));
    const st = { step: STEPS.includes(step) ? step : 'listen', showOriginal: !!m._showOriginal, blind: false };
    const lines = () => st.showOriginal && m.original ? m.original : m.sentences;

    function markStep(s) {
      if (done.has(s)) return;
      done.add(s); save('flow-next-steps-' + id, Array.from(done));
      if (S.user) api('/api/next/progress', { pack: id, step: s }).catch(() => {});
      const tab = view.querySelector(`[data-step="${s}"]`); if (tab && !tab.querySelector('.ok')) tab.insertAdjacentHTML('beforeend', '<span class="ok">✓</span>');
    }
    function go(s) { location.hash = `#/m/${encodeURIComponent(id)}/${s}`; }

    if (!same) {
      view.innerHTML = `<div class="study-head"><span class="kicker">${esc(m.theme_label)} · ${m.level}${m.variant ? ' → ' + m.variant.level : ''}${m.featured ? ' · 精选' : ''}</span>
        <h1 class="h1">${esc(m.title)}</h1>${m.title_en ? `<div class="title-en">${esc(m.title_en)}</div>` : ''}
        <span class="muted tiny">${esc(m.source)}${m.provenance.length ? ' · 来源：' + m.provenance.map(p => `<a class="link" href="${esc(p.url)}" target="_blank" rel="noopener noreferrer">${esc(p.title)}</a>`).join('、') : ''}</span></div>
        <div class="steps" role="tablist"><span class="ind" aria-hidden="true"></span>${STEPS.map(s => `<button role="tab" data-step="${s}" aria-selected="false">${STEP[s]}${done.has(s) ? '<span class="ok">✓</span>' : ''}</button>`).join('')}</div>
        <section id="pane"></section>`;
      view.querySelectorAll('[data-step]').forEach(b => b.onclick = () => go(b.dataset.step));
    }
    // Slide the tab indicator, and slide the pane in from the direction of travel.
    const tabs = [...view.querySelectorAll('[data-step]')];
    const prev = tabs.findIndex(b => b.getAttribute('aria-selected') === 'true');
    tabs.forEach(b => b.setAttribute('aria-selected', String(b.dataset.step === st.step)));
    const active = tabs.find(b => b.dataset.step === st.step), ind = view.querySelector('.steps .ind');
    const place = () => { ind.style.width = active.offsetWidth + 'px'; ind.style.transform = `translateX(${active.offsetLeft}px)`; };
    if (prev < 0) { ind.style.transition = 'none'; place(); requestAnimationFrame(() => { ind.style.transition = ''; }); } else requestAnimationFrame(place);
    const pane = view.querySelector('#pane');
    pane.style.setProperty('--dir', (prev > STEPS.indexOf(st.step) ? -14 : 14) + 'px');
    pane.classList.remove('pane-enter'); void pane.offsetWidth; pane.classList.add('pane-enter');
    // Switching steps far down the page: jump so the step bar sits under the header and the new content starts right below
    // it (the header comes back when scrolling up, so its height is always allowed for).
    if (same) { const top = view.querySelector('.study-head').getBoundingClientRect().bottom + scrollY - bar.offsetHeight; if (scrollY > top) scrollTo({ top, behavior: 'auto' }); }

    /* listen: sentence list, word-by-word highlight while it plays */
    // Narration is usable when this material has the chosen voice and the shown text is the original.
    async function narration(ls) {
      const voices = (m.audio && m.audio.voices) || [];
      if (!voices.length || (m.variant && !st.showOriginal)) return null;
      if (!voices.includes(S.voice)) S.voice = voices[0];
      const ok = await NAR.load(id, S.voice, m.audio.version);
      return ok && NAR.meta && NAR.meta.sentences.length === ls.length ? NAR.meta : null;
    }
    async function listen() {
      if (st.mode === 'shadow') return shadowMode();
      if (st.mode === 'dictate') return dictateMode();
      const ls = lines();
      const nm = await narration(ls);
      const voices = (m.audio && m.audio.voices) || [];
      pane.innerHTML = `${listenHead()}${voices.length ? voiceChips(voices) : ''}<div class="player">
          <button class="btn primary" id="playAll">${ICON.play.replace('<svg', '<svg width="18" height="18" fill="currentColor"')}<span>播放全文</span></button>
          <div class="speed" role="group" aria-label="语速">${[0.75, 1, 1.25].map(r => `<button data-rate="${r}" aria-pressed="${TTS.rate === r}">${r}×</button>`).join('')}</div>
          <button class="icon-btn ${st.blind ? 'on' : ''}" id="blind" aria-pressed="${st.blind}" title="盲听：先只听不看" aria-label="盲听">${ICON.eye}</button>
        </div>
        ${nm ? '' : (TTS.ok ? '<p class="muted tiny">这篇暂时没有真人声录音，先用浏览器朗读。</p>' : '<p class="err">这个浏览器不支持朗读，可以直接去「读」。</p>')}
        <p class="muted small">想练耳朵，可以先点 👁 只听不看；听不懂的句子单独点开反复听。播放时正在读的词会亮起来${TOUCH ? '' : '（空格键播放 / 停止）'}。</p>
        <div class="lines">${ls.map((s, i) => `<div class="line" data-i="${i}"><button class="icon-btn" data-say="${i}" aria-label="播放第 ${i + 1} 句">${ICON.speak}</button><div class="txt ${st.blind ? 'blind' : ''}">${wordSpans(s, () => 'kw')}</div></div>`).join('')}</div>
        <div class="section row between"><span class="muted small">共 ${ls.length} 句${nm ? ' · ' + Math.round(nm.duration / 60 * 10) / 10 + ' 分钟' : ''}</span><button class="btn" id="toRead">听完了，去读 →</button></div>`;
      let playing = -1, shown = -1;
      const lineEl = i => pane.querySelector(`.line[data-i="${i}"]`);
      const setNow = i => pane.querySelectorAll('.line').forEach(el => { const on = Number(el.dataset.i) === i; el.classList.toggle('now', on); if (!on) el.querySelectorAll('.cur').forEach(x => x.classList.remove('cur')); });
      const setBtn = on => { const b = pane.querySelector('#playAll'); if (b) { b.innerHTML = playIcon(on) + `<span>${on ? '停止' : '播放全文'}</span>`; b.setAttribute('aria-pressed', String(on)); } };
      const follow = t => {
        const [si, wc] = NAR.locate(t);
        if (si !== shown) { shown = si; setNow(si); MINI.update(`第 ${si + 1} / ${ls.length} 句`); const el = lineEl(si); if (el && playing >= 0) el.scrollIntoView({ block: 'center', behavior: REDUCED ? 'auto' : 'smooth' }); }
        if (si >= 0) lightAt(lineEl(si), wc);
      };
      const stopAll = () => { TTS.stop(); NAR.stop(); playing = -1; shown = -1; setNow(-1); setBtn(false); MINI.hide(); };
      const sayLine = (i, then) => {
        if (nm) { shown = -1; NAR.play(nm.sentences[i].s, nm.sentences[i].e, follow, then); return; }
        const el = lineEl(i); TTS.say(ls[i], then, c => lightWord(el, c));
      };
      const playFrom = i => {
        if (i >= ls.length) { stopAll(); markStep('listen'); return; }
        playing = i; setNow(i); MINI.update(`第 ${i + 1} / ${ls.length} 句`);
        const el = lineEl(i); if (el) el.scrollIntoView({ block: 'center', behavior: REDUCED ? 'auto' : 'smooth' });
        sayLine(i, () => playFrom(i + 1));
      };
      pane.querySelector('#playAll').onclick = () => {
        if (playing >= 0) return stopAll();
        setBtn(true); MINI.show('正在播放全文', stopAll);
        if (nm) { playing = 0; shown = -1; NAR.play(nm.sentences[0].s, null, follow, () => { stopAll(); markStep('listen'); }); }
        else playFrom(0);
      };
      pane.querySelectorAll('[data-say]').forEach(b => b.onclick = () => { const i = Number(b.dataset.say); stopAll(); setNow(i); sayLine(i, () => setNow(-1)); });
      pane.querySelectorAll('.line .txt').forEach((t, i) => t.onclick = e => { if (e.target.dataset.w && !st.blind) lookupSheet(e.target.dataset.w, ls[i], id); });
      pane.querySelectorAll('[data-rate]').forEach(b => b.onclick = () => { TTS.rate = Number(b.dataset.rate); save('flow-next-rate', TTS.rate); NAR.audio.playbackRate = TTS.rate; pane.querySelectorAll('[data-rate]').forEach(x => x.setAttribute('aria-pressed', String(x === b))); });
      pane.querySelectorAll('[data-voice]').forEach(b => b.onclick = async () => { if (b.disabled) return; stopAll(); await setVoice(b.dataset.voice); listen(); toast('已切换为' + VOICE_LABELS[b.dataset.voice]); });
      pane.querySelector('#blind').onclick = e => { st.blind = !st.blind; toast(st.blind ? '盲听：只听不看，再点一次显示原文' : '已显示原文'); e.currentTarget.classList.toggle('on', st.blind); e.currentTarget.setAttribute('aria-pressed', String(st.blind)); pane.querySelectorAll('.txt').forEach(t => t.classList.toggle('blind', st.blind)); };
      pane.querySelector('#toRead').onclick = () => { stopAll(); markStep('listen'); go('read'); };
      bindListenHead(stopAll);
      document.onkeydown = e => {
        if (isTyping(e) || !sheetEl.hidden || e.metaKey || e.ctrlKey || e.altKey) return;
        const b = pane.querySelector('#playAll'); if (b && (e.key === ' ' || e.key === 'k')) { e.preventDefault(); b.click(); }
      };
    }

    /* listen modes: 精听 (sentence list) · 跟读 (record, compare, AI feedback) · 听写 (type what you hear) */
    const MODES = { listen: '精听', shadow: '跟读', dictate: '听写' };
    if (!st.mode) st.mode = MODES[load('flow-next-listen-mode')] ? load('flow-next-listen-mode') : 'listen';
    const stripLabel = s => s.replace(/^[A-Z][a-z]+(?: [A-Z][a-z]+)?:\s+/, '');
    function listenHead() {
      const pr = m._prHidden ? [] : (m.preread || []);
      return `${pr.length ? `<div class="card sunk preread stack-s"><div class="row between"><b class="small">读前先认识这 ${pr.length} 个词</b><button class="link tiny" id="prHide">收起</button></div>
          <div class="pr-list">${pr.map((w, k) => `<div class="pr"><button class="icon-btn" data-prsay="${k}" aria-label="朗读 ${esc(w.word)}">${ICON.speak}</button>
            <div><b>${esc(w.word)}</b> <span class="ph">${esc(w.phonetic)}</span><div class="tiny muted">${esc(w.meaning)}</div></div></div>`).join('')}</div>
          <div class="row"><button class="btn small primary" id="prAdd">全部加入复习</button><span class="muted tiny">加入后会在文章里标出来</span></div></div>` : ''}
        <div class="seg modes" role="tablist" aria-label="听的方式">${Object.entries(MODES).map(([k, l]) => `<button role="tab" data-mode="${k}" aria-selected="${st.mode === k}">${l}</button>`).join('')}</div>`;
    }
    function bindListenHead(stop) {
      pane.querySelectorAll('[data-mode]').forEach(b => b.onclick = () => { stop(); st.mode = b.dataset.mode; save('flow-next-listen-mode', st.mode); listen(); });
      const pr = m.preread || [];
      pane.querySelectorAll('[data-prsay]').forEach(b => b.onclick = () => { stop(); const w = pr[Number(b.dataset.prsay)]; CLIP.word({ text: w.word, audio: w.audio }); });
      const hide = pane.querySelector('#prHide'); if (hide) hide.onclick = () => { m._prHidden = true; pane.querySelector('.preread').remove(); };
      const add = pane.querySelector('#prAdd');
      if (add) add.onclick = async () => {
        if (!S.user) return needLogin('登录后可以把这些词加入复习，按遗忘曲线安排。');
        add.disabled = true;
        try {
          const r = await api('/api/next/vocab/add', { pack: id, items: pr.map(w => ({ word: w.word, sentence: findContext(w.form, lines()) })) });
          toast(r.added ? `已加入 ${r.added} 个词，读的时候会标出来` : '这些词已经在复习里了');
          m.mine = (m.mine || []).concat(pr.map(w => ({ form: w.form, id: 0 })));
          m._prHidden = true; pane.querySelector('.preread').remove(); refreshHome().catch(() => {});
        } catch (e) { toast(e.message); add.disabled = false; }
      };
    }
    function wordDiff(target, typed) {  // same alignment as the server's compare_words
      const t = (target.toLowerCase().match(/[a-z]+(?:'[a-z]+)?/g) || []), h = (typed.toLowerCase().match(/[a-z]+(?:'[a-z]+)?/g) || []);
      const L = Array.from({ length: t.length + 1 }, () => new Array(h.length + 1).fill(0));
      for (let i = t.length - 1; i >= 0; i--) for (let j = h.length - 1; j >= 0; j--) L[i][j] = t[i] === h[j] ? L[i + 1][j + 1] + 1 : Math.max(L[i + 1][j], L[i][j + 1]);
      const out = []; let i = 0, j = 0;
      while (i < t.length) {
        if (j < h.length && t[i] === h[j]) { out.push({ w: t[i], ok: true }); i++; j++; }
        else if (j < h.length && L[i][j + 1] >= L[i + 1][j]) j++;
        else { out.push({ w: t[i], ok: false }); i++; }
      }
      return out;
    }
    const wordsHTML = ws => `<div class="wdiff">${ws.map(w => `<span class="${w.ok ? 'ok' : 'miss'}">${esc(w.w)}</span>`).join(' ')}</div>`;

    async function shadowMode() {
      const ls = lines(), nm = await narration(ls);
      pane.innerHTML = `${listenHead()}<p class="muted small">先点 ▶ 听原声，再点 ● 跟着读一遍（再点一次停止）。「对比」先放原声再放你的录音；${S.user ? '「AI 点评」会写出它听到的内容，并指出要改的地方。' : '登录后可以让 AI 点评。'}</p>
        <div class="lines">${ls.map((s, i) => `<div class="line sh" data-i="${i}"><div class="txt">${esc(s)}</div>
          <div class="sh-ctl"><button class="icon-btn" data-o="${i}" aria-label="听原声">${ICON.play.replace('<svg', '<svg fill="currentColor"')}</button>
            <button class="icon-btn rec" data-r="${i}" aria-label="录音"><span class="dot"></span></button>
            <button class="btn small" data-c="${i}" disabled>对比</button><button class="btn small" data-ai="${i}" disabled>✦ AI 点评</button></div>
          <div class="sh-out"></div></div>`).join('')}</div>
        <div class="section row between"><span></span><button class="btn" id="toRead">去读 →</button></div>`;
      const REC = { mr: null, blobs: {}, timer: 0, url: {} };
      const row = i => pane.querySelector(`.line[data-i="${i}"]`);
      const stop = () => { TTS.stop(); NAR.stop(); CLIP.stop(); if (REC.mr && REC.mr.state === 'recording') REC.mr.stop(); };
      const orig = (i, then) => { if (nm) NAR.play(nm.sentences[i].s, nm.sentences[i].e, null, then); else TTS.say(stripLabel(ls[i]), then); };
      async function record(i, btn) {
        if (REC.mr && REC.mr.state === 'recording') { REC.mr.stop(); return; }
        stop();
        if (!navigator.mediaDevices || !window.MediaRecorder) { toast('这个浏览器不支持录音，换 Safari 或 Chrome 试试'); return; }
        let stream;
        try { stream = await navigator.mediaDevices.getUserMedia({ audio: true }); } catch (e) { toast('没有拿到麦克风权限，可以在浏览器设置里打开'); return; }
        const type = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4'].find(t => MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported(t)) || '';
        const mr = new MediaRecorder(stream, type ? { mimeType: type } : undefined), chunks = [];
        REC.mr = mr;
        mr.ondataavailable = e => { if (e.data && e.data.size) chunks.push(e.data); };
        mr.onstop = () => {
          stream.getTracks().forEach(t => t.stop()); clearTimeout(REC.timer); btn.classList.remove('on'); btn.setAttribute('aria-label', '录音');
          if (!chunks.length) return;
          REC.blobs[i] = new Blob(chunks, { type: mr.mimeType || type || 'audio/webm' });
          if (REC.url[i]) URL.revokeObjectURL(REC.url[i]);
          REC.url[i] = URL.createObjectURL(REC.blobs[i]);
          row(i).querySelector('[data-c]').disabled = false; row(i).querySelector('[data-ai]').disabled = false;
        };
        mr.start(); btn.classList.add('on'); btn.setAttribute('aria-label', '停止录音');
        const secs = nm ? (nm.sentences[i].e - nm.sentences[i].s) * 2.2 + 2 : 12;
        REC.timer = setTimeout(() => { if (mr.state === 'recording') mr.stop(); }, Math.min(25, secs) * 1000);
      }
      function compare(i) { stop(); orig(i, () => { const a = new Audio(REC.url[i]); a.play().catch(() => {}); }); }
      async function aiCheck(i, btn) {
        if (!S.user) return needLogin('登录后，AI 会听你的跟读，指出漏读、读错和需要连读的地方。');
        const blob = REC.blobs[i]; if (!blob) return;
        if (blob.size > 1400000) { toast('录音太长了，读这一句就好'); return; }
        btn.disabled = true; btn.innerHTML = '<span class="spin"></span>';
        try {
          const data = await new Promise((ok, no) => { const r = new FileReader(); r.onload = () => ok(String(r.result).split(',')[1]); r.onerror = no; r.readAsDataURL(blob); });
          const mime = /mp4|m4a|aac/.test(blob.type) ? 'audio/mp4' : /ogg/.test(blob.type) ? 'audio/ogg' : 'audio/webm';
          const x = (await api('/api/next/shadow', { pack: id, i, audio: { mime_type: mime, data }, request_id: rid('sh') })).result;
          const flu = { smooth: '流畅', ok: '基本流畅', choppy: '有点断断续续' }[x.fluency];
          row(i).querySelector('.sh-out').innerHTML = `<div class="card flat sh-res stack-s enter">${wordsHTML(x.words)}
            <div class="tiny muted">AI 听到：${esc(x.transcript || '（没听清）')} · 读到 ${x.matched}/${x.words.length} 个词 · ${flu}</div>
            ${x.issues.map(it => `<div class="small"><b>${esc(it.word)}</b>：${esc(it.note)}</div>`).join('')}${x.tip ? `<div class="small tip">建议：${esc(x.tip)}</div>` : ''}</div>`;
        } catch (e) { toast(e.message); }
        btn.disabled = false; btn.textContent = '✦ AI 点评';
      }
      pane.querySelectorAll('[data-o]').forEach(b => b.onclick = () => { stop(); orig(Number(b.dataset.o)); });
      pane.querySelectorAll('[data-r]').forEach(b => b.onclick = () => record(Number(b.dataset.r), b));
      pane.querySelectorAll('[data-c]').forEach(b => b.onclick = () => compare(Number(b.dataset.c)));
      pane.querySelectorAll('[data-ai]').forEach(b => b.onclick = () => aiCheck(Number(b.dataset.ai), b));
      pane.querySelector('#toRead').onclick = () => { stop(); markStep('listen'); go('read'); };
      bindListenHead(stop);
    }

    async function dictateMode() {
      const ls = lines(), nm = await narration(ls);
      const score = m._dictScore || (m._dictScore = { got: 0, total: 0 });
      let i = Math.min(m._dictI || 0, ls.length - 1);
      const stop = () => { TTS.stop(); NAR.stop(); CLIP.stop(); };
      const play = slow => {
        stop(); const keep = TTS.rate; TTS.rate = slow ? 0.75 : keep;
        if (nm) NAR.play(nm.sentences[i].s, nm.sentences[i].e, null, null); else TTS.say(stripLabel(ls[i]));
        TTS.rate = keep;
      };
      function render() {
        pane.innerHTML = `${listenHead()}<div class="card flat dict stack"><div class="row between"><span class="kicker">听写 · 第 ${i + 1} / ${ls.length} 句</span>
            <span class="muted tiny">${score.total ? '这篇正确率 ' + Math.round(score.got / score.total * 100) + '%' : '可以反复播放'}</span></div>
          <div class="row"><button class="btn primary" id="dPlay">${ICON.play.replace('<svg', '<svg width="16" height="16" fill="currentColor"')}<span>播放这一句</span></button><button class="btn small" id="dSlow">慢速</button></div>
          <textarea id="dIn" rows="3" lang="en" enterkeyhint="done" placeholder="听到什么写什么，拼不出的词先空着" autocapitalize="off" autocomplete="off" autocorrect="off" spellcheck="false"></textarea>
          <div class="row"><button class="btn" id="dCheck">检查</button><button class="btn ghost" id="dSkip">跳过这句</button></div><div id="dOut"></div></div>
          <div class="section row between"><span class="muted small">听错的词可以直接加入复习。</span><button class="btn" id="toRead">去读 →</button></div>`;
        const inp = pane.querySelector('#dIn');
        pane.querySelector('#dPlay').onclick = () => { play(false); inp.focus({ preventScroll: true }); };
        pane.querySelector('#dSlow').onclick = () => play(true);
        const next = () => { i += 1; m._dictI = i; if (i >= ls.length) { m._dictI = 0; markStep('listen'); toast('这篇听写完了'); i = 0; } render(); play(false); };
        pane.querySelector('#dSkip').onclick = next;
        pane.querySelector('#dCheck').onclick = () => {
          const target = stripLabel(ls[i]), ws = wordDiff(target, inp.value), got = ws.filter(w => w.ok).length;
          score.got += got; score.total += ws.length;
          m._dictChecked = (m._dictChecked || 0) + 1; if (m._dictChecked >= 3) markStep('listen');
          if (S.user && ws.length) api('/api/next/skill', { kind: 'dictation', score: got / ws.length, pack: id }).catch(() => {});
          const missed = [...new Set(ws.filter(w => !w.ok).map(w => w.w))].filter(w => w.length > 3);
          pane.querySelector('#dOut').innerHTML = `<div class="stack-s enter">${wordsHTML(ws)}<div class="muted tiny">写对 ${got} / ${ws.length} 个词</div>
            <div class="row">${missed.length ? `<button class="btn small" id="dAdd">把听错的 ${missed.length} 个词加入复习</button>` : ''}<button class="btn small primary" id="dNext">${i + 1 < ls.length ? '下一句' : '完成'}</button></div></div>`;
          pane.querySelector('#dNext').onclick = next;
          const add = pane.querySelector('#dAdd');
          if (add) add.onclick = async () => {
            if (!S.user) return needLogin('登录后可以把听错的词加入复习。');
            add.disabled = true;
            try {
              const r = await api('/api/next/vocab/add', { pack: id, min_rank: 1500, items: missed.map(w => ({ word: w, sentence: target })) });
              const rest = missed.length - (r.added || 0);
              toast(r.added ? `已加入 ${r.added} 个词${rest ? `；另外 ${rest} 个是常用词或已在复习里` : ''}` : '这几个都是常用词（不用专门背），或已经在复习里了');
              add.textContent = r.added ? `已加入 ${r.added} 个` : '不用加';
            }
            catch (e) { toast(e.message); add.disabled = false; }
          };
        };
        inp.addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); pane.querySelector('#dCheck').click(); } });
        pane.querySelector('#toRead').onclick = () => { stop(); go('read'); };
        bindListenHead(stop);
      }
      render();
    }

    /* after reading: the words looked up here (and the pre-reading list) can go into review in one tap */
    function newWordsHTML() {
      const looked = [...((m._looked && m._looked.values()) || [])];
      const mine = new Set((m.mine || []).map(x => x.form));
      const items = looked.filter(x => !mine.has(x.word)).map(x => ({ ...x, on: true }));
      (m.preread || []).forEach(w => { if (!items.some(x => x.word === w.word) && !mine.has(w.form)) items.push({ word: w.word, meaning: w.meaning, sentence: findContext(w.form, lines()), on: false }); });
      if (!items.length) return '';
      return `<div class="card flat stack-s" id="newWords"><div class="row between"><b>这篇的生词</b><span class="muted tiny">勾选的会按遗忘曲线复习</span></div>
        <div class="nw-list">${items.slice(0, 14).map((x, k) => `<label class="nw"><input type="checkbox" data-nw="${k}" ${x.on ? 'checked' : ''}><b>${esc(x.word)}</b><span class="muted tiny">${esc(x.meaning || '')}</span></label>`).join('')}</div>
        <div><button class="btn small primary" id="nwAdd">加入复习</button></div></div>`;
    }
    function bindNewWords() {
      const box = pane.querySelector('#newWords'); if (!box) return;
      const looked = [...((m._looked && m._looked.values()) || [])];
      const items = looked.map(x => ({ ...x })); (m.preread || []).forEach(w => { if (!items.some(x => x.word === w.word)) items.push({ word: w.word, sentence: findContext(w.form, lines()) }); });
      box.querySelector('#nwAdd').onclick = async e => {
        if (!S.user) return needLogin('登录后可以把这些词加入复习。');
        const pick = [...box.querySelectorAll('[data-nw]:checked')].map(c => items[Number(c.dataset.nw)]).filter(Boolean);
        if (!pick.length) { toast('先勾选要复习的词'); return; }
        const btn = e.currentTarget; btn.disabled = true;
        try { const r = await api('/api/next/vocab/add', { pack: id, items: pick.map(x => ({ word: x.word, sentence: x.sentence || '' })) }); toast(r.added ? `已加入 ${r.added} 个词` : '这些词已经在复习里了'); refreshHome().catch(() => {}); box.remove(); }
        catch (x) { toast(x.message); btn.disabled = false; }
      };
    }

    /* read: tap a word, ✦ explains a sentence, select to save, read-along, expressions, knowledge points */
    function wordClass(part) {
      const key = part.toLowerCase();
      const isVocab = m.vocabulary.some(v => v.term.toLowerCase() === key);
      const mine = (m.mine || []).some(x => x.form === key) ? ' mine' : '';
      return (isVocab ? 'w vocab' : (m.hard[key] ? 'w hard' : 'w')) + mine;
    }
    // The ✦ is glued to the sentence's last word, so it can never wrap to the start of the next line.
    // A line that begins with a speaker ("Staff: …") starts a new turn on its own line.
    function sentenceHTML(s, i) {
      let html = wordSpans(s, wordClass, ` data-s="${i}"`);
      const at = html.lastIndexOf('<span class="');
      const btn = `<button class="link tiny" data-ex="${i}" aria-label="AI 讲解第 ${i + 1} 句">✦</button>`;
      html = at < 0 ? html + btn : html.slice(0, at) + '<span class="nobr">' + html.slice(at) + btn + '</span>';
      const turn = i > 0 && /^[A-Z][a-z]+(?: [A-Z][a-z]+)?:\s/.test(s) ? ' turn' : '';
      return `<span class="sent${turn}" data-si="${i}">${html}</span> `;
    }
    function read() {
      const ls = lines();
      const variantBar = m.variant ? `<div class="seg" role="tablist"><button data-ver="v" aria-selected="${!st.showOriginal}">适合我的版本（${m.variant.level}）</button><button data-ver="o" aria-selected="${st.showOriginal}">原文（${m.original_level}）</button><span></span></div>`
        : m.can_variant ? `<div class="card sunk row between"><span class="small">这篇原文是 ${m.original_level}，你选的是 ${m.user_level}。</span><button class="btn small" id="mkVar">改写成 ${m.user_level} 难度</button></div>` : '';
      pane.innerHTML = `${m.summary_zh ? `<details class="guide"><summary>中文导读</summary><p>${esc(m.summary_zh)}</p></details>` : ''}${variantBar}
        <div class="row between"><div class="legend"><span>本篇词汇</span><span class="h">可能超出你的水平</span>${(m.mine || []).length ? '<span class="m">你在背的词</span>' : ''}</div>
          <button class="btn small" id="readAlong" title="边听录音边看文字，读到哪句亮哪句">${playIcon(false, 14)}<span>伴读</span></button></div>
        <p class="muted tiny">点单词查词；点句尾的 ✦ 让 AI 讲解整句；${TOUCH ? '长按拖选' : '选中'}一段文字可以收藏。${TOUCH ? '' : '键盘：Tab 进入正文后用 ← → 逐词移动，↵ 查词，E 讲解这句。'}</p>
        <div class="text" id="reader" tabindex="0" aria-label="正文：左右方向键逐词移动，回车查词">${ls.map((s, i) => sentenceHTML(s, i)).join('')}</div>
        ${m.expressions.length ? `<div class="section"><div class="section-head"><h2 class="h2">地道表达</h2><span class="muted tiny">能直接搬进你自己话里的搭配</span></div><div class="stack-s">${m.expressions.map((x, i) => `<div class="expr"><span class="e">${esc(x.text)}</span><span class="row"><button class="icon-btn" data-sayx="${i}" aria-label="朗读">${ICON.speak}</button><button class="icon-btn" data-sx="${i}" aria-label="收藏 ${esc(x.text)}">${ICON.star}</button></span><span class="m">${esc(x.meaning)}</span><span class="n">${esc(x.note || '')}</span></div>`).join('')}</div></div>` : ''}
        ${m.vocabulary.length ? `<div class="section"><h2 class="h2">本篇词汇</h2><div class="vocab-list section">${m.vocabulary.map((v, i) => `<div class="vrow"><span class="term">${esc(v.term)}</span><button class="icon-btn" data-sv="${i}" aria-label="收藏 ${esc(v.term)}">${ICON.star}</button><span class="muted small">${esc(v.meaning)}</span><span class="vex">${esc(v.example || '')}</span></div>`).join('')}</div></div>` : ''}
        ${(m.variant && m.variant.notes.length) ? `<div class="section"><h2 class="h2">改写版新出现的表达</h2><div class="vocab-list section">${m.variant.notes.map((v, i) => `<div class="vrow"><span class="term">${esc(v.text)}</span><button class="icon-btn" data-sn="${i}" aria-label="收藏">${ICON.star}</button><span class="muted small">${esc(v.meaning)}</span></div>`).join('')}</div></div>` : ''}
        ${m.notes.length ? `<div class="section stack-s"><div class="section-head"><h2 class="h2">这篇练到的知识点</h2><a class="link small" href="#/graph">知识图谱 →</a></div>${m.notes.map(n => `<div class="knote"><div class="row between">${nodeChip({ id: n.node, title: n.title, status: n.status })}<span class="tiny muted">${esc(n.label)}</span></div><q>${esc(n.quote)}</q><div class="small muted">${esc(n.explanation)}</div></div>`).join('')}</div>` : ''}
        <div class="section" id="nwSlot">${newWordsHTML()}</div>
        <div class="section row between"><span></span><button class="btn" id="toCheck">读完了，做理解题 →</button></div>`;
      const reader = pane.querySelector('#reader');
      pane.querySelectorAll('[data-ver]').forEach(b => b.onclick = () => { st.showOriginal = b.dataset.ver === 'o'; m._showOriginal = st.showOriginal; read(); });
      const mk = pane.querySelector('#mkVar');
      if (mk) mk.onclick = async () => {
        if (!S.user) return needLogin('登录后可以让 AI 把这篇改写成适合你的难度（每天的 AI 次数有上限）。');
        mk.disabled = true; mk.innerHTML = '<span class="spin"></span> 正在改写…';
        try { const r = await api('/api/next/variant', { pack: id, level: m.user_level, request_id: rid('nv') }); m.variant = { level: r.level, body: r.body, notes: r.notes }; m.original = m.sentences; m.sentences = splitSentences(r.body); m.can_variant = false; read(); toast(r.cached ? '已打开改写版' : '改写好了'); }
        catch (e) { toast(e.message); mk.disabled = false; mk.textContent = `改写成 ${m.user_level} 难度`; }
      };
      reader.onclick = e => {
        const ex = e.target.closest('[data-ex]'); if (ex) return explainSheet(ls[Number(ex.dataset.ex)], id);
        const w = e.target.closest('.w'); if (w && !String(getSelection()).trim()) lookupSheet(w.dataset.w, ls[Number(w.dataset.s)], id, w.classList.contains('mine'));
      };
      // Read-along: sentence by sentence; the current sentence stays bright, the rest dims, the current word lights up.
      let along = false, alongShown = -1;
      const ra = pane.querySelector('#readAlong');
      const stopAlong = () => { along = false; TTS.stop(); NAR.stop(); MINI.hide(); reader.classList.remove('reading'); reader.querySelectorAll('.now,.cur').forEach(x => x.classList.remove('now', 'cur')); ra.innerHTML = playIcon(false, 14) + '<span>伴读</span>'; };
      const alongAudio = nm => {
        alongShown = -1;
        NAR.play(nm.sentences[0].s, null, t => {
          const [si, wc] = NAR.locate(t);
          const s = reader.querySelector(`.sent[data-si="${si}"]`);
          if (si !== alongShown && s) { alongShown = si; MINI.update(`伴读 · 第 ${si + 1} / ${ls.length} 句`); reader.querySelectorAll('.sent.now').forEach(x => x.classList.remove('now')); s.classList.add('now'); s.scrollIntoView({ block: 'center', behavior: REDUCED ? 'auto' : 'smooth' }); }
          if (s) lightAt(s, wc);
        }, () => { stopAlong(); markStep('read'); });
      };
      const alongFrom = i => {
        if (!along) return;
        if (i >= ls.length) { stopAlong(); markStep('read'); return; }
        reader.querySelectorAll('.sent.now').forEach(x => x.classList.remove('now'));
        const s = reader.querySelector(`.sent[data-si="${i}"]`); s.classList.add('now'); s.scrollIntoView({ block: 'center', behavior: REDUCED ? 'auto' : 'smooth' });
        TTS.say(ls[i], () => alongFrom(i + 1), c => lightWord(s, c));
      };
      ra.onclick = async () => {
        if (along) return stopAlong();
        along = true; reader.classList.add('reading'); ra.innerHTML = playIcon(true, 14) + '<span>停止</span>'; MINI.show('伴读中', stopAlong);
        const nm = await narration(ls);
        if (along) { if (nm) alongAudio(nm); else alongFrom(0); }
      };
      pane.querySelectorAll('[data-sayx]').forEach(b => b.onclick = () => TTS.say(m.expressions[Number(b.dataset.sayx)].text));
      pane.querySelectorAll('[data-sx]').forEach(b => b.onclick = () => { const x = m.expressions[Number(b.dataset.sx)]; saveCard({ text: x.text, meaning: x.meaning + (x.note ? '｜' + x.note : ''), context: findContext(x.text, ls), pack: id }, b); });
      pane.querySelectorAll('[data-sv]').forEach(b => b.onclick = () => { const v = m.vocabulary[Number(b.dataset.sv)]; saveCard({ text: v.term, meaning: v.meaning, context: findContext(v.term, ls) || v.example, pack: id }, b); });
      pane.querySelectorAll('[data-sn]').forEach(b => b.onclick = () => { const v = m.variant.notes[Number(b.dataset.sn)]; saveCard({ text: v.text, meaning: v.meaning, context: findContext(v.text, ls), pack: id }, b); });
      pane.querySelector('#toCheck').onclick = () => { stopAlong(); markStep('read'); go('check'); };
      // Reading to the end of the text counts as having read it (after a short while on the page, not a quick scroll).
      const t0r = Date.now();
      if ('IntersectionObserver' in window) {
        const io = new IntersectionObserver(es => { if (es.some(x => x.isIntersecting) && Date.now() - t0r > 20000) { markStep('read'); io.disconnect(); } });
        io.observe(pane.querySelector('#toCheck'));
      }
      // Keyboard reading: ← → walk the words, ↵ looks one up, E explains its sentence.
      const words = () => [...reader.querySelectorAll('.w')];
      let kw = -1;
      const kmove = k => { const ws = words(); if (!ws.length) return; reader.querySelectorAll('.kfocus').forEach(x => x.classList.remove('kfocus')); kw = Math.max(0, Math.min(ws.length - 1, k)); ws[kw].classList.add('kfocus'); ws[kw].scrollIntoView({ block: 'nearest' }); };
      reader.addEventListener('keydown', e => {
        if (e.metaKey || e.ctrlKey || e.altKey) return;
        const ws = words();
        if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') { e.preventDefault(); kmove(kw < 0 ? 0 : kw + (e.key === 'ArrowRight' ? 1 : -1)); }
        else if (e.key === 'Enter' && kw >= 0) { e.preventDefault(); const w = ws[kw]; lookupSheet(w.dataset.w, ls[Number(w.dataset.s)], id, w.classList.contains('mine')); }
        else if ((e.key === 'e' || e.key === 'E') && kw >= 0) { e.preventDefault(); explainSheet(ls[Number(ws[kw].dataset.s)], id); }
      });
      reader.addEventListener('blur', () => reader.querySelectorAll('.kfocus').forEach(x => x.classList.remove('kfocus')));
      bindNewWords();
      m._onLook = () => { const slot = pane.querySelector('#nwSlot'); if (!slot) return; slot.innerHTML = newWordsHTML(); bindNewWords(); };
      const onSel = () => {
        const sel = getSelection(); const t = String(sel).replace(/\s+/g, ' ').trim();
        if (!t || t.length > 160 || !/[A-Za-z]/.test(t) || !reader.contains(sel.anchorNode)) { hideSelbar(); return; }
        const sentEl = sel.anchorNode.parentElement && sel.anchorNode.parentElement.closest('.sent');
        const ctx = sentEl ? ls[Number(sentEl.dataset.si)] : '';
        if (!selbar) { selbar = document.createElement('div'); selbar.className = 'selbar'; document.body.appendChild(selbar); }
        selbar.innerHTML = `<span>${esc(t)}</span><button type="button">收藏</button>`;
        selbar.querySelector('button').onclick = () => { const from = selbar; saveCard({ text: t, context: ctx, pack: id }, null, from); sel.removeAllRanges(); setTimeout(hideSelbar, 50); };
      };
      document.onselectionchange = () => { clearTimeout(onSel.t); onSel.t = setTimeout(onSel, 250); };
    }

    /* check: answer, then the evidence sentence is swept in and flashed in the text */
    function check() {
      if (!m.questions.length) {
        pane.innerHTML = `<div class="empty"><p>这篇还没有理解题。</p>${m.imported ? '<button class="btn primary" id="mkQ">✦ 让 AI 出几道理解题</button><p class="muted tiny">同时挑出值得学的表达，写一段中文导读（用 1 次 AI）。</p>' : ''}</div><div class="row between"><span></span><button class="btn" id="toOut">去用出来 →</button></div>`;
        pane.querySelector('#toOut').onclick = () => { markStep('check'); go('output'); };
        const mk = pane.querySelector('#mkQ');
        if (mk) mk.onclick = async () => {
          if (!S.user) return needLogin('登录后可以让 AI 出题。');
          mk.disabled = true; mk.innerHTML = '<span class="spin"></span> 正在出题…';
          try { await api('/api/next/import/enrich', { id, request_id: rid('ie') }); delete MAT[id]; toast('题目出好了'); route(true); }
          catch (e) { toast(e.message); mk.disabled = false; mk.textContent = '✦ 让 AI 出几道理解题'; }
        };
        return;
      }
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
          box.querySelector('.fb').innerHTML = `<p class="small"><b>${r.correct ? '答对了。' : '答案在原文这里：'}</b></p>${r.evidence ? `<div class="evidence">${esc(r.evidence)}</div>` : ''}`;
          if (Object.keys(answered).length === m.questions.length) {
            const right = Object.values(answered).filter(Boolean).length;
            markStep('check');
            pane.querySelector('#score').innerHTML = `<div class="card sunk row between enter"><span><b>${right} / ${m.questions.length}</b> 题答对</span><button class="btn primary" id="toOut">去用出来 →</button></div>`;
            pane.querySelector('#toOut').onclick = () => go('output');
          }
        } catch (e) { toast(e.message); delete answered[i]; box.querySelectorAll('.ans').forEach(x => x.disabled = false); }
      });
    }

    /* output: write, get the AI rewrite comparison, tied back to the knowledge graph */
    /* output modes: 仿写 (above) · 复述 · 情景对话 · 翻译 · 写作 — all built on this material */
    const OUT_MODES = { model: '仿写', retell: '复述', dialog: '对话', translate: '翻译', essay: '写作' };
    function outTabs(cur) {
      return `<div class="seg outmodes" role="tablist" aria-label="输出练习">${Object.entries(OUT_MODES).map(([k, l]) => `<a role="tab" href="#/m/${encodeURIComponent(id)}/output${k === 'model' ? '' : '/' + k}" aria-selected="${cur === k}">${l}</a>`).join('')}</div>`;
    }
    const needAI = reason => { if (!S.user) { needLogin(reason); return true; } return false; };

    function retellMode() {
      pane.innerHTML = `${outTabs('retell')}<div class="card flat task stack-s"><div class="kicker">复述</div><b>不看原文，用自己的话把这篇讲一遍</b>
          <span class="muted small">可以打字，也可以点 ● 直接说（最长 2 分钟）。AI 会提炼原文要点，看你讲到了哪些，并改出最影响理解的错误。</span></div>
        <textarea id="rtText" rows="6" maxlength="2500" lang="en" data-submit="#rtGo" placeholder="In this article, ..."></textarea>
        <div class="row between"><span class="row">${recBtn('rtMic', '说出来')}<span class="muted tiny" id="rtState">打字或录音都行</span></span><button class="btn primary" id="rtGo">AI 看看我的复述</button></div>
        <div id="rtOut"></div>`;
      let blob = null;
      const mic = pane.querySelector('#rtMic'), state = pane.querySelector('#rtState');
      mic.onclick = () => MIC.toggle(mic, 120, b => { blob = b; state.textContent = '已录好一段，可以提交了（会先转写）'; });
      pane.querySelector('#rtGo').onclick = async e => {
        if (needAI('登录后 AI 会看你的复述讲到了哪些要点。')) return;
        const text = pane.querySelector('#rtText').value.trim();
        if (!blob && (text.match(/[A-Za-z]+/g) || []).length < 8) { toast('先说一段或写几句英文'); return; }
        const btn = e.currentTarget; btn.disabled = true; btn.innerHTML = '<span class="spin"></span> 正在看…';
        try {
          const body = { pack: id, request_id: rid('rt') };
          if (blob) body.audio = await MIC.payload(blob); else body.text = text;
          const x = (await api('/api/next/retell', body)).result;
          pane.querySelector('#rtOut').innerHTML = `<div class="result enter stack">
            ${blob ? `<div class="card sunk small"><span class="muted">AI 听到：</span>${esc(x.transcript)}</div>` : ''}
            <div class="card verdict"><span class="dot"></span><div>${esc(x.comment)}<div class="tiny muted">讲到 ${x.points.filter(p => p.covered).length} / ${x.points.length} 个要点</div></div></div>
            <div class="card flat stack-s"><b>原文要点</b>${x.points.map(p => `<div class="small"><span class="${p.covered ? 'ok-mark' : 'bad-mark'}">${p.covered ? '✓' : '✗'}</span> ${esc(p.point)}</div>`).join('')}</div>
            ${x.used.length ? `<div class="small">用上了原文的表达：${x.used.map(u => `<span class="pill green">${esc(u)}</span>`).join(' ')}</div>` : ''}
            ${fixesHTML(x.fixes)}
            ${x.model ? `<div class="card flat stack-s"><div class="row between"><b>示范复述</b><button class="icon-btn" id="rtSay" aria-label="朗读">${ICON.speak}</button></div><div class="text small">${esc(x.model)}</div></div>` : ''}</div>`;
          const say = pane.querySelector('#rtSay'); if (say) say.onclick = () => TTS.say(x.model);
          bringIntoView(pane.querySelector('#rtOut'));
          markStep('output'); blob = null; state.textContent = '打字或录音都行';
        } catch (x) { toast(x.message); }
        btn.disabled = false; btn.textContent = 'AI 看看我的复述';
      };
    }

    function dialogMode() {
      const hist = [];
      pane.innerHTML = `${outTabs('dialog')}<div class="card flat task stack-s"><div class="kicker">情景对话</div><b>${esc(m.speaking_task || '围绕这篇的话题和 AI 聊几句')}</b>
          <span class="muted small">AI 扮演情景里的另一方。可以打字或说，每说一句它会顺手纠正；聊 4–6 轮后点「结束并总结」。</span></div>
        <div class="chat" id="chat"></div>
        <div id="dlgIn" class="stack-s" hidden><div class="tiny muted" id="dlgHint"></div>
          <div class="chat-in"><textarea id="dlgText" rows="2" maxlength="480" lang="en" enterkeyhint="send" placeholder="用英文回答…"></textarea>${recBtn('dlgMic', '说出来')}<button class="btn primary" id="dlgSend">发送</button></div>
          <div><button class="btn small ghost" id="dlgEnd">结束并总结</button></div></div>
        <div><button class="btn primary" id="dlgStart">开始对话</button></div><div id="dlgOut"></div>`;
      const chat = pane.querySelector('#chat');
      const bubble = (role, text, extra) => { chat.insertAdjacentHTML('beforeend', `<div class="msg ${role}"><div class="b">${esc(text)}</div>${extra || ''}</div>`); chat.lastElementChild.scrollIntoView({ block: 'nearest', behavior: REDUCED ? 'auto' : 'smooth' }); };
      const busy = on => { ['#dlgSend', '#dlgEnd', '#dlgMic'].forEach(s => { const b = pane.querySelector(s); if (b) b.disabled = on; }); };
      // After each reply: the newest message and the answer box are on screen together, above the keyboard and the tabs.
      const showInput = () => { const box = pane.querySelector('#dlgIn'); if (box && !box.hidden) box.scrollIntoView({ block: 'end', behavior: REDUCED ? 'auto' : 'smooth' }); };
      async function turn(body) {
        busy(true);
        try { return (await api('/api/next/dialog', { pack: id, history: hist, request_id: rid('dg'), ...body })).result; }
        catch (e) { toast(e.message); return null; } finally { busy(false); }
      }
      pane.querySelector('#dlgStart').onclick = async e => {
        if (needAI('登录后可以和 AI 做情景对话。')) return;
        const btn = e.currentTarget; btn.disabled = true; btn.innerHTML = '<span class="spin"></span>';
        const x = await turn({}); if (!x) { btn.disabled = false; btn.textContent = '开始对话'; return; }
        btn.parentNode.remove();
        chat.insertAdjacentHTML('beforeend', `<div class="scene small">${esc(x.scene)}${x.role ? `（AI 扮演：${esc(x.role)}）` : ''}</div>`);
        bubble('ai', x.reply); TTS.say(x.reply); hist.push({ role: 'ai', text: x.reply });
        pane.querySelector('#dlgIn').hidden = false; showInput(); if (!TOUCH) pane.querySelector('#dlgText').focus({ preventScroll: true });
      };
      async function send(text, blob) {
        const body = blob ? { audio: await MIC.payload(blob) } : { text };
        const x = await turn(body); if (!x) return;
        const me = x.heard || text;
        bubble('me', me, x.correction ? `<div class="fix tiny"><del>${esc(x.correction.original)}</del> → <b>${esc(x.correction.better)}</b> <span class="muted">${esc(x.correction.why)}</span></div>` : '');
        hist.push({ role: 'me', text: me });
        bubble('ai', x.reply); TTS.say(x.reply); hist.push({ role: 'ai', text: x.reply });
        pane.querySelector('#dlgHint').textContent = x.hint ? '提示：' + x.hint : '';
        showInput();
        if (hist.length >= 14) toast('聊得差不多了，可以结束并看总结');
      }
      pane.querySelector('#dlgSend').onclick = () => { const t = pane.querySelector('#dlgText'); const v = t.value.trim(); if (!v) return; t.value = ''; send(v); };
      pane.querySelector('#dlgText').addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); pane.querySelector('#dlgSend').click(); } });
      const mic = pane.querySelector('#dlgMic'); mic.onclick = () => MIC.toggle(mic, 30, b => send('', b));
      pane.querySelector('#dlgEnd').onclick = async e => {
        if (hist.filter(h => h.role === 'me').length < 1) { toast('先说一两句再总结'); return; }
        const btn = e.currentTarget; btn.innerHTML = '<span class="spin"></span>';
        const x = await turn({ end: true }); if (!x) { btn.textContent = '结束并总结'; return; }
        pane.querySelector('#dlgIn').hidden = true; TTS.stop(); markStep('output');
        pane.querySelector('#dlgOut').innerHTML = `<div class="result enter stack"><div class="card verdict"><span class="dot"></span><div>${esc(x.summary)}</div></div>
          ${x.good.length ? `<div class="card flat stack-s"><b>说得好的句子</b>${x.good.map(g => `<div class="small text">${esc(g)}</div>`).join('')}</div>` : ''}
          ${fixesHTML(x.fixes)}
          ${x.expressions.length ? `<div class="card flat stack-s"><b>可以学的表达</b>${x.expressions.map((ex, k) => `<div class="row between small"><span><b>${esc(ex.text)}</b> <span class="muted">${esc(ex.meaning)}</span></span><button class="btn small" data-kx="${k}">收藏</button></div>`).join('')}</div>` : ''}
          <div class="row"><button class="btn primary" id="dlgAgain">再练一轮</button><a class="btn" href="#/m/${encodeURIComponent(id)}/output/translate">换个练法：翻译</a></div></div>`;
        pane.querySelectorAll('[data-kx]').forEach(b => b.onclick = () => { const ex = x.expressions[Number(b.dataset.kx)]; saveCard({ text: ex.text, meaning: ex.meaning, context: '', pack: id }, b); });
        pane.querySelector('#dlgAgain').onclick = () => { scrollTo({ top: 0 }); dialogMode(); };
        bringIntoView(pane.querySelector('#dlgOut'));
      };
    }

    function translateMode() {
      const ls = lines().map(s => s.replace(/^[A-Z][a-z]+(?: [A-Z][a-z]+)?:\s+/, ''));
      const good = ls.map((s, i) => [s, i]).filter(([s]) => (s.match(/[A-Za-z]+/g) || []).length >= 8);
      let k = Math.max(0, good.findIndex(([, i]) => i === m.dictation_index)), dir = load('flow-next-trans-dir') || 'zh2en';
      async function render() {
        const [en, i] = good[k] || [ls[0], 0];
        pane.innerHTML = `${outTabs('translate')}<div class="seg two" role="tablist"><button data-dir="zh2en" aria-selected="${dir === 'zh2en'}">汉译英</button><button data-dir="en2zh" aria-selected="${dir === 'en2zh'}">英译汉</button></div>
          <div class="card flat stack-s"><div class="row between"><span class="kicker">第 ${k + 1} / ${good.length} 句</span><button class="link small" id="trNext">换一句</button></div>
            <div class="text" id="trSrc">${dir === 'en2zh' ? esc(en) : '<span class="spin"></span>'}</div></div>
          <textarea id="trIn" rows="3" maxlength="800" lang="${dir === 'zh2en' ? 'en' : 'zh'}" data-submit="#trGo" placeholder="${dir === 'zh2en' ? '译成英文…' : '译成中文…'}"></textarea>
          <div class="row between"><span class="muted tiny">${dir === 'zh2en' ? '译完对照原文，看哪里不一样。' : '意思准确、读起来像中文就是好译文。'}</span><button class="btn primary" id="trGo">提交</button></div><div id="trOut"></div>`;
        pane.querySelectorAll('[data-dir]').forEach(b => b.onclick = () => { dir = b.dataset.dir; save('flow-next-trans-dir', dir); render(); });
        pane.querySelector('#trNext').onclick = () => { k = (k + 1) % good.length; render(); };
        if (dir === 'zh2en') {
          if (!S.user) { pane.querySelector('#trSrc').innerHTML = '<span class="muted small">登录后可以做汉译英（中文原句由 AI 翻出，全站共享）。</span>'; }
          else try { pane.querySelector('#trSrc').textContent = (await api('/api/next/translate/source', { pack: id, i, request_id: rid('ts') })).zh; }
          catch (e) { pane.querySelector('#trSrc').textContent = e.message; }
        }
        pane.querySelector('#trGo').onclick = async e => {
          if (needAI('登录后 AI 会批改你的译文。')) return;
          const text = pane.querySelector('#trIn').value.trim(); if (text.length < 2) { toast('先写下你的译文'); return; }
          const btn = e.currentTarget; btn.disabled = true; btn.innerHTML = '<span class="spin"></span>';
          try {
            const x = (await api('/api/next/translate', { pack: id, i, direction: dir, text, request_id: rid('tr') })).result;
            pane.querySelector('#trOut').innerHTML = `<div class="result enter stack"><div class="card verdict"><span class="dot"></span><div>得分 ${Math.round(x.score * 100)}<div class="small">${esc(x.accuracy)}</div><div class="small muted">${esc(x.fluency)}</div></div></div>
              ${fixesHTML(x.fixes)}<div class="card flat stack-s"><b>${dir === 'zh2en' ? '原文' : '参考译文'}</b><div class="text small">${esc(dir === 'zh2en' ? x.original : x.reference)}</div>
              ${dir === 'zh2en' && x.reference && x.reference !== x.original ? `<div class="tiny muted">另一种自然说法：${esc(x.reference)}</div>` : ''}</div></div>`;
            markStep('output'); bringIntoView(pane.querySelector('#trOut'));
          } catch (x) { toast(x.message); }
          btn.disabled = false; btn.textContent = '提交';
        };
      }
      render();
    }

    function essayMode() {
      const key = 'flow-next-essay-' + id, lv = m.user_level || level();
      // The task's own word count wins ("写 200–250 词"); otherwise a range that fits the level.
      const asked = /(\d{2,3})\s*[–~\-—至到]\s*(\d{2,3})\s*(?:个)?(?:英文)?词/.exec(m.writing_task || '');
      const range = asked ? [Number(asked[1]), Number(asked[2])] : { A2: [60, 120], B1: [80, 160], B2: [120, 250], C1: [180, 350] }[lv] || [80, 200];
      pane.innerHTML = `${outTabs('essay')}<div class="card flat task stack-s"><div class="kicker">写作 · 建议 ${range[0]}–${range[1]} 词</div><b>${esc(m.writing_task || '围绕这篇的话题，写一段你自己的看法或经历。')}</b>
          <span class="muted small">按内容、结构、准确、丰富四个维度批改，给段落点评和示范段落；改出来的错误进错题本。</span></div>
        <textarea id="esIn" rows="10" maxlength="3000" lang="en" data-submit="#esGo" placeholder="Write here…">${esc(load(key) || '')}</textarea>
        <div class="row between"><span class="counter" id="esN"></span><button class="btn primary" id="esGo">AI 批改</button></div><div id="esOut"></div>`;
      const ta = pane.querySelector('#esIn'), n = pane.querySelector('#esN');
      const count = () => { const w = (ta.value.match(/[A-Za-z]+(?:'[A-Za-z]+)?/g) || []).length; n.textContent = `${w} 词`; n.classList.toggle('warn', w && (w < range[0] || w > range[1])); return w; };
      ta.oninput = () => { save(key, ta.value); count(); }; count();
      pane.querySelector('#esGo').onclick = async e => {
        if (needAI('登录后 AI 会按评分维度批改你的短文。')) return;
        if (count() < 40) { toast('至少写 40 个词'); return; }
        const btn = e.currentTarget; btn.disabled = true; btn.innerHTML = '<span class="spin"></span> 正在批改…';
        try {
          const x = (await api('/api/next/essay', { pack: id, text: ta.value, request_id: rid('es') })).result;
          const dims = { content: '内容切题', organization: '结构衔接', accuracy: '语言准确', range: '词汇句式' };
          pane.querySelector('#esOut').innerHTML = `<div class="result enter stack"><div class="card verdict"><span class="dot"></span><div>${esc(x.comment)}${x.level ? `<div class="tiny muted">这篇体现的水平约 ${esc(x.level)}</div>` : ''}</div></div>
            <div class="card flat ab-list">${Object.entries(dims).map(([k, l]) => `<div class="ab"><span class="nm">${l}</span><span class="vbar"><i data-w="${x.scores[k] * 20}"></i></span><span class="lv">${x.scores[k]} / 5</span></div>`).join('')}</div>
            ${x.paragraphs.length ? `<div class="card flat stack-s"><b>段落点评</b>${x.paragraphs.map(pg => `<div class="small"><b>第 ${pg.para} 段</b>：${esc(pg.note)}</div>`).join('')}</div>` : ''}
            ${fixesHTML(x.fixes)}
            ${x.better.length ? `<div class="card flat stack-s"><b>可以写得更好</b>${x.better.map(b => `<div class="small"><del>${esc(b.from)}</del><br><ins>${esc(b.to)}</ins><div class="tiny muted">${esc(b.why)}</div></div>`).join('')}</div>` : ''}
            ${x.model ? `<div class="card flat stack-s"><b>示范段落</b><div class="text small">${esc(x.model)}</div></div>` : ''}</div>`;
          requestAnimationFrame(() => requestAnimationFrame(() => pane.querySelectorAll('#esOut .vbar i').forEach(i => { i.style.width = i.dataset.w + '%'; })));
          const wn = count();
          if (wn < range[0] || wn > range[1]) pane.querySelector('#esOut .result').insertAdjacentHTML('afterbegin', `<div class="card sunk small">这篇 ${wn} 词，任务建议 ${range[0]}–${range[1]} 词：${wn < range[0] ? '内容展开得还不够，考试里会影响「内容」分。' : '超出了建议长度，考试里要注意时间和篇幅。'}</div>`);
          markStep('output'); bringIntoView(pane.querySelector('#esOut'));
        } catch (x) { toast(x.message); }
        btn.disabled = false; btn.textContent = '再批改一次';
      };
    }

    function output() {
      const om = parts()[3];
      if (om === 'retell') return retellMode();
      if (om === 'dialog') return dialogMode();
      if (om === 'translate') return translateMode();
      if (om === 'essay') return essayMode();
      const key = 'flow-next-draft-' + id;
      const draft = load(key) || '';
      pane.innerHTML = `${outTabs('model')}<div class="stack"><div class="card flat task"><div class="kicker">用出来</div><b>${esc(m.task.prompt)}</b>
          ${m.task.model ? `<div class="model">${esc(m.task.model)} <button class="icon-btn" id="sayModel" aria-label="朗读参考句">${ICON.speak}</button></div>` : ''}
          ${m.task.hint ? `<div class="muted small">${esc(m.task.hint)}</div>` : ''}
          ${(m.mine || []).length ? `<div class="muted small">可以试着用上你在背的词：${[...new Set(m.mine.map(x => x.form))].slice(0, 5).map(w => `<b>${esc(w)}</b>`).join('、')}（用对了算一次成功复习）</div>` : ''}</div>
        <label class="field">你的英文<textarea id="ans" maxlength="600" lang="en" data-submit="#go" placeholder="写一两句就好，写错没关系。">${esc(draft)}</textarea></label>
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
        try { const r = await api('/api/next/rewrite', { pack: id, text, request_id: rid('nr') }); markStep('output'); renderResult(r.result, text, r.remaining); }
        catch (e) { err.textContent = e.message; }
        btn.disabled = false; btn.textContent = '再改一次';
      };
    }
    function renderResult(r, yours, remaining) {
      const box = pane.querySelector('#result');
      const same = r.corrected.trim() === yours.trim();
      box.innerHTML = `<div class="result enter">
        <div class="card verdict ${esc(r.verdict)}"><span class="dot"></span><div>${esc(r.summary)}</div></div>
        <div class="card compare"><div class="kicker">${same ? '你写的已经是对的' : '改对之后'}</div>
          ${same ? '' : `<div class="yours">${esc(yours)}</div>`}<div class="fixed">${esc(r.corrected)} <button class="icon-btn" data-say-text="${esc(r.corrected)}" aria-label="朗读">${ICON.speak}</button></div>
          ${r.changes.length ? `<div>${r.changes.map(c => `<div class="change"><span class="ft"><del>${esc(c.from)}</del> → <ins>${esc(c.to)}</ins></span><span class="why">${esc(c.why)}</span>${c.node ? `<span>${nodeChip({ id: c.node, title: c.node_title || c.node, status: 'watch' })}</span>` : ''}</div>`).join('')}</div>` : ''}
          ${r.used_well && r.used_well.length ? `<div class="used-well small"><span class="muted">用对了：</span>${r.used_well.map(n => nodeChip({ id: n.id, title: n.title, status: 'used' })).join('')}</div>` : ''}</div>
        <div class="stack-s"><h2 class="h2">还可以这样说</h2>${r.versions.map((v, i) => `<div class="version"><div class="row between"><span class="pill green">${esc(v.label)}</span><span class="row"><button class="icon-btn" data-say-text="${esc(v.text)}" aria-label="朗读">${ICON.speak}</button><button class="icon-btn" data-keep-v="${i}" aria-label="收藏这句">${ICON.star}</button></span></div><div class="v">${esc(v.text)}</div><div class="small muted">${esc(v.why)}</div></div>`).join('')}</div>
        ${r.word_use && r.word_use.length ? `<div class="card sunk stack-s"><div class="kicker">你用到了正在背的词</div>${r.word_use.map(u => `<div class="small"><span class="${u.ok ? 'ok-mark' : 'bad-mark'}">${u.ok ? '✓' : '✗'}</span> <b>${esc(u.word)}</b>：${esc(u.note)}</div>`).join('')}
          <div class="tiny muted">用对的算一次成功复习；用错的会提前安排复习。</div></div>` : ''}
        ${r.keep ? `<div class="card sunk row between"><div><div class="kicker">值得收藏</div><b class="text">${esc(r.keep.text)}</b> <span class="muted small">${esc(r.keep.meaning)}</span></div><button class="btn small primary" id="keep">收藏</button></div>` : ''}
        <div class="card done-card">${doneRing}<h2 class="h2">这篇完成了</h2><p class="muted small">${remaining != null ? '今天还可以用 AI ' + remaining + ' 次。' : ''}收藏的表达会在合适的时候出现在复习里，知识图谱也已更新。</p>
          <div class="row center"><a class="btn" href="#/graph">看知识图谱</a><a class="btn primary" href="#/">回到今日</a></div></div></div>`;
      box.querySelectorAll('[data-say-text]').forEach(b => b.onclick = () => TTS.say(b.dataset.sayText));
      box.querySelectorAll('[data-keep-v]').forEach(b => b.onclick = () => { const v = r.versions[Number(b.dataset.keepV)]; saveCard({ text: v.text, meaning: v.label + '：' + v.why, context: '', pack: id }, b); });
      const k = box.querySelector('#keep'); if (k) k.onclick = () => saveCard({ text: r.keep.text, meaning: r.keep.meaning, context: r.corrected, pack: id }, k);
      box.scrollIntoView({ behavior: REDUCED ? 'auto' : 'smooth', block: 'start' });
    }
    ({ listen, read, check, output })[st.step]();
  }
  function splitSentences(body) { return body.split(/(?<=[.!?]["”’]?)\s+/).map(s => s.trim()).filter(Boolean); }
  function findContext(term, ls) { const t = term.toLowerCase(); return ls.find(s => s.toLowerCase().includes(t)) || ''; }

  async function lookupSheet(word, sentence, pack, mine) {
    if (mine && S.user) api('/api/next/vocab/met', { word }).then(r => { if (r.card && r.card.moved) toast('这个词在你的复习里，查了说明还不熟，已提前安排复习'); }).catch(() => {});
    openSheet(`<p class="loading"><span class="spin"></span></p>`);
    let e = null;
    try { e = (await api('/api/next/lookup?w=' + encodeURIComponent(word))).entry; } catch (x) { /* show fallback */ }
    const meaning = e ? e.meaning : '';
    const mt = MAT[pack];
    // This text's own gloss (本篇词汇) says what the word means here; the dictionary lists every sense.
    const here = mt && (mt.vocabulary || []).find(v => { const t = v.term.toLowerCase(); return t === word.toLowerCase() || (e && t === e.lemma); });
    if (e && mt) { (mt._looked = mt._looked || new Map()).set(e.lemma, { word: e.lemma, meaning: meaning.split('；').slice(0, 2).join('；').slice(0, 40), sentence }); if (mt._onLook) mt._onLook(); }
    openSheet(`<div class="stack">
      <div class="row between"><div><div class="word" id="sheetTitle">${esc(e ? e.word : word)}</div><div class="ph">${esc(e ? e.phonetic : '')}${e && e.lemma !== word.toLowerCase() ? ' · 原形 ' + esc(e.lemma) : ''}</div></div>
        <button class="icon-btn" id="sayW" aria-label="朗读">${ICON.speak}</button></div>
      ${here ? `<div class="here"><span class="pill green">在这篇里</span> ${esc(here.meaning)}</div>` : ''}
      <div class="mean${here ? ' dict' : ''}">${e ? esc(meaning).replace(/；|;/g, '<br>') : '<span class="muted">词典里没有这个词，可以先收藏，复习时再查。</span>'}</div>
      ${e && e.example ? `<div class="small muted text">${esc(e.example)}</div>` : ''}
      <div class="card sunk small text">${esc(sentence)}</div>
      <div class="row"><button class="btn primary" id="saveW">${ICON.star.replace('<svg', '<svg width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.8"')}收藏这个词</button><button class="btn" id="saveS">收藏整句</button><button class="btn" id="exS">✦ AI 讲解整句</button></div>
      <button class="btn ghost" data-close>关闭</button></div>`, card => {
      card.querySelector('#sayW').onclick = () => TTS.say(e ? e.word : word);
      card.querySelector('#saveW').onclick = () => saveCard({ text: e ? e.lemma : word, meaning: here ? here.meaning + '；' + meaning : meaning, context: sentence, pack }, card.querySelector('#saveW')).then(ok => {
        if (!ok || !mt) return;
        const forms = new Set([word.toLowerCase(), e ? e.lemma : word.toLowerCase()]);
        mt.mine = (mt.mine || []).concat([...forms].map(f => ({ form: f, id: 0 })));
        document.querySelectorAll('#reader .w').forEach(w => { if (forms.has(w.dataset.w.toLowerCase())) w.classList.add('mine'); });
        if (mt._onLook) mt._onLook();
      });
      card.querySelector('#saveS').onclick = () => saveCard({ text: sentence, meaning: '', context: '', pack }, card.querySelector('#saveS'));
      card.querySelector('#exS').onclick = () => explainSheet(sentence, pack);
    });
    TTS.say(e ? e.word : word);
  }
  async function explainSheet(sentence, pack) {
    if (!S.user) { needLogin('登录后，AI 会结合知识图谱讲解这句话的结构、语气和可模仿的句型。'); return; }
    openSheet(`<div class="stack"><div class="kicker">AI 讲解</div><div class="text" id="sheetTitle">${esc(sentence)}</div><p class="loading"><span class="spin"></span> 正在分析这句话…</p></div>`);
    try {
      const r = await api('/api/next/explain', { pack, sentence, request_id: rid('nx') });
      const x = r.result;
      openSheet(`<div class="stack explain enter"><div class="row between"><div class="kicker">AI 讲解</div><button class="icon-btn" id="sayS" aria-label="朗读">${ICON.speak}</button></div>
        <div class="text" id="sheetTitle">${esc(sentence)}</div>
        <div class="tr">${esc(x.translation)}</div>${x.structure ? `<div class="small muted">${esc(x.structure)}</div>` : ''}
        ${x.points.map(p => `<div class="pt"><b>${esc(p.text)}</b><span class="small">${esc(p.note)}</span>${p.node ? `<span>${nodeChip({ id: p.node, title: p.node_title || p.node, status: 'met' })}</span>` : ''}</div>`).join('')}
        ${x.pattern ? `<div class="card sunk stack-s"><div class="kicker">可模仿的句型</div><div class="frame">${esc(x.pattern.frame)}</div>${x.pattern.example ? `<div class="text small">${esc(x.pattern.example)}</div>` : ''}<div><button class="btn small" id="savePat">收藏这个句型</button></div></div>` : ''}
        <button class="btn ghost" data-close>关闭</button></div>`, card => {
        card.querySelector('#sayS').onclick = () => TTS.say(sentence);
        card.querySelectorAll('.node-chip').forEach(a => a.addEventListener('click', closeSheet));
        const sp = card.querySelector('#savePat'); if (sp) sp.onclick = () => saveCard({ text: x.pattern.frame, meaning: '句型' + (x.pattern.example ? '｜例：' + x.pattern.example : ''), context: sentence, pack }, sp);
      });
    } catch (e) { openSheet(`<div class="stack"><p class="err">${esc(e.message)}</p><button class="btn" data-close>关闭</button></div>`); }
  }
  async function saveCard(c, btn, from) {
    if (!S.user) { needLogin('登录后才能收藏，并按遗忘曲线提醒你复习。'); return false; }
    try {
      const r = await api('/api/next/cards', c);
      toast(r.existing ? '已经在复习里了，已更新原句' : '已收藏，会按遗忘曲线提醒你复习');
      if (btn) { btn.classList.add('on'); if (btn.classList.contains('btn')) { btn.disabled = true; btn.textContent = r.existing ? '已在复习里 ✓' : '已收藏 ✓'; } }
      if (!r.existing) flyToBank(c.text, btn || from);
      return true;
    } catch (e) { toast(e.message); return false; }
  }
  // A small label flies from where you saved it to the 单词 tab, so you see where it went.
  function flyToBank(text, fromEl) {
    const tab = document.querySelector('[data-nav="cards"]');
    if (!tab) return;
    if (!REDUCED && fromEl && fromEl.getBoundingClientRect) {
      const a = fromEl.getBoundingClientRect(), b = tab.getBoundingClientRect();
      const f = document.createElement('div'); f.className = 'flyer'; f.textContent = text.length > 24 ? text.slice(0, 22) + '…' : text;
      f.style.left = a.left + 'px'; f.style.top = a.top + 'px'; document.body.appendChild(f);
      requestAnimationFrame(() => requestAnimationFrame(() => { f.style.transform = `translate(${b.left + b.width / 2 - a.left - 30}px, ${b.top - a.top}px) scale(.5)`; f.style.opacity = '0'; }));
      setTimeout(() => f.remove(), 700);
    }
    setTimeout(() => { tab.classList.remove('bump'); void tab.offsetWidth; tab.classList.add('bump'); }, REDUCED ? 0 : 520);
  }

  /* ---------- knowledge graph ---------- */
  const STATUS_ORDER = ['solid', 'used', 'met', 'watch', 'untouched'];
  // Radial map: 18 nodes evenly on an outer ring (grouped by topic, one empty slot between topics),
  // topic hubs on an inner ring, labels pointing outward so they never collide.
  function graphSVG(g, compact) {
    const C = 200, RH = 74, RN = 142, RL = 160;
    const slots = g.topics.reduce((n, t) => n + t.nodes.length + 1, 0), step = 2 * Math.PI / slots;
    let edges = '', pre = '', hubs = '', nodes = '', k = 0, slot = 0;
    const pos = {}, f = v => v.toFixed(1);
    g.topics.forEach((t, ti) => {
      const first = slot, angles = t.nodes.map((_, i) => -Math.PI / 2 + (first + i + 0.5) * step);
      slot += t.nodes.length + 1;
      const ha = angles.reduce((s, a) => s + a, 0) / angles.length;
      const hx = C + RH * Math.cos(ha), hy = C + RH * Math.sin(ha);
      edges += `<line class="edge" x1="${C}" y1="${C}" x2="${f(hx)}" y2="${f(hy)}" data-delay="${ti * 0.05}"/>`;
      hubs += `<g class="hub"><circle cx="${f(hx)}" cy="${f(hy)}" r="21"/><text x="${f(hx)}" y="${f(hy)}">${esc(t.title)}</text></g>`;
      t.nodes.forEach((n, ni) => {
        const a = angles[ni], x = C + RN * Math.cos(a), y = C + RN * Math.sin(a);
        const lx = C + RL * Math.cos(a), ly = C + RL * Math.sin(a), cos = Math.cos(a);
        const anchor = cos > 0.25 ? 'start' : cos < -0.25 ? 'end' : 'middle';
        const dy = Math.sin(a) > 0.6 ? 10 : Math.sin(a) < -0.6 ? -4 : 3.5;
        pos[n.id] = [x, y];
        edges += `<line class="edge" x1="${f(hx)}" y1="${f(hy)}" x2="${f(x)}" y2="${f(y)}" data-delay="${0.25 + k * 0.02}"/>`;
        nodes += `<g class="gn st st-${n.status}${n.focus ? ' focus' : ''}" tabindex="0" role="link" data-node="${esc(n.id)}" data-delay="${0.35 + k * 0.035}" aria-label="${esc(n.title)}：${esc(n.label)}">
          <circle class="ring" cx="${f(x)}" cy="${f(y)}" r="13"/><circle class="dot" cx="${f(x)}" cy="${f(y)}" r="8.5"/>
          <text x="${f(lx)}" y="${f(ly + dy)}" text-anchor="${anchor}">${esc(n.title)}</text></g>`;
        k++;
      });
    });
    g.topics.forEach(t => t.nodes.forEach(n => { if (n.prereq && pos[n.prereq]) { const [x1, y1] = pos[n.prereq], [x2, y2] = pos[n.id]; pre += `<path class="pre" d="M${f(x1)},${f(y1)} Q${C},${C} ${f(x2)},${f(y2)}"/>`; } }));
    const vb = compact ? '30 30 340 340' : '-78 -22 556 444';
    if (compact) nodes = nodes.replace(/<text[^>]*>[^<]*<\/text><\/g>/g, '</g>');
    return `<svg class="gmap${compact ? ' compact' : ''}" viewBox="${vb}" role="img" aria-label="知识图谱：6 类、18 个语法知识点">
      <circle class="hub-ring" cx="${C}" cy="${C}" r="${RN}"/>${pre}${edges}
      <g class="hub"><circle cx="${C}" cy="${C}" r="27"/><text x="${C}" y="${C}">语法</text></g>${hubs}${nodes}</svg>`;
  }
  async function graphView() {
    const g = await api('/api/next/graph' + guestQuery(true));
    const s = g.summary;
    view.innerHTML = `<div><span class="kicker">知识图谱</span><h1 class="h1">你的英语语法地图</h1>
        <p class="muted small">18 个知识点分成 6 类。读到过、用出来、做题做对，都会点亮它；AI 在你写作里发现的问题也会标在这里。外圈呼吸的点，是「${esc(g.level)}」现在适合重点建立的。</p></div>
      <div class="gsum section">${[['solid', '已验证'], ['used', '用出来过'], ['met', '读到过'], ['watch', '要留意']].map(([k, l]) => `<div class="st st-${k}"><b>${s[k]}</b><span>${l}</span></div>`).join('')}</div>
      ${graphSVG(g, innerWidth < 560)}
      <div class="glegend">${STATUS_ORDER.map(k => `<span class="st st-${k}">${esc(g.labels[k])}</span>`).join('')}</div>
      <div class="topic-list section">${g.topics.map(t => `<div class="card flat topic"><div class="row between"><b>${esc(t.title)}</b><span class="tiny muted">${t.nodes.filter(n => n.status !== 'untouched').length} / ${t.nodes.length}</span></div>
        <div class="nodes">${t.nodes.map(n => nodeChip(n)).join('')}</div></div>`).join('')}</div>
      ${S.user ? '' : '<p class="muted small section">登录后，你读过、写过的内容会实时点亮这张图。</p>'}`;
    // CSP forbids inline style attributes, so animation delays are applied through the CSSOM.
    view.querySelectorAll('.gmap [data-delay]').forEach(el => { el.style.animationDelay = el.dataset.delay + 's'; });
    view.querySelectorAll('.gn').forEach(el => {
      const goNode = () => { location.hash = '#/graph/' + encodeURIComponent(el.dataset.node); };
      el.addEventListener('click', goNode); el.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); goNode(); } });
    });
  }
  async function nodeView(nid) {
    const n = await api('/api/next/node?id=' + encodeURIComponent(nid) + guestQuery(false));
    view.innerHTML = `<div><a class="link small" href="#/graph">← 知识图谱</a></div>
      <div><span class="kicker">${esc(n.topic)}</span><h1 class="h1">${esc(n.title)}</h1>
        <div class="row section"><span class="node-chip st st-${n.status}">${esc(n.label)}</span><span class="tiny muted">读到过 ${n.met} 篇 · 用出来 ${n.used} 次${n.flags ? ' · 写作中被指出 ' + n.flags + ' 次' : ''}${n.evidence ? ' · 做题：' + esc(n.evidence) : ''}</span></div></div>
      ${n.lesson ? `<div class="card flat stack-s"><b>要点</b><div class="small">${esc(n.lesson)}</div>${n.example ? `<div class="text small">${esc(n.example)}</div>` : ''}</div>` : ''}
      ${(n.prereq || n.unlocks.length) ? `<div class="row">${n.prereq ? `<span class="tiny muted">先学</span>${nodeChip({ id: n.prereq.id, title: n.prereq.title, status: 'met' })}` : ''}${n.unlocks.length ? `<span class="tiny muted">接下来</span>${n.unlocks.map(u => nodeChip({ id: u.id, title: u.title, status: 'untouched' })).join('')}` : ''}</div>` : ''}
      ${n.notes.length ? `<div class="stack-s"><h2 class="h2">AI 在你写作里看到的</h2>${n.notes.map(x => `<div class="knote"><span class="small">${x.kind === 'flag' ? '需要留意：' : '用对了'}${esc((x.detail.split('|')[1] || ''))}</span><span class="tiny muted">${new Date(x.created * 1000).toLocaleDateString('zh-CN')}</span></div>`).join('')}</div>` : ''}
      ${n.examples.length ? `<div class="stack-s"><h2 class="h2">在真实句子里看它</h2>${n.examples.map(x => `<a class="ex-quote" href="#/m/${encodeURIComponent(x.pack)}/read"><span>${esc(x.quote)}</span><div class="small muted">${esc(x.explanation)}</div></a>`).join('')}</div>` : ''}
      ${n.materials.length ? `<div><div class="section-head"><h2 class="h2">练这个知识点</h2></div><div class="grid-list">${n.materials.map(m => miniCard(m)).join('')}</div></div>` : ''}`;
  }

  /* ---------- cards ---------- */
  /* ---------- words: one FSRS memory queue for word books, saved words/expressions and imports ---------- */
  function highlight(ctx, text) {
    if (!ctx) return '';
    const i = ctx.toLowerCase().indexOf(text.toLowerCase());
    return i < 0 ? esc(ctx) : esc(ctx.slice(0, i)) + '<mark>' + esc(ctx.slice(i, i + text.length)) + '</mark>' + esc(ctx.slice(i + text.length));
  }
  // A sentence with the word (as it appears there) turned into a gap, or highlighted once revealed.
  function gapped(sentence, form, open) {
    const re = new RegExp(`(^|[^A-Za-z])(${form.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})(?![A-Za-z])`, 'i');
    const m = re.exec(sentence); if (!m) return esc(sentence);
    const at = m.index + m[1].length, w = sentence.slice(at, at + m[2].length);
    return esc(sentence.slice(0, at)) + (open ? `<span class="gap open">${esc(w)}</span>` : `<span class="gap" aria-label="空格">${' '.repeat(Math.max(4, w.length))}</span>`) + esc(sentence.slice(at + w.length));
  }
  const pct = r => r == null ? '' : Math.round(r * 100) + '%';
  function recallPill(c) {
    if (c.known) return '<span class="pill green">熟知</span>';
    if (c.state === 'new') return '<span class="pill">待学</span>';
    const r = c.recall; const cls = r >= 0.9 ? 'green' : r >= 0.75 ? '' : 'amber';
    return `<span class="pill ${cls}" title="此刻记得的概率">${c.mastered ? '已掌握 · ' : ''}记得 ${pct(r)}</span>`;
  }
  const SOURCE = { book: '词书', saved: '收藏', import: '导入' };
  // By calendar day, not "within 24 hours": a card due tomorrow morning is not "later today".
  function dueText(t) {
    const ms = t * 1000; if (ms <= Date.now()) return '该复习了';
    const day = x => { const d = new Date(x); d.setHours(0, 0, 0, 0); return d.getTime(); };
    const n = Math.round((day(ms) - day(Date.now())) / 864e5);
    return n === 0 ? '今天晚些时候复习' : n === 1 ? '明天复习' : `${n} 天后复习`;
  }
  const WEEKDAY = '日一二三四五六';
  function dayLabel(iso) { const [y, m, d] = iso.split('-').map(Number); return (y !== new Date().getFullYear() ? y + '年' : '') + m + '月' + d + '日'; }

  async function vocabView(q, page, f) {
    if (!S.user) {
      view.innerHTML = `<h1 class="h1">单词</h1><div class="empty"><div class="big">☆</div><p>选一本词书，每天学几个新词，系统按遗忘曲线安排复习；<br>读文章时点词收藏的单词和表达，也会一起复习。</p>
        <div class="row center"><button class="btn primary" id="lg">登录 / 注册</button><a class="btn" href="#/vocab/test">先测测词汇量</a></div></div>`;
      document.getElementById('lg').onclick = () => openLogin(); return;
    }
    q = q || ''; page = page || 1; f = f || '';
    const [o, list] = await Promise.all([api('/api/next/vocab'), api('/api/next/cards?q=' + encodeURIComponent(q) + '&page=' + page + '&f=' + f)]);
    const n = o.due + o.new;
    const start = new Date(); start.setHours(0, 0, 0, 0);
    const maxF = Math.max(1, ...o.forecast), maxC = Math.max(1, ...o.calendar.map(d => d.n));
    const today = o.plan
      ? `<div class="card section stack-s vtoday"><div class="row between"><div><div class="kicker">今天</div>
            ${n ? `<div class="big-line">复习 <b>${o.due}</b> · 新词 <b>${o.new}</b></div><div class="muted small">大约 ${o.minutes} 分钟 · 已完成 ${o.done_today} 次</div>`
              : `<div class="big-line">今天的都完成了</div><div class="muted small">已完成 ${o.done_today} 次 · 明天预计 ${o.forecast[1]} 个复习</div>`}</div>
            ${n ? '<a class="btn primary" href="#/review">开始</a>' : ''}</div>
          ${o.book ? `<div class="stack-s"><div class="row between small"><span>《${esc(o.book.title)}》已学 ${o.book.started} / ${o.book.size - (o.book.skipped || 0)}${o.book.skipped ? `<span class="muted">（跳过 ${o.book.skipped} 个常用词）</span>` : ''}</span><span class="muted">${o.book.finish ? '预计 ' + dayLabel(o.book.finish) + '学完' : '已全部学过'}</span></div>
            <div class="vbar"><i data-w="${o.book.started / Math.max(1, o.book.size - (o.book.skipped || 0)) * 100}"></i></div></div>` : ''}
          <div class="row small"><a class="link" href="#/vocab/plan">调整计划</a><span class="muted">每天 ${o.plan.daily_new} 个新词 · 目标记住率 ${Math.round(o.plan.retention * 100)}%</span></div></div>`
      : `<div class="card section stack-s"><div class="kicker">开始背单词</div><b>选一本词书，每天几个新词，按遗忘曲线复习</b>
          <span class="muted small">例句来自你读的文章，还能听原文录音。不选词书也可以：读文章时点词收藏，收藏的词同样按遗忘曲线复习。</span>
          <div class="row"><a class="btn primary" href="#/vocab/plan">选词书</a><a class="btn" href="#/vocab/test">先测词汇量（约 3 分钟）</a></div>
          ${n ? `<div class="row between small"><span>收藏的词：复习 ${o.due} · 待学 ${o.new}</span><a class="btn small" href="#/review">开始复习</a></div>` : ''}</div>`;
    view.innerHTML = `<div class="row between"><div><h1 class="h1">单词</h1><span class="muted small">共 ${o.total} 个 · 已掌握 ${o.mastered}</span></div>
        <button class="btn small" id="imp">导入词表</button></div>
      ${today}
      <div class="stat-grid section"><div class="card flat stat"><b>${o.mastered}</b><span class="tiny muted">已掌握</span></div><div class="card flat stat"><b>${o.learning}</b><span class="tiny muted">学习中</span></div>
        <div class="card flat stat"><b>${o.plan && o.plan.estimate ? o.plan.estimate.toLocaleString() : '—'}</b><span class="tiny muted">${o.plan && o.plan.estimate ? '词汇量估计' : '<a class="link" href="#/vocab/test">测词汇量</a>'}</span></div></div>
      <div class="card flat section stack-s"><div class="row between"><b class="small">未来 7 天的复习量</b><span class="tiny muted">按你的记忆情况算出</span></div>
        ${o.forecast.some(Boolean) ? '' : '<p class="muted tiny">开始学习后，这里会显示每天大约要复习多少个。</p>'}
        <div class="forecast" aria-label="未来 7 天复习量">${o.forecast.map((v, k) => { const d = new Date(start.getTime() + k * 864e5); return `<div><span class="n">${v || ''}</span><i data-h="${v / maxF * 100}"></i><span class="tiny muted">${k === 0 ? '今天' : k === 1 ? '明天' : '周' + WEEKDAY[d.getDay()]}</span></div>`; }).join('')}</div>
        <div class="cal" aria-label="最近 5 周每天复习次数">${o.calendar.map(d => `<i class="l${d.n ? Math.min(4, Math.ceil(d.n / maxC * 4)) : 0}" title="${d.day}：${d.n} 次"></i>`).join('')}</div></div>
      <form class="searchrow section" id="sf" role="search"><input type="search" name="q" enterkeyhint="search" placeholder="搜索单词、意思或原句${TOUCH ? '' : '（按 / 跳到这里）'}" value="${esc(q)}"><button class="btn">搜索</button></form>
      <div class="chips filt" role="group" aria-label="筛选">${[['', '全部'], ['word', '单词'], ['phrase', '表达'], ['mistake', '错题']].map(([k, l]) => `<button class="chip small" data-f="${k}" aria-pressed="${f === k}">${l}</button>`).join('')}</div>
      <div id="listSlot">${listHTML(list, q, page, f)}</div>`;
    requestAnimationFrame(() => requestAnimationFrame(() => {
      view.querySelectorAll('.vbar i').forEach(i => { i.style.width = i.dataset.w + '%'; });
      view.querySelectorAll('.forecast i').forEach(i => { i.style.height = Math.max(3, i.dataset.h) + '%'; });
    }));
    // Filters, search and pages swap only the list: the rest of the page stays put (no reload flash, no lost scroll).
    const st = { q, page, f };
    const reload = async () => {
      const slot = document.getElementById('listSlot'); slot.classList.add('busy');
      try { const l = await api('/api/next/cards?q=' + encodeURIComponent(st.q) + '&page=' + st.page + '&f=' + st.f); slot.innerHTML = listHTML(l, st.q, st.page, st.f); bindList(); }
      catch (e) { toast(e.message); } finally { slot.classList.remove('busy'); }
    };
    const bindList = () => {
      view.querySelectorAll('#listSlot [data-card]').forEach(b => b.onclick = () => cardSheet(Number(b.dataset.card), reload));
      const pv = document.getElementById('pv'), nx = document.getElementById('nx');
      if (pv) pv.onclick = () => { st.page--; reload().then(() => bringIntoView(document.getElementById('sf'))); };
      if (nx) nx.onclick = () => { st.page++; reload().then(() => bringIntoView(document.getElementById('sf'))); };
    };
    document.getElementById('sf').onsubmit = e => { e.preventDefault(); st.q = e.target.q.value.trim(); st.page = 1; reload(); };
    view.querySelectorAll('[data-f]').forEach(b => b.onclick = () => { st.f = b.dataset.f; st.page = 1; view.querySelectorAll('[data-f]').forEach(x => x.setAttribute('aria-pressed', String(x === b))); reload(); });
    document.getElementById('imp').onclick = importSheet;
    bindList();
  }
  function listHTML(list, q, page, f) {
    const pages = Math.max(1, Math.ceil(list.total / list.per));
    const none = q ? '没有找到。' : { word: '还没有单词。选一本词书，或者读文章时点词收藏。', phrase: '还没有收藏的表达。读文章时选中一段文字，或在「地道表达」里点 ☆。',
      mistake: '还没有错题。理解题答错、写作和口语里被改出的错误，都会自动收进来。' }[f] || '还没有单词。选一本词书，或者学一篇材料时点词收藏。';
    return `${list.items.length ? `<div class="grid-list" id="clist">${list.items.map(c => `<button class="card flat xcard" data-card="${c.id}"><div class="row between"><span class="x">${esc(c.text)}</span>${recallPill(c)}</div>
          ${c.meaning ? `<div class="small">${esc(c.meaning)}</div>` : ''}${c.context ? `<div class="ctx">${c.source === 'mistake' ? esc(c.context) : highlight(c.context, c.text)}</div>` : ''}
          <div class="tiny muted">${c.source === 'mistake' ? '错题 · ' + ({ fix: '改错', question: '理解题', sound: '发音' }[c.kind] || '') : SOURCE[c.source] || ''}${c.state !== 'new' && !c.known ? ` · 已复习 ${c.reps} 次 · ${dueText(c.due)}` : ''}</div></button>`).join('')}</div>`
        : `<div class="empty"><p>${none}</p></div>`}
      ${pages > 1 ? `<div class="pager"><button class="btn small" id="pv" ${page <= 1 ? 'disabled' : ''}>上一页</button><span class="muted small">${page} / ${pages}</span><button class="btn small" id="nx" ${page >= pages ? 'disabled' : ''}>下一页</button></div>` : ''}`;
  }

  // Memory curve: recall chance from the last review onwards, with today and the target retention marked.
  function curveSVG(c, retention) {
    if (!c.stability || !c.last) return '';
    const W = 300, H = 110, P = 22, now = (Date.now() / 1000 - c.last) / 86400, span = Math.max(14, now * 1.4, (c.due - c.last) / 86400 * 1.6);
    const x = t => P + t / span * (W - P - 6), y = r => 8 + (1 - r) * (H - 30);
    let d = ''; for (let k = 0; k <= 60; k++) { const t = span * k / 60; d += (k ? 'L' : 'M') + x(t).toFixed(1) + ' ' + y(recallAt(c.stability, t)).toFixed(1); }
    const dueT = (c.due - c.last) / 86400;
    return `<svg class="curve" viewBox="0 0 ${W} ${H}" role="img" aria-label="记忆曲线：此刻记得的概率 ${pct(c.recall)}">
      <line class="target" x1="${P}" x2="${W - 6}" y1="${y(retention)}" y2="${y(retention)}"/><text class="lbl" x="${W - 8}" y="${y(retention) - 4}" text-anchor="end">目标 ${Math.round(retention * 100)}%</text>
      <path class="line" d="${d}"/>
      <line class="due" x1="${x(dueT)}" x2="${x(dueT)}" y1="6" y2="${H - 22}"/><text class="lbl" x="${Math.max(x(dueT), P + 58)}" y="${H - 8}" text-anchor="${x(dueT) < P + 58 ? 'start' : 'middle'}">下次复习</text>
      <circle class="now" cx="${x(Math.min(now, span))}" cy="${y(recallAt(c.stability, Math.min(now, span)))}" r="4.5"/><text class="lbl" x="${P}" y="${H - 8}">上次复习</text></svg>`;
  }
  function examplesHTML(c, open) {
    const list = [];
    if (c.context) list.push({ text: c.context, form: c.source === 'mistake' ? ((c.extra || {}).from || c.text) : c.text, pack: c.pack, title: c.source === 'mistake' ? '你当时写的' : '你收藏时的原句', audio: 0, mine: true });
    (c.examples || []).forEach(e => list.push(e));
    return list.length ? `<div class="exs">${list.map((e, k) => `<div class="ex"><button class="icon-btn" data-exp="${k}" aria-label="播放例句">${ICON.speak}</button>
      <div><div class="text">${open === false ? gapped(e.text, e.form || c.text, false) : gapped(e.text, e.form || c.text, true)}</div>${e.zh && open !== false ? `<div class="tiny muted">${esc(e.zh)}</div>` : ''}
      ${e.pack ? `<a class="tiny muted link" href="#/m/${encodeURIComponent(e.pack)}/read">${e.mine ? esc(e.title) : '出自《' + esc(e.title) + '》'}${e.audio ? ' · 原文录音' : ''}</a>` : `<span class="tiny muted">${esc(e.title)}</span>`}</div></div>`).join('')}</div>` : '';
  }
  function rootsHTML(c) {
    return c.roots && c.roots.length ? `<div class="roots">${c.roots.map(r => `<span class="root"><span class="k">${esc(r.kind)}</span> <b>${esc(r.part)}</b> ${esc(r.meaning)}</span>`).join('')}</div>` : '';
  }
  function bindExamples(root, c) {
    const list = []; if (c.context) list.push({ text: c.context, audio: 0 }); (c.examples || []).forEach(e => list.push(e));
    root.querySelectorAll('[data-exp]').forEach(b => b.onclick = () => CLIP.sentence(list[Number(b.dataset.exp)]));
  }
  async function cardSheet(id, after) {
    openSheet(`<p class="loading"><span class="spin"></span></p>`);
    let d; try { d = await api('/api/next/vocab/card?id=' + id); } catch (e) { openSheet(`<p class="err">${esc(e.message)}</p>`); return; }
    const c = d.card;
    const tl = { again: '忘了', hard: '模糊', good: '记得', easy: '很熟', known: '熟知', lookup: '读文章时查过' };
    openSheet(`<div class="stack">
      <div class="row between"><div><div class="word" id="sheetTitle">${esc(c.text)}</div><div class="ph">${esc(c.phonetic || '')}</div></div><button class="icon-btn" id="sayW" aria-label="朗读">${ICON.speak}</button></div>
      ${c.source === 'mistake' && (c.extra || {}).from ? `<div class="fixline"><del>${esc(c.extra.from)}</del> → <ins>${esc(c.text)}</ins></div>` : ''}
      ${c.meaning ? `<div class="mean">${esc(c.meaning).replace(/；|;/g, '<br>')}</div>` : ''}${rootsHTML(c)}
      <div class="row">${recallPill(c)}${c.stability ? `<span class="pill">记忆稳定性 ${c.stability < 1 ? '不到 1 天' : Math.round(c.stability) + ' 天'}</span>` : ''}${c.state !== 'new' && !c.known ? `<span class="pill">${dueText(c.due)}</span>` : ''}</div>
      ${curveSVG(c, d.retention)}
      <div id="exSlot">${examplesHTML(c) || (c.kind === 'word' && S.user ? '<p class="muted tiny"><span class="spin"></span> 正在找例句…</p>' : '')}</div>
      ${d.history.length ? `<div class="tiny muted">复习记录：${d.history.slice(-8).map(h => `${new Date(h.created * 1000).toLocaleDateString('zh-CN', { month: 'numeric', day: 'numeric' })} ${tl[h.rating] || h.rating}`).join(' · ')}</div>` : ''}
      <div class="row"><button class="btn" id="known">${c.known ? '取消熟知，继续复习' : '标为熟知，不再复习'}</button><button class="btn ghost" id="del">删除</button><button class="btn ghost" data-close>关闭</button></div></div>`, card => {
      card.querySelector('#sayW').onclick = () => CLIP.word(c);
      bindExamples(card, c);
      if (c.kind === 'word' && S.user && !(c.examples || []).length) {
        api('/api/next/vocab/examples', { words: [c.text.toLowerCase()], request_id: rid('ve') }).then(r => {
          const ex = (r.examples || {})[c.text.toLowerCase()], slot = card.querySelector('#exSlot');
          if (!slot || !document.contains(slot)) return;
          if (ex && ex.length) c.examples = ex;
          slot.innerHTML = examplesHTML(c) || '<p class="muted tiny">暂时没有例句。</p>'; bindExamples(slot, c);
        }).catch(() => { const slot = card.querySelector('#exSlot'); if (slot) slot.innerHTML = examplesHTML(c); });
      }
      card.querySelector('#known').onclick = async () => { try { await api('/api/next/vocab/known', { id: c.id, known: !c.known }); closeSheet(); toast(c.known ? '已恢复复习' : '已标为熟知'); refreshHome().catch(() => {}); if (after) after(); } catch (e) { toast(e.message); } };
      const delB = card.querySelector('#del'); if (delB) delB.setAttribute('aria-label', '删除 ' + c.text);
      card.querySelector('#del').onclick = async () => { if (!confirm('删除这个词和它的复习记录？')) return; try { await api('/api/next/cards/delete', { id: c.id }); closeSheet(); if (after) after(); } catch (e) { toast(e.message); } };
    });
    CLIP.word(c);
  }
  function importSheet() {
    openSheet(`<div class="stack"><h2 class="h2" id="sheetTitle">导入词表</h2>
      <p class="muted small">每行一个单词或短语（也可以用逗号分开），一次最多 500 个。词典里有的会自动配上释义和例句；已经在复习里的会跳过。适合导入专四、专八或老师给的词表。</p>
      <textarea id="impText" rows="8" placeholder="abandon&#10;make ends meet&#10;serendipity"></textarea>
      <div class="row"><button class="btn primary" id="impGo">导入</button><button class="btn ghost" data-close>取消</button></div></div>`, card => {
      card.querySelector('#impGo').onclick = async e => {
        e.currentTarget.disabled = true;
        try { const r = await api('/api/next/vocab/import', { text: card.querySelector('#impText').value }); closeSheet(); toast(`导入了 ${r.added} 个${r.skipped ? `，跳过 ${r.skipped} 个已有的` : ''}`); refreshHome().catch(() => {}); vocabView(); }
        catch (x) { toast(x.message); e.currentTarget.disabled = false; }
      };
    });
  }

  async function planView() {
    if (!S.user) return needLogin('登录后才能制定背词计划。');
    const o = await api('/api/next/vocab');
    const cur = o.plan || { book: o.suggested_book, daily_new: 10, retention: 0.9 };
    let book = cur.book, daily = cur.daily_new, ret = cur.retention;
    view.innerHTML = `<h1 class="h1">背词计划</h1><span class="muted small">随时可以改，已学的进度不会丢。</span>
      <div class="section stack-s"><h2 class="h2">词书</h2><span class="muted tiny">按词频分段的词书从你的水平往上走；考试词书按大纲词表、常用词在前。专四、专八等词表可以在「单词」页导入。</span>
        ${[['freq', '按词频'], ['exam', '考试词书']].map(([kind, label]) => `<div class="kicker">${label}</div><div class="books">${o.books.filter(b => b.kind === kind).map(b => `<button class="card flat bookc" data-book="${b.id}" aria-pressed="${b.id === book}"><div class="row between"><b>${esc(b.title)}</b>${b.id === o.suggested_book ? '<span class="pill green">推荐</span>' : ''}</div><span class="small">${esc(b.blurb)}</span><span class="tiny muted">${b.size} 词${b.range ? ' · 词频第 ' + b.range + ' 位' : ''}</span></button>`).join('')}${kind === 'exam' ? `<button class="card flat bookc" id="impBook" type="button"><b>专四 / 专八 / 老师给的词表</b><span class="small">这些没有可以内置的公开官方词表：把手上的词表粘贴进来，就和词书一起按遗忘曲线复习。</span><span class="tiny muted">导入词表 →</span></button>` : ''}</div>`).join('')}</div>
      <div class="section stack-s"><h2 class="h2">每天新词</h2><div class="chips" id="dn">${o.daily_new_options.map(v => `<button class="chip" data-v="${v}" aria-pressed="${v === daily}">${v} 个</button>`).join('')}</div>
        <span class="muted tiny" id="dnHint"></span></div>
      <div class="section stack-s"><h2 class="h2">目标记住率</h2><div class="chips" id="rt">${o.retention_options.map(v => `<button class="chip" data-v="${v}" aria-pressed="${v === ret}">${Math.round(v * 100)}%</button>`).join('')}</div>
        <span class="muted tiny">系统会在你记住的概率降到这个数时安排复习。越高记得越牢，但每天复习更多；90% 是比较均衡的选择。</span></div>
      ${o.plan && o.plan.estimate ? `<label class="section checkline"><input type="checkbox" id="skipKnown" ${o.plan.skip_rank ? 'checked' : ''}>考试词书里跳过测试显示你已经认识的常用词${o.plan.test_skip ? `（词频前 ${o.plan.test_skip} 位）` : ''}</label>` : ''}
      <div class="section row"><button class="btn primary" id="savePlan">${o.plan ? '保存' : '开始背'}</button><a class="btn ghost" href="#/cards">取消</a></div>
      <div class="section card flat stack-s" id="remind"><h2 class="h2">复习提醒</h2>
        <span class="muted tiny">遗忘曲线最怕"到期没人提醒"。选一个每天方便的时间：</span>
        <div class="row"><select id="rHour" aria-label="提醒时间">${Array.from({ length: 18 }, (_, k) => k + 6).map(h => `<option value="${h}" ${h === o.reminder.hour ? 'selected' : ''}>每天 ${h}:00</option>`).join('')}</select></div>
        <label class="checkline"><input type="checkbox" id="rMail" ${o.reminder.enabled ? 'checked' : ''} ${o.reminder.has_email ? '' : 'disabled'}><span>到点发邮件提醒（只在有词要复习时发）${o.reminder.has_email ? '' : '<br><span class="muted tiny">账号还没绑定邮箱：可以在<a class="link" href="#/me">「我的」</a>里绑定，或者先用下面的日历提醒。</span>'}</span></label>
        <div class="row"><a class="btn small" id="rCal" href="/api/next/vocab/reminder.ics?hour=${o.reminder.hour}">加到手机日历</a><span class="muted tiny">日历每天到点提醒，不依赖任何 App</span></div></div>`;
    const meta = id => o.books.find(b => b.id === id) || {};
    // Days left: words not yet studied, minus the ones this plan skips (everyday words; for exam books, what the test showed you know).
    const hint = () => {
      const sk = document.getElementById('skipKnown'), b = meta(book);
      const skip = book === 'core' || (sk ? sk.checked : true) ? (b.skippable || 0) : 0;
      const done = o.book && o.book.id === book ? o.book.started : 0;
      const days = Math.ceil(Math.max(0, (b.size || 0) - skip - done) / daily);
      document.getElementById('dnHint').textContent = `学完《${b.title}》大约需要 ${days} 天${skip ? `（跳过 ${skip} 个常用词）` : ''}；新词越多，之后每天的复习也越多（约为新词的 3–5 倍）。`;
    };
    view.querySelectorAll('[data-book]').forEach(b => b.onclick = () => { book = b.dataset.book; view.querySelectorAll('[data-book]').forEach(x => x.setAttribute('aria-pressed', String(x === b))); hint(); });
    const pick = (sel, set) => view.querySelectorAll(sel + ' [data-v]').forEach(b => b.onclick = () => { set(Number(b.dataset.v)); view.querySelectorAll(sel + ' [data-v]').forEach(x => x.setAttribute('aria-pressed', String(x === b))); hint(); });
    pick('#dn', v => { daily = v; }); pick('#rt', v => { ret = v; });
    const skBox = document.getElementById('skipKnown'); if (skBox) skBox.onchange = hint;
    document.getElementById('impBook').onclick = importSheet;
    hint();
    const rHour = document.getElementById('rHour'), rMail = document.getElementById('rMail'), rCal = document.getElementById('rCal');
    const saveRemind = async () => { rCal.href = '/api/next/vocab/reminder.ics?hour=' + rHour.value; try { await api('/api/next/vocab/reminder', { enabled: rMail.checked, hour: Number(rHour.value) }); toast(rMail.checked ? `每天 ${rHour.value}:00 会提醒你` : '提醒时间已更新'); } catch (x) { toast(x.message); rMail.checked = false; } };
    rHour.onchange = saveRemind; rMail.onchange = saveRemind;
    document.getElementById('savePlan').onclick = async e => {
      e.currentTarget.disabled = true;
      const sk = document.getElementById('skipKnown');
      try { await api('/api/next/vocab/plan', { book, daily_new: daily, retention: ret, ...(sk ? { skip_known: sk.checked } : {}) }); await refreshHome(); toast('计划已保存'); location.hash = '#/cards'; }
      catch (x) { toast(x.message); e.currentTarget.disabled = false; }
    };
  }

  async function vocabTest() {
    const t = await api('/api/next/vocab/test');
    const items = t.items, answers = {}; let i = 0;
    function show() {
      document.body.classList.add('reviewing');
      if (i >= items.length) return finish();
      view.innerHTML = `<div class="bar-progress"><i id="rp"></i></div><div class="review vtest enter"><p class="muted small">认识这个词吗？看到能想起大概意思就算认识。<br>有几个是编出来的假词，用来校正估计。</p>
        <div class="wordbig">${esc(items[i])}</div>
        <div class="choice two"><button data-a="0">不认识<small>←</small></button><button class="good" data-a="1">认识<small>→</small></button></div>
        <p class="muted tiny tc">${i + 1} / ${items.length}</p></div>`;
      document.getElementById('rp').style.width = (i / items.length * 100) + '%';
      view.querySelectorAll('[data-a]').forEach(b => b.onclick = () => answer(b.dataset.a === '1'));
      document.onkeydown = e => { if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') { e.preventDefault(); answer(e.key === 'ArrowRight'); } };
    }
    function answer(yes) { answers[items[i]] = yes; i++; show(); }
    async function finish() {
      document.onkeydown = null; document.body.classList.remove('reviewing');
      view.innerHTML = `<p class="loading"><span class="spin"></span> 正在估算…</p>`;
      const r = await api('/api/next/vocab/test', { answers });
      if (!S.user) save('flow-next-guest-test', { answers, at: Date.now() });  // kept, and saved to the account after signing in
      const o = S.user ? await api('/api/next/vocab') : null;
      const titles = r.titles || {}, title = titles[r.suggest] || r.suggest;
      view.innerHTML = `<div class="card done-card enter stack"><div class="kicker">词汇量估计</div><div class="huge">${r.estimate.toLocaleString()}</div>
        <p class="muted small">${r.guessing ? '你选了不少假词，估计可能偏高，已经按比例扣除。' : '按词频分段抽样估算，误差约几百词。'}</p>
        <div class="bands">${Object.entries(r.bands).map(([k, v]) => `<div class="row between small"><span>${esc(titles[k] || k)}</span><span class="vbar"><i data-w="${v * 100}"></i></span><span class="muted">${Math.round(v * 100)}%</span></div>`).join('')}</div>
        <p>${r.ceiling ? `常用的 2 万词你几乎都认识，超出了这个测试能测的范围。建议用《${esc(title)}》这类考试词表，或在「单词」页导入专四、专八或专业词表。` : `建议从《${esc(title)}》开始。`}</p>
        ${S.user ? '' : '<p class="muted small">结果已经记下，登录后会存到你的账号。</p>'}
        <div class="row center"><button class="btn primary" id="useBook">用《${esc(title)}》开始</button><button class="btn" id="retest">重新测</button><a class="btn ghost" href="#/cards">返回单词</a></div></div>`;
      document.getElementById('retest').onclick = () => vocabTest();
      requestAnimationFrame(() => requestAnimationFrame(() => view.querySelectorAll('.vbar i').forEach(x => { x.style.width = x.dataset.w + '%'; })));
      document.getElementById('useBook').onclick = async () => {
        if (!S.user) return needLogin('登录后可以按测试结果制定背词计划。');
        try { const cur = (o && o.plan) || {}; await api('/api/next/vocab/plan', { book: r.suggest, daily_new: cur.daily_new || 10, retention: cur.retention || 0.9 });
          await api('/api/next/vocab/test', { answers }); await refreshHome(); location.hash = '#/cards'; } catch (e) { toast(e.message); }
      };
    }
    show();
  }

  /* ---------- review: recognise -> recall -> spell as an item gets stronger ---------- */
  async function reviewView() {
    if (!S.user) return needLogin('登录后才能复习。');
    document.body.classList.add('reviewing');
    let first, offline = false;
    try { await OUTBOX.flush(); first = await api('/api/next/review'); save('flow-next-review-cache', { at: Date.now(), q: first }); }
    catch (e) {
      const cached = load('flow-next-review-cache');
      if (!e.network || !cached || Date.now() - cached.at > 2 * 86400000) throw e;
      const done = new Set(OUTBOX.list().map(x => x.body.id)); offline = true;
      first = { ...cached.q, items: cached.q.items.filter(x => !done.has(x.id)) };
    }
    if (offline) toast('现在没有网络：先用缓存的复习，联网后自动同步');
    prefetchAudio(first.items.flatMap(x => {
      const au = x.audio || {}, ac = au[CLIP.accent()] ? CLIP.accent() : au.us ? 'us' : null;
      return [ac ? `/audio/words/${ac}/${au[ac][0]}.mp4` : null, ...(x.examples || []).filter(e => e.audio).map(e => `/audio/${S.voice}/${encodeURIComponent(e.pack)}.json?v=${e.audio}`)];
    }));
    const lacking = first.items.filter(x => x.kind === 'word' && !(x.examples || []).length).map(x => x.text.toLowerCase()).slice(0, 8);
    if (lacking.length && !offline) api('/api/next/vocab/examples', { words: lacking, request_id: rid('ve') }).then(r => {
      Object.entries(r.examples || {}).forEach(([w, ex]) => items.forEach(x => { if (x.text.toLowerCase() === w && !(x.examples || []).length) x.examples = ex; }));
    }).catch(() => {});
    const items = first.items.slice(), seen = new Set(items.map(x => x.id));
    let i = 0, doneN = 0, left = first; const tally = { again: 0, hard: 0, good: 0, easy: 0, known: 0 };
    // Progress counts cards, not answers: a card shown again to consolidate it does not grow the total.
    const uniq = new Set(items.map(x => x.id)), doneIds = new Set();
    const pos = () => c.repeat ? '再巩固一次' : `${Math.min(uniq.size, doneIds.size + 1)} / ${uniq.size}${c.source === 'book' && c.state === 'new' ? ' · 新词' : ''}`;
    const foot = () => `<p class="muted tiny tc rfoot">${pos()}</p>`;
    const top = () => `<div class="rtop"><a class="link small" href="#/cards">结束</a><div class="bar-progress"><i id="rp"></i></div></div>`;
    const badge = res => { const b = document.getElementById('dueBadge'); if (b && res && res.due != null) { const n = res.due + res.new; b.hidden = !n; b.textContent = n > 99 ? '99+' : n; } };
    // Touch: swipe the card right for "I know it" (or the main button), left for "I don't".
    let swipe = null;
    const onSwipe = (right, left2) => { swipe = { right, left: left2 }; };
    if (!items.length) {
      document.body.classList.remove('reviewing');
      view.innerHTML = `<div class="empty"><div class="big">✓</div><p>现在没有要复习的单词。</p><div class="row center"><a class="btn" href="#/cards">单词</a><a class="btn primary" href="#/">回到今日</a></div></div>`; return;
    }
    let c, t0, claim;
    const bar = () => { const rp = document.getElementById('rp'); if (rp) rp.style.width = (doneIds.size / Math.max(1, uniq.size) * 100) + '%'; };
    const keys = map => { document.onkeydown = e => { if (!sheetEl.hidden || e.metaKey || e.ctrlKey || e.altKey) return; if (e.target.matches && e.target.matches('input,textarea')) { if (e.key === 'Enter' && map.Enter && ['spellIn', 'fixIn'].includes(e.target.id)) { e.preventDefault(); map.Enter(); } return; } const f = map[e.key] || map[e.key.toLowerCase()]; if (f) { e.preventDefault(); f(); } }; };
    let sx = null;
    view.ontouchstart = e => { sx = e.touches.length === 1 && !isTyping(e) && !e.target.closest('button,a,input') ? [e.touches[0].clientX, e.touches[0].clientY] : null; };
    view.ontouchmove = e => { if (!sx || !swipe) return; const dx = e.touches[0].clientX - sx[0], card = view.querySelector('.review'); if (card && Math.abs(dx) > Math.abs(e.touches[0].clientY - sx[1])) card.style.transform = `translateX(${dx * 0.35}px) rotate(${dx * 0.02}deg)`; };
    view.ontouchend = e => {
      const card = view.querySelector('.review'); if (card) card.style.transform = '';
      if (!sx || !swipe) return; const t = e.changedTouches[0], dx = t.clientX - sx[0], dy = t.clientY - sx[1]; sx = null;
      if (Math.abs(dx) > 80 && Math.abs(dy) < 70) { const f = dx > 0 ? swipe.right : swipe.left; if (f) f(); }
    };
    if (TOUCH && !load('flow-next-swipe-tip')) { save('flow-next-swipe-tip', 1); setTimeout(() => toast('小技巧：右滑「认识」，左滑「不认识」'), 600); }
    // A saved sentence pattern: the frame's fixed words become gaps in its example, so the front does not give it away.
    const frameCloze = (example, frame) => {
      const fixed = (frame.match(/[A-Za-z']+/g) || []).filter(w => !/^(A|B|C|sb|sth|do|doing|done|adj|n|v|X|Y)$/.test(w)).map(w => w.toLowerCase());
      let k = 0; const want = fixed.slice();
      return esc(example).replace(/[A-Za-z']+/g, w => (k < want.length && w.toLowerCase() === want[k]) ? (k++, `<span class="gap">${' '.repeat(Math.max(3, w.length))}</span>`) : w);
    };
    const sentenceOf = x => x.context && x.context.toLowerCase().includes(x.text.toLowerCase()) ? { text: x.context, form: x.text } : (x.examples && x.examples[0]) || null;
    const meaningHTML = x => x.meaning ? `<div class="mean-q">${esc(x.meaning).replace(/；|;/g, '<br>')}</div>` : '';

    // Mistakes come back on the forgetting curve too: answer the question again, fix the phrase, say the sound.
    function mistakeAsk() {
      const ex = c.extra || {}, src = { reading: '理解题', writing: '写作', speaking: '口语', translation: '翻译', pronunciation: '发音' }[c.skill] || '错题';
      const tag = `<span class="pill amber rtag">错题 · ${esc(src)}</span>`;
      let body = '';
      if (c.mode === 'question') {
        const opts = ex.options || [];
        body = `${tag}<div class="prompt-q">${esc(c.text)}</div><div class="qopts">${opts.map((o, k) => `<button class="qopt" data-o="${k}">${esc(o)}</button>`).join('')}</div>`;
      } else if (c.mode === 'fix') {
        // Just the sentence the mistake was in (older cards kept the whole paragraph), with the wrong part underlined.
        const sent = c.context && ex.from ? (splitSentences(c.context).find(x => x.toLowerCase().includes(ex.from.toLowerCase())) || '') : '';
        const ctx = sent ? highlight(sent, ex.from) : '';
        body = `${tag}<div class="muted small">上次这样写：</div><div class="cloze fixq">${ctx || `<mark>${esc(ex.from || '')}</mark>`}</div>
          ${c.node ? `<div>${nodeChip({ id: c.node.id, title: c.node.title, status: 'watch' })}</div>` : ''}
          <input id="fixIn" class="spell" lang="en" enterkeyhint="done" autocomplete="off" autocapitalize="off" autocorrect="off" spellcheck="false" placeholder="划线部分应该怎么写？">
          <div class="row center"><button class="btn primary" id="fixGo">确定</button><button class="btn ghost" id="fixNo">想不起来</button></div>`;
      } else {
        body = `${tag}<div class="wordbig">${esc(c.text)}</div><div><button class="icon-btn big" id="sayW" aria-label="听">${ICON.speak}</button></div>
          ${c.meaning ? `<div class="mean-q small">${esc(c.meaning)}</div>` : ''}
          <div class="row center">${recBtn('sndMic', '读一遍')}<span class="muted tiny" id="sndOut">${S.user ? '点 ● 读一遍，AI 听你读得准不准' : ''}</span></div>
          <div class="choice">${['读准了', '还不稳', '不会读'].map((t, k) => `<button class="${['good', '', 'again'][k]}" data-self="${['good', 'hard', 'again'][k]}">${t}</button>`).join('')}</div>`;
      }
      view.innerHTML = `${top()}<div class="review enter">${body}${foot()}</div>`;
      bar(); swipe = null;
      const after = (r, html) => {
        const ms = Date.now() - t0;
        view.querySelector('.review').insertAdjacentHTML('beforeend', `<div class="stack-s enter">${html}<div class="row center"><button class="btn primary" id="go">下一个</button></div></div>`);
        document.getElementById('go').onclick = () => rate(r, ms); keys({ Enter: () => rate(r, ms), ' ': () => rate(r, ms) });
      };
      if (c.mode === 'question') {
        view.querySelectorAll('[data-o]').forEach(b => b.onclick = () => {
          const k = Number(b.dataset.o), ok = k === ex.answer;
          view.querySelectorAll('[data-o]').forEach(x => { x.disabled = true; if (Number(x.dataset.o) === ex.answer) x.classList.add('right'); });
          if (!ok) b.classList.add('wrong');
          after(ok ? 'good' : 'again', `<div class="${ok ? 'ok' : 'bad'}">${ok ? '✓ 这次答对了' : '还是错了'}</div>${ex.evidence ? `<div class="small"><span class="muted">原文依据：</span>${esc(ex.evidence)}</div>` : ''}`);
        });
        keys({ 1: () => view.querySelector('[data-o="0"]').click(), 2: () => view.querySelector('[data-o="1"]').click(), 3: () => view.querySelector('[data-o="2"]').click(), 4: () => view.querySelector('[data-o="3"]').click() });
      } else if (c.mode === 'fix') {
        const inp = document.getElementById('fixIn'); setTimeout(() => inp.focus(), 50);
        const norm = s => s.toLowerCase().replace(/[^a-z' ]+/g, ' ').replace(/\s+/g, ' ').trim();
        const done = v => {
          view.querySelectorAll('#fixGo,#fixNo').forEach(b => b.remove()); inp.disabled = true;
          const ok = !!v && norm(v) === norm(c.text);
          after(ok ? 'good' : 'again', `<div class="${ok ? 'ok' : 'bad'}">${ok ? '✓ 改对了' : '应该是'}：<b>${esc(c.text)}</b></div>${c.meaning ? `<div class="small">${esc(c.meaning)}</div>` : ''}`);
        };
        document.getElementById('fixGo').onclick = () => done(inp.value.trim());
        document.getElementById('fixNo').onclick = () => done('');
        keys({ Enter: () => done(inp.value.trim()) });
      } else {
        document.getElementById('sayW').onclick = () => CLIP.word(c); CLIP.word(c);
        const mic = document.getElementById('sndMic'), out = document.getElementById('sndOut');
        mic.onclick = () => MIC.toggle(mic, 4, async blob => {
          out.innerHTML = '<span class="spin"></span>';
          try { const x = (await api('/api/next/say', { text: c.text, audio: await MIC.payload(blob), request_id: rid('sy') })).result; out.innerHTML = x.ok ? '<span class="ok-mark">✓ 这次读准了</span>' : `<span class="bad-mark">AI 听成了「${esc(x.heard || '?')}」</span><div class="tiny muted">${esc(x.tip || x.note || '')}</div>`; }
          catch (e) { out.textContent = e.message; }
        });
        view.querySelectorAll('[data-self]').forEach(b => b.onclick = () => rate(b.dataset.self, Date.now() - t0));
        onSwipe(() => rate('good', Date.now() - t0), () => rate('again', Date.now() - t0));
      }
    }
    function ask() {
      if (i >= items.length) return more();
      c = items[i]; claim = null; t0 = Date.now();
      if (['fix', 'question', 'sound'].includes(c.mode)) return mistakeAsk();
      const sent = sentenceOf(c), pattern = c.kind !== 'word' && /^句型｜例：/.test(c.meaning || '');
      // Nothing to recall from (an imported phrase with no meaning or sentence): show it and ask whether it is known.
      const m = (c.mode === 'recall' || c.mode === 'cloze') && !c.meaning && !sent ? 'recognize' : c.mode;
      let body = '', choices = '';
      if (m === 'recognize') {
        body = `<div class="wordbig${c.kind === 'word' ? '' : ' phrase'}">${esc(c.text)}</div><div class="ph">${esc(c.phonetic || '')} <button class="icon-btn" id="sayW" aria-label="朗读">${ICON.speak}</button></div>`;
        choices = ['认识', '模糊', '不认识'];
      } else if (m === 'spell') {
        body = `<div class="muted small">听发音，拼出这个词</div><div><button class="icon-btn big" id="sayW" aria-label="再听一次">${ICON.speak}</button></div>${meaningHTML(c)}
          ${sent ? `<div class="cloze">${gapped(sent.text, sent.form, false)}</div>` : ''}
          <input id="spellIn" class="spell" lang="en" enterkeyhint="done" autocomplete="off" autocapitalize="off" autocorrect="off" spellcheck="false" aria-label="拼写" placeholder="输入单词">`;
      } else if (pattern) {
        body = `<div class="hint">回忆这个句型</div><div class="cloze">${frameCloze(c.meaning.replace(/^句型｜例：/, ''), c.text)}</div>`;
        choices = ['想起来了', '有点模糊', '想不起来'];
      } else {
        body = `${meaningHTML(c) || '<div class="hint">回忆这个表达</div>'}${sent ? `<div class="cloze">${gapped(sent.text, sent.form, false)}</div>` : `<div class="cloze"><span class="gap">？</span></div>`}
          ${c.kind === 'word' ? `<div class="muted tiny">首字母 ${esc(c.text[0])} · ${c.text.length} 个字母</div>` : ''}`;
        choices = ['想起来了', '有点模糊', '想不起来'];
      }
      view.innerHTML = `${top()}<div class="review enter">${body}
        ${m === 'spell' ? '<div class="row center"><button class="btn primary" id="check">确定</button><button class="btn ghost" id="giveup">不会</button></div>'
          : `<div class="choice">${choices.map((t, k) => `<button class="${['good', '', 'again'][k]}" data-claim="${['know', 'fuzzy', 'forgot'][k]}">${t}${TOUCH ? '' : `<small>${k + 1}</small>`}</button>`).join('')}</div>`}
        ${foot()}</div>`;
      bar(); swipe = null;
      const say = document.getElementById('sayW'); if (say) say.onclick = () => CLIP.word(c);
      if (m === 'recognize' || m === 'spell') CLIP.word(c);
      if (m === 'spell') {
        const inp = document.getElementById('spellIn'); setTimeout(() => inp.focus(), 50);
        const check = () => { const v = inp.value.trim(); if (!v) return; spellResult(v); };
        document.getElementById('check').onclick = check; document.getElementById('giveup').onclick = () => spellResult('');
        keys({ Enter: check });
      } else {
        view.querySelectorAll('[data-claim]').forEach(b => b.onclick = () => reveal(b.dataset.claim));
        keys({ 1: () => reveal('know'), 2: () => reveal('fuzzy'), 3: () => reveal('forgot') });
        onSwipe(() => reveal('know'), () => reveal('forgot'));
      }
    }
    function answerHTML() {
      return `<div class="wordbig">${esc(c.text)}</div><div class="ph">${esc(c.phonetic || '')} <button class="icon-btn" id="sayW" aria-label="朗读">${ICON.speak}</button></div>
        ${c.meaning ? `<div class="mean-a">${esc(c.meaning).replace(/；|;/g, '<br>')}</div>` : ''}${rootsHTML(c)}${examplesHTML(c)}`;
    }
    function reveal(how) {
      claim = how; const ms = Date.now() - t0;
      const next = how === 'know' ? [['记错了', 'again', 'again x'], ['没错，下一个', 'good', 'good primary']] : [[how === 'fuzzy' ? '下一个' : '记住了，下一个', how === 'fuzzy' ? 'hard' : 'again', 'primary']];
      view.innerHTML = `${top()}<div class="review open-card">${answerHTML()}
        <div class="row center">${next.map(([t, r, cls]) => `<button class="btn ${cls.includes('primary') ? 'primary' : ''}" data-rate="${r}">${t}</button>`).join('')}</div>
        ${c.kind === 'word' && how === 'know' ? '<button class="btn ghost small" id="tooEasy">太简单了，以后不用再背</button>' : ''}${foot()}</div>`;
      bar(); bindExamples(view, c);
      document.getElementById('sayW').onclick = () => CLIP.word(c);
      if (c.mode !== 'recognize') CLIP.word(c);
      view.querySelectorAll('[data-rate]').forEach(b => b.onclick = () => rate(b.dataset.rate, ms));
      const te = document.getElementById('tooEasy'); if (te) te.onclick = () => known();
      const primary = next[next.length - 1][1];
      keys({ Enter: () => rate(primary, ms), ' ': () => rate(primary, ms), x: () => how === 'know' && rate('again', ms) });
      onSwipe(() => rate(primary, ms), how === 'know' ? () => rate('again', ms) : null);
    }
    function spellResult(v) {
      const ms = Date.now() - t0, want = c.text.toLowerCase(), got = v.toLowerCase();
      const dist = (a, b) => { const d = Array.from({ length: a.length + 1 }, (_, k) => [k]); for (let j = 1; j <= b.length; j++) d[0][j] = j;
        for (let k = 1; k <= a.length; k++) for (let j = 1; j <= b.length; j++) d[k][j] = Math.min(d[k - 1][j] + 1, d[k][j - 1] + 1, d[k - 1][j - 1] + (a[k - 1] === b[j - 1] ? 0 : 1)); return d[a.length][b.length]; };
      const r = !got ? 'again' : got === want ? 'good' : (want.length > 4 && dist(got, want) === 1) ? 'hard' : 'again';
      const msg = r === 'good' ? '<div class="ok">✓ 拼对了</div>' : r === 'hard' ? `<div class="warn">差一点：你写的是 <s>${esc(v)}</s></div>` : got ? `<div class="bad">你写的是 <s>${esc(v)}</s></div>` : '';
      view.innerHTML = `${top()}<div class="review open-card">${msg}${answerHTML()}<div class="row center"><button class="btn primary" id="go">下一个</button></div>${foot()}</div>`;
      bar(); bindExamples(view, c); document.getElementById('sayW').onclick = () => CLIP.word(c); CLIP.word(c);
      document.getElementById('go').onclick = () => rate(r, ms); keys({ Enter: () => rate(r, ms), ' ': () => rate(r, ms) });
      onSwipe(() => rate(r, ms), null);
    }
    let busy = false;
    async function rate(r, ms) {
      if (busy) return; busy = true; document.onkeydown = null;
      try {
        const body = { id: c.id, rating: r, mode: c.mode, ms: Math.min(ms, 3599999), at: Math.floor(Date.now() / 1000) };
        let res;
        try { res = await api('/api/next/review', body); }
        catch (e) {
          if (!e.network) throw e;
          OUTBOX.push({ path: '/api/next/review', body });  // offline: keep going, sync later
          const learning = c.state !== 'review' || r === 'again';
          res = { card: { ...c, state: learning && r !== 'easy' ? (c.state === 'review' ? 'relearning' : 'learning') : 'review' }, due: left ? left.due : 0, new: left ? left.new : 0 };
          if (r === 'good' && c.state === 'learning' && (c.step || 0) >= 1) res.card.state = 'review';
          res.card.step = (c.step || 0) + 1;
        }
        tally[r]++; doneN++; left = res; i++; doneIds.add(c.id); badge(res);
        const n = res.card;
        // Only what is due again within minutes (a miss, or a fuzzy new card) comes back in this session, a few cards later;
        // a card answered right waits for its next step (10 minutes, then days) and is picked up by "继续" or the next session.
        const soon = n.due ? n.due * 1000 - Date.now() < 5 * 60000 : r === 'again';
        if ((n.state === 'learning' || n.state === 'relearning') && soon) {
          const again = { ...c, ...n, mode: c.kind === 'word' ? 'recognize' : c.mode, repeat: true };
          items.splice(Math.min(items.length, i + 4), 0, again);
        }
        const el = view.querySelector('.review'); if (el) el.classList.add('out');
        setTimeout(ask, REDUCED ? 0 : 180);
      } catch (e) { toast(e.message); keys({}); }
      finally { busy = false; }
    }
    async function known() {
      try { const res = await api('/api/next/vocab/known', { id: c.id, known: true }); tally.known++; doneN++; i++; doneIds.add(c.id); left = res; toast('已标为熟知'); ask(); } catch (e) { toast(e.message); }
    }
    async function more() {
      document.onkeydown = null;
      try {
        const q = await api('/api/next/review');
        const fresh = q.items.filter(x => !seen.has(x.id) || (x.state !== 'new' && x.due * 1000 <= Date.now()));
        const extra = fresh.filter(x => !items.slice(i).some(y => y.id === x.id));
        if (extra.length) { extra.forEach(x => { seen.add(x.id); uniq.add(x.id); items.push(x); }); return ask(); }
        left = q;
      } catch (e) { /* show the summary anyway */ }
      refreshHome().catch(() => {});
      view.ontouchstart = view.ontouchmove = view.ontouchend = null; document.body.classList.remove('reviewing');
      view.innerHTML = `<div class="card done-card enter">${doneRing}<h2 class="h2">这一轮复习了 ${doneIds.size} 个</h2>${doneN > doneIds.size ? `<p class="muted tiny">共作答 ${doneN} 次，其中 ${doneN - doneIds.size} 次是再巩固</p>` : ''}
        <p class="muted small">记得 ${tally.good + tally.easy} · 模糊 ${tally.hard} · 忘了 ${tally.again}${tally.known ? ' · 熟知 ' + tally.known : ''}。新学的词 10 分钟后还会再见一次，之后按遗忘曲线安排。</p>
        ${left && (left.due + left.new) ? `<p class="small">还有 ${left.due + left.new} 个可以继续。</p>` : ''}
        <div class="row center"><a class="btn" href="#/cards">单词</a>${left && (left.due + left.new) ? '<button class="btn primary" id="again">继续</button>' : '<a class="btn primary" href="#/">回到今日</a>'}</div></div>`;
      const ag = document.getElementById('again'); if (ag) ag.onclick = () => reviewView();
    }
    ask();
  }

  /* ---------- learner model: ability profile, daily path, level suggestion ---------- */
  const SKILL_NAME = { vocab: '词汇', grammar: '语法', listening: '听力', reading: '阅读', speaking: '口语', writing: '写作', translation: '翻译', pronunciation: '发音' };
  const LV_W = { A2: 25, B1: 50, B2: 75, C1: 100 };
  function abilityHTML(ab) {
    const ev = s => s.id === 'vocab' ? (s.size ? `词汇量约 ${s.size.toLocaleString()}` : (s.count ? `已掌握 ${s.count} 词` : '做一次词汇量测试'))
      : s.id === 'grammar' ? (s.count ? `${s.count} 个知识点用对或做对${s.watch ? ` · ${s.watch} 个要留意` : ''}` : '读和写的时候会点亮')
      : s.count ? `${s.count} 次练习 · 平均 ${Math.round((s.avg || 0) * 100)}%` : '还没练过';
    return `<div class="card flat stack-s" id="ability"><div class="row between"><b>能力画像</b><span class="muted tiny">按近 45 天的练习估计</span></div>
      <div class="ab-list">${ab.skills.map(s => `<div class="ab ${s.level ? '' : 'none'}"><span class="nm">${esc(s.label)}</span><span class="vbar"><i data-w="${s.level ? LV_W[s.level] : 3}"></i></span>
        <span class="lv">${s.level || '—'}</span><span class="tiny muted ev">${esc(ev(s))}</span></div>`).join('')}</div>
      ${ab.weakest ? `<div class="small">现在最值得练：<b>${esc(SKILL_NAME[ab.weakest])}</b>。首页的「今天的计划」已经按这个安排。</div>` : '<div class="muted small">做几次理解题、听写、跟读和写作，画像就会越来越准。</div>'}</div>`;
  }
  function suggestHTML(sg) {
    return sg ? `<div class="card sunk section suggest row between"><div class="small">${esc(sg.reason)}</div>
      <div class="row"><button class="btn small primary" id="sgYes">换到 ${esc(sg.to)}</button><button class="btn small ghost" id="sgNo">先不用</button></div></div>` : '';
  }
  function bindSuggest(h) {
    const y = document.getElementById('sgYes'), n = document.getElementById('sgNo');
    if (y) y.onclick = async () => { try { await api('/api/next/profile', { ...h.profile, level: h.suggest.to }); toast('已换到 ' + h.suggest.to + '，推荐会跟着变'); await refreshHome(); S.homeFresh = true; route(); } catch (e) { toast(e.message); } };
    if (n) n.onclick = () => { save('flow-next-suggest-skip', Date.now()); y.closest('.suggest').remove(); };
  }

  /* ---------- microphone: one spoken answer, sent to the AI as {mime_type, data} ---------- */
  const MIC = {
    mr: null, timer: 0,
    busy() { return !!(this.mr && this.mr.state === 'recording'); },
    stop() { if (this.busy()) this.mr.stop(); },
    async toggle(btn, maxSecs, onDone) {
      if (this.busy()) { this.mr.stop(); return; }
      TTS.stop(); NAR.stop(); CLIP.stop();
      if (!navigator.mediaDevices || !window.MediaRecorder) { toast('这个浏览器不支持录音，换 Safari 或 Chrome 试试'); return; }
      let stream;
      try { stream = await navigator.mediaDevices.getUserMedia({ audio: true }); } catch (e) { toast('没有拿到麦克风权限，可以在浏览器设置里打开'); return; }
      const type = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4'].find(t => MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported(t)) || '';
      const mr = new MediaRecorder(stream, type ? { mimeType: type } : undefined), chunks = [];
      this.mr = mr;
      mr.ondataavailable = e => { if (e.data && e.data.size) chunks.push(e.data); };
      mr.onstop = () => {
        stream.getTracks().forEach(t => t.stop()); clearTimeout(this.timer); btn.classList.remove('on');
        if (chunks.length) onDone(new Blob(chunks, { type: mr.mimeType || type || 'audio/webm' }));
      };
      mr.start(); btn.classList.add('on');
      this.timer = setTimeout(() => this.stop(), maxSecs * 1000);
    },
    async payload(blob) {
      if (blob.size > 1400000) throw new Error('录音太长了，缩短一点再试');
      const data = await new Promise((ok, no) => { const r = new FileReader(); r.onload = () => ok(String(r.result).split(',')[1]); r.onerror = no; r.readAsDataURL(blob); });
      return { mime_type: /mp4|m4a|aac/.test(blob.type) ? 'audio/mp4' : /ogg/.test(blob.type) ? 'audio/ogg' : 'audio/webm', data };
    },
  };
  const recBtn = (id, label) => `<button class="icon-btn rec" id="${id}" type="button" aria-label="${label || '录音'}"><span class="dot"></span></button>`;
  const fixesHTML = fs => fs && fs.length ? `<div class="stack-s">${fs.map(f => `<div class="change"><span class="ft"><del>${esc(f.from)}</del> → <ins>${esc(f.to)}</ins></span><span class="why">${esc(f.why)}</span></div>`).join('')}
    <div class="tiny muted">这些已经放进错题本，会按遗忘曲线回来让你再改一次。</div></div>` : '';

  /* ---------- 我的文章: paste any English text and study it with Flow's tools ---------- */
  async function importView() {
    if (!S.user) return needLogin('登录后可以导入自己想读的英文文章，用点词、AI 讲解、生词复习来学。');
    const d = await api('/api/next/import');
    if (!S.meta) S.meta = await api('/api/next/meta');
    view.innerHTML = `<h1 class="h1">我的文章</h1><span class="muted small">论文、新闻、小说章节都可以：贴进来，就能点词查义、AI 讲解句子、听写跟读、把生词加入复习。只有你自己看得到。</span>
      <form class="card flat section stack" id="impF"><input name="title" type="text" maxlength="80" placeholder="标题（可不填）" aria-label="标题">
        <textarea name="text" rows="8" lang="en" aria-label="英文正文" placeholder="粘贴英文正文（200–8000 个字符）"></textarea>
        <select name="theme" aria-label="话题"><option value="">话题：按内容自动判断</option>${S.meta.themes.map(t => `<option value="${t.id}">话题：${esc(t.label)}</option>`).join('')}</select>
        <div class="row between"><span class="muted tiny" id="impN">0 字符</span><button class="btn primary">保存并开始学</button></div></form>
      <div class="section stack-s"><div class="row between"><h2 class="h2">已保存</h2><span class="muted tiny">${d.items.length} / ${d.max}</span></div>
      ${d.items.length ? `<div class="grid-list">${d.items.map(a => `<div class="card flat stack-s imp"><div class="row between"><b>${esc(a.title)}</b><span class="pill">${esc(a.level)}</span></div>
        <div class="muted small">${esc(a.preview)}…</div><div class="row"><a class="btn small primary" href="#/m/${encodeURIComponent(a.id)}/read">学这篇</a>
        ${a.enriched ? '<span class="pill green">已出题</span>' : `<button class="btn small" data-enrich="${esc(a.id)}">✦ AI 出题和挑表达</button>`}
        <button class="btn small ghost" data-del="${esc(a.id)}">删除</button></div></div>`).join('')}</div>` : '<div class="empty"><p>还没有导入的文章。</p></div>'}</div>`;
    const f = document.getElementById('impF');
    f.text.oninput = () => { document.getElementById('impN').textContent = f.text.value.length + ' 字符'; };
    f.onsubmit = async e => {
      e.preventDefault(); const b = f.querySelector('button'); b.disabled = true;
      try { const r = await api('/api/next/import', { title: f.title.value, text: f.text.value, theme: f.theme.value }); toast(r.existing ? '这篇已经导入过了' : `已保存，估计难度 ${r.level}`); location.hash = `#/m/${encodeURIComponent(r.id)}/read`; }
      catch (x) { toast(x.message); b.disabled = false; }
    };
    view.querySelectorAll('[data-enrich]').forEach(b => b.onclick = async () => {
      b.disabled = true; b.innerHTML = '<span class="spin"></span> 正在出题…';
      try { await api('/api/next/import/enrich', { id: b.dataset.enrich, request_id: rid('ie') }); delete MAT[b.dataset.enrich]; toast('已生成导读、理解题和表达'); importView(); }
      catch (x) { toast(x.message); b.disabled = false; b.textContent = '✦ AI 出题和挑表达'; }
    });
    view.querySelectorAll('[data-del]').forEach(b => b.onclick = async () => { if (!confirm('删除这篇文章？')) return; try { await api('/api/next/import/delete', { id: b.dataset.del }); importView(); } catch (x) { toast(x.message); } });
  }

  /* ---------- 发音入门: minimal pairs, tell them apart, then say them ---------- */
  async function soundsView(setId) {
    if (!S.sounds) S.sounds = (await api('/api/next/sounds')).sets;
    const sets = S.sounds;
    if (!setId) {
      view.innerHTML = `<h1 class="h1">发音入门</h1><span class="muted small">中国学习者最容易混的 ${sets.length} 组音。先听辨，再跟读；读不准的会进错题本。</span>
        <div class="grid-list section">${sets.map(s => `<a class="card flat mini" href="#/sounds/${esc(s.id)}"><span class="t">${esc(s.title)}</span><span class="pill">${s.pairs.length} 对</span>
          <span class="p">${esc(s.pairs.slice(0, 3).map(p => p[0].word + ' / ' + p[1].word).join('　'))}</span></a>`).join('')}</div>`;
      return;
    }
    const s = sets.find(x => x.id === setId); if (!s) { location.hash = '#/sounds'; return; }
    view.innerHTML = `<a class="link small" href="#/sounds">← 全部</a><h1 class="h1">${esc(s.title)}</h1><div class="card sunk small stack-s"><span>${esc(s.tip)}</span>${s.listen ? `<span class="muted">${esc(s.listen)}</span>` : ''}</div>
      <div class="section row between"><h2 class="h2">先听，再跟读</h2><button class="btn small primary" id="quiz">听辨练习</button></div>
      <p class="muted tiny">点 ▶ 听，点 ● 读这个词（再点一次停止）；${S.user ? 'AI 会告诉你目标音发得对不对。' : '登录后 AI 会告诉你目标音发得对不对。'}</p>
      <div class="stack-s pairs">${s.pairs.map((p, i) => `<div class="card flat pair">${p.map((w, j) => `<div class="pw"><span class="wd"><b>${esc(w.word)}</b>${w.phonetic ? `<span class="ph">${esc(w.phonetic)}</span>` : ''}</span>
        <button class="icon-btn" data-play="${i}-${j}" aria-label="听 ${esc(w.word)}">${ICON.speak}</button>${recBtn(`r${i}-${j}`, '跟读 ' + w.word)}<span class="tiny res" id="o${i}-${j}"></span></div>`).join('')}</div>`).join('')}</div>`;
    const word = (i, j) => s.pairs[i][j];
    view.querySelectorAll('[data-play]').forEach(b => b.onclick = () => { const [i, j] = b.dataset.play.split('-').map(Number); CLIP.word({ text: word(i, j).word, audio: word(i, j).audio }); });
    s.pairs.forEach((p, i) => p.forEach((w, j) => {
      const btn = document.getElementById(`r${i}-${j}`), out = document.getElementById(`o${i}-${j}`);
      btn.onclick = () => MIC.toggle(btn, 4, async blob => {
        if (!S.user) { needLogin('登录后 AI 会听你的发音。'); return; }
        out.innerHTML = '<span class="spin"></span>';
        try {
          const x = (await api('/api/next/say', { text: w.word, audio: await MIC.payload(blob), request_id: rid('sy') })).result;
          out.innerHTML = x.ok ? `<span class="ok-mark">✓ 读对了</span>` : `<span class="bad-mark">听着像 ${esc(x.heard || '?')}</span>`;
          if (!x.ok) toast(x.confirmed ? '两次都没读准，已放进错题本：' + (x.tip || x.note) : `AI 听成了「${x.heard || '?'}」，再读一遍确认一下`);
        } catch (e) { out.textContent = ''; toast(e.message); }
      });
    }));
    document.getElementById('quiz').onclick = () => soundQuiz(s);
  }
  function soundQuiz(s) {
    // Each pair in turn (shuffled), never the same pair twice in a row.
    const deck = []; while (deck.length < 10) { const sh = s.pairs.slice().sort(() => Math.random() - 0.5); if (deck.length && sh[0] === deck[deck.length - 1]) sh.push(sh.shift()); deck.push(...sh); }
    const rounds = deck.slice(0, 10).map(p => ({ p, k: Math.random() < 0.5 ? 0 : 1 }));
    let i = 0, right = 0; const missed = [];
    const play = () => { const r = rounds[i]; CLIP.word({ text: r.p[r.k].word, audio: r.p[r.k].audio }); };
    function show() {
      if (i >= rounds.length) {
        if (S.user) api('/api/next/skill', { kind: 'discriminate', score: right / rounds.length }).catch(() => {});
        view.innerHTML = `<div class="card done-card enter">${doneRing}<h2 class="h2">听对了 ${right} / ${rounds.length}</h2><p class="muted small">${right >= 8 ? '耳朵已经分得清了，去跟读几遍吧。' : '再多听几遍对比。' + esc(s.listen || '')}</p>
          ${missed.length ? `<div class="small">听错的：${missed.map(x => `<b>${esc(x)}</b>`).join('、')}</div>` : ''}
          <div class="row center"><a class="btn" href="#/sounds/${esc(s.id)}">回到这组</a><button class="btn primary" id="again">再练一轮</button></div></div>`;
        document.getElementById('again').onclick = () => soundQuiz(s); return;
      }
      const r = rounds[i];
      view.innerHTML = `<div class="rtop"><a class="link small" href="#/sounds/${esc(s.id)}">结束</a><div class="bar-progress"><i id="rp"></i></div></div><div class="review enter"><p class="muted small">听到的是哪一个？${TOUCH ? '' : '（← → 选，空格再听）'}</p>
        <div><button class="icon-btn big" id="pl" aria-label="再听一次">${ICON.speak}</button></div>
        <div class="choice two">${r.p.map((w, k) => `<button data-k="${k}">${esc(w.word)}</button>`).join('')}</div><p class="muted tiny tc">${i + 1} / ${rounds.length}</p></div>`;
      document.getElementById('rp').style.width = (i / rounds.length * 100) + '%';
      document.getElementById('pl').onclick = play; play();
      document.onkeydown = e => { if (e.key === ' ') { e.preventDefault(); play(); } else if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') { e.preventDefault(); const b = view.querySelector(`[data-k="${e.key === 'ArrowLeft' ? 0 : 1}"]`); if (b && !b.disabled) b.click(); } };
      view.querySelectorAll('[data-k]').forEach(b => b.onclick = () => {
        const ok = Number(b.dataset.k) === r.k; if (ok) right++; else missed.push(r.p[r.k].word);
        b.classList.add(ok ? 'good' : 'again'); if (!ok) view.querySelector(`[data-k="${r.k}"]`).classList.add('good');
        view.querySelectorAll('[data-k]').forEach(x => x.disabled = true);
        setTimeout(() => { i++; show(); }, ok ? 500 : 1100);
      });
    }
    show();
  }

  /* ---------- weekly report, with a picture to share ---------- */
  async function reportView() {
    if (!S.user) return needLogin('登录后可以看每周学习报告。');
    const r = await api('/api/next/report');
    const arrow = s => s.now == null ? '—' : `${Math.round(s.now * 100)}%${s.before != null ? (s.now > s.before + 0.02 ? ' ↑' : s.now < s.before - 0.02 ? ' ↓' : '') : ''}`;
    view.innerHTML = `<h1 class="h1">这周的学习</h1><span class="muted small">${esc(r.from)} – ${esc(r.to)}</span>
      <div class="stat-grid section"><div class="card flat stat"><b>${r.days}</b><span class="tiny muted">学习天数</span></div><div class="card flat stat"><b>${r.minutes}</b><span class="tiny muted">分钟（估算）</span></div>
        <div class="card flat stat"><b>${r.materials}</b><span class="tiny muted">学完的材料</span></div><div class="card flat stat"><b>${r.outputs}</b><span class="tiny muted">输出练习</span></div>
        <div class="card flat stat"><b>${r.learned}</b><span class="tiny muted">新学的词</span></div><div class="card flat stat"><b>${r.mastered}</b><span class="tiny muted">进入长期记忆</span></div></div>
      <div class="card flat section stack-s"><b>各项练习的平均分</b><div class="ab-list">${r.skills.filter(s => s.count || s.before != null).map(s => `<div class="ab"><span class="nm">${esc(s.label)}</span>
        <span class="vbar"><i data-w="${Math.max(3, (s.now || 0) * 100)}"></i></span><span class="lv">${arrow(s)}</span><span class="tiny muted ev">${s.count} 次</span></div>`).join('') || '<p class="muted small">这周还没有练习记录。</p>'}</div></div>
      <div class="card flat section stack-s"><b>错题</b><span class="small">新进错题本 ${r.mistakes_new} 个，改对 ${r.mistakes_fixed} 个。</span>
        ${r.watch.length ? `<span class="small">写作里要留意：${r.watch.map(n => nodeChip({ id: n.id, title: n.title, status: 'watch' })).join(' ')}</span>` : ''}
        ${r.focus ? `<div class="small"><b>下周重点：</b>${esc(r.focus)}</div>` : ''}</div>
      <div class="section row"><button class="btn primary" id="share">生成分享图</button><a class="btn" href="#/me">能力画像</a></div><div id="shareOut" class="section"></div>`;
    requestAnimationFrame(() => requestAnimationFrame(() => view.querySelectorAll('.vbar i').forEach(i => { i.style.width = i.dataset.w + '%'; })));
    document.getElementById('share').onclick = () => {
      const url = shareImage(r);
      document.getElementById('shareOut').innerHTML = `<img class="share-img" src="${url}" alt="本周学习分享图"><div class="row"><a class="btn small primary" download="flow-week.png" href="${url}">保存图片</a><span class="muted tiny">${TOUCH ? '也可以长按图片保存' : '或右键图片另存为'}</span></div>`;
      bringIntoView(document.getElementById('shareOut'));
    };
  }
  function shareImage(r) {
    const rows = r.skills.filter(s => s.now != null).slice(0, 5).length;
    const W = 1080, H = rows ? 900 + rows * 70 + 170 : 860, cv = document.createElement('canvas'); cv.width = W; cv.height = H;
    const g = cv.getContext('2d'), green = '#1f9d55', ink = '#1b1d1a', muted = '#6f7369';
    g.fillStyle = '#fbfaf6'; g.fillRect(0, 0, W, H);
    g.fillStyle = green; g.beginPath(); g.roundRect ? g.roundRect(80, 90, 96, 96, 26) : g.rect(80, 90, 96, 96); g.fill();
    g.strokeStyle = '#fff'; g.lineWidth = 9; g.lineCap = 'round';
    [[103, 133, 151], [121, 115, 169], [139, 124, 160], [157, 133, 145]].forEach(([x, a, b]) => { g.beginPath(); g.moveTo(x, a); g.lineTo(x, b); g.stroke(); });
    const font = (s, w) => `${w || 600} ${s}px -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif`;
    g.fillStyle = ink; g.font = font(44, 700); g.fillText('语流 Flow · 本周学习', 200, 152);
    g.fillStyle = muted; g.font = font(30, 400); g.fillText(`${r.from} – ${r.to}`, 80, 250);
    const stats = [[r.days, '学习天数'], [r.minutes, '分钟'], [r.materials, '篇材料'], [r.learned, '个新词'], [r.mastered, '个词记牢了'], [r.outputs, '次输出练习']];
    stats.forEach(([v, l], k) => {
      const x = 80 + (k % 3) * 320, y = 320 + Math.floor(k / 3) * 220;
      g.fillStyle = '#ffffff'; g.fillRect(x, y, 290, 190); g.fillStyle = green; g.font = font(84, 800); g.fillText(String(v), x + 30, y + 110);
      g.fillStyle = muted; g.font = font(30, 500); g.fillText(l, x + 30, y + 160);
    });
    let y = 820; g.fillStyle = ink; g.font = font(36, 700); if (rows) g.fillText('各项练习', 80, y); y += 30;
    r.skills.filter(s => s.now != null).slice(0, 5).forEach(s => {
      y += 70; g.fillStyle = ink; g.font = font(32, 500); g.fillText(s.label, 80, y);
      g.fillStyle = '#e7e3d8'; g.fillRect(240, y - 24, 600, 22); g.fillStyle = green; g.fillRect(240, y - 24, 600 * s.now, 22);
      g.fillStyle = muted; g.fillText(Math.round(s.now * 100) + '%', 870, y);
    });
    g.fillStyle = muted; g.font = font(30, 400); g.fillText('每天一篇，学了就能用 · flow.jasa.hk', 80, H - 90);
    return cv.toDataURL('image/png');
  }

  /* ---------- library ---------- */
  async function libraryView(f) {
    let saved = null; try { saved = JSON.parse(sessionStorage.getItem('flow-next-lib') || 'null'); } catch (e) { /* private mode */ }
    f = f || saved || { level: hasProfile() ? level() : '', theme: '', page: 1, featured: '1' };
    try { sessionStorage.setItem('flow-next-lib', JSON.stringify(f)); } catch (e) { /* private mode */ }
    const d = await api(`/api/next/library?level=${f.level}&theme=${f.theme}&page=${f.page}&featured=${f.featured}`);
    const pages = Math.max(1, Math.ceil(d.total / d.per));
    view.innerHTML = `<div class="row between"><h1 class="h1">全部材料</h1><a class="btn small" href="#/import">我的文章</a></div><span class="muted small">${d.total} 篇${f.featured === '1' ? ' · 精选' : ''}</span>
      <div class="filters"><select id="ff" aria-label="范围"><option value="1" ${f.featured === '1' ? 'selected' : ''}>精选</option><option value="" ${f.featured !== '1' ? 'selected' : ''}>全部材料</option></select>
        <select id="fl" aria-label="难度"><option value="">全部难度</option>${['A2', 'B1', 'B2', 'C1'].map(l => `<option ${f.level === l ? 'selected' : ''}>${l}</option>`).join('')}</select>
        <select id="ft" aria-label="话题"><option value="">全部话题</option>${Object.entries(d.themes).map(([k, v]) => `<option value="${k}" ${f.theme === k ? 'selected' : ''}>${esc(v)}</option>`).join('')}</select></div>
      <div class="grid-list" id="lib">${d.items.map(m => miniCard(m, m.daily ? '热点' : '')).join('') || '<div class="empty">这个筛选下还没有材料。</div>'}</div>
      ${pages > 1 ? `<div class="pager"><button class="btn small" id="pv" ${f.page <= 1 ? 'disabled' : ''}>上一页</button><span class="muted small">${f.page} / ${pages}</span><button class="btn small" id="nx" ${f.page >= pages ? 'disabled' : ''}>下一页</button></div>` : ''}`;
    const again = nf => libraryView(nf).then(() => enter(document.getElementById('lib')));
    document.getElementById('ff').onchange = e => again({ ...f, featured: e.target.value, page: 1 });
    document.getElementById('fl').onchange = e => again({ ...f, level: e.target.value, page: 1 });
    document.getElementById('ft').onchange = e => again({ ...f, theme: e.target.value, page: 1 });
    const pv = document.getElementById('pv'), nx = document.getElementById('nx');
    if (pv) pv.onclick = () => { scrollTo(0, 0); again({ ...f, page: f.page - 1 }); };
    if (nx) nx.onclick = () => { scrollTo(0, 0); again({ ...f, page: f.page + 1 }); };
  }

  /* ---------- me ---------- */
  async function meView() {
    if (!S.meta) S.meta = await api('/api/next/meta');
    const p = (S.home && S.home.profile) || S.guest || {};
    const lv = S.meta.levels.find(l => l.id === p.level), goal = S.meta.goals.find(g => g.id === p.goal);
    const themes = S.meta.themes.filter(t => (p.themes || []).includes(t.id)).map(t => t.label);
    const st = S.home && S.home.stats;
    view.innerHTML = `<h1 class="h1">${S.user ? esc(S.user.username) : '我的'}</h1>
      ${S.user ? '' : `<div class="card sunk stack-s"><b>还没有登录</b><span class="muted small">登录后才能保存进度、收藏表达和使用 AI。</span><div><button class="btn primary small" id="lg">登录 / 注册</button></div></div>`}
      ${st ? `<div class="stat-grid"><div class="card flat stat"><b>${st.week.filter(d => d.active).length}</b><span class="tiny muted">本周学习天数</span></div><div class="card flat stat"><b>${st.materials_done}</b><span class="tiny muted">学完的材料</span></div><div class="card flat stat"><b>${st.cards}</b><span class="tiny muted">单词与表达</span></div></div>` : ''}
      <div class="card flat stack-s"><div class="row between"><b>学习设置</b><a class="link small" href="#/welcome/edit">修改</a></div>
        <div class="small">水平：${lv ? esc(lv.label) + '（' + lv.id + '）' : '未设置'}</div><div class="small">目标：${goal ? esc(goal.label) : '未设置'}</div>
        <div class="small">话题：${themes.length ? esc(themes.join('、')) : '随机'}</div><div class="small">每天：${p.minutes || 10} 分钟</div>
        <div class="small">朗读声音：</div>${voiceChips(null)}<p class="muted tiny">精选材料用真人声（Kokoro）朗读，可以随时在「听」这一步切换。</p></div>
      ${matchMedia('(display-mode: standalone)').matches || navigator.standalone ? '' : `<div class="card flat stack-s" id="install"><b>添加到手机桌面</b>
        <span class="muted small">像 App 一样从桌面打开，界面全屏；听过的音频会缓存下来，网络差的时候也能复习。</span>
        ${installPrompt ? '<div><button class="btn small primary" id="doInstall">添加到桌面</button></div>' : /iPhone|iPad|iPod/.test(navigator.userAgent)
          ? '<span class="small">iPhone：用 Safari 打开，点底部的「分享」按钮，再选「添加到主屏幕」。</span>' : '<span class="small">安卓：在浏览器菜单里选「添加到主屏幕」或「安装应用」。</span>'}</div>`}
      ${S.user ? `<div class="card flat stack-s" id="acct"><div class="row between"><b>邮箱</b><span class="small muted" id="acctEmail"><span class="spin"></span></span></div>
        <span class="muted tiny">绑定后可以收复习提醒和周报、用验证码登录、找回密码。</span><div><button class="btn small" id="bindMail" hidden>绑定邮箱</button></div></div>` : ''}
      ${S.user ? '<div id="abSlot"><div class="card flat"><p class="loading"><span class="spin"></span></p></div></div>' : ''}
      <div class="card flat list">
        ${S.user ? '<a href="#/report">这周的学习报告 <span>→</span></a><a href="#/cards/mistake">错题本 <span>→</span></a>' : ''}
        <a href="#/sounds">发音入门：容易混的音 <span>→</span></a>
        <a href="#/import">我的文章：导入任何英文来学 <span>→</span></a>
        <a href="#/graph">我的知识图谱 <span>→</span></a>
        <a href="#/library">全部材料 <span>→</span></a>
        <a href="/survey">参与匿名问卷：你想要什么样的英语学习网站 <span>→</span></a>
        <a href="/?classic=1">经典版（AI 私教、诊断测评、内容管理）<span>→</span></a>
        ${S.user ? '<button id="out">退出登录 <span>→</span></button>' : ''}</div>`;
    const lg = document.getElementById('lg'); if (lg) lg.onclick = () => openLogin();
    const slot = document.getElementById('abSlot');
    if (slot) api('/api/next/ability').then(ab => { slot.innerHTML = abilityHTML(ab); requestAnimationFrame(() => requestAnimationFrame(() => slot.querySelectorAll('.vbar i').forEach(i => { i.style.width = i.dataset.w + '%'; }))); }).catch(() => { slot.innerHTML = ''; });
    if (S.user) api('/api/account').then(a => {
      const el = document.getElementById('acctEmail'), b = document.getElementById('bindMail'); if (!el) return;
      el.textContent = a.email || '还没有绑定';
      if (a.mail_enabled) { b.hidden = false; b.textContent = a.email ? '更换邮箱' : '绑定邮箱'; b.onclick = () => bindEmailSheet(a.email); }
      else el.textContent += a.email ? '' : '（邮件服务暂未开启）';
    }).catch(() => { const el = document.getElementById('acctEmail'); if (el) el.textContent = ''; });
    const di = document.getElementById('doInstall'); if (di) di.onclick = async () => { installPrompt.prompt(); try { await installPrompt.userChoice; } catch (e) { /* dismissed */ } installPrompt = null; meView(); };
    view.querySelectorAll('[data-voice]').forEach(b => b.onclick = async () => { await setVoice(b.dataset.voice); view.querySelectorAll('[data-voice]').forEach(x => { x.setAttribute('aria-pressed', String(x === b)); x.setAttribute('aria-checked', String(x === b)); }); toast('朗读声音：' + VOICE_LABELS[b.dataset.voice]); });
    const out = document.getElementById('out');
    if (out) out.onclick = async () => { try { await api('/api/logout', {}); } catch (e) { /* ignore */ } S.user = null; S.csrf = ''; await refreshHome(); toast('已退出'); route(); };
  }

  function bindEmailSheet(cur) {
    openSheet(`<div class="stack"><h2 class="h2" id="sheetTitle">${cur ? '更换' : '绑定'}邮箱</h2>
      <p class="muted small">先发一封验证邮件到新邮箱；邮件里有一串验证令牌，复制回来粘贴到这里就完成了（30 分钟内有效）。</p>
      <form id="bm1" class="stack" novalidate><label class="field">邮箱<input name="email" type="email" autocomplete="email" inputmode="email" required></label>
        <label class="field">当前密码（确认是你本人）<input name="password" type="password" autocomplete="current-password" required></label>
        <button class="btn primary" type="submit">发送验证邮件</button></form>
      <form id="bm2" class="stack" novalidate hidden><label class="field">验证令牌<input name="token" type="text" autocomplete="one-time-code" autocapitalize="off" spellcheck="false" required></label>
        <button class="btn primary" type="submit">完成绑定</button></form>
      <p class="err" id="bmErr" role="alert"></p><button class="btn ghost" data-close type="button">取消</button></div>`, card => {
      const f1 = card.querySelector('#bm1'), f2 = card.querySelector('#bm2'), err = card.querySelector('#bmErr');
      f1.onsubmit = async e => {
        e.preventDefault(); err.textContent = ''; const b = f1.querySelector('button'); b.disabled = true;
        try { await api('/api/account/email/request', { email: f1.email.value.trim(), password: f1.password.value }); f1.hidden = true; f2.hidden = false; f2.token.focus(); toast('验证邮件已发出，请查看邮箱'); }
        catch (x) { err.textContent = x.message; b.disabled = false; }
      };
      f2.onsubmit = async e => {
        e.preventDefault(); err.textContent = ''; const b = f2.querySelector('button'); b.disabled = true;
        try { await api('/api/account/email/confirm', { token: f2.token.value.trim() }); closeSheet(); toast('邮箱已绑定'); meView(); }
        catch (x) { err.textContent = x.message; b.disabled = false; }
      };
    });
  }

  /* ---------- boot ---------- */
  (async function boot() {
    if ('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js').catch(() => {});
    try { await refreshHome(); S.homeFresh = true; } catch (e) { /* offline: route() asks again and offers a retry */ }
    route();
    OUTBOX.flush();
  })();
})();

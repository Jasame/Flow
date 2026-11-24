'use strict';
/* Flow — one learning loop: listen → read → check → use it → review what you saved,
   steered by the knowledge graph (18 grammar nodes) and AI. See NEXT.md. */
(function () {
  const view = document.getElementById('view');
  const bar = document.getElementById('bar');
  const sheetEl = document.getElementById('sheet');
  const sheetCard = document.getElementById('sheetCard');
  const toastEl = document.getElementById('toast');
  const S = { user: null, csrf: '', meta: null, home: null, homeFresh: false, placed: '', guest: load('flow-next-guest'), lastRoute: '', voice: load('flow-next-voice') || 'us-f' };
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
  // One request to the server: an error becomes a message the page can show, and a session that ended asks to sign in
  // again (not for a preload: quiet). Returns the answer parsed (j) and as text (t, for the data layer to share).
  async function request(path, body, quiet) {
    const opt = { credentials: 'same-origin', headers: {} };
    if (body !== undefined) { opt.method = 'POST'; opt.headers['Content-Type'] = 'application/json'; if (S.csrf) opt.headers['X-CSRF-Token'] = S.csrf; opt.body = JSON.stringify(body); }
    let r;
    try { r = await fetch(path, opt); } catch (x) { noteIssue('api', '网络连接失败', path.split('?')[0]); const e = new Error('网络连接失败，请检查网络'); e.network = true; throw e; }
    const t = await r.text().catch(() => '');
    let j = {}; try { j = t ? JSON.parse(t) : {}; } catch (x) { /* not JSON: an error page */ }
    if (!r.ok) {
      if (r.status >= 500) noteIssue('api', `服务器返回 ${r.status}`, path.split('?')[0]);  // 4xx are answers (a wrong password …), not faults
      const e = new Error(j.error || ('请求失败（' + r.status + '）')); e.status = r.status; e.field = j.field; e.code = j.code;
      // Signed out on the server (30 days away, a password change, 退出所有设备): say so and offer to sign in again.
      if (r.status === 401 && S.user && !quiet && !/^\/api\/(login|register|auth\/)/.test(path)) {
        S.user = null; S.csrf = ''; e.message = '登录已过期，请重新登录';
        if (sheetEl.hidden) setTimeout(() => openLogin('登录已过期，请重新登录。登录后会回到这一页。'), 0);
      }
      throw e;
    }
    return { j, t };
  }
  // Reading goes through the data layer (05-data.js: shared, kept a short while, preloaded). Sending waits until the
  // server has said who is signed in (the page may first be drawn from the copy kept on the phone), and empties the
  // data layer's memory, since what was sent may change what the pages show.
  async function api(path, body) {
    if (body === undefined) return dataGet(path);
    await DATA.ready;
    const { j } = await request(path, body);
    dataForget();
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
  const ST_LABEL = { untouched: '还没接触', met: '读到过', used: '用出来过', watch: '需要留意', solid: '做题已验证' };  // next_service.STATUS_LABEL
  function nodeChip(n) { const st = n.status || 'untouched'; return `<a class="node-chip st st-${esc(st)}" href="#/graph/${encodeURIComponent(n.id || n.node)}" title="${esc(ST_LABEL[st] || '')}" aria-label="${esc(n.title)}，${esc(ST_LABEL[st] || '')}">${esc(n.title)}</a>`; }
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
  // WeChat's built-in browser (and some other in-app browsers) cannot use the browser voice, and plays sound only when it
  // starts inside a tap; the way out it offers is 「在浏览器打开」.
  const WECHAT = /MicroMessenger/i.test(navigator.userAgent);
  function noSound(what) { noteIssue('audio', what + (WECHAT ? '（微信）' : '')); toast(WECHAT ? `微信里${what}：点右上角「···」，选「在浏览器打开」就能听` : `这个浏览器${what}，换 Safari 或 Chrome 试试`); }
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
      if (!this.ok) { noSound('不能用电脑朗读的声音'); return; }
      speechSynthesis.cancel();
      const u = new SpeechSynthesisUtterance(text);
      u.lang = 'en-US'; u.rate = this.rate; const v = this.voice || this.pick(); if (v) u.voice = v;
      const t = ++this.token;
      if (onword) u.onboundary = e => { if (t === this.token && e.name !== 'sentence') onword(e.charIndex); };
      u.onend = () => { if (t === this.token && onend) onend(); };
      // A browser with speechSynthesis but no voice to speak with (WeChat on Android) neither starts nor fails: after
      // 2.5 s without a start, say so (and stop counting on it when it has no voices at all) instead of waiting in silence.
      const watch = setTimeout(() => { if (t !== this.token) return; speechSynthesis.cancel(); if (!speechSynthesis.getVoices().length) this.ok = false; noSound('不能用电脑朗读的声音'); }, 2500);
      u.onstart = () => clearTimeout(watch); u.onerror = () => clearTimeout(watch);
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

  /* ---------- two lines for audio: this server first (fastest from mainland China), then the media domain ---------- */
  // S.home.session.media = {base: '<media domain>/audio', version} when the server keeps audio in R2 (flow/media.py).
  function mediaAlt(url) {
    const m = S.home && S.home.session && S.home.session.media;
    if (!m || !m.base || !/^\/audio\//.test(url || '')) return '';
    return `${m.base}/${url.split('?')[0].slice(7).replace(/\.mp4$/, '.m4a')}?v=${encodeURIComponent(m.version)}`;
  }
  const mainDown = () => Date.now() - (S.mediaMainDown || 0) < 120000;  // after a failure, the other line for 2 minutes
  async function mediaJSON(url) {
    const alt = mediaAlt(url);
    if (!(alt && mainDown())) {
      try { const r = await fetch(url); if (r.ok) return await r.json(); } catch (e) { /* this server did not answer */ }
      if (!alt) throw new Error('no audio timing');
      S.mediaMainDown = Date.now();
    }
    const r = await fetch(alt); if (!r.ok) throw new Error('no audio timing');
    return r.json();
  }
  // Point an <audio> at this server; if it fails, or waits more than 8 s while playing, switch once to the media
  // domain, keeping the position and whether it was playing (a.dataset.want).
  function mediaSrc(a, url) {
    const alt = mediaAlt(url);
    a.dataset.src = url; a.dataset.alt = alt; a.dataset.line = alt && mainDown() ? 'alt' : 'main';
    if (!a.dataset.armed) {
      a.dataset.armed = '1';
      a.addEventListener('error', () => mediaSwap(a));
      a.addEventListener('waiting', () => { clearTimeout(a.stallTimer); a.stallTimer = setTimeout(() => mediaSwap(a), 8000); });
      a.addEventListener('playing', () => clearTimeout(a.stallTimer));
      a.addEventListener('pause', () => clearTimeout(a.stallTimer));
    }
    a.preload = 'auto'; a.src = a.dataset.line === 'alt' ? alt : PRELOAD.url(url);  // this server: the preloaded copy if there is one
  }
  function mediaSwap(a) {
    clearTimeout(a.stallTimer);
    if (!a.dataset.alt || a.dataset.line === 'alt') return false;
    S.mediaMainDown = Date.now();
    // where it was; a file that failed before it loaded starts where it was asked to (a._from: a clip, a sentence)
    const at = a.readyState ? a.currentTime || 0 : a._from || 0, play = a.dataset.want === '1';
    a.dataset.line = 'alt'; a.src = a.dataset.alt; a.load();
    a.addEventListener('loadedmetadata', () => { try { a.currentTime = at; } catch (e) { /* not seekable yet */ } if (play) a.play().catch(() => {}); }, { once: true });
    return true;
  }
  // Both lines failed (or there is only one): nothing more to try for this file.
  const mediaGaveUp = a => !a.dataset.alt || a.dataset.line === 'alt';

  /* ---------- narration: pre-generated Kokoro audio + timings (sentence exact, words estimated) ---------- */
  const NAR = {
    audio: new Audio(), meta: null, key: '', raf: 0, stopAt: null, onTick: null, onEnd: null,
    async load(id, voice, version) {
      const key = voice + '/' + id + '@' + version;
      if (this.key === key && this.meta) return true;
      this.stop(); this.meta = null; this.key = '';
      try {
        this.meta = await mediaJSON(`/audio/${voice}/${encodeURIComponent(id)}.json?v=${version}`); this.key = key;
        const net = this.net = `/audio/${voice}/${encodeURIComponent(id)}.mp4?v=${version}`;
        mediaSrc(this.audio, net);  // the copy in memory, when it was preloaded
        PRELOAD.warm(net).then(b => { if (b && this.net === net && this.audio.paused && this.audio.getAttribute('src') === net) this.audio.src = b; });
        return true;
      } catch (e) { return false; }
    },
    play(from, to, onTick, onEnd) {
      this.stopLoop(); this.stopAt = to; this.onTick = onTick; this.onEnd = onEnd;
      const a = this.audio, asked = a.src;
      claim(a); a.playbackRate = TTS.rate; a.preservesPitch = true; a.dataset.want = '1'; a._from = from;
      try { a.currentTime = from; } catch (e) { /* not seekable yet */ }
      // Refused (WeChat: not inside a tap): say how to hear it. A file that fails is tried on the other line first
      // (mediaSwap changes the source, and that play() is the one that counts); only when none is left, give up.
      a.play().catch(e => { if (e && e.name === 'NotAllowedError') { noSound('没有放出声音'); this.finish(); } else if (a.src === asked && mediaGaveUp(a)) this.gaveUp(); });
      const loop = () => {
        const t = this.audio.currentTime;
        if (this.onTick) this.onTick(t);
        if ((this.stopAt != null && t >= this.stopAt) || this.audio.ended) { this.audio.pause(); this.finish(); return; }
        this.raf = requestAnimationFrame(loop);
      };
      this.raf = requestAnimationFrame(loop);
    },
    finish() { this.stopLoop(); this.audio.dataset.want = ''; const cb = this.onEnd; this.onEnd = null; this.onTick = null; if (cb) cb(); },
    gaveUp() { if (!this.raf && !this.onEnd) return; noteIssue('audio', '全文录音没加载出来', this.net ? this.net.split('?')[0] : ''); toast('音频暂时没加载出来，稍后再点一次'); this.finish(); },
    stopLoop() { cancelAnimationFrame(this.raf); this.raf = 0; },
    stop() { this.stopLoop(); this.audio.dataset.want = ''; this.onEnd = null; this.onTick = null; try { this.audio.pause(); } catch (e) { /* ignore */ } },
    // -> [sentence index, char offset of the current word] at time t
    locate(t) {
      const ss = this.meta.sentences; let si = -1;
      for (let i = 0; i < ss.length; i++) { if (t >= ss[i].s - 0.02 && t < ss[i].e + 0.25) { si = i; break; } if (t < ss[i].s) break; }
      if (si < 0) return [-1, null];
      let wc = null; for (const w of ss[si].w) { if (t >= w[1]) wc = w[0]; else break; }
      return [si, wc];
    },
  };
  NAR.audio.addEventListener('error', () => { if (mediaGaveUp(NAR.audio)) NAR.gaveUp(); });
  function lightAt(container, charOffset) {
    container.querySelectorAll('.cur').forEach(el => el.classList.remove('cur'));
    if (charOffset == null) return;
    const el = container.querySelector(`[data-c="${charOffset}"]`); if (el) el.classList.add('cur');
  }
  /* ---------- short clips: a word's pronunciation, or one sentence from a material's narration ---------- */
  const CLIP = {
    audio: new Audio(), raf: 0, metas: {}, want: null,
    accent() { return (S.voice || 'us-f').startsWith('uk') ? 'uk' : 'us'; },
    stop() { cancelAnimationFrame(this.raf); this.want = null; this.audio.dataset.want = ''; try { this.audio.pause(); } catch (e) { /* ignore */ } },
    // play() is called right away, inside the tap: in-app browsers (WeChat) and iPhones refuse a play() that starts
    // later, when the file has loaded. A new file plays muted until it has jumped to the clip.
    // text: said by the browser voice if neither line can play the clip.
    play(src, from, to, text) {
      NAR.stop(); TTS.stop(); this.stop();
      const a = this.audio, want = this.want = { from, to, text };
      const loop = () => { if (this.want !== want) return; if (a.currentTime >= to || a.ended) { a.pause(); return; } this.raf = requestAnimationFrame(loop); };
      const refused = e => { if (this.want === want && e && e.name === 'NotAllowedError') noSound('没有放出声音'); };
      claim(a); a.playbackRate = TTS.rate; a.dataset.want = '1'; a._from = from;
      if (a.dataset.src === src && a.readyState >= 1) {
        try { a.currentTime = from; } catch (e) { /* not seekable yet */ }
        a.muted = false; a.play().catch(refused); this.raf = requestAnimationFrame(loop); return;
      }
      mediaSrc(a, src); a.muted = true;
      a.addEventListener('loadedmetadata', () => { if (this.want === want) { try { a.currentTime = from; } catch (e) { /* ignore */ } } }, { once: true });
      a.addEventListener('seeked', () => { if (this.want !== want) return; a.muted = false; this.raf = requestAnimationFrame(loop); }, { once: true });
      a.play().catch(refused);
    },
    // c: {text, audio: {us: [sprite, start, end], uk: [...]}}; falls back to the browser voice
    word(c) {
      const au = c.audio || {}, ac = au[this.accent()] ? this.accent() : au.us ? 'us' : au.uk ? 'uk' : null;
      if (!ac) { TTS.say(c.text); return; }
      const w = au[ac]; this.play(`/audio/words/${ac}/${w[0]}.mp4`, w[1], w[2], c.text);
    },
    // ex: {pack, i, text, audio: narration version or 0}
    async sentence(ex) {
      if (!ex.audio) { TTS.say(ex.text); return; }
      const key = S.voice + '/' + ex.pack;
      try {
        if (!this.metas[key]) this.metas[key] = await mediaJSON(`/audio/${S.voice}/${encodeURIComponent(ex.pack)}.json?v=${ex.audio}`);
        const s = this.metas[key].sentences[ex.i]; if (!s) throw new Error('no sentence');
        this.play(`/audio/${S.voice}/${encodeURIComponent(ex.pack)}.mp4?v=${ex.audio}`, s.s, s.e + 0.05, ex.text);
      } catch (e) { TTS.say(ex.text); }
    },
  };
  CLIP.audio.addEventListener('error', () => {
    const w = CLIP.want; if (!w || !mediaGaveUp(CLIP.audio)) return;
    CLIP.stop(); if (w.text) TTS.say(w.text);
  });
  /* ---------- preloading: the recording likely to be played next is fetched while the page is open ---------- */
  // iPhones and WeChat's browser download a recording only when it is played: on a phone network that is a second or
  // two after the tap. The recording being studied (and today's article, from 今日) is fetched in the background and kept
  // in memory as a blob: URL, so a tap plays at once. Not with Save-Data or on 2G; at most 8 recordings are kept.
  // (Word sounds are not preloaded: a word's file holds about 100 words, and the player fetches only that word's bytes.)
  const PRELOAD = {
    done: new Map(), going: new Map(),
    frugal() { const c = navigator.connection; return !!(c && (c.saveData || /(^|-)2g$/.test(c.effectiveType || ''))); },
    url(u) { return this.done.get(u) || u; },
    warm(u) {
      if (!u) return Promise.resolve(null);
      if (this.done.has(u)) return Promise.resolve(this.done.get(u));
      if (this.going.has(u)) return this.going.get(u);
      if (this.frugal()) return Promise.resolve(null);
      const p = fetch(u).then(r => (r.ok ? r.blob() : null)).then(b => {
        this.going.delete(u); if (!b || !b.size) return null;
        const blob = URL.createObjectURL(b); this.done.set(u, blob);
        for (const [old, ou] of this.done) {  // oldest first; a recording a player is using stays
          if (this.done.size <= 8) break;
          if (![NAR.audio, CLIP.audio].some(a => a.getAttribute('src') === ou)) { this.done.delete(old); URL.revokeObjectURL(ou); }
        }
        return blob;
      }).catch(() => { this.going.delete(u); return null; });
      this.going.set(u, p); return p;
    },
  };
  // From 今日: the material most likely opened next, and its recording, so the study page opens and plays without a wait.
  async function preloadMaterial(id) {
    if (!id || MAT[id] || PRELOAD.frugal()) return;
    try {
      const m = await api(materialPath(id));
      MAT[id] = m; m._preloaded = Date.now(); snapMaterial(materialPath(id), m);
      const vs = (m.audio && m.audio.voices) || [];
      if (vs.length) PRELOAD.warm(`/audio/${vs.includes(S.voice) ? S.voice : vs[0]}/${encodeURIComponent(id)}.mp4?v=${m.audio.version}`);
    } catch (e) { /* it loads when opened */ }
  }

  /* ---------- unlocking: a media element that has played once inside a tap may play later on its own ---------- */
  // WeChat's browser, iPhones and many Android in-app browsers refuse sound that does not start inside a tap, which is
  // what a play after a download is (a word's clip, a sentence after its timings, a reply read out). On the first tap
  // anywhere, both players play a moment of silence; from then on they may play when their file arrives.
  // Four samples of silence, as a blob: URL (the page's CSP allows blob: and 'self' for media, not data:).
  const SILENT = (() => {
    try { const b = atob('UklGRiwAAABXQVZFZm10IBAAAAABAAEAQB8AAIA+AAACABAAZGF0YQgAAAAAAAAAAAAAAA=='), u = new Uint8Array(b.length);
      for (let i = 0; i < b.length; i++) u[i] = b.charCodeAt(i);
      return URL.createObjectURL(new Blob([u], { type: 'audio/wav' })); } catch (e) { return ''; }
  })();
  function claim(a) { a._uses = (a._uses || 0) + 1; a.muted = false; }
  function unlockAudio() {
    ['touchend', 'click', 'keydown'].forEach(t => window.removeEventListener(t, unlockAudio, true));
    [NAR.audio, CLIP.audio].forEach(a => {
      const own = a.getAttribute('src'), uses = a._uses || 0;
      if (!own && SILENT) a.setAttribute('src', SILENT);
      a.muted = true;
      const after = () => {
        if ((a._uses || 0) !== uses) return;  // this same tap started real playback: leave it alone
        a.pause(); a.muted = false;
        if (!own && a.getAttribute('src') === SILENT) { a.removeAttribute('src'); a.load(); }
      };
      try { const p = a.play(); if (p && p.then) p.then(after, after); else after(); } catch (e) { after(); }
    });
    if (TTS.ok) { try { const u = new SpeechSynthesisUtterance(' '); u.volume = 0; speechSynthesis.speak(u); } catch (e) { /* ignore */ } }
  }
  ['touchend', 'click', 'keydown'].forEach(t => window.addEventListener(t, unlockAudio, true));
  // Attached to the page: some Android in-app browsers lose a detached player's sound.
  addEventListener('DOMContentLoaded', () => { [NAR.audio, CLIP.audio].forEach(a => { a.hidden = true; document.body.appendChild(a); }); });
  if (document.readyState !== 'loading') [NAR.audio, CLIP.audio].forEach(a => { a.hidden = true; document.body.appendChild(a); });

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
    // 撤销 of a rating made offline: it has not been sent, so it is simply taken out again
    unpush(item) { const l = this.list(), k = l.map(x => JSON.stringify(x)).lastIndexOf(JSON.stringify(item)); if (k >= 0) { l.splice(k, 1); save(this.key, l); return true; } return false; },
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
      if (sent) { toast(`没网时做的 ${sent} 项已同步`); refreshHome().catch(() => {}); }  // said once, here (also after the 'online' event)
      return sent;
    },
  };
  // sent when the phone is back online: 06-offline.js (which also says how much was synced)
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
  // Screen readers read the page in Chinese (lang="zh-CN"); English on it (a text, a question, a word, an example)
  // gets lang="en" as it appears, so it is read with an English voice. An element is marked when all of its text is
  // English; one that mixes both is left as it is (VoiceOver and TalkBack still switch for the Latin letters).
  const HAN = /[\u3400-\u9fff\uf900-\ufaff]/, LATIN2 = /[A-Za-z]{2}/;  // Chinese characters (not the full-width punctuation)
  function markEnglish(root) {
    const w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT), seen = new Set(); let n;
    while ((n = w.nextNode())) {
      const el = n.parentElement;
      if (!el || seen.has(el) || !LATIN2.test(n.nodeValue)) continue;
      seen.add(el);
      const own = el.closest('[lang]');
      if (own && own !== document.documentElement) continue;  // it says its language already
      if (!HAN.test(el.textContent) && !/^(SCRIPT|STYLE|TEXTAREA|OPTION)$/.test(el.tagName)) el.lang = 'en';
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
  // The home data: who is signed in, today's plan and counts. Kept on the phone for the next visit (05-data.js).
  // Says whether anything changed since the copy the page was drawn from.
  async function refreshHome() {
    const before = S.home ? JSON.stringify(S.home) : '';
    S.home = await api('/api/next/home' + guestQuery(true));
    if (S.home.session) { S.user = S.home.session.user; S.csrf = S.user ? S.user.csrf : ''; }
    S.homeFromSnap = false; DATA.ok();
    const changed = before !== JSON.stringify(S.home);
    if (changed) snapHome();
    if (S.home.profile && S.home.profile.voice) { S.voice = S.home.profile.voice; save('flow-next-voice', S.voice); }
    setDueBadge();
    return changed;
  }
  function setDueBadge() {
    const due = S.home && S.home.stats ? S.home.stats.due + S.home.stats.new : 0;
    const b = document.getElementById('dueBadge'); b.hidden = !due; b.textContent = due > 99 ? '99+' : due;
  }
  // The page drawn again with fresher data, without the loading skeleton or the entrance animation, and only when it
  // would not take anything from the learner (a sheet open, typing in a field, another page by now).
  function redrawQuietly(drawnFor) {
    if (location.hash !== drawnFor || !sheetEl.hidden || (document.activeElement && /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName))) return;
    S.homeFresh = true; route(true, true);
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

  /* ---------- router ---------- */
  function setNav(name) { document.querySelectorAll('[data-nav]').forEach(a => a.dataset.nav === name ? a.setAttribute('aria-current', 'page') : a.removeAttribute('aria-current')); }
  function parts() { return location.hash.replace(/^#\/?/, '').split('/'); }
  async function route(keepScroll, quiet) {
    if (/^#reset=/.test(location.hash)) {  // an older password-reset email
      const token = decodeURIComponent(location.hash.slice(7)); history.replaceState(null, '', location.pathname + location.search + '#/');
      setTimeout(() => resetByLink(token), 0);
    }
    TTS.stop(); NAR.stop(); CLIP.stop(); MIC.stop(); MINI.hide(); hideSelbar(); swipeOff(); document.body.classList.remove('reviewing'); bar.classList.remove('hide'); document.onselectionchange = null; document.onkeydown = null;
    const [name, a, b] = parts();
    const last = S.lastRoute.split('/');
    const sameMaterial = name === 'm' && last[0] === 'm' && last[1] === a && !!view.querySelector('#pane');
    S.prevRoute = S.lastRoute; S.lastRoute = parts().join('/');  // 问题反馈 says which page it came from
    if (!sameMaterial && !quiet) view.innerHTML = skeleton();
    let fresh = S.homeFresh; S.homeFresh = false;  // home data fetched just before this page: today() need not ask again
    try {
      if (!S.home) { await refreshHome(); fresh = true; }
      if (name === 'welcome') { setNav(''); await welcome(a === 'edit'); }
      // Only the personalised home needs the level questions first; everything else works for a new guest too.
      else if (!hasProfile() && !['me', 'vocab', 'sounds', 'library', 'graph', 'm', 'cards', 'import', 'report', 'review', 'placement', 'exam', 'series', 'mix', 'easy', 'words', 'speak', 'growth', 'radar', 'practice', 'guide', 'feedback', 'weekly-off'].includes(name)) { location.replace('#/welcome'); return; }
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
      else if (name === 'weekly-off') { setNav('me'); await weeklyOffView(decodeURIComponent(a || '')); }  // the link in the Sunday mail
      else if (name === 'vocab') { setNav('cards'); await (a === 'plan' ? planView() : a === 'test' ? vocabTest() : vocabView()); }
      else if (name === 'review') { setNav('cards'); await reviewView(); }
      else if (name === 'library') { setNav('practice'); await libraryView(); }
      else if (name === 'practice') { setNav('practice'); await practiceView(); }
      else if (name === 'guide') { setNav('practice'); await guideView(a ? decodeURIComponent(a) : ''); }
      else if (name === 'me') { setNav('me'); await meView(); }
      else if (name === 'feedback') { setNav('me'); await feedbackView(); }
      else { setNav('today'); await today(fresh); }
      if (!sameMaterial && name !== 'welcome' && !quiet) enter(view);
      if (!sameMaterial && !quiet) { const h = view.querySelector('h1'); announce(h ? h.textContent : document.title); }
    } catch (e) {
      const kept = e.network ? OFF.list() : [];  // offline: what can still be studied
      view.innerHTML = `<div class="empty"><div class="big">⚠︎</div><p>${esc(e.message)}</p><button class="btn" id="retry">重试</button>
        ${kept.length ? `<p class="small">没网时，这些已存到手机的材料还能学：</p><div class="mlist">${kept.map(k => mrow(k, null, '', '')).join('')}</div>` : ''}
        <p class="small"><a class="link" href="#/feedback">反馈这个问题</a></p></div>`;
      document.getElementById('retry').onclick = () => route();
    } finally { if (!keepScroll && !sameMaterial && !quiet) view.focus({ preventScroll: true }); }
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

  /* ---------- 内测版: flow.jasa.hk, a second site with its own data, where new versions run before 语流 gets them ---------- */
  // The server says which site the page is on (<html data-channel>, app.CHANNEL). 语流 itself is flowlang.cn. On the
  // 内测版: a line under the top bar on every page, 「内测」 in the tab's title, a note in the sign-in sheet (95-channel.css),
  // and once per phone a sheet saying where 语流 is. Until 2026-11-24 this address was 语流 itself, so what this phone
  // kept for an account from then (instant-page copies, materials kept for offline study, the review queue, answers not
  // sent yet) is cleared before the page starts: none of it belongs to this site's accounts.
  const BETA = document.documentElement.dataset.channel === 'beta';
  const MAIN_SITE = 'https://flowlang.cn';
  const BETA_BEFORE = (() => {
    if (!BETA || load('flow-channel') === 'beta') return null;
    let before = false;
    try {
      before = Object.keys(localStorage).some(k => k.startsWith('flow-'));
      ['flow-snap', 'flow-offline', 'flow-next-outbox', 'flow-next-review-cache', 'flow-habit-lastweek', 'flow-habit-cheered'].forEach(k => localStorage.removeItem(k));
    } catch (e) { /* private mode */ }
    save('flow-channel', 'beta');
    return before;
  })();
  if (BETA) {
    document.title = '内测 · ' + document.title;
    document.getElementById('bar').insertAdjacentHTML('afterend', `<p class="beta-bar" id="betaBar" role="note"><b>内测版</b><span>先试新功能，账号和数据与正式版分开</span><a href="${MAIN_SITE}/" data-tap="beta-main">去正式版 flowlang.cn</a></p>`);
  }
  // Once per phone, after the first page is up.
  if (BETA_BEFORE !== null) setTimeout(() => openSheet(`<div class="stack"><h2 class="h2" id="sheetTitle">这里是语流内测版</h2>
    ${BETA_BEFORE ? '<p><b>语流的网址改成了 flowlang.cn。</b></p><p class="small">你的账号和学习记录都在 flowlang.cn，用原来的用户名和密码登录就行（换了网址，要重新登录一次）。加到了手机桌面的话，也请在 flowlang.cn 重新添加一次。</p>'
      : '<p>语流正式版的网址是 <b>flowlang.cn</b>。</p>'}
    <p class="small muted">这里（flow.jasa.hk）用来先试还没正式上线的新功能。账号和数据都和正式版分开，内测期间可能会清空。</p>
    <a class="btn primary" href="${MAIN_SITE}/" data-tap="beta-main">去正式版 flowlang.cn</a>
    <button class="btn ghost" data-close type="button">留在内测版</button></div>`), 700);
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
  // Signing out (and 注销账号): the account's copies on this phone go, with the review queue kept for offline review and
  // anything still waiting to be sent (the sign-out sends it first while there is a connection: OUTBOX.flush), so the
  // next person on a shared phone sees none of it and none of it is sent into their account.
  function snapClear() {
    save(SNAP, null); DATA.mem.clear(); OFF.clear();
    try { localStorage.removeItem('flow-next-review-cache'); localStorage.removeItem('flow-next-outbox'); } catch (e) { /* private mode */ }
  }

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
  /* ---------- 存到手机: materials kept on the phone, to study without a connection ---------- */
  // Today's article and the next two are kept by themselves (when the phone is idle; not with Save-Data or on 2G), any
  // other with 「存到手机」 on its page; ten at most, per account. A kept material has its text, its questions with the
  // answers (graded on the phone without a connection) and its narration (kept by the service worker). What is done
  // offline (steps, answers) waits in the outbox and is sent when the phone is back online, so progress and the
  // mistake book are recorded as usual.
  const OFF = {
    key: 'flow-offline', max: 10,
    all() { const s = load(this.key); return s && s.v === 1 && s.owner === snapOwner() ? s : { v: 1, owner: snapOwner(), mats: {} }; },
    get(id) { const s = this.all(); return s.mats[id] ? s.mats[id].m : null; },
    has(id) { return !!this.all().mats[id]; },
    count() { return Object.keys(this.all().mats).length; },
    list() { const s = this.all(); return Object.keys(s.mats).map(id => s.mats[id].m).filter(Boolean); },
    put(id, m) {
      const s = this.all(); s.mats[id] = { at: Date.now(), m };
      Object.keys(s.mats).sort((a, b) => s.mats[b].at - s.mats[a].at).slice(this.max).forEach(k => delete s.mats[k]);
      try { save(this.key, s); } catch (e) { /* full: the oldest stays out */ }
    },
    clear() { save(this.key, null); },
  };
  async function keepOffline(id, quiet) {
    try {
      const m = await dataGet(materialPath(id) + '&offline=1', quiet);
      OFF.put(id, m);
      if (MAT[id] && !MAT[id].answers) MAT[id].answers = m.answers;  // the page open now can grade offline too
      const vs = (m.audio && m.audio.voices) || [], sw = navigator.serviceWorker && navigator.serviceWorker.controller;
      if (vs.length && sw) {  // the narration and its timings, kept by the service worker like any audio it has served
        const base = `/audio/${vs.includes(S.voice) ? S.voice : vs[0]}/${encodeURIComponent(id)}`;
        sw.postMessage({ type: 'prefetch', urls: [`${base}.json?v=${m.audio.version}`, `${base}.mp4?v=${m.audio.version}`] });
      }
      if (!quiet) toast('已存到手机，没网也能学');  // the chip itself is short now, so the toast says what it means
      return true;
    } catch (e) { if (!quiet) toast(e.network ? '现在没网，存不了' : e.message); return false; }
  }
  function keepTodayOffline() {
    if (PRELOAD.frugal() || !S.home) return;
    const h = S.home, ids = [], read = h.path && h.path.steps && h.path.steps.find(s => s.key === 'read');
    if (read) ids.push(decodeURIComponent(read.href.split('/')[2] || ''));
    (h.today || []).forEach(m => ids.push(m.id));
    idle(() => [...new Set(ids)].filter(Boolean).slice(0, 3).forEach(id => { if (!OFF.has(id)) keepOffline(id, true); }));
  }
  // On a material's page: 存到手机, or that it is kept.
  function offChip(id) {
    // a phone with a down arrow in front, at the right of the kicker line (the full meaning is in the title and the toast)
    const icon = '<svg class="offi" viewBox="0 0 24 24" aria-hidden="true"><rect x="6" y="2.5" width="12" height="19" rx="2.5"/><path d="M12 7.5v7m-3-3 3 3 3-3"/></svg>';
    return OFF.has(id) ? '<span class="offk on" id="keepOff" title="没网也能学">✓ 已存到手机</span>' : `<button class="link small offk" id="keepOff" type="button" data-tap="study-keep" title="存到手机，没网也能学">${icon}存到手机</button>`;
  }
  function bindOffChip(id) {
    const b = document.getElementById('keepOff'); if (!b || b.tagName !== 'BUTTON') return;
    b.onclick = async () => { b.disabled = true; b.textContent = '正在存…'; const ok = await keepOffline(id); b.outerHTML = offChip(id); if (!ok) bindOffChip(id); };
  }
  // Losing and finding the connection: said once each way; what waited is sent.
  addEventListener('offline', () => { const n = OFF.count(); toast(n ? `现在没网：已存到手机的 ${n} 篇还能学` : '现在没网：复习单词还能做，联网后自动同步'); });
  addEventListener('online', () => { OUTBOX.flush(); });  // it says how much was synced
  /* ---------- QR codes (byte mode, error correction M, versions 1–6): the 分享卡片's way back to the site ---------- */
  // Written out here rather than loaded from elsewhere (the page loads nothing from other sites). tools/ui_test.py reads
  // the codes back with the browser's own BarcodeDetector where it has one. Up to 106 bytes: plenty for a link.
  const QR = (() => {
    const BLOCKS = [null, [10, 1, 16], [16, 1, 28], [26, 1, 44], [18, 2, 32], [24, 2, 43], [16, 4, 27]];  // [ECC per block, blocks, data per block]
    const ALIGN = [null, [], [6, 18], [6, 22], [6, 26], [6, 30], [6, 34]];
    const EXP = new Array(512), LOG = new Array(256);  // GF(256) with x^8 + x^4 + x^3 + x^2 + 1
    for (let i = 0, x = 1; i < 255; i++) { EXP[i] = x; LOG[x] = i; x <<= 1; if (x & 256) x ^= 0x11d; }
    for (let i = 255; i < 512; i++) EXP[i] = EXP[i - 255];
    const mul = (a, b) => (a && b ? EXP[LOG[a] + LOG[b]] : 0);
    function ecc(data, n) {  // Reed–Solomon: the remainder of data·x^n divided by the generator of degree n
      let g = [1];
      for (let i = 0; i < n; i++) { const ng = new Array(g.length + 1).fill(0); g.forEach((v, j) => { ng[j] ^= v; ng[j + 1] ^= mul(v, EXP[i]); }); g = ng; }
      const r = data.concat(new Array(n).fill(0));
      for (let i = 0; i < data.length; i++) { const f = r[i]; if (f) g.forEach((v, j) => { r[i + j] ^= mul(v, f); }); }
      return r.slice(data.length);
    }
    function codewords(bytes, ver) {
      const [ecN, blocks, per] = BLOCKS[ver], cap = blocks * per, bits = [];
      const put = (v, n) => { for (let i = n - 1; i >= 0; i--) bits.push((v >> i) & 1); };
      put(4, 4); put(bytes.length, 8); bytes.forEach(b => put(b, 8));
      put(0, Math.min(4, cap * 8 - bits.length));
      while (bits.length % 8) bits.push(0);
      const data = [];
      for (let i = 0; i < bits.length; i += 8) data.push(bits.slice(i, i + 8).reduce((a, b) => a * 2 + b, 0));
      for (let p = 0; data.length < cap; p++) data.push(p % 2 ? 0x11 : 0xec);
      const ds = [], es = [];
      for (let b = 0; b < blocks; b++) { const d = data.slice(b * per, (b + 1) * per); ds.push(d); es.push(ecc(d, ecN)); }
      const out = [];
      for (let i = 0; i < per; i++) ds.forEach(d => out.push(d[i]));
      for (let i = 0; i < ecN; i++) es.forEach(e => out.push(e[i]));
      return out;
    }
    const MASKS = [(r, c) => (r + c) % 2 === 0, r => r % 2 === 0, (r, c) => c % 3 === 0, (r, c) => (r + c) % 3 === 0,
      (r, c) => (Math.floor(r / 2) + Math.floor(c / 3)) % 2 === 0, (r, c) => ((r * c) % 2) + ((r * c) % 3) === 0,
      (r, c) => (((r * c) % 2) + ((r * c) % 3)) % 2 === 0, (r, c) => (((r + c) % 2) + ((r * c) % 3)) % 2 === 0];
    function penalty(m) {  // the standard's four rules; a lower score scans more easily (any mask is valid)
      const n = m.length; let s = 0, dark = 0;
      const line = get => { let run = 1; for (let i = 1; i < n; i++) { if (get(i) === get(i - 1)) { run++; if (run === 5) s += 3; else if (run > 5) s++; } else run = 1; } };
      for (let i = 0; i < n; i++) { line(j => m[i][j]); line(j => m[j][i]); }
      for (let r = 0; r < n - 1; r++) for (let c = 0; c < n - 1; c++) { const v = m[r][c]; if (v === m[r][c + 1] && v === m[r + 1][c] && v === m[r + 1][c + 1]) s += 3; }
      const pat = [1, 0, 1, 1, 1, 0, 1, 0, 0, 0, 0], rev = pat.slice().reverse();
      const at = (get, i, p) => p.every((b, k) => (get(i + k) ? 1 : 0) === b);
      for (let i = 0; i < n; i++) for (let j = 0; j + 11 <= n; j++) {
        const row = k => m[i][k], col = k => m[k][i];
        if (at(row, j, pat) || at(row, j, rev)) s += 40;
        if (at(col, j, pat) || at(col, j, rev)) s += 40;
      }
      m.forEach(r => r.forEach(v => { if (v) dark++; }));
      return s + 10 * Math.max(0, Math.ceil(Math.abs(dark * 20 - n * n * 10) / (n * n)) - 1);
    }
    function matrix(text) {
      const bytes = Array.from(new TextEncoder().encode(text));
      let ver = 1;
      while (ver <= 6 && bytes.length > BLOCKS[ver][1] * BLOCKS[ver][2] - 2) ver++;
      if (ver > 6) throw new Error('link too long for the QR code');
      const n = 17 + 4 * ver, M = [...Array(n)].map(() => new Array(n).fill(false)), fn = [...Array(n)].map(() => new Array(n).fill(false));
      const set = (r, c, v) => { M[r][c] = v; fn[r][c] = true; };
      for (const [r0, c0] of [[0, 0], [0, n - 7], [n - 7, 0]]) {  // finders, with their light separators
        for (let r = -1; r <= 7; r++) for (let c = -1; c <= 7; c++) {
          const rr = r0 + r, cc = c0 + c; if (rr < 0 || cc < 0 || rr >= n || cc >= n) continue;
          set(rr, cc, r >= 0 && r <= 6 && c >= 0 && c <= 6 && (r === 0 || r === 6 || c === 0 || c === 6 || (r >= 2 && r <= 4 && c >= 2 && c <= 4)));
        }
      }
      for (let i = 8; i < n - 8; i++) { set(6, i, i % 2 === 0); set(i, 6, i % 2 === 0); }  // timing
      const al = ALIGN[ver], last = al[al.length - 1];
      for (const r of al) for (const c of al) {
        if ((r === 6 && c === 6) || (r === 6 && c === last) || (r === last && c === 6)) continue;
        for (let dr = -2; dr <= 2; dr++) for (let dc = -2; dc <= 2; dc++) set(r + dr, c + dc, Math.max(Math.abs(dr), Math.abs(dc)) !== 1);
      }
      set(n - 8, 8, true);  // the dark module
      for (let i = 0; i < 9; i++) { if (!fn[8][i]) set(8, i, false); if (!fn[i][8]) set(i, 8, false); }  // format areas, filled later
      for (let i = 0; i < 8; i++) { if (!fn[8][n - 1 - i]) set(8, n - 1 - i, false); if (!fn[n - 1 - i][8]) set(n - 1 - i, 8, false); }
      const bits = []; codewords(bytes, ver).forEach(b => { for (let i = 7; i >= 0; i--) bits.push((b >> i) & 1); });
      let k = 0;
      for (let right = n - 1; right >= 1; right -= 2) {  // two columns at a time, up then down, from the bottom right
        if (right === 6) right = 5;
        for (let v = 0; v < n; v++) for (let j = 0; j < 2; j++) {
          const c = right - j, r = ((right + 1) & 2) === 0 ? n - 1 - v : v;
          if (!fn[r][c]) { M[r][c] = k < bits.length && bits[k] === 1; k++; }
        }
      }
      let best = null;
      for (let mask = 0; mask < 8; mask++) {
        const m = M.map((row, r) => row.map((v, c) => (fn[r][c] ? v : v !== MASKS[mask](r, c))));
        const data = mask;  // level M is 00
        let rem = data; for (let i = 0; i < 10; i++) rem = (rem << 1) ^ ((rem >> 9) * 0x537);
        const f = ((data << 10) | rem) ^ 0x5412, bit = i => ((f >> i) & 1) === 1;
        for (let i = 0; i <= 5; i++) m[i][8] = bit(i);
        m[7][8] = bit(6); m[8][8] = bit(7); m[8][7] = bit(8);
        for (let i = 9; i < 15; i++) m[8][14 - i] = bit(i);
        for (let i = 0; i < 8; i++) m[8][n - 1 - i] = bit(i);
        for (let i = 8; i < 15; i++) m[n - 15 + i][8] = bit(i);
        m[n - 8][8] = true;
        const score = penalty(m);
        if (!best || score < best.score) best = { m, score };
      }
      return best.m;
    }
    // Drawn dark on light at x, y, size px across, with the quiet zone (4 modules) inside that size.
    function draw(g, text, x, y, size, dark = '#13261b', light = '#ffffff') {
      // whole pixels per module, the code centred in the box: no seams between modules
      const m = matrix(text), u = Math.max(1, Math.floor(size / (m.length + 8))), o = Math.round((size - u * m.length) / 2);
      g.fillStyle = light; g.fillRect(x, y, size, size); g.fillStyle = dark;
      m.forEach((row, r) => row.forEach((v, c) => { if (v) g.fillRect(x + o + c * u, y + o + r * u, u, u); }));
    }
    return { matrix, draw };
  })();
  /* ---------- welcome ---------- */
  async function welcome(edit) {
    if (!S.meta) S.meta = await api('/api/next/meta');
    const cur = (S.home && S.home.profile) || S.guest || {};
    // Back from the starting check with a level: the level question is answered, go on with the rest.
    const st = { step: S.placed ? 1 : 0, level: S.placed || cur.level || '', goal: cur.goal || '', themes: (cur.themes || []).slice(), minutes: cur.minutes || 10 };
    S.placed = '';
    const total = 4;
    function draw() {
      let body = '';
      // A first visit (often from a link in WeChat) can start with today's article right away: no questions, no account.
      const trial = !edit && !S.user && !cur.level && S.home && S.home.today && S.home.today[0];
      if (st.step === 0 && trial) body = `<div class="card sunk try-first stack-s"><b>先试读一篇，觉得有用再定水平</b>
          <span class="small muted">「${esc(trial.title)}」 · 约 ${trial.minutes} 分钟：听一遍、读一遍、做几道理解题。不用回答问题，也不用注册。</span>
          <a class="btn primary" href="#/m/${encodeURIComponent(trial.id)}" data-tap="welcome-try">先试读一篇</a></div><p class="tiny muted tc">或者先回答 4 个问题，按你的水平推荐</p>`;
      if (st.step === 0) body += `<h1 class="h1">你能轻松读懂哪一句？</h1><p class="muted">选你不查词典也能读懂的最难一句。之后随时可以改。</p>
        <div class="choice opts four">${S.meta.levels.map(l => `<button class="opt" data-v="${l.id}" aria-pressed="${st.level === l.id}"><div class="row between"><span class="l">${esc(l.label)}</span><span class="pill">${l.id}</span></div><div class="s">${esc(l.sample)}</div><div class="d">${esc(l.desc)}</div></button>`).join('')}</div>
        <a class="link small place-link" href="#/placement">拿不准？做个 16 题的语法小测，帮你定起点 →</a>`;
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
    // Drawn at once from the home data already here; the server's answer follows and, if anything changed, the page is
    // drawn again quietly (05-data.js). Only the very first visit, with nothing here yet, waits.
    if (!fresh) {
      if (S.home) { const drawnFor = location.hash; refreshHome().then(changed => { if (changed) redrawQuietly(drawnFor); }).catch(() => {}); }
      else await refreshHome();
    }
    const h = S.home, pick = h.today[0], st = h.stats;
    const name = S.user ? S.user.username : '';
    const path = S.user && h.path, weekN = st ? st.week.filter(d => d.active).length : 0;
    // One clear first action: the plan's next step (signed in), or today's article (guest). Under it a short list of
    // steps, at most one notice, and a few materials as one-line rows.
    let top = '', readId = '';
    if (path) {
      const p = h.path, nextK = p.steps.findIndex(s => !s.done), next = p.steps[nextK], read = p.steps.find(s => s.key === 'read');
      readId = read ? decodeURIComponent(read.href.split('/')[2] || '') : '';
      const art = [pick, h.resume, ...h.today].find(m => m && m.id === readId);
      top = `<section class="today-plan" aria-labelledby="tpTitle">
        <div class="tp-head"><div><h1 class="h1" id="tpTitle">${next ? '今天的计划' : '今天的计划完成了'}</h1>
          <span class="muted small">${p.total} 步 · 约 ${p.minutes} 分钟 · 已完成 ${p.done} / ${p.total}</span></div>
          <span class="ring" data-p="${Math.round(p.done / Math.max(1, p.total) * 100)}" aria-hidden="true"><b>${p.done}/${p.total}</b></span></div>
        ${next ? `<a class="btn primary block go-next" href="${esc(next.href)}">${p.done ? '继续' : '开始'}第 ${nextK + 1} 步<span aria-hidden="true">→</span></a>`
          : `<div class="tp-done">${doneRing}<span>都完成了。想多学一点，就再读一篇。</span></div><a class="btn primary block go-next" href="#/library">再学一篇<span aria-hidden="true">→</span></a>`}
        <div class="plist">${p.steps.map((s, k) => {
          const a = s.key === 'read' ? art : null;
          return `<a class="prow${s.done ? ' done' : ''}${s === next ? ' next' : ''}" href="${esc(s.href)}"><span class="num">${s.done ? '✓' : k + 1}</span>
            <span class="t"><b>${esc(a ? a.title : s.title)}</b><span class="muted tiny">${esc(a ? `今天这篇 · ${a.level} · ${a.theme_label} · 约 ${a.minutes} 分钟` : s.sub)}</span></span>
            <span class="go" aria-hidden="true">›</span></a>`;
        }).join('')}</div></section>`;
    } else if (pick) {
      top = `<div class="hello"><h1 class="h1">今天学一篇，用上一句。</h1><span class="muted small">按「${esc(h.level_label)}（${h.level}）」为你挑选 · <a class="link" href="#/welcome/edit">调整</a></span></div>
        <article class="card hero"><div class="meta">${pick.featured ? '<span class="pill feat">精选</span>' : ''}<span class="pill green">今日推荐</span><span class="pill">${pick.level}</span><span class="pill">${esc(pick.theme_label)}</span></div>
        <h2 class="title">${esc(pick.title)}</h2>${pick.title_en ? `<div class="title-en">${esc(pick.title_en)}</div>` : ''}<p class="preview">${esc(pick.preview)}</p>${reasonsHTML(pick)}
        <span class="muted small">${pick.words} 词 · 约 ${pick.minutes} 分钟 · 听、读、理解、用出来</span>
        <a class="btn primary block go-next" href="#/m/${encodeURIComponent(pick.id)}">开始学习<span aria-hidden="true">→</span></a></article>`;
    } else top = '<div class="empty">今天没有可推荐的材料了。</div>';
    const resume = h.resume && h.resume.id !== readId ? h.resume : null, news = h.news && h.news.id !== readId ? h.news : null;
    const more = h.today.filter(m => m.id !== readId && (path || m !== pick) && (!resume || m.id !== resume.id) && (!news || m.id !== news.id)).slice(0, 3);
    view.innerHTML = `<div class="greet-row"><span class="kicker greet">${greeting()}${name ? `，<span class="nm">${esc(name)}</span>` : ''}</span>
        ${st && st.progress ? '' : st && st.habit ? habitChip(st.habit) : st ? `<span class="wk" title="本周学了 ${weekN} 天"><span class="tiny muted">本周 ${weekN} 天</span><span class="week" aria-hidden="true">${st.week.map(d => `<span class="${d.active ? 'on' : ''}"></span>`).join('')}</span></span>` : ''}</div>
      ${announceHTML(h)}
      ${weekCardHTML(h)}
      ${top}
      <div id="notice"></div>
      ${S.user && !path ? vocabHome(st) : ''}
      <section class="section" aria-labelledby="mTitle"><div class="section-head"><h2 class="h2" id="mTitle">也可以读</h2><a class="link small" href="#/welcome/edit">按 ${h.level} 挑选 · 调整</a></div>
        <div class="mlist">${resume ? mrow(resume, ['继续', 'green'], `#/m/${encodeURIComponent(resume.id)}/${nextStep(resume.steps)}`, 'home-resume') : ''}${news ? mrow(news, ['热点', 'amber'], '', 'home-news') : ''}${more.map(m => mrow(m, null, '', 'home-pick')).join('')}
          <a class="mrow more" href="#/library" data-tap="home-more"><span class="t"><b>更多材料</b><span class="tiny muted">按话题和级别挑一篇</span></span><span class="go" aria-hidden="true">›</span></a></div>
        ${news ? '<p class="tiny muted">「热点」是联网检索后改写的，未经人工审核。</p>' : ''}</section>`;
    const ring = view.querySelector('.ring'); if (ring) ring.style.setProperty('--p', ring.dataset.p + '%');  // CSP: no inline style attributes
    fillNotice(h);
    bindAnnounce(h);
    bindWeekCard();  // 这周进步 (11-progress.js)
    const hb = document.getElementById('habitBtn'); if (hb) hb.onclick = habitSheet;
    if (st && st.habit) cheerWeek(st.habit);
    const nextRead = readId || (pick && pick.id);
    if (nextRead) setTimeout(() => preloadMaterial(nextRead), 600);  // after the page is drawn, not before
  }
  // 每周目标: this week's days (Monday to Sunday) against the goal; a missed day breaks nothing while the week still
  // reaches it. The weeks reached are counted up, never as a run that breaks (r27). A tap changes the goal. Signed in,
  // the 这周进步 card (11-progress.js) shows all this, and the chip is only for a 今日 kept from before it.
  function habitChip(hb) {
    return `<button class="wk habit" id="habitBtn" type="button" aria-label="本周学了 ${hb.done} 天，目标 ${hb.goal} 天${hb.weeks ? '，已达成 ' + hb.weeks + ' 周' : ''}。点这里改每周目标" data-tap="home-habit">
      <span class="tiny ${hb.met ? 'met' : 'muted'}">本周 ${hb.done}/${hb.goal} 天${hb.weeks ? ` · 已达成 ${hb.weeks} 周` : ''}</span>
      <span class="week" aria-hidden="true">${hb.days.map(d => `<span class="${d.active ? 'on' : ''}${d.today ? ' today' : ''}"></span>`).join('')}</span></button>`;
  }
  function habitSheet() {
    const hb = (S.home && S.home.stats && S.home.stats.habit) || { goal: 4 };
    openSheet(`<div class="stack"><h2 class="h2" id="sheetTitle">每周目标</h2>
      <p class="muted small">一周里学够这么多天就算达成。哪天没空也没关系，不会清零；坚持的是一周一周，不是天天打卡。</p>
      <div class="chips" role="radiogroup" aria-label="每周学几天">${[2, 3, 4, 5, 6, 7].map(n => `<button class="chip" type="button" role="radio" data-goal="${n}" aria-checked="${hb.goal === n}">每周 ${n} 天</button>`).join('')}</div>
      <p class="tiny muted">学一步材料或复习几个词，都算学了这一天。</p><button class="btn ghost" data-close type="button">完成</button></div>`, card => {
      card.querySelectorAll('[data-goal]').forEach(b => b.onclick = async () => {
        try {
          const r = await api('/api/next/habit', { goal: Number(b.dataset.goal) });
          if (S.home && S.home.stats) S.home.stats.habit = r.habit;
          card.querySelectorAll('[data-goal]').forEach(x => x.setAttribute('aria-checked', String(x === b)));
          const v = document.getElementById('meHabitV'); if (v) v.textContent = `每周 ${r.habit.goal} 天`;
          const chip = document.getElementById('habitBtn'); if (chip) { chip.outerHTML = habitChip(r.habit); const n = document.getElementById('habitBtn'); if (n) n.onclick = habitSheet; }
          refreshWeekCard();
          toast(`每周目标：${r.habit.goal} 天`);
        } catch (e) { toast(e.message); }
      });
    });
  }
  // The week's goal reached: said once, the first time 今日 shows it that week.
  function cheerWeek(hb) {
    if (!hb.met || load('flow-habit-cheered') === hb.monday) return;
    save('flow-habit-cheered', hb.monday);
    toast(hb.weeks > 1 ? `本周目标达成！一共达成 ${hb.weeks} 周了` : '本周目标达成！');
  }
  // A material as one row: title, then level, topic and time; a pill says why it is on the list.
  function mrow(m, tag, href, tapKey) {
    return `<a class="mrow" href="${href || '#/m/' + encodeURIComponent(m.id)}"${tapKey ? ` data-tap="${tapKey}"` : ''}><span class="t"><b>${esc(m.title)}</b>
      <span class="tiny muted">${m.level} · ${esc(m.theme_label)}${m.minutes ? ` · 约 ${m.minutes} 分钟` : ''}${m.steps && m.steps.length ? ` · 学了 ${m.steps.length}/4 步` : ''}${OFF.has(m.id) ? ' · 已存到手机' : ''}</span></span>
      ${tag ? `<span class="pill ${tag[1]}">${tag[0]}</span>` : m.featured ? '<span class="pill feat">精选</span>' : ''}<span class="go" aria-hidden="true">›</span></a>`;
  }
  // 公告 from the operators (xmc.hk console, r26): one line at the very top of 今日, for everyone, until it ends.
  // 「知道了」 (or going to its page) hides that one on this phone; a new one shows again.
  function announceHTML(h) {
    const a = h.announce;
    if (!a || load('flow-announce-seen') === a.id) return '';
    return `<div class="card sunk section notice announce stack-s" id="announce" role="status"><b>${esc(a.text)}</b>
      <div class="row">${a.link ? `<a class="btn small primary" href="${esc(a.link)}" data-tap="announce-open">去看看</a>` : ''}<button class="btn small ghost" id="annOk" type="button">知道了</button></div></div>`;
  }
  function bindAnnounce(h) {
    const box = document.getElementById('announce'); if (!box) return;
    const seen = () => { save('flow-announce-seen', h.announce.id); box.remove(); };
    document.getElementById('annOk').onclick = seen;
    const go = box.querySelector('a'); if (go) go.addEventListener('click', () => save('flow-announce-seen', h.announce.id));
  }
  // One notice at a time under the plan, the most useful first: sign in (guest), a level that fits better, an email
  // for getting back in, then the guide for the first few days. Putting one off brings up the next.
  function noticeHTML(h) {
    if (!S.user) return `<div class="card sunk section notice stack-s"><b>登录后，进度和收藏的表达会保存下来</b><span class="muted small">不登录也可以听、读和做理解题。</span><div><button class="btn small" id="loginCta" data-tap="notice-login">登录 / 注册</button></div></div>`;
    if (h.suggest && Date.now() - (load('flow-next-suggest-skip') || 0) > 7 * 864e5) return suggestHTML(h.suggest);
    const hb = h.stats && h.stats.habit;  // on Monday and Tuesday: how last week went, once
    if (hb && hb.last_week.done && (hb.days[0].today || hb.days[1].today) && load('flow-habit-lastweek') !== hb.monday)
      return `<div class="card sunk section notice stack-s" id="lastWeek"><b>${hb.last_week.met ? `上周学了 ${hb.last_week.done} 天，目标达成了 🎉` : `上周学了 ${hb.last_week.done} 天，离目标还差 ${hb.goal - hb.last_week.done} 天`}</b>
        <span class="small">${hb.last_week.met ? '这周接着来。' : '没关系，这周重新开始，学一步材料或复习几个词就算一天。'}</span>
        <div class="row"><a class="btn small primary" href="#/report" data-tap="notice-week">看上周报告</a><button class="btn small ghost" id="lwOk" type="button">知道了</button></div></div>`;
    const mail = mailNudgeHTML(); if (mail) return mail;
    if (installNudgeDue(h)) return `<div class="card sunk section notice stack-s" id="installNudge"><b>把语流放到手机桌面</b><span class="small">像 App 一样一点就开，全屏；听过的音频网络差的时候也能复习。</span>
      <div class="row"><button class="btn small primary" id="inGo" type="button" data-tap="notice-install">怎么放</button><button class="btn small ghost" id="inLater" type="button">以后再说</button></div></div>`;
    if (!h.stats || (h.stats.materials_done || 0) < 3) return `<a class="card sunk section notice guide-hint" href="#/guide" data-tap="notice-guide"><span class="stack-s"><b>第一次用？看操作指南</b><span class="small muted">每个页面怎么用、按哪里，一步一步讲清楚。</span></span><span class="go" aria-hidden="true">›</span></a>`;
    return '';
  }
  function fillNotice(h) {
    const slot = document.getElementById('notice'); if (!slot) return;
    slot.innerHTML = noticeHTML(h);
    const cta = document.getElementById('loginCta'); if (cta) cta.onclick = () => openLogin();
    if (h.suggest) bindSuggest(h, () => fillNotice(h));
    bindMailNudge(() => fillNotice(h));
    const lw = document.getElementById('lwOk'); if (lw) lw.onclick = () => { save('flow-habit-lastweek', h.stats.habit.monday); fillNotice(h); };
    const lwr = document.querySelector('#lastWeek a'); if (lwr) lwr.addEventListener('click', () => save('flow-habit-lastweek', h.stats.habit.monday));
    const ig = document.getElementById('inGo'), il = document.getElementById('inLater');
    if (ig) ig.onclick = installSheet;
    if (il) il.onclick = () => { save('flow-install-later', Date.now()); fillNotice(h); };
  }
  function vocabHome(st) {
    if (!st) return '';
    const n = st.due + st.new;
    if (!st.vocab_plan && !n) return `<a class="card flat section mini" href="#/cards"><span class="t">背单词</span><span class="pill">按遗忘曲线</span><span class="p">选一本词书，每天几个新词；例句来自你读的文章，还能听原文录音。</span></a>`;
    return `<div class="card section due"><div><div class="kicker">单词</div><div>${n ? `复习 <b>${st.due}</b> · 新词 <b>${st.new}</b>` : '今天的单词都完成了'}</div>
      <div class="muted small">${n ? `大约 ${st.minutes} 分钟` : '明天见'}</div></div>${n ? '<a class="btn primary" href="#/review">开始</a>' : '<a class="btn" href="#/cards">查看</a>'}</div>`;
  }
  function nextStep(steps) { return STEPS.find(s => !steps.includes(s)) || 'output'; }

  /* ---------- 这周进步 (r27): the week so far, at the top of 今日; its details; the Sunday mail ---------- */
  // Four numbers from the learner's own records (progress_service.week): words remembered for the first time (a later
  // day's review still recalled them), texts finished, the share of questions answered right without a hint against
  // last week, and the weekly goal with the weeks reached so far (they only count up). A tap opens the details.
  const WEEKDAYS = '一二三四五六日';
  function accText(a) {
    const n = a.now, b = a.before;
    const value = n.rate != null ? n.rate + '%' : n.total ? `${n.right}/${n.total}` : '—';
    const sub = n.rate != null && b.rate != null ? (n.rate > b.rate ? `<span class="up">比上周 ↑${n.rate - b.rate}</span>` : n.rate < b.rate ? `比上周 ↓${b.rate - n.rate}` : '和上周持平')
      : n.rate == null ? (n.total ? `满 ${a.min} 题才算` : '这周还没做题') : b.total ? '上周题太少' : '上周没做题';
    return { value, sub };
  }
  function weekCardHTML(h) {
    const st = h && h.stats, p = st && st.progress, hb = st && st.habit;
    if (!S.user || !p || !hb) return '';
    const acc = accText(p.accuracy), weeks = hb.weeks || 0;
    const empty = !p.remembered.now && !p.finished.now && !p.accuracy.now.total && !hb.done;
    const tile = (cls, value, label, sub) => `<span class="wk-tile${cls ? ' ' + cls : ''}"><b>${value}</b><span class="tiny muted">${label}</span><span class="tiny sub">${sub}</span></span>`;
    const label = `这周进步：记住 ${p.remembered.now} 个新词，学完 ${p.finished.now} 篇，做题正确率 ${p.accuracy.now.rate != null ? p.accuracy.now.rate + '%' : '还不够算'}，`
      + `本周学了 ${hb.done} 天，目标 ${hb.goal} 天${weeks ? `，已达成 ${weeks} 周` : ''}。点开看明细`;
    return `<button class="card week-card" id="weekCard" type="button" data-tap="home-week" aria-label="${esc(label)}">
      <span class="wk-head"><b>这周进步</b><span class="tiny wk-total${weeks ? ' on' : ''}">${weeks ? `已达成 ${weeks} 周` : '看明细'}<span aria-hidden="true"> ›</span></span></span>
      <span class="wk-tiles">${tile('', p.remembered.now, '记住的新词', `上周 ${p.remembered.before}`)}${tile('', p.finished.now, '学完的文章', `上周 ${p.finished.before}`)}`
      + `${tile('', acc.value, '做题正确率', acc.sub)}${tile('goal' + (hb.met ? ' met' : ''), `${hb.done}<small>/${hb.goal}天</small>`, '每周目标', hb.met ? '达成 ✓' : `还差 ${hb.goal - hb.done} 天`)}</span>
      <span class="wk-foot"><span class="week" aria-hidden="true">${hb.days.map(d => `<span class="${d.active ? 'on' : ''}${d.today ? ' today' : ''}"></span>`).join('')}</span>
        <span class="tiny muted">${empty ? '做完今天的第一步，这里就开始记录' : '数字都来自你自己的学习记录'}</span></span></button>`;
  }
  function bindWeekCard() {
    const b = document.getElementById('weekCard'); if (b) b.onclick = weekSheet;
  }
  // After the goal changes (habitSheet): the card is drawn again from the new numbers.
  function refreshWeekCard() {
    const b = document.getElementById('weekCard'); if (!b || !S.home) return;
    b.outerHTML = weekCardHTML(S.home); bindWeekCard();
  }
  async function weekSheet() {
    openSheet('<div class="stack"><h2 class="h2" id="sheetTitle">这周进步</h2><div class="loading"><span class="spin"></span></div></div>');
    let w;
    try { w = await api('/api/next/week'); } catch (e) { closeSheet(); return toast(e.message); }
    if (sheetEl.hidden) return;
    const hb = w.habit, r = w.remembered, f = w.finished, a = accText(w.accuracy), an = w.accuracy.now, ab = w.accuracy.before;
    const day = s => { const [, m, d] = s.split('-').map(Number); return `${m} 月 ${d} 日`; };
    openSheet(`<div class="stack wk-sheet"><div><h2 class="h2" id="sheetTitle">这周进步</h2><span class="small muted">${day(w.from)} – ${day(w.to)} · 数字都来自你自己的学习记录</span></div>
      <section class="wk-sec" aria-label="每周目标"><div class="row between"><b>每周目标</b><span class="small ${hb.met ? 'met' : 'muted'}">本周 ${hb.done} / ${hb.goal} 天${hb.met ? ' · 达成 ✓' : ''}</span></div>
        <div class="wk-days">${hb.days.map((d, k) => `<span class="${d.active ? 'on' : ''}${d.today ? ' today' : ''}"><i aria-hidden="true"></i><span class="tiny">${WEEKDAYS[k]}</span><span class="sr-only">${d.active ? '学了' : '没学'}</span></span>`).join('')}</div>
        <p class="small">${hb.weeks ? `已经有 <b>${hb.weeks}</b> 周达成了目标。` : '还没有达成目标的周。'}一周学够 ${hb.goal} 天就算达成一周；哪天、哪周没学都不会清零，只会越攒越多。</p>
        <p class="tiny muted">学一步材料、复习几个词、做一组练习或读一篇轻松读，都算学了这一天。</p>
        <div><button class="btn small" id="wkGoal" type="button">改每周目标</button></div></section>
      <section class="wk-sec" aria-label="记住的新词"><div class="row between"><b>记住的新词</b><span class="wk-num">${r.now}</span></div>
        <p class="small muted">新词要隔天复习时还记得才算，一个词只算一次。上周 ${r.before} 个。</p>
        ${r.words.length ? `<div class="wk-words">${r.words.map(x => `<span class="pill" lang="en">${esc(x)}</span>`).join('')}</div>` : '<p class="small">这周还没有。今天学的新词，明天复习还记得就会出现在这里。</p>'}</section>
      <section class="wk-sec" aria-label="学完的文章"><div class="row between"><b>学完的文章</b><span class="wk-num">${f.now}</span></div>
        <p class="small muted">做完一篇的理解题就算学完。上周 ${f.before} 篇。</p>
        ${f.titles.length ? `<div class="wk-list">${f.titles.map(t => `<a class="link small" href="#/m/${encodeURIComponent(t.id)}" data-close>《${esc(t.title)}》</a>`).join('')}</div>` : ''}
        ${w.easy && w.easy[0] ? `<p class="small">另外轻松读了 ${w.easy[0]} 篇，共 ${Number(w.easy[1]).toLocaleString()} 个词。</p>` : ''}</section>
      <section class="wk-sec" aria-label="做题正确率"><div class="row between"><b>做题正确率</b><span class="wk-num">${a.value}</span></div>
        <p class="small">${an.total ? `这周做了 ${an.total} 题，对了 ${an.right} 题` : '这周还没做题'}${an.total && an.rate == null ? `，满 ${w.accuracy.min} 题才算正确率` : ''}。${ab.total ? `上周 ${ab.total} 题对 ${ab.right} 题${ab.rate != null ? `（${ab.rate}%）` : ''}。` : '上周没做题。'}</p>
        <p class="tiny muted">算的是不看提示做的理解题、语法题、辨析和考试练习；语法起点小测不算（它会一直加难，错一半是正常的）。</p></section>
      <div class="row"><a class="btn primary" href="#/report" data-close>这周的报告</a><a class="btn" href="#/growth" data-close>我的进步</a><button class="btn ghost" data-close type="button">关闭</button></div></div>`, card => {
      card.querySelector('#wkGoal').onclick = habitSheet;
    });
  }
  // 我的 → 每周进度邮件: on by default for an account with an email; the mail's own link turns it off too.
  function weeklyMailLabel() {
    const m = S.home && S.home.stats && S.home.stats.progress && S.home.stats.progress.mail;
    return !m ? '' : !m.email ? '绑定邮箱后可以收' : m.on ? '每周日晚上 8 点' : '已关闭';
  }
  function weeklyMailSheet() {
    const p = S.home && S.home.stats && S.home.stats.progress, m = (p && p.mail) || { on: true, email: false };
    openSheet(`<div class="stack"><h2 class="h2" id="sheetTitle">每周进度邮件</h2>
      <p class="small">每周日晚上 8 点，把这周的进步发到你绑定的邮箱：记住的新词、学完的文章、做题正确率和每周目标。这周没学的话，会提醒你一下；连着几周没学就不再发。</p>
      ${m.email ? `<div class="chips" role="radiogroup" aria-label="收不收每周进度邮件">${[[true, '每周收'], [false, '不收']].map(([v, l]) => `<button class="chip" type="button" role="radio" data-mail="${v}" aria-checked="${m.on === v}">${l}</button>`).join('')}</div>
        <p class="tiny muted">每封邮件最下面也有退订链接。</p>`
        : `<p class="small muted">还没有绑定邮箱。</p><div><button class="btn small primary" id="wmBind" type="button">绑定邮箱</button></div>`}
      <button class="btn ghost" data-close type="button">完成</button></div>`, card => {
      card.querySelectorAll('[data-mail]').forEach(b => b.onclick = async () => {
        try {
          const r = await api('/api/next/weekly-mail', { on: b.dataset.mail === 'true' });
          if (p) p.mail = r;
          card.querySelectorAll('[data-mail]').forEach(x => x.setAttribute('aria-checked', String(x === b)));
          const v = document.getElementById('meMailV'); if (v) v.textContent = weeklyMailLabel();
          toast(r.on ? '每周日晚上会收到进度邮件' : '不再发每周进度邮件');
        } catch (e) { toast(e.message); }
      });
      const bind = card.querySelector('#wmBind'); if (bind) bind.onclick = () => bindEmailSheet('');
    });
  }
  // The link in the mail (#/weekly-off/<token>): no sign-in needed. It asks once, so a mail scanner opening the link
  // turns nothing off; 「撤销」 takes it back.
  async function weeklyOffView(token) {
    const draw = (off, err) => {
      view.innerHTML = `<div class="stack weekly-off"><div><span class="kicker">每周进度邮件</span><h1 class="h1">${off ? '已退订' : '退订每周进度邮件'}</h1></div>
        <p class="small">${off ? '以后不会再收到每周进度邮件了。想再收，可以点下面的「撤销」，或者在「我的 → 每周进度邮件」里打开。'
          : '每周日晚上 8 点，语流会把你这周的进步发到绑定的邮箱：记住的新词、学完的文章、做题正确率和每周目标。退订后就不再发。'}</p>
        <div class="row">${off ? '<button class="btn" id="offUndo" type="button">撤销，继续收</button><a class="btn primary" href="#/">去学习</a>'
          : '<button class="btn primary" id="offGo" type="button">退订</button><a class="btn ghost" href="#/">不退订，去学习</a>'}</div>
        <p class="err" role="alert">${esc(err || '')}</p></div>`;
      const send = on => async e => {
        e.currentTarget.disabled = true;
        try { await api('/api/next/weekly-mail/off', { token, on }); draw(!on); toast(on ? '会继续收到每周进度邮件' : '已退订'); }
        catch (x) { draw(on, x.message); }
      };
      const go = document.getElementById('offGo'); if (go) go.onclick = send(false);
      const undo = document.getElementById('offUndo'); if (undo) undo.onclick = send(true);
    };
    draw(false);
  }
  /* ---------- study ---------- */
  let selbar = null;
  function hideSelbar() { if (selbar) { selbar.remove(); selbar = null; } }
  const MAT = {}; // the material being studied: step changes reuse it instead of refetching and re-animating the header
  // Under the title: where the text comes from and how AI took part (r20). The writing rules of the originals, or the
  // sources of a news text, are one tap away.
  function originHTML(m, extra = '') {  // extra: 存到手机 (06-offline.js), on the same line so the step below stays in view
    const o = m.origin || { kind: 'original', label: m.source, ai: '', reviewed: null, url: '', references: m.provenance || [] };
    return `<div class="origin tiny"><span class="muted">来源：${o.url ? `<a class="link" href="${esc(o.url)}" target="_blank" rel="noopener noreferrer">${esc(o.label)}</a>` : esc(o.label)}</span>${o.ai ? `<span class="otag">${esc(o.ai)}</span>` : ''}${o.reviewed === false ? '<span class="otag warn">未经人工审核</span>' : ''}${o.kind === 'import' ? '' : `<button class="link tiny" type="button" id="originMore" data-tap="study-origin">${o.references.length ? `${o.kind === 'news' ? '来源' : '参考资料'} ${o.references.length} 条` : '怎么写的'}</button>`}${extra}</div>`;
  }
  function originSheet(m) {
    const o = m.origin, news = o.kind === 'news';
    openSheet(`<div class="stack"><h2 class="h2" id="sheetTitle">这篇材料从哪来</h2>
      ${news ? '<p class="small">今日热点是 AI 联网检索新闻后改写成的学习材料，<b>没有经过人工审核</b>。下面是它检索到的来源，事实以原文为准。</p>'
        : m.featured ? `<p class="small">精选材料由 Flow 编辑部按统一的写作规范原创${o.ai ? `（${esc(o.ai)}）` : ''}：</p>
          <ul class="small origin-rules"><li>不抄、不改写已有的文章、书籍和影视台词；</li><li>只写广为人知、稳定的常识，不写具体的统计数字、年份、价格和研究结论；</li><li>不写在世的真实人物，也不写时事新闻；</li><li>每道理解题的答案都要在原文里找得到依据，发布前由程序逐篇检查。</li></ul>`
        : `<p class="small">这是 Flow 编辑部较早编写的练习材料${o.ai ? `（${esc(o.ai)}）` : ''}。</p>`}
      ${o.references.length ? `<div class="stack-s"><b class="small">${news ? '来源' : '核对事实用的参考资料'}</b>${o.references.map(r => `<a class="link small" href="${esc(r.url)}" target="_blank" rel="noopener noreferrer">${esc(r.title)}</a>`).join('')}</div>` : ''}
      <button class="btn ghost" data-close type="button">知道了</button></div>`);
  }

  async function study(id, step, same) {
    let m = (same || (MAT[id] && Date.now() - (MAT[id]._preloaded || 0) < 6e5)) && MAT[id];
    if (m) delete m._preloaded;
    if (!m) {
      // A copy kept on the phone (one of the last five opened) shows at once; the server's copy replaces it for the
      // next step. Otherwise the request is often already on its way: preloaded from 今日 or when the link was touched.
      // A material kept with 存到手机 (06-offline.js) comes first: only that copy has the answers, to grade without a
      // connection, and the fresher copy from the server keeps them.
      const path = materialPath(id), off = OFF.get(id), kept = off || snapMaterialGet(path);
      if (kept) {
        m = kept; MAT[id] = m;
        api(path).then(f => { if (!f.answers && kept.answers) f.answers = kept.answers; if (MAT[id] === kept) MAT[id] = f; snapMaterial(path, f); if (off) OFF.put(id, f); }).catch(() => {});
      }
      else { m = await api(path); MAT[id] = m; snapMaterial(path, m); }
    }
    const done = new Set(m.steps.concat(load('flow-next-steps-' + id) || []));
    const st = { step: STEPS.includes(step) ? step : 'listen', showOriginal: !!m._showOriginal, blind: false };
    const lines = () => st.showOriginal && m.original ? m.original : m.sentences;

    function markStep(s) {
      if (done.has(s)) return;
      done.add(s); save('flow-next-steps-' + id, Array.from(done));
      // without a connection the step waits in the outbox and is sent when the phone is back online
      if (S.user) api('/api/next/progress', { pack: id, step: s }).catch(e => { if (e.network) OUTBOX.push({ path: '/api/next/progress', body: { pack: id, step: s } }); });
      const tab = view.querySelector(`[data-step="${s}"]`); if (tab && !tab.querySelector('.ok')) tab.insertAdjacentHTML('beforeend', '<span class="ok">✓</span>');
    }
    function go(s) { location.hash = `#/m/${encodeURIComponent(id)}/${s}`; }

    if (!same) {
      // 存到手机 sits at the right of the kicker line, so the source line under the title stays one line on a phone
      view.innerHTML = `<div class="study-head"><div class="sh-top"><span class="kicker">${m.series ? `<a class="link" href="#/series/${encodeURIComponent(m.series.id)}">连载《${esc(m.series.title)}》第 ${m.series.part} / ${m.series.of} 集</a> · ${m.level}` : `${esc(m.theme_label)} · ${m.level}${m.variant ? ' → ' + m.variant.level : ''}${m.featured ? ' · 精选' : ''}`}</span>${offChip(id)}</div>
        <h1 class="h1">${esc(m.title)}</h1>${m.title_en ? `<div class="title-en">${esc(m.title_en)}</div>` : ''}
        ${originHTML(m)}</div>
        <div class="steps" role="tablist"><span class="ind" aria-hidden="true"></span>${STEPS.map(s => `<button role="tab" data-step="${s}" aria-selected="false">${STEP[s]}${done.has(s) ? '<span class="ok">✓</span>' : ''}</button>`).join('')}</div>
        <section id="pane"></section>`;
      view.querySelectorAll('[data-step]').forEach(b => b.onclick = () => go(b.dataset.step));
      const om = view.querySelector('#originMore'); if (om) om.onclick = () => originSheet(m);
    }
    // Slide the tab indicator, and slide the pane in from the direction of travel.
    const tabs = [...view.querySelectorAll('[data-step]')];
    const prev = tabs.findIndex(b => b.getAttribute('aria-selected') === 'true');
    tabs.forEach(b => b.setAttribute('aria-selected', String(b.dataset.step === st.step)));
    const head = view.querySelector('.study-head'); if (head) head.dataset.at = st.step;
    bindOffChip(id);  // phones: a shorter header once past listen and read
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
    const LOOP = Object.assign({ rep: 1, gap: 0 }, load('flow-next-loop') || {});  // 复读, kept on the phone
    // 复听 (relisten_service), from 今日: the text hidden at first; after a listen, how much was understood, then the text.
    const RELISTEN = [[3, '几乎都懂'], [2, '大部分'], [1, '一半左右'], [0, '很少']];
    function relistenHTML() {
      return st.relistened ? `<div class="card sunk stack-s relisten" id="relisten" aria-live="polite"><b>${esc(st.relistened)}</b><span class="small muted">原文出来了：没听懂的句子，点句子前面的喇叭单独再听几遍。</span></div>`
        : `<div class="card sunk stack-s relisten" id="relisten"><b>复听：先不看原文，从头听一遍</b>
          <span class="small">点「播放全文」。听完选一下听懂了多少，原文就会出来，再看没听懂的句子。</span>
          <div class="chips" role="group" aria-label="听懂了多少">${RELISTEN.map(([k, l]) => `<button class="chip" type="button" data-und="${k}">${l}</button>`).join('')}</div></div>`;
    }
    function bindRelisten() {
      const showText = () => {
        st.blind = false; pane.querySelectorAll('.line .txt').forEach(t => t.classList.remove('blind'));
        const bl = pane.querySelector('#blind'); if (bl) { bl.classList.remove('on'); bl.setAttribute('aria-pressed', 'false'); }
        const box = pane.querySelector('#relisten'); if (box) box.outerHTML = relistenHTML();
      };
      pane.querySelectorAll('[data-und]').forEach(b => b.onclick = async () => {
        const body = { pack: id, understood: Number(b.dataset.und) }, label = b.textContent;
        pane.querySelectorAll('[data-und]').forEach(x => { x.disabled = true; });
        try {
          const r = await api('/api/next/relisten', body);
          st.relistened = `记下了：听懂了${r.label}。` + (r.known ? '这篇已经听熟了，以后不再安排复听。' : `${r.next_days} 天后再听一次。`);
        } catch (e) {
          if (!e.network) { toast(e.message); pane.querySelectorAll('[data-und]').forEach(x => { x.disabled = false; }); return; }
          OUTBOX.push({ path: '/api/next/relisten', body });  // without a connection: sent when the phone is back online
          st.relistened = `记下了：听懂了${label}，联网后同步。`;
        }
        showText();
      });
    }
    async function listen() {
      const again = parts()[3] === 'again' && !!S.user;
      if (again && !st.againSet) { st.againSet = true; st.mode = 'listen'; st.blind = true; }
      if (st.mode === 'shadow') return shadowMode();
      if (st.mode === 'dictate') return dictateMode();
      const ls = lines();
      const nm = await narration(ls);
      const voices = (m.audio && m.audio.voices) || [];
      // One line says how it will play (语速 · 复读 · 停顿); the choices open under it, so the first sentences stay on the
      // first screen of a phone. Open or closed is remembered.
      const rateL = r => `${r}×`, repL = n => (n === 0 ? '单句循环' : `每句 ${n} 遍`), gapL = n => (n === 0 ? '句后不停' : n === -1 ? '留时间跟说' : `句后停 ${n} 秒`);
      const psum = () => `${rateL(TTS.rate)} · ${repL(LOOP.rep)} · ${gapL(LOOP.gap)}`;
      pane.innerHTML = `${again ? relistenHTML() : ''}${modeTabs()}<div class="player">
          <button class="btn primary" id="playAll">${ICON.play.replace('<svg', '<svg width="18" height="18" fill="currentColor"')}<span>播放全文</span></button>
          <button class="icon-btn ${st.blind ? 'on' : ''}" id="blind" aria-pressed="${st.blind}" title="盲听：先只听不看" aria-label="盲听">${ICON.eye}</button>
        </div>
        <details class="playset" ${load('flow-next-playset') ? 'open' : ''}><summary data-tap="listen-settings"><span class="tiny muted" id="psum">${psum()}</span><span class="tiny link">播放设置</span></summary>
          <div class="loopbar"><div class="lg" role="group" aria-label="语速"><span class="tiny muted">语速</span>${[0.75, 1, 1.25].map(r => `<button class="chip small" data-rate="${r}" aria-pressed="${TTS.rate === r}">${r}×</button>`).join('')}</div>
            <div class="lg" role="group" aria-label="复读：每句几遍"><span class="tiny muted">每句</span>${[[1, '1 遍'], [3, '3 遍'], [5, '5 遍'], [0, '循环']].map(([n, l]) => `<button class="chip small" data-rep="${n}" aria-pressed="${LOOP.rep === n}">${l}</button>`).join('')}</div>
            <div class="lg" role="group" aria-label="复读：句后停顿"><span class="tiny muted">句后</span>${[[0, '不停'], [2, '停 2 秒'], [-1, '留时间跟说']].map(([n, l]) => `<button class="chip small" data-gap="${n}" aria-pressed="${LOOP.gap === n}">${l}</button>`).join('')}</div>
            ${voices.length ? `<div class="lg"><span class="tiny muted">声音</span>${voiceChips(voices)}</div>` : ''}</div></details>
        ${prereadHTML()}
        ${!nm && !TTS.ok ? '<p class="err">这个浏览器不支持朗读，可以直接去「读」。</p>' : ''}
        <p class="muted tiny listen-tip">${nm ? '' : '这篇还没有真人录音，先用浏览器朗读。'}点 👁 只听不看，点句子前的喇叭单句反复听${TOUCH ? '' : '；空格键播放 / 停止'}。</p>
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
      const stopAll = () => { loopTok++; clearTimeout(loopTimer); TTS.stop(); NAR.stop(); playing = -1; shown = -1; setNow(-1); setBtn(false); MINI.hide(); };
      // 复读: a sentence said LOOP.rep times (0: until stopped), with a pause after it: none, 2 s, or as long as the
      // sentence itself and a little more, to say it back.
      let loopTok = 0, loopTimer = 0;
      const gapMs = i => (LOOP.gap === -1 ? Math.max(1500, nm ? (nm.sentences[i].e - nm.sentences[i].s) * 1300 : ls[i].split(' ').length * 450) : LOOP.gap * 1000);
      const sayRepeated = (i, then, n = 0) => {
        const tok = loopTok;
        sayLine(i, () => {
          if (tok !== loopTok) return;
          const more = LOOP.rep === 0 || n + 1 < LOOP.rep, next = () => { if (tok === loopTok) { if (more) sayRepeated(i, then, n + 1); else if (then) then(); } };
          const g = more || then ? gapMs(i) : 0;
          if (g) loopTimer = setTimeout(next, g); else next();
        });
      };
      const looping = () => LOOP.rep !== 1 || LOOP.gap !== 0;
      const sayLine = (i, then) => {
        if (nm) { shown = -1; NAR.play(nm.sentences[i].s, nm.sentences[i].e, follow, then); return; }
        const el = lineEl(i); TTS.say(ls[i], then, c => lightWord(el, c));
      };
      const playFrom = i => {
        if (i >= ls.length) { stopAll(); markStep('listen'); return; }
        playing = i; setNow(i); MINI.update(`第 ${i + 1} / ${ls.length} 句`);
        const el = lineEl(i); if (el) el.scrollIntoView({ block: 'center', behavior: REDUCED ? 'auto' : 'smooth' });
        sayRepeated(i, () => playFrom(i + 1));
      };
      pane.querySelector('#playAll').onclick = () => {
        if (playing >= 0) return stopAll();
        setBtn(true); MINI.show('正在播放全文', stopAll);
        // one sentence after another (each said again, and pauses, when 复读 is set); otherwise the narration straight through
        if (nm && !looping()) { playing = 0; shown = -1; NAR.play(nm.sentences[0].s, null, follow, () => { stopAll(); markStep('listen'); }); }
        else playFrom(0);
      };
      pane.querySelectorAll('[data-say]').forEach(b => b.onclick = () => {
        const i = Number(b.dataset.say); stopAll(); setNow(i);
        if (looping()) MINI.show(`复读第 ${i + 1} 句`, stopAll);  // a stop button on screen while it repeats
        sayRepeated(i, () => { setNow(-1); MINI.hide(); });
      });
      pane.querySelectorAll('[data-rep], [data-gap]').forEach(b => b.onclick = () => {
        const k = 'rep' in b.dataset ? 'rep' : 'gap'; LOOP[k] = Number(b.dataset[k]); save('flow-next-loop', LOOP);
        pane.querySelectorAll(`[data-${k}]`).forEach(x => x.setAttribute('aria-pressed', String(x === b)));
        pane.querySelector('#psum').textContent = psum();
      });
      pane.querySelector('.playset').ontoggle = e => save('flow-next-playset', e.currentTarget.open);
      pane.querySelectorAll('.line .txt').forEach((t, i) => t.onclick = e => { if (e.target.dataset.w && !st.blind) lookupSheet(e.target.dataset.w, ls[i], id); });
      pane.querySelectorAll('[data-rate]').forEach(b => b.onclick = () => { TTS.rate = Number(b.dataset.rate); save('flow-next-rate', TTS.rate); NAR.audio.playbackRate = TTS.rate; pane.querySelectorAll('[data-rate]').forEach(x => x.setAttribute('aria-pressed', String(x === b))); pane.querySelector('#psum').textContent = psum(); });
      pane.querySelectorAll('[data-voice]').forEach(b => b.onclick = async () => { if (b.disabled) return; stopAll(); await setVoice(b.dataset.voice); listen(); toast('已切换为' + VOICE_LABELS[b.dataset.voice]); });
      pane.querySelector('#blind').onclick = e => { st.blind = !st.blind; toast(st.blind ? '盲听：只听不看，再点一次显示原文' : '已显示原文'); e.currentTarget.classList.toggle('on', st.blind); e.currentTarget.setAttribute('aria-pressed', String(st.blind)); pane.querySelectorAll('.txt').forEach(t => t.classList.toggle('blind', st.blind)); };
      pane.querySelector('#toRead').onclick = () => { stopAll(); markStep('listen'); go('read'); };
      if (again) bindRelisten();
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
    // The words worth knowing before listening, folded into one line (open it for the meaning, the sound, review).
    function prereadHTML() {
      const pr = m._prHidden ? [] : (m.preread || []);
      return pr.length ? `<details class="card sunk fold preread"><summary data-tap="listen-preread"><b class="small">读前先认识这 ${pr.length} 个词</b><span class="tiny muted">${pr.map(w => esc(w.word)).join(' · ')}</span></summary>
          <div class="stack-s"><div class="pr-list">${pr.map((w, k) => `<div class="pr"><button class="icon-btn" data-prsay="${k}" aria-label="朗读 ${esc(w.word)}">${ICON.speak}</button>
            <div><b>${esc(w.word)}</b> <span class="ph">${esc(w.phonetic)}</span><div class="tiny muted">${esc(w.meaning)}</div></div></div>`).join('')}</div>
          <div class="row"><button class="btn small primary" id="prAdd">全部加入复习</button><span class="muted tiny">加入后会在文章里标出来</span></div></div></details>` : '';
    }
    function modeTabs() {
      return `<div class="seg modes" role="tablist" aria-label="听的方式">${Object.entries(MODES).map(([k, l]) => `<button role="tab" data-mode="${k}" aria-selected="${st.mode === k}">${l}</button>`).join('')}</div>`;
    }
    function listenHead() { return modeTabs() + prereadHTML(); }
    function bindListenHead(stop) {
      pane.querySelectorAll('[data-mode]').forEach(b => b.onclick = () => { stop(); st.mode = b.dataset.mode; save('flow-next-listen-mode', st.mode); listen(); });
      const pr = m.preread || [];
      pane.querySelectorAll('[data-prsay]').forEach(b => b.onclick = () => { stop(); const w = pr[Number(b.dataset.prsay)]; CLIP.word({ text: w.word, audio: w.audio }); });
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
      // Every sentence keeps its ▶; the recording tools (●, 对比, AI 点评) show under the sentence being practised only,
      // so eleven rows of four buttons do not bury the text. A tap anywhere on a sentence makes it the one.
      pane.innerHTML = `${listenHead()}<p class="muted small">点一句开始练：先点 ▶ 听原声，再点 ● 跟着读一遍（再点一次停止）。「对比」先放原声再放你的录音；${S.user ? '「AI 点评」会写出它听到的内容，并指出要改的地方。' : '登录后可以让 AI 点评。'}</p>
        <div class="lines">${ls.map((s, i) => `<div class="line sh${i === 0 ? ' cur' : ''}" data-i="${i}"><div class="txt">${esc(s)}</div>
          <div class="sh-ctl"><button class="icon-btn" data-o="${i}" aria-label="听原声">${ICON.play.replace('<svg', '<svg fill="currentColor"')}</button>
            <button class="icon-btn rec" data-r="${i}" aria-label="录音"><span class="dot"></span></button>
            <button class="btn small" data-c="${i}" disabled>对比</button><button class="btn small" data-ai="${i}" disabled>✦ AI 点评</button></div>
          <div class="sh-out"></div></div>`).join('')}</div>
        <div class="section row between"><span></span><button class="btn" id="toRead">去读 →</button></div>`;
      const REC = { mr: null, blobs: {}, timer: 0, url: {} };
      const row = i => pane.querySelector(`.line[data-i="${i}"]`);
      pane.querySelectorAll('.line.sh').forEach(l => l.addEventListener('click', () => {
        if (l.classList.contains('cur')) return;
        pane.querySelectorAll('.line.sh.cur').forEach(x => x.classList.remove('cur')); l.classList.add('cur');
      }, true));  // capture: a tap on ▶ of another sentence plays it and makes it the one
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
    function newWordItems() {
      const looked = [...((m._looked && m._looked.values()) || [])];
      const mine = new Set((m.mine || []).map(x => x.form));
      const items = looked.filter(x => !mine.has(x.word)).map(x => ({ ...x, on: true }));
      (m.preread || []).forEach(w => { if (!items.some(x => x.word === w.word) && !mine.has(w.form)) items.push({ word: w.word, meaning: w.meaning, sentence: findContext(w.form, lines()), on: false }); });
      return items.slice(0, 14);
    }
    function newWordsHTML() {
      const items = newWordItems();
      if (!items.length) return '<p class="muted small">读的时候点过的词会出现在这里，勾选后按遗忘曲线复习。</p>';
      return `<div class="stack-s" id="newWords"><div class="row between"><b class="small">这篇的生词</b><span class="muted tiny">勾选的会按遗忘曲线复习</span></div>
        <div class="nw-list">${items.map((x, k) => `<label class="nw"><input type="checkbox" data-nw="${k}" ${x.on ? 'checked' : ''}><b>${esc(x.word)}</b><span class="muted tiny">${esc(x.meaning || '')}</span></label>`).join('')}</div>
        <div><button class="btn small primary" id="nwAdd">加入复习</button></div></div>`;
    }
    function bindNewWords() {
      const box = pane.querySelector('#newWords'); if (!box) return;
      const items = newWordItems();
      box.querySelector('#nwAdd').onclick = async e => {
        if (!S.user) return needLogin('登录后可以把这些词加入复习。');
        const pick = [...box.querySelectorAll('[data-nw]:checked')].map(c => items[Number(c.dataset.nw)]).filter(Boolean);
        if (!pick.length) { toast('先勾选要复习的词'); return; }
        const btn = e.currentTarget; btn.disabled = true;
        try {
          const r = await api('/api/next/vocab/add', { pack: id, items: pick.map(x => ({ word: x.word, sentence: x.sentence || '' })) });
          toast(r.added ? `已加入 ${r.added} 个词` : '这些词已经在复习里了'); refreshHome().catch(() => {});
          m.mine = (m.mine || []).concat(pick.map(x => ({ form: x.word.toLowerCase(), id: 0 }))); m._looked = new Map();
          if (m._onLook) m._onLook();
        } catch (x) { toast(x.message); btn.disabled = false; }
      };
    }
    // What this text leaves you with, in one folded card under the text: expressions, words (the ones looked up
    // too, to put into review) and grammar points, one tab at a time. Open or closed and the tab are remembered.
    function gainsTabs() {
      const vocab = m.vocabulary.length + (m.variant ? m.variant.notes.length : 0), fresh = newWordItems().filter(x => x.on).length;
      return [
        m.expressions.length && ['expr', '表达', m.expressions.length, () => `<p class="muted tiny">能直接搬进你自己话里的搭配。</p><div class="stack-s">${m.expressions.map((x, i) => `<div class="expr"><span class="e">${esc(x.text)}</span><span class="row"><button class="icon-btn" data-sayx="${i}" aria-label="朗读">${ICON.speak}</button><button class="icon-btn" data-sx="${i}" aria-label="收藏 ${esc(x.text)}">${ICON.star}</button></span><span class="m">${esc(x.meaning)}</span><span class="n">${esc(x.note || '')}</span></div>`).join('')}</div>`],
        ['words', '词汇', vocab + fresh, () => `${m.vocabulary.length ? `<div class="vocab-list">${m.vocabulary.map((v, i) => `<div class="vrow"><span class="term">${esc(v.term)}</span><button class="icon-btn" data-sv="${i}" aria-label="收藏 ${esc(v.term)}">${ICON.star}</button><span class="muted small">${esc(v.meaning)}</span><span class="vex">${esc(v.example || '')}</span></div>`).join('')}</div>` : ''}
          ${(m.variant && m.variant.notes.length) ? `<b class="small">改写版新出现的表达</b><div class="vocab-list">${m.variant.notes.map((v, i) => `<div class="vrow"><span class="term">${esc(v.text)}</span><button class="icon-btn" data-sn="${i}" aria-label="收藏">${ICON.star}</button><span class="muted small">${esc(v.meaning)}</span></div>`).join('')}</div>` : ''}
          <div id="nwSlot">${newWordsHTML()}</div>`],
        m.notes.length && ['notes', '知识点', m.notes.length, () => `<div class="stack-s">${m.notes.map(n => `<div class="knote"><div class="row between">${nodeChip({ id: n.node, title: n.title, status: n.status })}<span class="tiny muted">${esc(n.label)}</span></div><q>${esc(n.quote)}</q><div class="small muted">${esc(n.explanation)}</div></div>`).join('')}
          <a class="link small" href="#/graph">在知识图谱里看 →</a></div>`]].filter(Boolean);
    }
    function gainsSummary() {
      const vocab = m.vocabulary.length + (m.variant ? m.variant.notes.length : 0), fresh = newWordItems().filter(x => x.on).length;
      return [m.expressions.length && `${m.expressions.length} 个表达`, vocab && `${vocab} 个词`, m.notes.length && `${m.notes.length} 个知识点`, fresh && `查过 ${fresh} 个词，可以加入复习`].filter(Boolean).join(' · ') || '查过的词会收在这里';
    }
    function gainsHTML() {
      const tabs = gainsTabs();
      let open = false, cur = tabs[0][0];
      try { open = localStorage.getItem('flow-gains-open') === '1'; const t = localStorage.getItem('flow-gains-tab'); if (tabs.some(x => x[0] === t)) cur = t; } catch (e) { /* private mode */ }
      return `<details class="card flat fold gains section" id="gains"${open ? ' open' : ''}><summary data-tap="read-gains"><b>这篇的收获</b><span class="tiny muted" id="gainsSum">${gainsSummary()}</span></summary>
        <div class="seg gtabs" role="tablist" aria-label="这篇的收获">${tabs.map(([k, l, n]) => `<button role="tab" type="button" data-gt="${k}" aria-selected="${k === cur}">${l} ${n}</button>`).join('')}</div>
        ${tabs.map(([k, , , html]) => `<div class="gpane stack-s" data-gp="${k}" role="tabpanel"${k === cur ? '' : ' hidden'}>${html()}</div>`).join('')}</details>`;
    }
    function bindGains() {
      const g = pane.querySelector('#gains'); if (!g) return;
      g.addEventListener('toggle', () => { try { localStorage.setItem('flow-gains-open', g.open ? '1' : ''); } catch (e) { /* private mode */ } });
      g.querySelectorAll('[data-gt]').forEach(b => b.onclick = () => {
        g.querySelectorAll('[data-gt]').forEach(x => x.setAttribute('aria-selected', String(x === b)));
        g.querySelectorAll('[data-gp]').forEach(p => { p.hidden = p.dataset.gp !== b.dataset.gt; });
        try { localStorage.setItem('flow-gains-tab', b.dataset.gt); } catch (e) { /* private mode */ }
      });
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
      // One row of tools (中文导读, 改写成我的难度, 伴读) and one line of colour key and hints, so the text starts on the
      // first screen of a phone; the summary opens under the row.
      const variantBar = m.variant ? `<div class="seg" role="tablist"><button data-ver="v" aria-selected="${!st.showOriginal}">适合我的版本（${m.variant.level} · AI 改写）</button><button data-ver="o" aria-selected="${st.showOriginal}">原文（${m.original_level}）</button><span></span></div>` : '';
      pane.innerHTML = `<div class="read-tools">${m.summary_zh ? '<button class="chip small" id="zhGuide" type="button" aria-expanded="false" aria-controls="zhText">中文导读</button>' : ''}
          ${m.can_variant ? `<button class="chip small" id="mkVar" type="button" title="这篇原文是 ${m.original_level}，你选的是 ${m.user_level}">改写成 ${m.user_level} 难度</button>` : ''}
          <button class="btn small" id="readAlong" title="边听录音边看文字，读到哪句亮哪句">${playIcon(false, 14)}<span>伴读</span></button></div>
        ${m.summary_zh ? `<p class="guide-zh small" id="zhText" hidden>${esc(m.summary_zh)}</p>` : ''}${variantBar}
        <div class="read-hint tiny muted"><div class="legend"><span>本篇词汇</span><span class="h">可能超出你的水平</span>${(m.mine || []).length ? '<span class="m">你在背的词</span>' : ''}</div>
          <span>点词查词，点句尾 ✦ 讲解整句，${TOUCH ? '长按拖选' : '选中'}可收藏${TOUCH ? '' : '；键盘：Tab 进入正文后 ← → 逐词，↵ 查词，E 讲解'}</span></div>
        <div class="text" id="reader" tabindex="0" aria-label="正文：左右方向键逐词移动，回车查词">${ls.map((s, i) => sentenceHTML(s, i)).join('')}</div>
        <div class="section row between"><span></span><button class="btn primary" id="toCheck">读完了，做理解题 →</button></div>
        ${gainsHTML()}`;
      const reader = pane.querySelector('#reader');
      // The narration's timings are fetched now, so a tap on 伴读 can start the sound inside the tap (in-app browsers
      // such as WeChat's refuse sound that starts after a download).
      let nmNow = null; narration(ls).then(x => { nmNow = x; }).catch(() => {});
      pane.querySelectorAll('[data-ver]').forEach(b => b.onclick = () => { st.showOriginal = b.dataset.ver === 'o'; m._showOriginal = st.showOriginal; read(); });
      const zg = pane.querySelector('#zhGuide');
      if (zg) zg.onclick = () => { const t = pane.querySelector('#zhText'), open = t.hidden; t.hidden = !open; zg.setAttribute('aria-expanded', String(open)); };
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
        const nm = nmNow || await narration(ls);
        if (along) { if (nm) alongAudio(nm); else alongFrom(0); }
      };
      // An expression is read by the browser voice; where there is none (WeChat on Android), its sentence from the narration.
      pane.querySelectorAll('[data-sayx]').forEach(b => b.onclick = () => {
        const x = m.expressions[Number(b.dataset.sayx)], k = ls.findIndex(s => s.toLowerCase().includes(x.text.toLowerCase()));
        if (!TTS.ok && nmNow && k >= 0) NAR.play(nmNow.sentences[k].s, nmNow.sentences[k].e, null, null); else TTS.say(x.text);
      });
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
      bindGains(); bindNewWords();
      m._onLook = () => {
        const slot = pane.querySelector('#nwSlot'); if (!slot) return;
        slot.innerHTML = newWordsHTML(); bindNewWords();
        const sum = pane.querySelector('#gainsSum'); if (sum) sum.textContent = gainsSummary();
        const n = (gainsTabs().find(x => x[0] === 'words') || [])[2], t = pane.querySelector('[data-gt="words"]'); if (t) t.textContent = '词汇 ' + n;
      };
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
        ${q.options.map((o, j) => `<button class="ans" data-q="${i}" data-o="${j}"><span class="k">${'ABCD'[j]}</span><span>${esc(o)}</span></button>`).join('')}<div class="fb" aria-live="polite"></div></div>`).join('')}
        <div id="score"></div></div>`;
      pane.querySelectorAll('.ans').forEach(b => b.onclick = async () => {
        const i = Number(b.dataset.q), j = Number(b.dataset.o);
        if (answered[i] != null) return;
        answered[i] = j;
        const box = pane.querySelector(`.q[data-q="${i}"]`);
        box.querySelectorAll('.ans').forEach(x => x.disabled = true);
        try {
          let r;
          try { r = await api('/api/next/check', { pack: id, index: i, choice: j }); }
          catch (e) {
            // Without a connection, a material kept on the phone is graded there with its own answers; the answer is
            // sent when the phone is back online (mistake book, progress).
            const a = e.network && m.answers && m.answers[i]; if (!a) throw e;
            r = { correct: j === a.answer, answer: a.answer, evidence: a.evidence };
            if (S.user) OUTBOX.push({ path: '/api/next/check', body: { pack: id, index: i, choice: j } });
          }
          answered[i] = r.correct;
          box.querySelector(`[data-o="${r.answer}"]`).classList.add('right');
          if (!r.correct) b.classList.add('wrong');
          box.querySelector('.fb').innerHTML = `<p class="small"><b>${r.correct ? '答对了。' : '答案在原文这里：'}</b></p>${r.evidence ? `<div class="evidence">${esc(r.evidence)}</div>` : ''}`;
          if (Object.keys(answered).length === m.questions.length) {
            const right = Object.values(answered).filter(Boolean).length;
            markStep('check');
            pane.querySelector('#score').innerHTML = `<div class="card sunk row between enter"><span><b>${right} / ${m.questions.length}</b> 题答对</span><button class="btn primary" id="toOut">去用出来 →</button></div>
              ${(m.expressions || []).length ? '<div class="row"><button class="link small" id="shareX" type="button" data-tap="share-material">把学会的一句做成卡片，分享或保存</button></div>' : ''}`;
            const sx = pane.querySelector('#shareX'); if (sx) sx.onclick = () => shareFromMaterial(m);
            pane.querySelector('#toOut').onclick = () => go('output');
            // After a first article tried without any questions: offer the level questions (and an account) next.
            if (!S.user && !hasProfile()) pane.querySelector('#score').insertAdjacentHTML('beforeend', `<div class="card stack-s enter try-next"><b>觉得有用？按你的水平每天推荐一篇</b>
              <span class="small muted">回答 4 个问题，大约 1 分钟；注册以后，进度和收藏会保存下来。</span>
              <div class="row"><a class="btn primary" href="#/welcome" data-tap="trial-level">回答 4 个问题</a><button class="btn" id="trialReg" type="button">注册 / 登录</button></div></div>`);
            const tr = pane.querySelector('#trialReg'); if (tr) tr.onclick = () => openLogin();
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
      pane.innerHTML = `${outTabs('retell')}<div class="card flat task stack-s"><b>不看原文，用自己的话把这篇讲一遍</b>
          <span class="muted small">可以打字，也可以点 ● 直接说（最长 2 分钟）。AI 会提炼原文要点，看你讲到了哪些，并改出最影响理解的错误。</span></div>
        <textarea id="rtText" aria-label="用英文复述这篇" rows="6" maxlength="2500" lang="en" data-submit="#rtGo" placeholder="In this article, ..."></textarea>
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
          markStep('output'); showFinish(pane, m, id); blob = null; state.textContent = '打字或录音都行';
        } catch (x) { toast(x.message); }
        btn.disabled = false; btn.textContent = 'AI 看看我的复述';
      };
    }

    function dialogMode() {
      const hist = [];
      pane.innerHTML = `${outTabs('dialog')}<div class="card flat task stack-s"><b>${esc(m.speaking_task || '围绕这篇的话题和 AI 聊几句')}</b>
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
        showFinish(pane, m, id); bringIntoView(pane.querySelector('#dlgOut'));
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
          <textarea id="trIn" aria-label="你的译文" rows="3" maxlength="800" lang="${dir === 'zh2en' ? 'en' : 'zh'}" data-submit="#trGo" placeholder="${dir === 'zh2en' ? '译成英文…' : '译成中文…'}"></textarea>
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
            markStep('output'); showFinish(pane, m, id); bringIntoView(pane.querySelector('#trOut'));
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
      pane.innerHTML = `${outTabs('essay')}<div class="card flat task stack-s"><div class="kicker">建议 ${range[0]}–${range[1]} 词</div><b>${esc(m.writing_task || '围绕这篇的话题，写一段你自己的看法或经历。')}</b>
          <span class="muted small">按内容、结构、准确、丰富四个维度批改，给段落点评和示范段落；改出来的错误进错题本。</span></div>
        <textarea id="esIn" aria-label="你的英文作文" rows="10" maxlength="3000" lang="en" data-submit="#esGo" placeholder="Write here…">${esc(load(key) || '')}</textarea>
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
          markStep('output'); showFinish(pane, m, id); bringIntoView(pane.querySelector('#esOut'));
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
      pane.innerHTML = `${outTabs('model')}<div class="stack"><div class="card flat task"><b>${esc(m.task.prompt)}</b>
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
        </div>`;
      box.querySelectorAll('[data-say-text]').forEach(b => b.onclick = () => TTS.say(b.dataset.sayText));
      showFinish(pane, m, id, remaining);  // 这篇完成了, with what this text gave (25-finish.js)
      box.querySelectorAll('[data-keep-v]').forEach(b => b.onclick = () => { const v = r.versions[Number(b.dataset.keepV)]; saveCard({ text: v.text, meaning: v.label + '：' + v.why, context: '', pack: id }, b); });
      const k = box.querySelector('#keep'); if (k) k.onclick = () => saveCard({ text: r.keep.text, meaning: r.keep.meaning, context: r.corrected, pack: id }, k);
      box.scrollIntoView({ behavior: REDUCED ? 'auto' : 'smooth', block: 'start' });
    }
    ({ listen, read, check, output })[st.step]();
  }
  /* ---------- 这篇完成了 (r27): after 用出来, three lines on what this text gave the learner ---------- */
  // The expressions and words saved from this text, and one grammar point to work on (progress_service.text_summary):
  // one the AI corrected in what was written for it, else one of its points that needs attention or has not been
  // checked with questions yet. Each line goes where that work continues. Shown after any of the five ways of 用出来,
  // once at the end of the step (a second answer draws it again with what has changed). The share card stays.
  function finishCard(m, id, remaining) {
    const share = (m.expressions || []).length ? '<button class="link small" id="shareDone" type="button" data-tap="share-material">把学会的一句做成卡片</button>' : '';
    const next = m.series && m.series.next ? `<a class="btn" href="#/">回到今日</a><a class="btn primary" href="#/m/${encodeURIComponent(m.series.next)}">下一集：第 ${m.series.part + 1} 集</a>`
      : '<a class="btn" href="#/graph">看知识图谱</a><a class="btn primary" href="#/">回到今日</a>';
    return `<div class="card done-card fin enter" id="finCard">${doneRing}<h2 class="h2">这篇完成了</h2>
      ${S.user ? '<div class="fin-sum" id="finSum" aria-live="polite" aria-busy="true"><span class="fin-wait"><span class="spin"></span> 正在整理这篇学到的…</span></div>' : ''}
      ${share}<p class="muted tiny">${remaining != null ? '今天还可以用 AI ' + remaining + ' 次。' : ''}收藏的表达和生词会按遗忘曲线安排复习。</p>
      <div class="row center">${next}</div></div>`;
  }
  function finishLines(s, id) {
    const row = (k, text, href, tap) => href ? `<a class="fin-row" href="${href}" data-tap="${tap}"><span class="k">${k}</span><span class="t">${text}</span><span class="go" aria-hidden="true">›</span></a>`
      : `<div class="fin-row"><span class="k">${k}</span><span class="t">${text}</span></div>`;
    const list = xs => xs.slice(0, 2).map(x => `<b lang="en">${esc(x.text || x)}</b>`).join('、');
    const e = s.expressions, w = s.words, g = s.grammar;
    const expr = e.count ? row('表达', `收藏了 ${e.count} 个：${list(e.saved)}${e.count > 2 ? ' 等' : ''}`, '#/cards/phrase', 'finish-expr')
      : e.key.length ? row('表达', `还没收藏。这篇的重点：${list(e.key)}`, `#/m/${encodeURIComponent(id)}/read`, 'finish-expr') : row('表达', '这篇没有收藏表达');
    const words = w.count ? row('新词', `收藏了 ${w.count} 个：${list(w.saved)}${w.count > 2 ? ' 等' : ''}，明天开始复习`, '#/cards/word', 'finish-words')
      : w.mine.length ? row('新词', `没有收藏生词；这篇里有你在背的 ${w.mine.length} 个：${list(w.mine)}${w.mine.length > 2 ? ' 等' : ''}`, '#/cards/word', 'finish-words')
      : row('新词', '这篇没有收藏生词');
    const node = g && g.id ? `#/graph/${encodeURIComponent(g.id)}` : '';
    const gram = !g ? row('语法', '这篇没有标出语法点')
      : g.all_solid ? row('语法', `这篇的 ${g.count} 个语法点都做题验证过了 ✓`)
      : g.why === 'flag' ? row('语法', `「${esc(g.title)}」写错了 ${g.times} 次${g.change ? `（<span lang="en">${esc(g.change)}</span>）` : ''}，做 4 题巩固`, node, 'finish-grammar')
      : g.why === 'watch' ? row('语法', `「${esc(g.title)}」需要留意，做 4 题巩固`, node, 'finish-grammar')
      : row('语法', `这篇用到了「${esc(g.title)}」，做 4 题验证一下`, node, 'finish-grammar');
    return expr + words + gram;
  }
  // The finish card at the end of the step's pane (one; drawn again after another answer), then its three lines.
  async function showFinish(pane, m, id, remaining) {
    let slot = pane.querySelector('#finSlot');
    if (!slot) { slot = document.createElement('div'); slot.id = 'finSlot'; slot.className = 'section'; pane.appendChild(slot); }
    slot.innerHTML = finishCard(m, id, remaining);
    const sd = slot.querySelector('#shareDone'); if (sd) sd.onclick = () => shareFromMaterial(m);
    const box = slot.querySelector('#finSum'); if (!box) return;
    try {
      const s = await api('/api/next/text-summary?pack=' + encodeURIComponent(id));
      if (box.isConnected) { box.innerHTML = finishLines(s, id); box.removeAttribute('aria-busy'); }
    } catch (e) { box.remove(); }
  }
  function splitSentences(body) { return body.split(/(?<=[.!?]["”’]?)\s+/).map(s => s.trim()).filter(Boolean); }
  function findContext(term, ls) { const t = term.toLowerCase(); return ls.find(s => s.toLowerCase().includes(t)) || ''; }

  async function lookupSheet(word, sentence, pack, mine) {
    if (mine && S.user) api('/api/next/vocab/met', { word }).then(r => { if (r.card && r.card.moved) toast('这个词在你的复习里，查了说明还不熟，已提前安排复习'); }).catch(() => {});
    openSheet(`<p class="loading"><span class="spin"></span></p>`);
    let e = null;
    try { e = (await api('/api/next/lookup?w=' + encodeURIComponent(word))).entry; } catch (x) { /* show fallback */ }
    const meaning = e ? e.meaning : '';
    // The recorded pronunciation when there is one (it plays in every browser, WeChat's too); else the browser voice.
    const sayWord = () => (e && e.audio && (e.audio.us || e.audio.uk) ? CLIP.word({ text: e.word, audio: e.audio }) : TTS.say(e ? e.word : word));
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
      ${e && e.confusable && e.confusable.length ? e.confusable.map(g => `<div class="cf-hint"><div><span class="pill amber">容易混</span> <b class="en">${esc(g.words.join(' / '))}</b></div>
        <div class="tiny muted">${esc(g.how)}</div><a class="link small" href="#/words/confuse/${encodeURIComponent(g.id)}" data-close>辨析练习 →</a></div>`).join('') : ''}
      <div class="card sunk small text">${esc(sentence)}</div>
      <div class="row"><button class="btn primary" id="saveW">${ICON.star.replace('<svg', '<svg width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.8"')}收藏这个词</button><button class="btn" id="saveS">收藏整句</button><button class="btn" id="exS">✦ AI 讲解整句</button></div>
      <button class="btn ghost" data-close>关闭</button></div>`, card => {
      card.querySelector('#sayW').onclick = sayWord;
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
    sayWord();
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
  const LEVEL_ORDER = ['A2', 'B1', 'B2', 'C1'];
  // The point to practise next: one flagged in their writing or a wrong answer first, then one whose spaced re-check
  // has come (any level), then at the learner's level one they have met but not yet checked, then a new one; easier first.
  function nextPoint(g) {
    const all = g.topics.flatMap(t => t.nodes.map(n => ({ ...n, topic: t.title })));
    const rank = n => n.status === 'watch' ? 0 : n.due ? 1 : { met: 2, used: 3, untouched: 4 }[n.status];
    const open = all.filter(n => n.status === 'watch' || n.due || (n.focus && n.status !== 'solid'));
    open.sort((a, b) => rank(a) - rank(b) || LEVEL_ORDER.indexOf(a.level) - LEVEL_ORDER.indexOf(b.level) || b.materials - a.materials);
    return open[0] || all.find(n => n.status !== 'solid') || null;
  }
  // The learning route: the 44 points in the order to learn them, one line per level, like stops on a metro line.
  // Only the level being learnt is open (the one with the next stop, else the learner's level); the others fold.
  const BAND = { A2: '入门', B1: '进阶', B2: '中高级', C1: '高级' };
  function routeHTML(g, next) {
    const openBand = (next && (g.route.find(b => b.nodes.some(n => n.id === next.id)) || {}).band) || (g.route.some(b => b.band === g.level) ? g.level : g.route[0] && g.route[0].band);
    return `<div class="route">${g.route.map(b => {
      const lit = b.nodes.filter(n => n.status !== 'untouched').length;
      return `<details class="rband fold"${b.band === openBand ? ' open' : ''}><summary class="rband-h"><b>${b.band}</b><span class="small muted">${BAND[b.band]} · ${b.nodes.length} 个点 · 已点亮 ${lit}</span></summary>
        <ol class="rline">${b.nodes.map((n, k) => { const here = next && n.id === next.id;
          return `<li class="rnode st st-${n.status}${n.status !== 'untouched' ? ' lit' : ''}${here ? ' here' : ''}" data-k="${k}"><a href="#/graph/${encodeURIComponent(n.id)}">
            <i class="dot" aria-hidden="true"></i><span class="t">${esc(n.title)}${here ? '<span class="here-tag">下一站</span>' : ''}${n.due ? '<span class="due-tag">该复习</span>' : ''}</span><span class="go" aria-hidden="true">›</span></a></li>`; }).join('')}</ol></details>`;
    }).join('')}</div>`;
  }
  async function graphView() {
    const g = await api('/api/next/graph' + guestQuery(true));
    const s = g.summary, next = nextPoint(g);
    const focusAll = g.topics.flatMap(t => t.nodes).filter(n => n.focus), focusSolid = focusAll.filter(n => n.status === 'solid').length;
    view.innerHTML = `<div><span class="kicker">知识图谱</span><h1 class="h1">你的英语语法地图</h1>
        <p class="muted small">${g.total} 个语法点，分成 ${g.topics.length} 类。读到、用出来、做题做对都会点亮它；AI 在你写作里发现的问题也会标在这里。</p></div>
      ${next ? `<div class="gnext"><div class="small muted">「${esc(g.level)}」现在的重点 ${focusAll.length} 个，已验证 ${focusSolid} 个</div>
        <a class="btn primary block go-next" href="#/graph/${encodeURIComponent(next.id)}">下一个：${esc(next.title)}<span aria-hidden="true">→</span></a>
        <div class="tiny muted">${next.status === 'watch' ? '你在写作或做题里在这里出过错，先补上它。' : next.due ? '按遗忘曲线该复习它了：做 4 道题，记得更牢。' : next.status === 'untouched' ? '先看讲解，再做几道题验证。' : '你已经读到过它，做几道题把它变成“已验证”。'}</div>
        ${s.due > 1 ? `<div class="tiny muted">一共 ${s.due} 个点该复习了，每天做一个就好。</div>` : ''}</div>` : ''}
      ${s.solid + s.used + s.met + s.watch < 5 ? `<a class="card flat place-cta" href="#/placement"><b>不知道从哪开始？</b><span class="small muted">做 16 道题的语法小测，3–6 分钟：给你一个起点等级，做对的点直接点亮。</span></a>` : ''}
      <div class="seg two section" role="tablist" aria-label="看法"><button role="tab" data-gv="route">学习路线</button><button role="tab" data-gv="all">全部 ${g.total} 个点</button></div>
      <div id="gRoute">${routeHTML(g, next)}</div><div id="gAll">
      <div class="gsum section">${[['solid', '已验证'], ['used', '用出来过'], ['met', '读到过'], ['watch', '要留意']].map(([k, l]) => `<div class="st st-${k}"><b>${s[k]}</b><span>${l}</span></div>`).join('')}</div>
      <div class="tgrid section" role="list" aria-label="13 类语法">${g.topics.map(t => {
        const lit = t.nodes.filter(n => n.status !== 'untouched').length, watch = t.nodes.some(n => n.status === 'watch');
        const focus = t.nodes.some(n => n.focus && n.status !== 'solid');
        return `<a class="tile${focus ? ' focus' : ''}" role="listitem" href="#/graph" data-topic="${esc(t.id)}" aria-label="${esc(t.title)}：${lit} / ${t.nodes.length} 个点亮${watch ? '，有要留意的' : ''}">
          <span class="ring" data-p="${Math.round(lit / t.nodes.length * 100)}"><b>${lit}/${t.nodes.length}</b>${watch ? '<i class="warn" aria-hidden="true"></i>' : ''}</span><span class="tl">${esc(t.title)}</span></a>`;
      }).join('')}</div>
      <div class="glegend">${STATUS_ORDER.map(k => `<span class="st st-${k}">${esc(g.labels[k])}</span>`).join('')}<span class="fz">${esc(g.level)} 重点</span></div>
      <div class="topic-list section">${g.topics.map(t => `<section class="topic" id="topic-${esc(t.id)}"><div class="row between"><h2 class="h2">${esc(t.title)}</h2><span class="tiny muted">${t.nodes.filter(n => n.status !== 'untouched').length} / ${t.nodes.length}</span></div>
        <div class="plist">${t.nodes.map(n => `<a class="nrow st st-${n.status}${n.focus ? ' focus' : ''}" href="#/graph/${encodeURIComponent(n.id)}"><i class="dot" aria-hidden="true"></i>
          <span class="t"><b>${esc(n.title)}</b><span class="tiny muted">${esc(n.label)}${n.due ? ' · <span class="due-tag">该复习</span>' : ''}${n.materials ? ` · ${n.materials} 篇材料` : ''}</span></span><span class="lv">${esc(n.level || '')}</span><span class="go" aria-hidden="true">›</span></a>`).join('')}</div></section>`).join('')}</div>
      </div>${S.user ? '' : '<p class="muted small section">登录后，你读过、写过、做对的内容会实时点亮这张图。</p>'}`;
    const show = gv => {
      document.getElementById('gRoute').hidden = gv !== 'route'; document.getElementById('gAll').hidden = gv === 'route';
      view.querySelectorAll('[data-gv]').forEach(b => b.setAttribute('aria-selected', String(b.dataset.gv === gv)));
      try { localStorage.setItem('flow-graph-view', gv); } catch (e) { /* private mode */ }
      if (gv === 'route') view.querySelectorAll('.rnode').forEach(li => { li.classList.remove('drawn'); li.style.setProperty('--d', (Number(li.dataset.k) * 45) + 'ms'); requestAnimationFrame(() => requestAnimationFrame(() => li.classList.add('drawn'))); });
    };
    let gv = 'route'; try { gv = localStorage.getItem('flow-graph-view') === 'all' ? 'all' : 'route'; } catch (e) { /* private mode */ }
    view.querySelectorAll('[data-gv]').forEach(b => b.onclick = () => show(b.dataset.gv));
    show(gv);
    view.querySelectorAll('details.rband').forEach(d => d.addEventListener('toggle', () => {
      if (d.open) d.querySelectorAll('.rnode').forEach(li => { li.classList.remove('drawn'); requestAnimationFrame(() => requestAnimationFrame(() => li.classList.add('drawn'))); });
    }));
    // CSP forbids inline style attributes, so the ring fill is set through the CSSOM.
    view.querySelectorAll('.tile .ring').forEach(r => r.style.setProperty('--p', r.dataset.p + '%'));
    view.querySelectorAll('.tile').forEach(a => a.onclick = e => {
      e.preventDefault();
      const sec = document.getElementById('topic-' + a.dataset.topic); if (sec) scrollToEl(sec);
    });
  }
  function scrollToEl(el) {
    const head = document.getElementById('bar').getBoundingClientRect().bottom;
    window.scrollTo({ top: window.scrollY + el.getBoundingClientRect().top - Math.max(0, head) - 12, behavior: REDUCED ? 'auto' : 'smooth' });
  }
  async function nodeView(nid) {
    const n = await api('/api/next/node?id=' + encodeURIComponent(nid) + guestQuery(false));
    const pg = n.page && n.page.status === 'ready' ? n.page : null;
    const stats = `读到过 ${n.met} 篇 · 用出来 ${n.used} 次${n.flags ? ' · 写作中被指出 ' + n.flags + ' 次' : ''}${n.evidence ? ' · 做题：' + esc(n.evidence) : ''}`;
    const choice = (q, i, kind) => `<div class="q gq" data-kind="${kind}" data-i="${i}"><div class="prompt">${esc(q.prompt)}</div>
      ${q.options.map((o, j) => `<button class="ans" data-o="${q.map ? q.map[j] : j}"><span class="k">${'ABCD'[j]}</span><span>${esc(o)}</span></button>`).join('')}<div class="fb" aria-live="polite"></div></div>`;
    const reviewText = r => !r ? '' : r.is_due ? '按遗忘曲线，今天该复习这个点了' : `下次复习：${r.in_days} 天后（第 ${r.step + 1} / ${r.rungs} 轮）`;
    view.innerHTML = `<div><a class="link small" href="#/graph">← 知识图谱</a></div>
      <div class="node-head"><span class="kicker">${esc(n.topic)} · ${esc(n.level || '')}${n.focus ? ' · 你现在的重点' : ''}</span><h1 class="h1">${esc(n.title)}</h1>
        <div class="row"><span class="node-chip st st-${n.status}" id="nodeStatus">${esc(n.label)}</span>${n.practice.length ? `<button class="btn small" id="toPractice">做 ${n.practice.length} 题验证 ↓</button>` : ''}</div><div class="tiny muted">${stats}</div><div class="tiny muted" id="nodeReview">${esc(reviewText(n.review))}</div></div>
      <div class="lesson section stack-s">
        <p class="goal">${esc(pg ? pg.goal : n.lesson)}</p>
        ${pg ? `<ol class="steps-list">${pg.steps.map(x => `<li>${esc(x)}</li>`).join('')}</ol>` : (n.example ? `<div class="text small">${esc(n.example)}</div>` : '')}
      </div>
      ${n.l1 ? `<div class="l1 section"><div class="kicker">中文思维陷阱</div><p class="small">${esc(n.l1.why)}</p>
        <div class="l1-rows"><div class="zh"><span class="tiny muted">中文</span>${esc(n.l1.zh)}</div><div class="bad"><span aria-label="常见错误">✗</span> ${esc(n.l1.wrong)}</div><div class="good"><span aria-label="正确">✓</span> ${esc(n.l1.right)}</div></div></div>` : ''}
      ${pg ? `<div class="section stack-s"><h2 class="h2">对比着看</h2><div class="plist">${pg.contrast.map(([en, zh]) => `<div class="crow"><button class="icon-btn" data-say="${esc(en)}" aria-label="朗读">${ICON.speak}</button><span><span class="en">${esc(en)}</span><span class="tiny muted">${esc(zh)}</span></span></div>`).join('')}</div></div>
      <div class="section stack-s"><h2 class="h2">常见错误</h2><div class="stack-s">${pg.pitfalls.map(([bad, good, why]) => `<div class="pit"><div class="bad"><span aria-label="错误">✗</span> ${esc(bad)}</div><div class="good"><span aria-label="正确">✓</span> ${esc(good)}</div><div class="tiny muted">${esc(why)}</div></div>`).join('')}</div></div>
      <div class="section stack-s"><div class="section-head"><h2 class="h2">先试一题</h2><span class="tiny muted">有提示，不计入验证</span></div>${choice(pg.guided, 0, 'guided')}</div>` : ''}
      ${n.practice.length ? `<div class="section stack-s" id="practice"><div class="section-head"><h2 class="h2">验证一下</h2><span class="tiny muted">${S.user ? '做对会点亮这个点；做错的会进错题本' : '登录后成绩会记进你的图谱'}</span></div>
        ${pg ? `<p class="small muted">做题前先问自己：${esc(pg.clue)}</p>` : ''}<div class="stack">${n.practice.map((q, i) => choice(q, i, 'check')).join('')}</div><div id="pscore" class="small"></div>
        <button class="btn" id="again" hidden>再来一组（题库 10 题，随机抽 4 题）</button></div>` : ''}
      <div class="section stack-s rel"><h2 class="h2">和它相连的点</h2>
        <div class="rel-flow">${n.prereq ? `<div class="rel-step"><span class="tiny muted">先学</span>${nodeChip(n.prereq)}</div><i class="rel-arrow" aria-hidden="true"></i>` : ''}
          <div class="rel-step me"><span class="tiny muted">现在</span><span class="node-chip st st-${n.status}">${esc(n.title)}</span></div>
          ${n.unlocks.length ? `<i class="rel-arrow" aria-hidden="true"></i><div class="rel-step"><span class="tiny muted">接下来</span><span class="chips">${n.unlocks.map(u => nodeChip(u)).join('')}</span></div>` : ''}</div>
        ${n.related.confusable.length ? `<div class="stack-s"><div class="kicker">容易和它混</div>${n.related.confusable.map(x => `<div class="confuse"><div class="row between">${nodeChip(x)}<a class="btn small" href="#/mix/pair/${encodeURIComponent(n.id + ',' + x.id)}">辨析练习</a></div><div class="tiny muted">${esc(x.how)}</div></div>`).join('')}</div>` : ''}
        ${n.related.together.length ? `<div class="stack-s"><div class="kicker">常和它一起出现</div><div class="chips">${n.related.together.map(x => nodeChip(x)).join('')}</div><span class="tiny muted">在同一篇材料里出现得最多的点，读到时可以留意它们怎么配合。</span></div>` : ''}</div>
      ${n.notes.length ? `<div class="stack-s section"><h2 class="h2">AI 在你写作里看到的</h2>${n.notes.map(x => `<div class="knote"><span class="small">${x.kind === 'flag' ? '需要留意：' : '用对了'}${esc((x.detail.split('|')[1] || ''))}</span><span class="tiny muted">${new Date(x.created * 1000).toLocaleDateString('zh-CN')}</span></div>`).join('')}</div>` : ''}
      ${n.examples.length ? `<div class="stack-s section"><h2 class="h2">在真实句子里看它</h2>${n.examples.map(x => `<a class="ex-quote" href="#/m/${encodeURIComponent(x.pack)}/read"><span>${esc(x.quote)}</span><div class="small muted">${esc(x.explanation)}</div></a>`).join('')}</div>` : ''}
      ${n.materials.length ? `<div class="section"><div class="section-head"><h2 class="h2">在文章里练它</h2></div><div class="grid-list">${n.materials.map(m => miniCard(m)).join('')}</div></div>` : ''}`;
    view.querySelectorAll('[data-say]').forEach(b => b.onclick = () => TTS.say(b.dataset.say));
    const jump = view.querySelector('#toPractice'); if (jump) jump.onclick = () => scrollToEl(view.querySelector('#practice'));
    const guided = pg ? pg.guided : null;
    let right = 0, answered = 0;
    view.querySelectorAll('.gq').forEach(box => box.querySelectorAll('.ans').forEach(b => b.onclick = async () => {
      if (box.dataset.done) return;
      const o = +b.dataset.o, fb = box.querySelector('.fb');
      let ok, answer, why;
      if (box.dataset.kind === 'guided') {  // learning support: checked here, never sent as evidence
        ok = o === guided.answer; answer = guided.answer; why = ok ? guided.explanation : '提示：' + guided.scaffold;
        if (!ok) { b.classList.add('wrong'); fb.textContent = why; return; }  // a hint and another go
      } else {
        const q = n.practice[+box.dataset.i];
        try { const r = await api('/api/next/node/answer', { question: q.id, choice: o }); ok = r.correct; answer = r.answer; why = r.explanation;
          if (r.label) { const st = view.querySelector('#nodeStatus'), was = st.className; st.className = 'node-chip st st-' + r.status; st.textContent = r.label;
            if (r.status === 'solid' && !/st-solid/.test(was)) { st.classList.add('lit-up'); toast('点亮了！「' + n.title + '」做题已验证'); } }
          if (r.review) view.querySelector('#nodeReview').textContent = ok ? reviewText(r.review) : '做错了：明天会再练一次这个点'; }
        catch (e) { toast(e.message); return; }
        answered++; if (ok) right++;
        const sc = view.querySelector('#pscore');
        if (answered === n.practice.length) {
          sc.textContent = `${n.practice.length} 题做对 ${right} 题。${right === n.practice.length ? (S.user ? '这个点可以算掌握了，到时间会提醒你再抽查一次。' : '这个点可以算掌握了。') : (S.user ? '错的题已经放进错题本，会按遗忘曲线再出现。' : '')}`;
          const again = view.querySelector('#again'); again.hidden = false; again.onclick = () => { const y = window.scrollY; route(true).then(() => window.scrollTo(0, y)); };
        }
      }
      box.dataset.done = '1';
      box.querySelectorAll('.ans').forEach(x => { x.disabled = true; if (+x.dataset.o === answer) x.classList.add('right'); });
      if (!ok) b.classList.add('wrong');
      fb.textContent = (ok ? '✓ ' : '✗ ') + (why || '') + (!ok && box.dataset.kind === 'check' && S.user ? ' 错题是最值钱的题：明天换一道题再考你。' : '');
      announce(ok ? '答对了' : '答错了');
    }));
  }
  /* ---------- grammar starting check: places the learner and lights the points they already know ---------- */
  async function placementView() {
    if (!S.meta) S.meta = await api('/api/next/meta');
    const t = await api('/api/next/placement');
    const items = t.items, per = t.per_band, answers = [];
    let i = 0;
    view.innerHTML = `<div class="place stack"><div><span class="kicker">语法起点小测</span><h1 class="h1">16 道题，找到你的起点</h1>
        <p class="muted">从简单到难，每 4 题一档。会就选，不会就点「不会」，不用猜。题目明显变难、开始吃力时会自动结束，一般 3–6 分钟。</p></div>
      <ul class="steps-list small"><li>做完给你一个起点等级，可以直接用它开始学</li><li>做对的语法点会点亮${S.user ? '' : '（登录后保存）'}，几天后再抽查一次</li><li>该补的点会排进今天的计划</li></ul>
      <p class="tiny muted">${esc(t.note)}</p>
      <button class="btn primary block" id="pStart">开始</button></div>`;
    document.getElementById('pStart').onclick = () => ask();
    function ask() {
      const q = items[i];
      view.innerHTML = `<div class="place stack"><div class="progress-line"><i id="pp"></i></div>
        <div class="row between"><span class="tiny muted">第 ${i + 1} 题 · 共最多 ${items.length} 题</span><span class="pill">${esc(q.band)}</span></div>
        <div class="q gq"><div class="prompt">${esc(q.prompt)}</div>
          ${q.options.map((o, j) => `<button class="ans" data-o="${q.map[j]}"><span class="k">${'ABCD'[j]}</span><span>${esc(o)}</span></button>`).join('')}</div>
        <button class="btn ghost" id="pSkip">不会</button></div>`;
      const pp = document.getElementById('pp'); pp.style.width = (i / items.length * 100) + '%';
      requestAnimationFrame(() => requestAnimationFrame(() => { pp.style.width = ((i + 1) / items.length * 100) + '%'; }));
      enter(view.querySelector('.q'));
      const pick = (choice, btn) => {
        view.querySelectorAll('.ans, #pSkip').forEach(b => b.disabled = true);
        if (btn) btn.classList.add('chosen');
        answers.push({ question: q.id, choice });
        setTimeout(step, REDUCED ? 0 : 220);
      };
      view.querySelectorAll('.ans').forEach(b => b.onclick = () => pick(+b.dataset.o, b));
      document.getElementById('pSkip').onclick = () => pick(null, null);
      announce(`第 ${i + 1} 题`);
    }
    async function step() {
      i++;
      if (i % per === 0 || i === items.length) {  // a band is done: ask whether the check is decided
        let r;
        try { r = await api('/api/next/placement', { answers, final: i === items.length }); }
        catch (e) { toast(e.message); i--; answers.pop(); ask(); return; }
        if (r.done) return result(r);
      }
      ask();
    }
    function result(r) {
      const byId = Object.fromEntries(items.map(q => [q.id, q])), lv = (S.meta && S.meta.levels || []).find(l => l.id === r.level);
      const cur = (S.home && S.home.profile) || S.guest || null;
      view.innerHTML = `<div class="place stack"><div><span class="kicker">小测结果</span><h1 class="h1">建议从 ${esc(r.level)} 开始</h1>
          ${lv ? `<p class="muted">${esc(lv.label)}：${esc(lv.desc)}</p>` : ''}</div>
        <div class="pl-bands">${r.scores.map(s => `<div class="pl-band${s.right <= per / 2 ? ' low' : ''}"><b>${esc(s.band)}</b><span>${s.right} / ${s.of}</span></div>`).join('')}</div>
        <button class="btn primary block" id="pUse">${cur && cur.level === r.level ? `保持 ${esc(r.level)}，去学习` : `用 ${esc(r.level)} 开始学`}</button>
        ${r.gaps.length ? `<div class="section stack-s"><h2 class="h2">先补这 ${r.gaps.length} 个点</h2><p class="small muted">在你的起点以内做错了。${r.saved ? '已经标为“要留意”，每天的计划会先排一个来补。' : '登录后再测，它们会排进每天的计划。'}</p>
          <div class="plist">${r.gaps.map(g => `<a class="nrow st st-watch" href="#/graph/${encodeURIComponent(g.id)}"><i class="dot" aria-hidden="true"></i><span class="t"><b>${esc(g.title)}</b></span><span class="lv">${esc(g.band)}</span><span class="go" aria-hidden="true">›</span></a>`).join('')}</div></div>` : ''}
        ${r.known.length ? `<p class="small section">${r.known.length} 个语法点做对了${r.saved ? '，已经在图谱里点亮，几天后会再抽查一次' : '；登录后再测一次，就会点亮在你的图谱里'}。</p>` : ''}
        <details class="section"><summary class="small">看每题的解析</summary><div class="stack-s">${r.results.map(x => { const q = byId[x.id]; if (!q) return '';
          const right = q.options[q.map.indexOf(x.answer)];
          return `<div class="pit"><div class="small">${esc(q.prompt)}</div><div class="${x.correct ? 'good' : 'bad'} small">${x.correct ? '✓ 答对' : '✗ 答案'}：${esc(right)}</div><div class="tiny muted">${esc(x.explanation)}</div></div>`; }).join('')}</div></details>
        <div class="row"><a class="link small" href="#/graph">看我的语法地图 →</a>${r.saved ? '<a class="link small" href="#/radar">语法这一项已记进能力雷达 →</a>' : ''}</div></div>`;
      enter(view.firstElementChild);
      announce('小测结束，建议从 ' + r.level + ' 开始');
      document.getElementById('pUse').onclick = async () => {
        if (!cur) { S.placed = r.level; location.hash = '#/welcome'; return; }  // first visit: the other questions still to come
        const prof = { ...cur, level: r.level };
        S.guest = prof; save('flow-next-guest', prof);
        if (S.user) { try { await api('/api/next/profile', prof); } catch (e) { toast(e.message); return; } }
        await refreshHome(); S.homeFresh = true; location.hash = '#/';
      };
    }
  }
  /* ---------- exam practice: a timed set at 中考 … 专八 / IELTS difficulty ---------- */
  const mmss = s => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
  function examHist(h) {
    return h.length ? `<div class="exam-hist" role="img" aria-label="最近 ${h.length} 次正确率：${h.map(x => x.pct + '%').join('、')}">${h.map(x => `<i data-h="${Math.max(6, x.pct)}"></i>`).join('')}</div>` : '';
  }
  function sizeHist() { view.querySelectorAll('.exam-hist i').forEach(i => i.style.height = i.dataset.h + '%'); }  // CSP: no inline styles
  async function examView(pick) {
    const o = await api('/api/next/exam');
    const cur = o.exams.find(e => e.id === pick) || null;
    // The chosen exam opens right under its own card (with eight exams, a block under the list was a scroll away): the
    // list is cut after it, so the details sit between the two halves and keep their own button styles.
    const at = cur ? o.exams.indexOf(cur) : o.exams.length - 1;
    const pickList = list => list.length ? `<div class="exam-pick choice">${list.map(e => `<a class="opt" href="#/exam/${e.id}" aria-pressed="${cur && cur.id === e.id}"><span class="l">${esc(e.title)}</span>
        <span class="d">${esc(e.blurb)}</span><span class="tiny muted">约 ${e.minutes} 分钟${e.history.length ? ` · 上次 ${e.history[e.history.length - 1].pct}%` : ''}</span></a>`).join('')}</div>` : '';
    const detail = cur ? `<div class="stack-s exam-cur" id="examCur"><h2 class="h2">${esc(cur.title)}</h2>
        <ul class="steps-list small"><li>词汇 10 题：${esc(cur.book_title)}里的词，选中文意思</li><li>语法 8 题：这个考试常考的语法点</li><li>阅读 2 篇短文，4 题</li></ul>
        ${cur.history.length ? `<div class="stack-s"><span class="tiny muted">最近 ${cur.history.length} 次的正确率</span>${examHist(cur.history)}</div>` : ''}
        <button class="btn primary block" id="exStart">开始一套（约 ${cur.minutes} 分钟）</button>
        ${S.user ? (o.plan && o.plan.book === cur.book ? `<p class="tiny muted">你现在就在用「${esc(cur.book_title)}」背单词（${cur.words} 词）。</p>` :
          `<div class="row"><button class="btn small" id="exBook">改用「${esc(cur.book_title)}」背单词</button><span class="tiny muted">${cur.words} 词，按遗忘曲线每天背</span></div>`) :
          '<p class="tiny muted">登录后成绩会保存，语法错题进错题本，没认出的词可以一键加进单词本。</p>'}</div>` : '';
    view.innerHTML = `<div class="stack"><div><span class="kicker">考试练习</span><h1 class="h1">按考试难度练一套</h1>
        <p class="muted small">${esc(o.note)}</p></div>
      ${cur ? '' : '<p class="muted small">选一个考试开始。每套约 12–20 分钟，每周做一套就能看到变化。</p>'}
      ${pickList(o.exams.slice(0, at + 1))}${detail}${pickList(o.exams.slice(at + 1))}</div>`;
    sizeHist();
    if (!cur) return;
    requestAnimationFrame(() => { const d = document.getElementById('examCur'); if (d && d.getBoundingClientRect().bottom > innerHeight) d.scrollIntoView({ block: 'nearest', behavior: REDUCED ? 'auto' : 'smooth' }); });
    document.getElementById('exStart').onclick = () => examPaper(cur.id);
    const book = document.getElementById('exBook');
    if (book) book.onclick = async () => {
      const p = o.plan || { daily_new: 10, retention: 0.9 };
      try { await api('/api/next/vocab/plan', { book: cur.book, daily_new: p.daily_new, retention: p.retention }); toast(`已改用「${cur.book_title}」，明天起每天背 ${p.daily_new} 个新词`); examView(pick); }
      catch (e) { toast(e.message); }
    };
  }
  async function examPaper(exam) {
    const p = await api('/api/next/exam/paper', { exam });
    const ans = { vocab: [], grammar: [], reading: [] };
    const started = Date.now();
    let n = 0;
    const q = (key, i, prompt, options, map, sub) => {
      const k = n++;
      return `<div class="q gq" data-key="${key}" data-i="${i}"><div class="prompt">${k + 1}. ${prompt}</div>${sub || ''}
        ${options.map((x, j) => `<button class="ans" data-o="${map ? map[j] : j}"><span class="k">${'ABCD'[j]}</span><span>${esc(x)}</span></button>`).join('')}</div>`;
    };
    const part = pt => {
      if (pt.key === 'vocab') return pt.items.map((x, i) => q('vocab', i, `<b class="en">${esc(x.word)}</b>`, x.options, null, x.phonetic ? `<div class="tiny muted">${esc(x.phonetic)}</div>` : '')).join('');
      if (pt.key === 'grammar') return pt.items.map((x, i) => q('grammar', i, esc(x.prompt), x.options, x.map)).join('');
      let i = 0;
      return pt.passages.map(ps => `<article class="stack-s"><h3 class="h3">${esc(ps.title)}</h3><div class="exam-passage">${esc(ps.body)}</div>
        ${ps.items.map(x => q('reading', i++, esc(x.prompt), x.options)).join('')}</article>`).join('');
    };
    const total = p.parts.reduce((s, pt) => s + (pt.items ? pt.items.length : pt.passages.reduce((a, ps) => a + ps.items.length, 0)), 0);
    view.innerHTML = `<div class="stack"><div class="exam-bar"><b>${esc(p.title)} · 练习</b><span class="clock" id="exClock" aria-live="off">0:00</span></div>
      ${p.parts.map(pt => `<section class="exam-part"><h2 class="h2">${esc(pt.title)}</h2><p class="tiny muted">${esc(pt.hint)}</p>${part(pt)}</section>`).join('')}
      <button class="btn primary block" id="exDone">交卷</button><p class="tiny muted">建议 ${p.minutes} 分钟内完成；超时也可以交卷，只是会标出来。</p></div>`;
    const clock = document.getElementById('exClock');
    view.querySelector('.exam-bar').style.top = (bar.offsetHeight + 6) + 'px';  // just under the app's top bar, whatever its height
    const tick = setInterval(() => {
      if (!document.body.contains(clock)) { clearInterval(tick); return; }
      const s = Math.round((Date.now() - started) / 1000); clock.textContent = mmss(s); clock.classList.toggle('late', s > p.minutes * 60);
    }, 1000);
    view.querySelectorAll('.gq').forEach(box => box.querySelectorAll('.ans').forEach(b => b.onclick = () => {
      box.querySelectorAll('.ans').forEach(x => x.classList.toggle('chosen', x === b));
      ans[box.dataset.key][+box.dataset.i] = +b.dataset.o;
    }));
    let warned = false;
    document.getElementById('exDone').onclick = async () => {
      const done = ['vocab', 'grammar', 'reading'].reduce((s, k) => s + ans[k].filter(x => x !== undefined && x !== null).length, 0);
      const btn = document.getElementById('exDone');
      if (done < total && !warned) { warned = true; btn.textContent = `还有 ${total - done} 题没做，再点一次交卷`; return; }
      btn.disabled = true;
      const fill = (a, len) => Array.from({ length: len }, (_, i) => a[i] === undefined ? null : a[i]);
      const lens = { vocab: 0, grammar: 0, reading: 0 };
      p.parts.forEach(pt => { lens[pt.key] = pt.items ? pt.items.length : pt.passages.reduce((a, ps) => a + ps.items.length, 0); });
      try {
        const r = await api('/api/next/exam/submit', { paper: p.paper, seconds: Math.round((Date.now() - started) / 1000),
          answers: { vocab: fill(ans.vocab, lens.vocab), grammar: fill(ans.grammar, lens.grammar), reading: fill(ans.reading, lens.reading) } });
        clearInterval(tick); window.scrollTo(0, 0); examResult(p, r);
      } catch (e) { btn.disabled = false; toast(e.message); }
    };
  }
  function examResult(p, r) {
    const missed = r.vocab.filter(v => !v.correct), gmiss = r.grammar.filter(g => !g.correct);
    const nodes = [...new Map(gmiss.map(g => [g.node, g.node_title])).entries()];
    const late = r.seconds > r.minutes * 60;
    view.innerHTML = `<div class="stack"><div><span class="kicker">${esc(r.title)} · 练习结果</span><h1 class="h1">${r.total} 题做对 ${r.score} 题（${r.pct}%）</h1>
        <p class="muted small">用时 ${mmss(r.seconds)}${late ? `，比建议的 ${r.minutes} 分钟多了 ${mmss(r.seconds - r.minutes * 60)}` : `，在建议的 ${r.minutes} 分钟以内`}。</p></div>
      <div class="exam-score">${r.parts.map(x => `<div><span class="tiny muted">${esc(x.title)}</span><b>${x.right}/${x.of}</b></div>`).join('')}</div>
      ${r.history.length > 1 ? `<div class="stack-s"><span class="tiny muted">最近 ${r.history.length} 次的正确率</span>${examHist(r.history)}</div>` : ''}
      ${missed.length ? `<div class="section stack-s"><h2 class="h2">没认出的 ${missed.length} 个词</h2><div class="plist">${missed.map(v => `<div class="crow"><button class="icon-btn" data-say="${esc(v.word)}" aria-label="朗读">${ICON.speak}</button><span><span class="en">${esc(v.word)}</span><span class="tiny muted">${esc(v.answer)}</span></span></div>`).join('')}</div>
        ${S.user ? '<button class="btn" id="exAdd">全部加进单词本</button>' : ''}</div>` : ''}
      ${nodes.length ? `<div class="section stack-s"><h2 class="h2">要补的语法点</h2><p class="small muted">${r.saved ? '错题已经放进错题本，这些点也排进了每天的计划。' : '登录后错题会进错题本。'}</p>
        <div class="plist">${nodes.map(([id, t]) => `<a class="nrow st st-watch" href="#/graph/${encodeURIComponent(id)}"><i class="dot" aria-hidden="true"></i><span class="t"><b>${esc(t)}</b></span><span></span><span class="go" aria-hidden="true">›</span></a>`).join('')}</div></div>` : ''}
      <details class="section"><summary class="small">看语法和阅读的解析</summary><div class="stack-s">
        ${r.grammar.map((g, i) => { const it = p.parts.find(x => x.key === 'grammar').items[i]; const right = it.options[it.map.indexOf(g.answer)];
          return `<div class="pit"><div class="small">${esc(it.prompt)}</div><div class="${g.correct ? 'good' : 'bad'} small">${g.correct ? '✓ 答对' : '✗ 答案'}：${esc(right)}</div><div class="tiny muted">${esc(g.explanation)}</div></div>`; }).join('')}
        ${(() => { const rp = p.parts.find(x => x.key === 'reading'); if (!rp) return ''; const items = rp.passages.flatMap(ps => ps.items);
          return r.reading.map((x, i) => `<div class="pit"><div class="small">${esc(items[i].prompt)}</div><div class="${x.correct ? 'good' : 'bad'} small">${x.correct ? '✓ 答对' : '✗ 答案'}：${esc(items[i].options[x.answer])}</div>${x.evidence ? `<div class="tiny muted">原文依据：${esc(x.evidence)}</div>` : ''}</div>`).join(''); })()}
      </div></details>
      <div class="row"><button class="btn primary" id="exAgain">再来一套</button><a class="btn ghost" href="#/exam/${esc(r.exam)}">回到考试练习</a></div></div>`;
    sizeHist();
    announce(`练习结果：${r.total} 题做对 ${r.score} 题`);
    view.querySelectorAll('[data-say]').forEach(b => b.onclick = () => TTS.say(b.dataset.say));
    const add = document.getElementById('exAdd');
    if (add) add.onclick = async () => {
      add.disabled = true;
      try { const x = await api('/api/next/vocab/add', { items: missed.map(v => ({ word: v.word })) }); add.textContent = x.added ? `已加入 ${x.added} 个词` : '这些词都已经在单词本里了'; }
      catch (e) { add.disabled = false; toast(e.message); }
    };
    document.getElementById('exAgain').onclick = () => examPaper(r.exam);
  }
  /* ---------- mixed grammar rounds: several points interleaved (today's review, a confusable pair, a whole topic) ---------- */
  // Questions on different points mixed together make the learner decide which rule applies first: that decision is
  // what real use asks for, and it is what one-point-at-a-time practice never trains.
  async function mixView(kind, arg) {
    const q = kind === 'pair' ? '?pair=' + encodeURIComponent(arg) : kind === 'topic' ? '?topic=' + encodeURIComponent(arg) : guestQuery(true);
    const m = await api('/api/next/mix' + q);
    const TITLE = { due: '今天的语法复习', practice: '语法混合练习', pair: '辨析练习', topic: '这一类混着练' };
    const intro = m.kind === 'due' ? `${m.nodes.length} 个点混在一起出题：先想清楚这题考的是哪条规则，再选。${m.left ? `还有 ${m.left} 个点明天接着练。` : ''}`
      : m.kind === 'pair' ? '两个容易混的点交替出题，做的时候先判断是哪一个。'
      : m.kind === 'practice' ? '今天没有到期要复习的点。先混着练几个你这个级别的，做对的会点亮。' : '这一类里的每个点各出一题。';
    const items = m.items, before = Object.fromEntries(m.nodes.map(n => [n.id, n.status])), after = {}, per = {};
    let i = 0, right = 0, streak = 0;
    view.innerHTML = `<div class="stack mix"><div><span class="kicker">${esc(TITLE[m.kind])}</span><h1 class="h1">${m.kind === 'pair' ? esc(m.nodes.map(n => n.title).join(' vs ')) : `${items.length} 道题，${m.nodes.length} 个点`}</h1>
        <p class="muted small">${esc(intro)}</p></div>
      ${m.note ? `<div class="howto"><b>怎么区分</b><span class="small">${esc(m.note)}</span></div>` : ''}
      <div class="mix-dots" aria-hidden="true">${items.map(() => '<i></i>').join('')}</div>
      <div id="mixQ"></div></div>`;
    const dots = [...view.querySelectorAll('.mix-dots i')];
    function ask() {
      const it = items[i], box = document.getElementById('mixQ');
      dots.forEach((d, k) => d.classList.toggle('now', k === i));
      box.innerHTML = `<div class="q gq enter"><div class="tiny muted">第 ${i + 1} / ${items.length} 题</div><div class="prompt">${esc(it.prompt)}</div>
        ${it.options.map((o, j) => `<button class="ans" data-o="${it.map[j]}"><span class="k">${'ABCD'[j]}</span><span>${esc(o)}</span></button>`).join('')}<div class="fb" aria-live="polite"></div></div>`;
      box.querySelectorAll('.ans').forEach(b => b.onclick = () => answer(it, b, box));
      keys4(box);
    }
    function keys4(box) {
      document.onkeydown = e => { const k = Number(e.key); if (k >= 1 && k <= 4 && !e.metaKey && !e.ctrlKey) { const b = box.querySelectorAll('.ans')[k - 1]; if (b && !b.disabled) b.click(); } };
    }
    async function answer(it, b, box) {
      box.querySelectorAll('.ans').forEach(x => { x.disabled = true; });
      let r;
      try { r = await api('/api/next/node/answer', { question: it.id, choice: Number(b.dataset.o), from: 'mix' }); }
      catch (e) { toast(e.message); box.querySelectorAll('.ans').forEach(x => { x.disabled = false; }); return; }
      box.querySelectorAll('.ans').forEach(x => { if (Number(x.dataset.o) === r.answer) x.classList.add('right'); });
      if (!r.correct) b.classList.add('wrong');
      const p = per[it.node] = per[it.node] || { right: 0, of: 0 }; p.of++;
      if (r.correct) { right++; p.right++; streak++; } else streak = 0;
      if (r.status) after[it.node] = { status: r.status, label: r.label };
      dots[i].classList.add(r.correct ? 'ok' : 'no');
      box.querySelector('.fb').innerHTML = `<div class="${r.correct ? 'ok' : 'bad'}">${r.correct ? '✓ 对了' : '✗ 这题选错了'}${streak >= 3 ? ` · 连对 ${streak} 题` : ''}</div>
        <div class="small">${esc(r.explanation || '')}</div><div class="tiny muted">考的是：<a class="link" href="#/graph/${encodeURIComponent(it.node)}">${esc(it.node_title)}</a></div>
        <button class="btn primary block" id="mixNext">${i + 1 < items.length ? '下一题' : '看结果'}</button>`;
      announce(r.correct ? '答对了' : '答错了');
      const nx = document.getElementById('mixNext');
      nx.scrollIntoView({ block: 'nearest', behavior: REDUCED ? 'auto' : 'smooth' });  // the explanation and the next button, above the tab bar
      nx.onclick = () => { i++; if (i < items.length) ask(); else done(); };
      document.onkeydown = e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); nx.click(); } };
      nx.focus({ preventScroll: true });
    }
    function done() {
      document.onkeydown = null;
      const all = right === items.length, rows = m.nodes.filter(n => per[n.id]);
      const lit = rows.filter(n => before[n.id] !== 'solid' && (after[n.id] || {}).status === 'solid');
      const msg = all ? `全对！${S.user ? '这几个点都往后推了，到时间再抽查。' : ''}`
        : `${items.length - right} 题没做对。${S.user ? '它们明天会换一道题再来——错题是最值钱的题，弄懂一个就少一个。' : ''}`;
      view.innerHTML = `<div class="stack mix-done">${right * 2 >= items.length ? `<div class="done-burst${all ? ' all' : ''}" aria-hidden="true">${doneRing}</div>` : ''}
        <div class="tc"><span class="kicker">${esc(TITLE[m.kind])}</span><h1 class="h1">${items.length} 题做对 ${right} 题</h1><p class="small">${esc(msg)}</p>
        ${lit.length ? `<p class="small cheer">新点亮了 ${lit.length} 个点：${esc(lit.map(n => n.title).join('、'))}</p>` : ''}</div>
        <div class="plist">${rows.map((n, k) => { const a = after[n.id] || n, pr = per[n.id];
          return `<a class="nrow st st-${a.status} pop-in" data-k="${k}" href="#/graph/${encodeURIComponent(n.id)}"><i class="dot" aria-hidden="true"></i><span class="t"><b>${esc(n.title)}</b><span class="tiny muted">${esc(a.label || '')}</span></span><span class="lv">${pr.right}/${pr.of}</span><span class="go" aria-hidden="true">›</span></a>`; }).join('')}</div>
        ${S.user ? '' : '<p class="muted small">登录后，做对的点会点亮在你的语法地图里，错的会按遗忘曲线回来。</p>'}
        <div class="row center"><a class="btn" href="#/graph">语法地图</a>${m.kind === 'due' ? '<a class="btn primary" href="#/">回到今日</a>' : '<button class="btn primary" id="mixAgain">再来一轮</button>'}</div></div>`;
      view.querySelectorAll('.pop-in').forEach(el => el.style.setProperty('--d', (Number(el.dataset.k) * 90 + 200) + 'ms'));
      const again = document.getElementById('mixAgain'); if (again) again.onclick = () => mixView(kind, arg);
      announce(`${items.length} 题做对 ${right} 题`);
      if (S.user) refreshHome().catch(() => {});
    }
    if (!items.length) {
      document.getElementById('mixQ').innerHTML = '<div class="empty"><p>这里暂时没有题。</p><a class="btn" href="#/graph">回到语法地图</a></div>';
      return;
    }
    ask();
  }
  /* ---------- easy reading: a lot of easy text, read fast, no tasks ---------- */
  async function easyView() {
    const d = await api('/api/next/easy' + guestQuery(true)), st = d.stats;
    view.innerHTML = `<div class="stack"><div><span class="kicker">轻松读</span><h1 class="h1">读得多，比读得难更重要</h1>
        <p class="muted small">${esc(d.note)}</p></div>
      ${st ? `<div class="easy-stats"><div><b>${st.week_words.toLocaleString()}</b><span class="tiny muted">这周读了（词）</span></div>
        <div><b>${st.avg_wpm || '—'}</b><span class="tiny muted">阅读速度（词/分钟）</span></div><div><b>${st.reads}</b><span class="tiny muted">一共读了（篇）</span></div></div>
        ${st.first_wpm && st.avg_wpm > st.first_wpm ? `<p class="small cheer">比刚开始快了 ${st.avg_wpm - st.first_wpm} 词/分钟。</p>` : ''}` : '<p class="muted small">登录后会记下你读了多少、读得多快。</p>'}
      <div class="section stack-s"><div class="row between"><h2 class="h2">今天可以读</h2><span class="pill">${esc(d.target)}</span></div>
        <div class="grid-list">${d.items.map(m => `<a class="card flat mini" href="#/easy/${encodeURIComponent(m.id)}"><span class="t">${esc(m.title)}</span>
          <span class="meta"><span class="pill">${m.level}</span></span><span class="p">${esc(m.preview_en)}</span><span class="tiny muted">${m.words} 词 · 约 ${Math.max(1, Math.round(m.words / 120))} 分钟</span></a>`).join('') || '<div class="empty"><p>这个难度的材料都读过了，明天会有新的。</p></div>'}</div></div>
      <p class="tiny muted">怎么读：不查词也能猜个大概就继续往下读；实在影响理解再点词。读完选一下难不难就行。</p></div>`;
  }
  async function easyRead(id) {
    const m = await api('/api/next/material?id=' + encodeURIComponent(id) + guestQuery(false));
    const ls = m.sentences, t0 = Date.now();
    let looked = 0;
    view.innerHTML = `<div><a class="link small" href="#/easy">← 轻松读</a></div>
      <div class="study-head"><span class="kicker">轻松读 · ${esc(m.level)} · ${ls.join(' ').split(/\s+/).length} 词</span><h1 class="h1">${esc(m.title_en || m.title)}</h1>
        ${m.title_en ? `<div class="muted small">${esc(m.title)}</div>` : ''}</div>
      <div class="reader easy-reader" id="easyText" lang="en">${ls.map((s, k) => `<span class="s">${wordSpans(s, () => 'w', ` data-s="${k}"`)}</span> `).join('')}</div>
      <div class="section stack-s" id="easyEnd"><div class="kicker">读完了，觉得怎么样？</div>
        <div class="choice three">${[['easy', '太简单'], ['ok', '刚好'], ['hard', '有点难']].map(([v, l]) => `<button class="opt" data-r="${v}"><span class="l">${l}</span></button>`).join('')}</div>
        <span class="tiny muted">选“太简单”，下一篇会难一点；选“有点难”，会简单一点。</span></div>`;
    document.getElementById('easyText').onclick = e => {
      const w = e.target.closest('.w'); if (!w || String(getSelection()).trim()) return;
      looked++; lookupSheet(w.dataset.w, ls[Number(w.dataset.s)], id, false);
    };
    view.querySelectorAll('[data-r]').forEach(b => b.onclick = async () => {
      view.querySelectorAll('[data-r]').forEach(x => { x.disabled = true; x.setAttribute('aria-pressed', String(x === b)); });
      const seconds = Math.max(5, Math.round((Date.now() - t0) / 1000));
      let r; try { r = await api('/api/next/easy/done', { pack: id, seconds, rating: b.dataset.r }); }
      catch (e) { toast(e.message); view.querySelectorAll('[data-r]').forEach(x => { x.disabled = false; }); return; }
      const st = r.stats;
      document.getElementById('easyEnd').insertAdjacentHTML('beforeend', `<div class="easy-done pop-in"><div class="easy-stats"><div><b>${r.words}</b><span class="tiny muted">读了（词）</span></div>
          <div><b>${r.wpm || '—'}</b><span class="tiny muted">词/分钟</span></div><div><b>${looked}</b><span class="tiny muted">查了（次）</span></div></div>
        <p class="small cheer">${st ? `这周已经读了 ${st.week_words.toLocaleString()} 词。` : ''}${looked <= 3 ? '几乎没查词就读完了，这正是轻松读要的感觉。' : '这篇查得有点多：觉得吃力的话，选“有点难”，下一篇就会简单一点。'}</p>
        <div class="row"><a class="btn primary" href="#/easy">再读一篇</a><a class="btn ghost" href="#/">回到今日</a></div></div>`);
      if (S.user) refreshHome().catch(() => {});
    });
  }
  /* ---------- words Chinese speakers mix up: how to tell them apart, and interleaved practice ---------- */
  async function confuseView() {
    const d = await api('/api/next/words/confuse');
    const LV = ['A2', 'B1', 'B2', 'C1'];
    view.innerHTML = `<div class="stack"><div><span class="kicker">词汇辨析</span><h1 class="h1">中文里是一个词，英语里是两个</h1>
        <p class="muted small">借 = borrow / lend，看 = look / see / watch……这些词靠中文分不开，只能放在一起练。选几组混着做，错的会进复习，每次换一道题。</p></div>
      <button class="btn primary block" id="cfMix" disabled>混合练习选中的组</button>
      ${LV.map(lv => { const gs = d.groups.filter(g => g.level === lv); return gs.length ? `<section class="stack-s section"><h2 class="h2">${lv}</h2>
        <div class="cf-list">${gs.map(g => `<label class="cf-row${g.tries ? ' tried' : ''}"><input type="checkbox" value="${esc(g.id)}"><span class="t"><b class="en">${esc(g.words.join(' / '))}</b>
          <span class="tiny muted">${esc(g.how)}</span></span><span class="tiny muted">${g.tries ? `${g.right}/${g.tries}` : ''}</span><a class="btn small" href="#/words/confuse/${encodeURIComponent(g.id)}">练</a></label>`).join('')}</div></section>` : ''; }).join('')}</div>`;
    const boxes = [...view.querySelectorAll('.cf-row input')], go = document.getElementById('cfMix');
    const upd = () => { const n = boxes.filter(b => b.checked).length; go.disabled = n < 2; go.textContent = n < 2 ? '选两组以上，混合练习' : `混合练习选中的 ${n} 组`; };
    boxes.forEach(b => b.onchange = () => { if (boxes.filter(x => x.checked).length > 6) { b.checked = false; toast('一次最多混 6 组'); } upd(); });
    go.onclick = () => { location.hash = '#/words/confuse/' + boxes.filter(b => b.checked).map(b => b.value).join(','); };
    upd();
  }
  async function confuseRound(groups) {
    const d = await api('/api/next/words/confuse/round?groups=' + encodeURIComponent(groups));
    const items = d.items; let i = 0, right = 0;
    view.innerHTML = `<div class="stack mix"><div><a class="link small" href="#/words/confuse">← 词汇辨析</a></div>
      <div><span class="kicker">词汇辨析</span><h1 class="h1">${esc(d.groups.map(g => g.words.join(' / ')).join(' · '))}</h1></div>
      ${d.groups.map(g => `<div class="howto"><b class="en">${esc(g.words.join(' / '))}</b><span class="small">${esc(g.how)}</span></div>`).join('')}
      <div class="mix-dots" aria-hidden="true">${items.map(() => '<i></i>').join('')}</div><div id="mixQ"></div></div>`;
    const dots = [...view.querySelectorAll('.mix-dots i')];
    const ask = () => {
      const it = items[i], box = document.getElementById('mixQ');
      dots.forEach((x, k) => x.classList.toggle('now', k === i));
      box.innerHTML = `<div class="q gq enter"><div class="tiny muted">第 ${i + 1} / ${items.length} 题</div><div class="prompt">${esc(it.prompt)}</div>
        ${it.options.map((o, j) => `<button class="ans" data-o="${j}"><span class="k">${'ABCD'[j]}</span><span>${esc(o)}</span></button>`).join('')}<div class="fb" aria-live="polite"></div></div>`;
      box.querySelectorAll('.ans').forEach(b => b.onclick = () => {
        const ok = Number(b.dataset.o) === it.answer;
        box.querySelectorAll('.ans').forEach((x, j) => { x.disabled = true; if (j === it.answer) x.classList.add('right'); });
        if (!ok) b.classList.add('wrong'); else right++;
        dots[i].classList.add(ok ? 'ok' : 'no');
        api('/api/next/words/confuse/answer', { item: it.id, correct: ok }).catch(() => {});
        box.querySelector('.fb').innerHTML = `<div class="${ok ? 'ok' : 'bad'}">${ok ? '✓ 对了' : '✗ 选错了'}</div><div class="small">${esc(it.explanation)}</div>
          <button class="btn primary block" id="mixNext">${i + 1 < items.length ? '下一题' : '看结果'}</button>`;
        const nx = document.getElementById('mixNext'); nx.scrollIntoView({ block: 'nearest', behavior: REDUCED ? 'auto' : 'smooth' });
        nx.onclick = () => { i++; if (i < items.length) ask(); else done(); };
        announce(ok ? '答对了' : '答错了');
      });
    };
    const done = () => {
      view.innerHTML = `<div class="stack mix-done">${right * 2 >= items.length ? `<div class="done-burst${right === items.length ? ' all' : ''}" aria-hidden="true">${doneRing}</div>` : ''}
        <div class="tc"><span class="kicker">词汇辨析</span><h1 class="h1">${items.length} 题做对 ${right} 题</h1>
        <p class="small">${right === items.length ? '全对！这几组你已经分得很清楚了。' : S.user ? `错的 ${items.length - right} 组已经放进复习，下次会换一道题考你。` : '登录后，错的会进复习，下次换一道题考你。'}</p></div>
        <div class="row center"><a class="btn" href="#/words/confuse">选别的组</a><button class="btn primary" id="cfAgain">再来一轮</button></div></div>`;
      document.getElementById('cfAgain').onclick = () => confuseRound(groups);
      announce(`${items.length} 题做对 ${right} 题`);
    };
    ask();
  }
  /* ---------- the speaking route: role-play scenes from ordering a coffee to answering a sceptical boss ---------- */
  async function speakView() {
    const d = await api('/api/next/speak' + guestQuery(true));
    const LV = { A2: '入门', B1: '中级', B2: '中高级', C1: '高级' };
    view.innerHTML = `<div class="stack"><div><span class="kicker">口语路线</span><h1 class="h1">开口说，从真实情景开始</h1>
        <p class="muted small">AI 扮演情景里的另一方：店员、房东、面试官……你用英文完成任务，可以说也可以打字。每说一句它会顺手纠正一处，结束时告诉你哪里说得好、哪里要改。</p></div>
      ${d.next ? `<a class="btn primary block" href="#/speak/${encodeURIComponent(d.next)}">下一个：${esc(d.items.find(x => x.id === d.next).title)}<span aria-hidden="true">→</span></a>` : ''}
      <p class="small muted">已完成 ${d.done} / ${d.total} 个情景</p>
      ${['A2', 'B1', 'B2', 'C1'].map(lv => { const xs = d.items.filter(x => x.level === lv); return xs.length ? `<section class="stack-s section"><h2 class="h2">${lv} · ${LV[lv]}</h2>
        <div class="plist">${xs.map(x => `<a class="nrow ${x.done ? 'st st-solid' : 'st st-untouched'}" href="#/speak/${encodeURIComponent(x.id)}"><i class="dot" aria-hidden="true"></i>
          <span class="t"><b>${esc(x.title)}</b><span class="tiny muted">你：${esc(x.me)} · AI：${esc(x.ai)}${x.done ? ' · 完成过' : ''}</span></span><span></span><span class="go" aria-hidden="true">›</span></a>`).join('')}</div></section>` : ''; }).join('')}</div>`;
  }
  async function speakScene(sid) {
    const d = await api('/api/next/speak' + guestQuery(true)), x = d.items.find(s => s.id === sid);
    if (!x) { view.innerHTML = '<div class="empty"><p>没有这个情景。</p><a class="btn" href="#/speak">口语路线</a></div>'; return; }
    const hist = [];
    view.innerHTML = `<div><a class="link small" href="#/speak">← 口语路线</a></div>
      <div class="stack"><div><span class="kicker">情景对话 · ${esc(x.level)}</span><h1 class="h1">${esc(x.title)}</h1><div class="title-en">${esc(x.title_en)}</div>
        <p class="small">${esc(x.brief)}</p></div>
      <div class="scene-goals"><div class="kicker">你的任务</div><ol class="steps-list small">${x.goals.map(g => `<li>${esc(g)}</li>`).join('')}</ol></div>
      <details class="useful"><summary class="small">用得上的说法（${x.useful.length}）</summary><div class="plist">${x.useful.map(u => `<div class="crow"><button class="icon-btn" data-say="${esc(u.text)}" aria-label="朗读">${ICON.speak}</button><span><span class="en">${esc(u.text)}</span><span class="tiny muted">${esc(u.meaning)}</span></span></div>`).join('')}</div></details>
      <div class="chat" id="chat"></div>
      <div id="dlgIn" class="stack-s" hidden><div class="tiny muted" id="dlgHint"></div>
        <div class="chat-in"><textarea id="dlgText" rows="2" maxlength="480" lang="en" enterkeyhint="send" placeholder="用英文回答，或者点 ● 说出来"></textarea>${recBtn('dlgMic', '说出来')}<button class="btn primary" id="dlgSend">发送</button></div>
        <div class="row between"><span class="tiny muted" id="dlgCount"></span><button class="btn small ghost" id="dlgEnd">结束并看反馈</button></div></div>
      <div><button class="btn primary block" id="dlgStart">开始对话</button></div><div id="dlgOut"></div></div>`;
    view.querySelectorAll('[data-say]').forEach(b => b.onclick = () => TTS.say(b.dataset.say));
    const chat = view.querySelector('#chat');
    const bubble = (role, text, extra) => { chat.insertAdjacentHTML('beforeend', `<div class="msg ${role}"><div class="b">${esc(text)}</div>${extra || ''}</div>`); chat.lastElementChild.scrollIntoView({ block: 'nearest', behavior: REDUCED ? 'auto' : 'smooth' }); };
    const busy = on => { ['#dlgSend', '#dlgEnd', '#dlgMic'].forEach(s => { const b = view.querySelector(s); if (b) b.disabled = on; }); };
    const showInput = () => { const box = view.querySelector('#dlgIn'); if (box && !box.hidden) box.scrollIntoView({ block: 'end', behavior: REDUCED ? 'auto' : 'smooth' }); };
    const mine = () => hist.filter(h => h.role === 'me').length;
    async function turn(body) {
      busy(true);
      try { return (await api('/api/next/dialog', { scenario: sid, history: hist, request_id: rid('sp'), ...body })).result; }
      catch (e) { toast(e.message); return null; } finally { busy(false); }
    }
    view.querySelector('#dlgStart').onclick = async e => {
      if (!S.user) { needLogin('登录后可以和 AI 做情景对话。'); return; }
      const btn = e.currentTarget; btn.disabled = true; btn.innerHTML = '<span class="spin"></span>';
      const r = await turn({}); if (!r) { btn.disabled = false; btn.textContent = '开始对话'; return; }
      btn.parentNode.remove();
      chat.insertAdjacentHTML('beforeend', `<div class="scene small">${esc(r.scene)}${r.role ? `（AI 扮演：${esc(r.role)}）` : ''}</div>`);
      bubble('ai', r.reply); TTS.say(r.reply); hist.push({ role: 'ai', text: r.reply });
      view.querySelector('#dlgIn').hidden = false; showInput(); if (!TOUCH) view.querySelector('#dlgText').focus({ preventScroll: true });
    };
    async function send(text, blob) {
      const body = blob ? { audio: await MIC.payload(blob) } : { text };
      const r = await turn(body); if (!r) return;
      const me = r.heard || text;
      bubble('me', me, r.correction ? `<div class="fix tiny"><del>${esc(r.correction.original)}</del> → <b>${esc(r.correction.better)}</b> <span class="muted">${esc(r.correction.why)}</span></div>` : '');
      hist.push({ role: 'me', text: me });
      bubble('ai', r.reply); TTS.say(r.reply); hist.push({ role: 'ai', text: r.reply });
      view.querySelector('#dlgHint').textContent = r.hint ? '提示：' + r.hint : '';
      const n = mine(); view.querySelector('#dlgCount').textContent = n < 4 ? `已经说了 ${n} 句，说到 4 句左右就可以看反馈` : `已经说了 ${n} 句，可以看反馈了`;
      showInput();
    }
    view.querySelector('#dlgSend').onclick = () => { const t = view.querySelector('#dlgText'); const v = t.value.trim(); if (!v) return; t.value = ''; send(v); };
    view.querySelector('#dlgText').addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); view.querySelector('#dlgSend').click(); } });
    const mic = view.querySelector('#dlgMic'); mic.onclick = () => MIC.toggle(mic, 30, b => send('', b));
    view.querySelector('#dlgEnd').onclick = async e => {
      if (mine() < 1) { toast('先说一两句再看反馈'); return; }
      const btn = e.currentTarget; btn.innerHTML = '<span class="spin"></span>';
      const r = await turn({ end: true }); if (!r) { btn.textContent = '结束并看反馈'; return; }
      view.querySelector('#dlgIn').hidden = true; TTS.stop();
      view.querySelector('#dlgOut').innerHTML = `<div class="result enter stack"><div class="card verdict"><span class="dot"></span><div>${esc(r.summary)}</div></div>
        ${r.good.length ? `<div class="stack-s"><b>说得好的句子</b>${r.good.map(g => `<div class="small text">${esc(g)}</div>`).join('')}</div>` : ''}
        ${r.fixes.length ? `<div class="stack-s"><b>要改的地方</b><span class="tiny muted">已经放进错题本，会按遗忘曲线回来。</span>${fixesHTML(r.fixes)}</div>` : ''}
        ${r.expressions.length ? `<div class="stack-s"><b>可以学的表达</b>${r.expressions.map((ex, k) => `<div class="row between small"><span><b>${esc(ex.text)}</b> <span class="muted">${esc(ex.meaning)}</span></span><button class="btn small" data-kx="${k}">收藏</button></div>`).join('')}</div>` : ''}
        <p class="small cheer">${mine() >= 4 ? '完整完成了一个情景。' : ''}敢开口就是进步：说错的地方，正是下次能说对的地方。</p>
        <div class="row"><button class="btn" id="dlgAgain">再练一次</button><a class="btn primary" href="#/speak">下一个情景</a></div></div>`;
      view.querySelectorAll('[data-kx]').forEach(b => b.onclick = () => { const ex = r.expressions[Number(b.dataset.kx)]; saveCard({ text: ex.text, meaning: ex.meaning, context: '', pack: null }, b); });
      view.querySelector('#dlgAgain').onclick = () => { scrollTo({ top: 0 }); speakScene(sid); };
      bringIntoView(view.querySelector('#dlgOut'));
      if (S.user) refreshHome().catch(() => {});
    };
  }
  /* ---------- my progress: this month against the last, and milestones that only count up ---------- */
  async function growthView(month) {
    if (!S.user) return needLogin('登录后可以看到每个月的进步。');
    const d = await api('/api/next/growth' + (month ? '?month=' + encodeURIComponent(month) : ''));
    const n = d.now, b = d.before;
    const cmp = (k, unit) => b[k] == null || n[k] == null ? '' : n[k] > b[k] ? `<span class="up">比上月多 ${(n[k] - b[k]).toLocaleString()}${unit}</span>` : n[k] < b[k] ? `<span class="tiny muted">上月 ${b[k].toLocaleString()}</span>` : '';
    const tile = (k, label, unit) => `<div class="gtile"><b>${n[k] == null ? '—' : n[k].toLocaleString()}</b><span class="tiny muted">${label}</span>${cmp(k, unit)}</div>`;
    const thisMonth = new Date(); const cur = `${thisMonth.getFullYear()}-${String(thisMonth.getMonth() + 1).padStart(2, '0')}`;
    view.innerHTML = `<div class="stack"><div><span class="kicker">我的进步</span><h1 class="h1">${esc(d.label)}</h1><p class="muted small">${esc(d.note)}</p></div>
      <div class="row"><a class="btn small" href="#/growth/${encodeURIComponent(d.prev)}">← 上个月</a>${d.month !== cur ? `<a class="btn small" href="#/growth">回到本月</a>` : ''}<a class="btn small ghost" href="#/report">这周的报告</a></div>
      <div class="gtiles">${tile('days', '学习天数', ' 天')}${tile('words_read', '读了（词）', ' 词')}${tile('materials', '学完的材料', ' 篇')}${tile('wpm', '阅读速度（词/分钟）', '')}
        ${tile('reviews', '复习次数', ' 次')}${tile('new_words', '新学的词', ' 个')}${tile('grammar_checks', '语法做题', ' 题')}${tile('speaking', '开口说', ' 次')}</div>
      <section class="section stack-s"><div class="row between"><h2 class="h2">里程碑</h2><span class="small muted">已达成 ${d.reached} / ${d.total}</span></div>
        <div class="miles">${d.milestones.map((m, k) => `<div class="mile${m.done ? ' done' : ''} pop-in" data-k="${k}"><span class="mi" aria-hidden="true">${m.done ? '✓' : ''}</span>
          <span class="t"><b>${esc(m.title)}</b><span class="vbar"><i data-w="${Math.round(m.have / m.need * 100)}"></i></span><span class="tiny muted">${m.have.toLocaleString()} / ${m.need.toLocaleString()} ${esc(m.unit)}</span></span></div>`).join('')}</div></section></div>`;
    view.querySelectorAll('.pop-in').forEach(el => el.style.setProperty('--d', Math.min(10, Number(el.dataset.k)) * 60 + 'ms'));
    requestAnimationFrame(() => requestAnimationFrame(() => view.querySelectorAll('.vbar i').forEach(i => { i.style.width = i.dataset.w + '%'; })));
  }
  /* ---------- ability radar: six skills against the learner's own goals, and what moved ---------- */
  const DIM_TEST = { vocab: '#/vocab/test', grammar: '#/placement', reading: '#/radar/test/reading', listening: '#/radar/test/listening', speaking: '#/radar/test/speaking', writing: '#/radar/test/writing' };
  const CONF = { high: '测评', medium: '估计', low: '粗略估计' };
  function radarSVG(dims, prev) {
    const W = 320, C = 160, R = 112, n = dims.length;
    const pt = (k, v) => { const a = -Math.PI / 2 + k * 2 * Math.PI / n, r = R * Math.max(0, Math.min(100, v)) / 100; return [C + r * Math.cos(a), C + r * Math.sin(a)]; };
    const poly = vals => vals.map((v, k) => pt(k, v).map(x => x.toFixed(1)).join(',')).join(' ');
    const rings = [25, 50, 75].map(v => `<polygon class="rg" points="${poly(dims.map(() => v))}"/>`).join('');
    const axes = dims.map((d, k) => { const [x, y] = pt(k, 100); return `<line class="ax" x1="${C}" y1="${C}" x2="${x.toFixed(1)}" y2="${y.toFixed(1)}"/>`; }).join('');
    const labels = dims.map((d, k) => { const [x, y] = pt(k, 128); const anchor = Math.abs(x - C) < 8 ? 'middle' : x > C ? 'start' : 'end';
      return `<text class="lb" x="${x.toFixed(1)}" y="${(y + 4).toFixed(1)}" text-anchor="${anchor}">${esc(d.label)}<tspan class="sc" dx="4">${d.score == null ? '?' : d.score}</tspan></text>`; }).join('');
    const cur = dims.map(d => d.score == null ? 0 : d.score);
    const dots = dims.map((d, k) => { const [x, y] = pt(k, cur[k]); return `<circle class="dt${d.score == null ? ' none' : ''}" cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="${d.score == null ? 3 : 4.5}"/>`; }).join('');
    return `<svg class="radar" viewBox="-40 0 400 ${W}" role="img" aria-label="能力雷达：${dims.map(d => d.label + (d.score == null ? '暂无数据' : ' ' + d.score + ' 分')).join('，')}">
      ${rings}${axes}<polygon class="goal" points="${poly(dims.map(() => 100))}"/>
      ${prev ? `<polygon class="prev" points="${poly(dims.map(d => prev[d.id] == null ? 0 : prev[d.id]))}"/>` : ''}
      <g class="cur"><polygon class="area" points="${poly(cur)}"/>${dots}</g>${labels}</svg>`;
  }
  function spark(vals) {
    const xs = vals.filter(v => v != null); if (xs.length < 2) return '';
    const pts = vals.map((v, k) => v == null ? null : `${(k / (vals.length - 1) * 60).toFixed(1)},${(18 - v / 100 * 16).toFixed(1)}`).filter(Boolean).join(' ');
    return `<svg class="spark" viewBox="0 0 60 20" aria-hidden="true"><polyline points="${pts}"/></svg>`;
  }
  async function radarView() {
    if (!S.user) return needLogin('登录后可以设定目标、做能力测评，看到自己每一项离目标还差多少。');
    const r = await api('/api/next/radar');
    const prev = r.before ? (r.history.find(h => h.created === r.before) || {}).scores : null;
    const known = r.dims.filter(d => d.score != null);
    view.innerHTML = `<div class="stack"><div><span class="kicker">能力雷达</span><h1 class="h1">离目标还差多少</h1><p class="muted small">${esc(r.note)}</p></div>
      ${r.goals_chosen ? '' : `<a class="card flat place-cta" href="#/radar/goals"><b>先定一个目标</b><span class="small muted">每一项想到什么水平？现在先按比你的水平高一级来算，可以随时改。</span></a>`}
      <div class="radar-box">${radarSVG(r.dims, prev)}
        <div class="radar-legend tiny"><span class="lg goal">目标（100 分）</span>${prev ? '<span class="lg prev">上次</span>' : ''}<span class="lg cur">现在</span></div></div>
      ${known.length < r.dims.length ? `<p class="small">${r.dims.length - known.length} 项还没有足够的数据。做一次测评，雷达图就完整了。</p>` : ''}
      <div class="row"><a class="btn primary" href="#/radar/test">${r.due.length ? `做测评（${r.due.length} 项该测了）` : '再测一次'}</a><a class="btn" href="#/radar/goals">调整目标</a></div>
      <section class="stack-s section">${r.dims.map((d, k) => { const delta = d.score != null && d.prev_score != null ? d.score - d.prev_score : null;
        return `<div class="rdim pop-in" data-k="${k}"><div class="row between"><b>${esc(d.label)}</b><span class="tiny muted">目标 ${esc(d.goal)}</span></div>
          ${d.score == null ? `<div class="small muted">还没有数据 · <a class="link" href="${DIM_TEST[d.id]}">测一测</a></div>` : `
          <div class="rbar"><span class="vbar"><i data-w="${d.score}"></i></span><b class="num">${d.score}</b>${delta ? `<span class="${delta > 0 ? 'up' : 'down'}">${delta > 0 ? '+' : ''}${delta}</span>` : ''}${spark(r.history.map(h => h.scores[d.id]))}</div>
          <div class="tiny muted">现在约 ${esc(d.level)} · ${CONF[d.confidence] || ''}${d.assessed ? '（' + new Date(d.assessed * 1000).toLocaleDateString('zh-CN') + ' 测评）' : '（来自平时练习）'}
            · <a class="link" href="${DIM_TEST[d.id]}">${d.due ? '该测了' : '重测'}</a>${r.gap === d.id ? ` · <a class="link" href="${d.href}">差距最大：${esc(d.tip)}</a>` : ''}</div>`}</div>`; }).join('')}</section>
      ${r.gap ? `<p class="small cheer">${esc(r.dims.find(d => d.id === r.gap).label)}离目标最远，每天的计划会多安排这方面的练习。</p>` : ''}
      <details class="card flat fold" id="abFold"><summary><b>按平时练习估计</b><span class="tiny muted">近 45 天 · 8 项，含翻译和发音</span></summary><div id="abSlot"><p class="muted small"><span class="spin"></span></p></div></details></div>`;
    view.querySelectorAll('.pop-in').forEach(el => el.style.setProperty('--d', Number(el.dataset.k) * 60 + 'ms'));
    // What used to be the 能力画像 card on 我的: loaded when it is opened.
    const fold = document.getElementById('abFold');
    fold.addEventListener('toggle', () => {
      if (!fold.open || fold.dataset.done) return;
      fold.dataset.done = '1';
      api('/api/next/ability').then(ab => {
        const slot = document.getElementById('abSlot'); if (!slot) return;
        slot.innerHTML = abilityHTML(ab);
        requestAnimationFrame(() => requestAnimationFrame(() => slot.querySelectorAll('.vbar i').forEach(i => { i.style.width = i.dataset.w + '%'; })));
      }).catch(e => { const slot = document.getElementById('abSlot'); if (slot) slot.innerHTML = `<p class="muted small">${esc(e.message)}</p>`; delete fold.dataset.done; });
    });
    requestAnimationFrame(() => requestAnimationFrame(() => { view.querySelectorAll('.vbar i').forEach(i => { i.style.width = i.dataset.w + '%'; }); const g = view.querySelector('.radar .cur'); if (g) g.classList.add('on'); }));
  }
  async function radarGoals() {
    if (!S.user) return needLogin('登录后可以设定目标。');
    const r = await api('/api/next/radar'), g = { ...r.goals }, LV = { A2: '入门', B1: '中级', B2: '中高级', C1: '高级' };
    const draw = () => {
      view.innerHTML = `<div class="stack"><div><a class="link small" href="#/radar">← 能力雷达</a></div><div><span class="kicker">设定目标</span><h1 class="h1">每一项想到什么水平？</h1>
          <p class="muted small">目标就是雷达图上的 100 分。可以每项不一样，比如“口语到 B1，阅读到 B2”。</p></div>
        <div class="row"><span class="small muted">全部设为</span>${r.goal_levels.map(l => `<button class="chip" data-all="${l}">${l}</button>`).join('')}</div>
        ${r.dims.map(d => `<div class="stack-s goal-row"><b>${esc(d.label)}</b><div class="chips">${r.goal_levels.map(l => `<button class="chip" data-d="${d.id}" data-l="${l}" aria-pressed="${g[d.id] === l}">${l} ${LV[l]}</button>`).join('')}</div></div>`).join('')}
        <button class="btn primary block" id="gSave">保存目标</button></div>`;
      view.querySelectorAll('[data-d]').forEach(b => b.onclick = () => { g[b.dataset.d] = b.dataset.l; draw(); });
      view.querySelectorAll('[data-all]').forEach(b => b.onclick = () => { r.dims.forEach(d => { g[d.id] = b.dataset.all; }); draw(); });
      document.getElementById('gSave').onclick = async e => { e.currentTarget.disabled = true; try { await api('/api/next/radar/goals', { goals: g }); toast('目标已保存'); location.hash = '#/radar'; } catch (x) { toast(x.message); e.currentTarget.disabled = false; } };
    };
    draw();
  }
  async function radarTests() {
    if (!S.user) return needLogin('登录后可以做能力测评。');
    const r = await api('/api/next/radar');
    const MIN = { vocab: 3, grammar: 5, reading: 6, listening: 8, speaking: 3, writing: 10 };
    view.innerHTML = `<div class="stack"><div><a class="link small" href="#/radar">← 能力雷达</a></div><div><span class="kicker">能力测评</span><h1 class="h1">选一项，测 3–10 分钟</h1>
        <p class="muted small">不用一次测完。建议每 4 周测一轮，雷达图会把两次的变化画出来。</p></div>
      <div class="plist">${r.dims.map(d => `<a class="nrow ${d.due ? 'st st-untouched' : 'st st-solid'}" href="${DIM_TEST[d.id]}"><i class="dot" aria-hidden="true"></i>
        <span class="t"><b>${esc(d.label)}</b><span class="tiny muted">约 ${MIN[d.id]} 分钟 · ${d.assessed ? '上次 ' + new Date(d.assessed * 1000).toLocaleDateString('zh-CN') : '还没测过'}${d.due ? ' · 该测了' : ''}</span></span><span></span><span class="go" aria-hidden="true">›</span></a>`).join('')}</div>
      <p class="tiny muted">词汇用词汇量测试，语法用起点小测；阅读和听力各有 2–3 段短文；口语录一段回答、写作写一小段，由 AI 按 CEFR 描述评分。</p></div>`;
  }
  async function assessComprehension(kind) {
    if (!S.user) return needLogin('登录后可以做能力测评。');
    const t = await api('/api/next/assess/test?kind=' + kind), answers = [];
    let k = 0, plays = 0;
    const name = kind === 'reading' ? '阅读' : '听力';
    const show = () => {
      const p = t.passages[k]; plays = 0;
      view.innerHTML = `<div class="stack"><div class="row between"><span class="kicker">${name}测评 · 第 ${k + 1} / ${t.passages.length} 段</span><span class="pill">${esc(p.level)}</span></div>
        ${kind === 'reading' ? `<h2 class="h2">${esc(p.title)}</h2><div class="exam-passage">${esc(p.body)}</div>` :
          `<p class="small muted">听一段录音，然后回答两道题。最多听两遍，听的时候看不到原文。</p><button class="btn primary block" id="aPlay">▶ 播放录音</button><p class="tiny muted" id="aPlays"></p>`}
        <div id="aQs" ${kind === 'listening' ? 'hidden' : ''}>${p.questions.map(q => `<div class="q gq" data-i="${q.i}"><div class="prompt">${esc(q.prompt)}</div>
          ${q.options.map((o, j) => `<button class="ans" data-o="${j}"><span class="k">${'ABCD'[j]}</span><span>${esc(o)}</span></button>`).join('')}</div>`).join('')}
          <button class="btn primary block" id="aNext" disabled>${k + 1 < t.passages.length ? '下一段' : '交卷，看结果'}</button></div></div>`;
      const chosen = {};
      view.querySelectorAll('.gq').forEach(box => box.querySelectorAll('.ans').forEach(b => b.onclick = () => {
        box.querySelectorAll('.ans').forEach(x => x.classList.toggle('chosen', x === b)); chosen[box.dataset.i] = Number(b.dataset.o);
        document.getElementById('aNext').disabled = Object.keys(chosen).length < p.questions.length;
      }));
      const play = document.getElementById('aPlay');
      // The recording is loaded before the tap, so the tap itself starts the sound (WeChat's browser allows only that).
      const voices = p.audio.voices || [];
      const loading = voices.length ? NAR.load(p.pack, voices.includes(S.voice) ? S.voice : voices[0], p.audio.version) : Promise.resolve(false);
      let loaded = null; loading.then(ok => { loaded = ok; });
      if (play) play.onclick = async () => {
        if (plays >= 2) return; plays++; play.disabled = true; play.textContent = '正在播放…';
        const done = () => { play.disabled = plays >= 2; play.textContent = plays >= 2 ? '已经听了两遍' : '▶ 再听一遍'; document.getElementById('aQs').hidden = false; document.getElementById('aPlays').textContent = `已听 ${plays} / 2 遍`; };
        if (loaded === true || (loaded === null && await loading)) NAR.play(0, null, null, done);
        else TTS.say(p.body.replace(/^[A-Z][a-z]+(?: [A-Z][a-z]+)?:\s+/gm, ''), done);
      };
      document.getElementById('aNext').onclick = async () => {
        NAR.stop(); TTS.stop();
        p.questions.forEach(q => answers.push({ pack: p.pack, i: q.i, choice: chosen[q.i] }));
        if (++k < t.passages.length) { window.scrollTo(0, 0); show(); return; }
        let r; try { r = await api('/api/next/assess/comprehension', { kind, answers }); } catch (e) { toast(e.message); return; }
        assessResult(name, r.recorded, `<div class="stack-s">${Object.entries(r.levels).map(([lv, x]) => `<div class="row between small"><span>${lv} 难度</span><span>${x.right} / ${x.of}</span></div>`).join('')}</div>`);
      };
    };
    if (!t.passages.length) { view.innerHTML = '<div class="empty"><p>暂时没有合适的测评材料。</p><a class="btn" href="#/radar/test">返回</a></div>'; return; }
    show();
  }
  async function assessJudged(kind) {
    if (!S.user) return needLogin('登录后可以做能力测评。');
    const t = await api('/api/next/assess/task?kind=' + kind), name = kind === 'speaking' ? '口语' : '写作';
    view.innerHTML = `<div class="stack"><div><a class="link small" href="#/radar/test">← 能力测评</a></div>
      <div><span class="kicker">${name}测评 · ${esc(t.level)}</span><h1 class="h1">${esc(t.question)}</h1><p class="small">${esc(t.task)}</p><p class="tiny muted">${esc(t.limit)}。AI 按 CEFR 描述从四个方面评分，不看话题难易${kind === 'speaking' ? '，口音不扣分' : ''}。</p></div>
      ${kind === 'speaking' ? `<div class="row center">${recBtn('aMic', '开始回答')}<span class="small" id="aState">点 ● 开始说，说完再点一下结束</span></div>` :
        `<textarea id="aText" aria-label="你的英文回答" rows="9" lang="en" placeholder="用英文写……" autocapitalize="sentences" spellcheck="false"></textarea><div class="row between"><span class="tiny muted" id="aCount">0 词</span><button class="btn primary" id="aGo">提交</button></div>`}
      <div id="aOut"></div></div>`;
    const send = async body => {
      const out = document.getElementById('aOut'); out.innerHTML = '<p class="loading"><span class="spin"></span> AI 正在评估…</p>';
      try {
        const x = (await api('/api/next/assess/' + kind, { question: t.question, request_id: rid('as'), ...body })).result;
        const DIMN = kind === 'speaking' ? { fluency: '流利度', accuracy: '准确度', range: '词汇句式', pronunciation: '发音清晰度' } : { content: '内容切题', organization: '结构衔接', accuracy: '语言准确', range: '词汇句式' };
        assessResult(name, x.recorded, `${x.transcript ? `<div class="small"><span class="muted">AI 听到的：</span>${esc(x.transcript)}</div>` : ''}
          <div class="ab-list">${Object.entries(x.scores).map(([k2, v]) => `<div class="ab"><span class="nm">${DIMN[k2] || k2}</span><span class="vbar"><i data-w="${v * 20}"></i></span><span class="lv">${v} / 5</span></div>`).join('')}</div>
          ${x.strength ? `<div class="small"><span class="ok">做得好：</span>${esc(x.strength)}</div>` : ''}${(x.next || []).map(s => `<div class="small">· ${esc(s)}</div>`).join('')}`);
      } catch (e) { out.innerHTML = ''; toast(e.message); }
    };
    if (kind === 'speaking') {
      const mic = document.getElementById('aMic'), st = document.getElementById('aState');
      mic.onclick = () => { st.textContent = MIC.busy() ? '' : '正在录音，说完再点一下'; MIC.toggle(mic, 75, async blob => { st.textContent = ''; send({ audio: await MIC.payload(blob) }); }); };
    } else {
      const ta = document.getElementById('aText'), cnt = document.getElementById('aCount');
      ta.oninput = () => { cnt.textContent = (ta.value.match(/[A-Za-z]+(?:'[A-Za-z]+)?/g) || []).length + ' 词'; };
      document.getElementById('aGo').onclick = () => send({ text: ta.value });
    }
  }
  function assessResult(name, rec, detail) {
    view.innerHTML = `<div class="stack"><div class="done-burst" aria-hidden="true">${doneRing}</div>
      <div class="tc"><span class="kicker">${esc(name)}测评结果</span><h1 class="h1">${rec ? `约 ${esc(rec.level)} · ${rec.score} 分` : '已完成'}</h1>
        ${rec ? `<p class="small muted">目标 ${esc(rec.goal)} = 100 分。这是一次测评的估计，和平时练习结合起来看更准。</p>` : ''}</div>
      ${detail}<div class="row center"><a class="btn" href="#/radar/test">测别的项目</a><a class="btn primary" href="#/radar">看雷达图</a></div></div>`;
    requestAnimationFrame(() => requestAnimationFrame(() => view.querySelectorAll('.vbar i').forEach(i => { i.style.width = i.dataset.w + '%'; })));
    if (S.user) refreshHome().catch(() => {});
  }
  /* ---------- 操作指南: the same source as the PDF (flow/public/guide/guide.md, rendered by user_guide.py) ---------- */
  async function guideView(id) {
    if (!S.guide) S.guide = await api('/api/next/guide');
    const g = S.guide;
    view.innerHTML = `<h1 class="h1">操作指南</h1><p class="muted small">${esc(g.updated)} · 从第一次打开到每一个页面，一步一步讲清楚。</p>
      <div class="row">${g.pdf ? `<a class="btn small primary" href="${g.pdf}" download="语流操作指南.pdf">下载 PDF 版</a>` : ''}<a class="btn small" href="#/practice">去练习</a></div>
      <label class="field section"><span class="sr-only">在指南里搜索</span><input class="guide-search" id="gq" type="search" placeholder="搜一搜：比如 复习、录音、提醒" autocomplete="off"></label>
      <nav class="card flat guide-toc" id="gtoc" aria-label="指南目录">${g.chapters.map((ch, k) => `<a href="#/guide/${ch.id}" data-ch="${ch.id}"><span class="n">${k + 1}</span><span>${esc(ch.title)}</span></a>`).join('')}</nav>
      <p class="muted small" id="gnone" hidden>没有找到，换个词试试，或者看看「常见问题」。</p>
      <div class="guide-body">${g.chapters.map((ch, k) => `<section id="g-${ch.id}" data-ch="${ch.id}"><h2>${k + 1}. ${esc(ch.title)}</h2>${ch.html}</section>`).join('')}</div>
      <div class="section row"><a class="btn small" href="#/guide">回到目录</a>${g.pdf ? `<a class="btn small" href="${g.pdf}" download="语流操作指南.pdf">下载 PDF 版</a>` : ''}</div>`;
    const q = document.getElementById('gq'), none = document.getElementById('gnone');
    q.oninput = () => {
      const t = q.value.trim().toLowerCase();
      let shown = 0;
      g.chapters.forEach(ch => {
        const hit = !t || ch.text.toLowerCase().includes(t) || ch.title.toLowerCase().includes(t);
        view.querySelectorAll(`[data-ch="${ch.id}"]`).forEach(el => { el.hidden = !hit; });
        if (hit) shown++;
      });
      none.hidden = shown > 0;
    };
    if (id) {
      const sec = document.getElementById('g-' + id);
      if (sec) requestAnimationFrame(() => sec.scrollIntoView({ block: 'start' }));
    }
  }

  /* ---------- 练习: every kind of practice in one place, grouped by skill, with one suggestion on top ---------- */
  // Each tile: [href, title, one line on what it is for, extra]. The guide (#/guide) explains each one step by step.
  // extra 'due' adds the review count; 'map' makes the tile the grammar map's wide card (the map has no tab of its own).
  const PRACTICE = [
    ['语法', [  // first: the map used to be a tab of its own, so it is on the first screen
      ['#/graph', '知识图谱', '44 个语法点按顺序连成路线，点亮一个学一个', 'map'],
      ['#/mix', '混合练习', '几个语法点打乱一起练，记得更牢'],
      ['#/placement', '语法起点小测', '16 题定出你的语法起点']]],
    ['听和读', [
      ['#/', '今天的材料', '听一遍、读一遍、答几题、用出来，每天 10–20 分钟'],
      ['#/easy', '轻松读', '读比你低一级的短文，练速度、攒阅读量'],
      ['#/library', '全部材料', '按话题和级别挑一篇来学'],
      ['#/import', '我的文章', '贴一段任何英文，变成可以学的材料']]],
    ['说和写', [
      ['#/speak', '口语路线', '12 个生活和校园情景，和 AI 对话'],
      ['#/sounds', '发音入门', '中国学习者容易混的音，听辨再跟读']]],
    ['单词', [
      ['#/review', '复习单词', '到期的词和错过的题，一张张过', 'due'],
      ['#/words/confuse', '词汇辨析', '最容易混的词放在一起练'],
      ['#/cards/mistake', '错题本', '做错过的词和题都在这里'],
      ['#/vocab/plan', '词书和每天新词', '换词书、改每天学多少'],
      ['#/vocab/test', '词汇量测试', '5 分钟估一估你认识多少词']]],
    ['考试和测评', [
      ['#/exam', '考试练习', '中考高考、四六级、考研、专四专八、雅思，限时做'],
      ['#/radar', '能力雷达', '六项能力对照你的目标，定期测一测']]],
    ['看进步', [
      ['#/report', '这周的报告', '这周学了什么、哪里进步了'],
      ['#/growth', '我的进步', '这个月和上个月比，里程碑']]]];

  const PICON = {
    '#/mix': '<path d="M4 7h3l10 10h3"/><path d="M4 17h3l2.5-2.5"/><path d="M14.5 9.5 17 7h3"/><path d="m18 5 2 2-2 2"/><path d="m18 15 2 2-2 2"/>',
    '#/placement': '<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="3.5"/>',
    '#/': '<rect x="4" y="5" width="16" height="15" rx="2"/><path d="M4 10h16M9 3v4m6-4v4"/>',
    '#/easy': '<path d="M5 19c8 0 14-6 14-14-8 0-14 6-14 14z"/><path d="m5 19 8-8"/>',
    '#/library': '<rect x="4" y="4" width="7" height="7" rx="1.5"/><rect x="13" y="4" width="7" height="7" rx="1.5"/><rect x="4" y="13" width="7" height="7" rx="1.5"/><rect x="13" y="13" width="7" height="7" rx="1.5"/>',
    '#/import': '<path d="M6 3h8l4 4v14H6z"/><path d="M14 3v4h4M12 11v6m-3-3h6"/>',
    '#/speak': '<path d="M4 5h16v11H9l-5 4z"/>',
    '#/sounds': '<path d="M12 4a3 3 0 0 1 3 3v5a3 3 0 0 1-6 0V7a3 3 0 0 1 3-3z"/><path d="M6 11a6 6 0 0 0 12 0M12 17v3"/>',
    '#/review': '<path d="M20 12a8 8 0 1 1-2.3-5.6"/><path d="M20 4v5h-5"/>',
    '#/words/confuse': '<circle cx="9" cy="12" r="5.5"/><circle cx="15" cy="12" r="5.5"/>',
    '#/cards/mistake': '<path d="M6 3h12v18H6z"/><path d="m9.5 9.5 5 5m0-5-5 5"/>',
    '#/vocab/plan': '<path d="M5 5a2 2 0 0 1 2-2h11v15H7a2 2 0 0 0-2 2z"/><path d="M5 20a2 2 0 0 0 2 1h11v-3"/>',
    '#/vocab/test': '<path d="M4 17a8 8 0 0 1 16 0"/><path d="m12 17 4-5"/>',
    '#/exam': '<circle cx="12" cy="13" r="7"/><path d="M12 9v4l3 2M10 3h4"/>',
    '#/radar': '<path d="M12 3 20 8v8l-8 5-8-5V8z"/><path d="m12 8 4 3-1.5 5h-5L8 11z"/>',
    '#/report': '<path d="M5 20V10m5 10V5m5 15v-7m5 7V8"/>',
    '#/growth': '<path d="m4 17 6-6 4 4 6-7"/><path d="M15 8h5v5"/>'};
  // One row per practice (icon, title, one line on what it is for): a phone shows a whole group at a glance.
  const practiceRow = ([href, title, line, badge], due) => `<a class="px-row" href="${href}"><span class="pico" aria-hidden="true"><svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${PICON[href] || ''}</svg></span>
    <span class="t"><b>${title}${badge === 'due' && due ? ` <i class="pbadge">${due > 99 ? '99+' : due}</i>` : ''}</b><span class="tiny muted">${line}</span></span><span class="go" aria-hidden="true">›</span></a>`;

  async function practiceView() {
    const st = S.home && S.home.stats, due = st ? (st.due || 0) + (st.new || 0) : 0;
    view.innerHTML = `<h1 class="h1">练习</h1>
      <p class="muted small">想练哪一项，就从这里进。不知道先练什么，看最上面的建议。</p>
      <div id="pSuggest">${practiceTip(null, due)}</div>
      ${PRACTICE.map(([group, items]) => `<section class="pgroup stack-s"><h2 class="h2 pgroup-h">${group}</h2>
        ${items.filter(x => x[3] === 'map').map(([href, title, line]) => mapTile(href, title, line)).join('')}
        <div class="px-list">${items.filter(x => x[3] !== 'map').map(x => practiceRow(x, due)).join('')}</div></section>`).join('')}
      <a class="card flat place-cta guide-cta" href="#/guide"><b>第一次用？看操作指南</b><span class="small muted">每个页面怎么用、按哪里、学完去哪，一步一步讲清楚；也可以下载 PDF。</span></a>`;
    requestAnimationFrame(() => requestAnimationFrame(() => view.querySelectorAll('.gbar i').forEach(i => { i.style.width = i.dataset.w + '%'; })));
    if (S.user) api('/api/next/radar').then(r => {
      const el = document.getElementById('pSuggest'); if (el && r && r.gap) el.innerHTML = practiceTip(r, due);
    }).catch(() => { /* the plain suggestion stays */ });
  }
  // The grammar map, as wide as the row: how much of it is lit, and what needs a look first.
  function mapTile(href, title, line) {
    const g = S.home && S.home.graph, total = g ? g.total : 44, lit = g ? total - g.untouched : 0;
    const look = g && g.watch.length ? '需要留意：' + g.watch.map(w => esc(w.title)).join('、') : g && g.due && g.due.length ? '该复习：' + g.due.map(w => esc(w.title)).join('、') : line;
    return `<a class="ptile pmap card flat" href="${href}" data-tap="practice-map"><span class="row between"><b>${title}</b>${g ? `<span class="pill green">已点亮 ${lit} / ${total}</span>` : ''}</span>
      <span class="small muted">${look}</span>
      ${g ? `<span class="gbar" aria-hidden="true">${['solid', 'used', 'met', 'watch'].map(k => `<i class="st st-${k}" data-w="${g[k] / total * 100}"></i>`).join('')}</span>` : ''}</a>`;
  }
  function practiceTip(radar, due) {
    const d = radar && radar.dims.find(x => x.id === radar.gap);
    if (d) return `<a class="card psuggest" data-tap="practice-tip" href="${esc(d.href)}"><span class="tiny">今天建议</span><b>${esc(d.label)}离目标最远（${d.score} 分）</b><span class="small">${esc(d.tip)}</span><span class="btn small primary">去练 ${esc(d.label)}</span></a>`;
    if (due) return `<a class="card psuggest" data-tap="practice-tip" href="#/review"><span class="tiny">今天建议</span><b>有 ${due} 个词等你复习</b><span class="small">先复习再学新的，记得最牢。</span><span class="btn small primary">开始复习</span></a>`;
    return `<a class="card psuggest" data-tap="practice-tip" href="#/"><span class="tiny">今天建议</span><b>先做今天的计划</b><span class="small">今日页已经按你的水平排好了顺序。</span><span class="btn small primary">打开今日</span></a>`;
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
  // The 单词 page's tool row: [link or button id, label, icon paths].
  const WORD_TOOLS = [
    ['#/vocab/plan', '词书计划', '<path d="M5 5a2 2 0 0 1 2-2h11v15H7a2 2 0 0 0-2 2z"/><path d="M5 20a2 2 0 0 0 2 1h11v-3"/>'],
    ['#/words/confuse', '辨析', '<circle cx="9" cy="12" r="5.5"/><circle cx="15" cy="12" r="5.5"/>'],
    ['#/cards/mistake', '错题本', '<path d="M6 3h12v18H6z"/><path d="m9.5 9.5 5 5m0-5-5 5"/>'],
    ['#/vocab/test', '测词汇量', '<path d="M4 17a8 8 0 0 1 16 0"/><path d="m12 17 4-5"/>'],
    ['imp', '导入', '<path d="M12 3v11m-4-4 4 4 4-4"/><path d="M5 15v5h14v-5"/>']];
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
            ${n ? '<a class="btn primary" href="#/review">开始</a>' : '<button class="btn small" id="moreNew">再学 10 个</button>'}</div>
          ${o.book ? `<div class="stack-s"><div class="row between small"><span>《${esc(o.book.title)}》已学 ${o.book.started} / ${o.book.size - (o.book.skipped || 0)}${o.book.skipped ? `<span class="muted">（跳过 ${o.book.skipped} 个常用词）</span>` : ''}</span></div>
            <div class="vbar"><i data-w="${o.book.started / Math.max(1, o.book.size - (o.book.skipped || 0)) * 100}"></i></div></div>` : ''}
          <span class="tiny muted">${o.book ? (o.book.finish ? '预计 ' + dayLabel(o.book.finish) + '学完 · ' : '已全部学过 · ') : ''}每天 ${o.plan.daily_new} 个新词 · 目标记住率 ${Math.round(o.plan.retention * 100)}%</span></div>`
      : `<div class="card section stack-s"><div class="kicker">开始背单词</div><b>选一本词书，每天几个新词，按遗忘曲线复习</b>
          <span class="muted small">例句来自你读的文章，还能听原文录音。不选词书也可以：读文章时点词收藏，收藏的词同样按遗忘曲线复习。</span>
          <div class="row"><a class="btn primary" href="#/vocab/plan">选词书</a><a class="btn" href="#/vocab/test">先测词汇量（约 3 分钟）</a></div>
          ${n ? `<div class="row between small"><span>收藏的词：复习 ${o.due} · 待学 ${o.new}</span><a class="btn small" href="#/review">开始复习</a></div>` : ''}</div>`;
    let statsOpen = false; try { statsOpen = localStorage.getItem('flow-words-stats') === 'open'; } catch (e) { /* private mode */ }
    const est = o.plan && o.plan.estimate;
    const TAP = { '#/vocab/plan': 'words-plan', '#/words/confuse': 'words-confuse', '#/cards/mistake': 'words-mistake', '#/vocab/test': 'words-test', imp: 'words-import' };
    view.innerHTML = `<div><h1 class="h1">单词</h1><span class="muted small">共 ${o.total} 个 · 已掌握 ${o.mastered}</span></div>
      ${today}
      <nav class="tools section" aria-label="单词工具">${WORD_TOOLS.map(([to, label, icon]) => `${to[0] === '#' ? `<a href="${to}" data-tap="${TAP[to]}">` : `<button type="button" id="${to}" data-tap="${TAP[to]}">`}
        <svg viewBox="0 0 24 24" aria-hidden="true">${icon}</svg><span>${label}</span>${to[0] === '#' ? '</a>' : '</button>'}`).join('')}</nav>
      <details class="card flat fold section" id="vStats"${statsOpen ? ' open' : ''}><summary data-tap="words-stats"><b>统计和复习预测</b><span class="tiny muted">已掌握 ${o.mastered} · 学习中 ${o.learning}${est ? ` · 词汇量约 ${est.toLocaleString()}` : ''}</span></summary>
        <div class="stack-s">
        <div class="stat-grid"><div class="card sunk stat"><b>${o.mastered}</b><span class="tiny muted">已掌握</span></div><div class="card sunk stat"><b>${o.learning}</b><span class="tiny muted">学习中</span></div>
          <div class="card sunk stat"><b>${est ? est.toLocaleString() : '—'}</b><span class="tiny muted">${est ? '词汇量估计' : '<a class="link" href="#/vocab/test">测词汇量</a>'}</span></div></div>
        <div class="row between"><b class="small">未来 7 天的复习量</b><span class="tiny muted">按你的记忆情况算出</span></div>
        ${o.forecast.some(Boolean) ? `<div class="forecast" aria-label="未来 7 天复习量">${o.forecast.map((v, k) => { const d = new Date(start.getTime() + k * 864e5); return `<div><span class="n">${v || ''}</span><i data-h="${v / maxF * 100}"></i><span class="tiny muted">${k === 0 ? '今天' : k === 1 ? '明天' : '周' + WEEKDAY[d.getDay()]}</span></div>`; }).join('')}</div>`
          : '<p class="muted tiny">开始学习后，这里会显示每天大约要复习多少个。</p>'}
        <div class="cal" aria-label="最近 5 周每天复习次数">${o.calendar.map(d => `<i class="l${d.n ? Math.min(4, Math.ceil(d.n / maxC * 4)) : 0}" title="${d.day}：${d.n} 次"></i>`).join('')}</div></div></details>
      <form class="searchrow section" id="sf" role="search"><input type="search" name="q" aria-label="搜索单词、意思或原句" enterkeyhint="search" placeholder="搜索单词、意思或原句${TOUCH ? '' : '（按 / 跳到这里）'}" value="${esc(q)}"><button class="btn">搜索</button></form>
      <div class="chips filt" role="group" aria-label="筛选">${[['', '全部'], ['word', '单词'], ['phrase', '表达'], ['mistake', '错题']].map(([k, l]) => `<button class="chip small" data-f="${k}" aria-pressed="${f === k}">${l}</button>`).join('')}</div>
      <div id="listSlot">${listHTML(list, q, page, f)}</div>
      ${o.total ? '<p class="tc section"><button class="link small" type="button" id="wbExport" data-tap="words-export">导出单词本：Excel 表格或 Anki</button></p>' : ''}`;
    requestAnimationFrame(() => requestAnimationFrame(() => {
      view.querySelectorAll('.vbar i').forEach(i => { i.style.width = i.dataset.w + '%'; });
      view.querySelectorAll('.forecast i').forEach(i => { i.style.height = Math.max(3, i.dataset.h) + '%'; });
    }));
    // Filters, search and pages swap only the list: the rest of the page stays put (no reload flash, no lost scroll).
    const mn = document.getElementById('moreNew');
    if (mn) mn.onclick = async () => {  // today's words are done and the learner wants more: one extra batch now
      mn.disabled = true;
      try { const r = await api('/api/next/vocab/more', { n: 10 }); if (r.added) location.hash = '#/review'; else { toast('词书里的词都学过了'); } }
      catch (e) { toast(e.message); mn.disabled = false; }
    };
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
    const wx = document.getElementById('wbExport'); if (wx) wx.onclick = dataSheet;
    const vs = document.getElementById('vStats');
    vs.addEventListener('toggle', () => { try { localStorage.setItem('flow-words-stats', vs.open ? 'open' : ''); } catch (e) { /* private mode */ } });
    bindList();
  }
  function listHTML(list, q, page, f) {
    const pages = Math.max(1, Math.ceil(list.total / list.per));
    const none = q ? '没有找到。' : { word: '还没有单词。选一本词书，或者读文章时点词收藏。', phrase: '还没有收藏的表达。读文章时选中一段文字，或在「地道表达」里点 ☆。',
      mistake: '还没有错题。理解题答错、写作和口语里被改出的错误，都会自动收进来。' }[f] || '还没有单词。选一本词书，或者学一篇材料时点词收藏。';
    const sub = c => c.source === 'mistake' ? '错题 · ' + ({ fix: '改错', question: '理解题', sound: '发音' }[c.kind] || '') + (c.context ? ' · ' + esc(c.context) : '')
      : esc(c.meaning || c.context || SOURCE[c.source] || '');
    return `${list.items.length ? `<div class="xlist" id="clist">${list.items.map(c => `<button class="xrow" type="button" data-card="${c.id}"><span class="t"><span class="x">${esc(c.text)}</span><span class="tiny muted">${sub(c)}</span></span>${recallPill(c)}</button>`).join('')}</div>`
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
      <p class="muted small">每行一个单词或短语（也可以用逗号分开），一次最多 500 个。词典里有的会自动配上释义和例句；已经在复习里的会跳过。适合导入老师给的或自己整理的词表。</p>
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
    // One book in the picker: title, word count and what it is for; a data book (专四、专八…) also says how it was made.
    const bookCard = b => `<div class="bookcell"><button class="card flat bookc" data-book="${esc(b.id)}" aria-pressed="${b.id === book}">
        <span class="bk-top"><b>${esc(b.title)}</b><span class="bk-tags">${b.id === o.suggested_book ? '<span class="pill green">推荐</span>' : ''}<span class="pill bk-on">已选</span><span class="tiny muted bk-n">${(b.count || b.size || 0).toLocaleString()} 词</span></span></span>
        ${b.blurb ? `<span class="small">${esc(b.blurb)}</span>` : ''}${b.range ? `<span class="tiny muted">词频第 ${b.range} 位</span>` : ''}</button>
        ${b.basis ? `<details class="basis"><summary>这份词书怎么来的</summary><p class="tiny muted">${esc(b.basis)}</p></details>` : ''}</div>`;
    view.innerHTML = `<h1 class="h1">背词计划</h1><span class="muted small">随时可以改，已学的进度不会丢。</span>
      <div class="section stack-s"><h2 class="h2">词书</h2>
        ${(o.exam_goals || []).length ? `<div class="stack-s"><span class="small" id="goalQ">你在准备什么考试？点一下就选好对应的词书。</span>
          <div class="chips" id="goal" role="group" aria-labelledby="goalQ">${[{ title: '不考试', book: '' }, ...o.exam_goals].map(g => `<button class="chip" data-goal="${esc(g.book)}" aria-pressed="false">${esc(g.title)}</button>`).join('')}</div></div>` : ''}
        <div class="card flat booksel stack-s"><div class="row between"><span class="small" id="bookNow" aria-live="polite"></span>
          <button class="link small" id="moreBooks" type="button" aria-expanded="false" aria-controls="allBooks">换一本（共 ${o.books.length} 本）</button></div><div id="bookSelInfo"></div></div>
        <div class="bookgroups" id="allBooks" hidden><span class="muted tiny">按词频的词书从你的水平往上走；其他词书按考试或用途分组，点一本就选中。</span>${(o.groups || [...new Set(o.books.map(b => b.group))]).map(g => `<section class="bookgroup" aria-label="${esc(g)}"><div class="kicker">${esc(g)}</div><div class="books">${o.books.filter(b => b.group === g).map(bookCard).join('')}</div></section>`).join('')}</div>
        <section class="bookgroup" aria-label="自己的词表"><div class="kicker">自己的词表</div><div class="books"><button class="card flat bookc" id="impBook" type="button"><b>导入老师给的词表</b><span class="small">把手上的词表粘贴进来，和词书一起按遗忘曲线复习。</span><span class="tiny muted">导入词表 →</span></button></div></section></div>
      <div class="section stack-s"><h2 class="h2">每天新词</h2><div class="chips" id="dn">${o.daily_new_options.map(v => `<button class="chip" data-v="${v}" aria-pressed="${v === daily}">${v} 个</button>`).join('')}</div>
        <div class="row"><label class="small" for="dnOwn">自己定：</label><input id="dnOwn" type="number" inputmode="numeric" min="1" max="200" step="1" class="num-in" value="${o.daily_new_options.includes(daily) ? '' : daily}" placeholder="1–200"><span class="small muted">个 / 天</span></div>
        <span class="muted tiny" id="dnHint"></span><span class="muted tiny">学完当天的，复习页还可以「再学 10 个」，不用改计划。</span></div>
      <div class="section stack-s"><h2 class="h2">目标记住率</h2><div class="chips" id="rt">${o.retention_options.map(v => `<button class="chip" data-v="${v}" aria-pressed="${v === ret}">${Math.round(v * 100)}%</button>`).join('')}</div>
        <span class="muted tiny">系统会在你记住的概率降到这个数时安排复习。越高记得越牢，但每天复习更多；90% 是比较均衡的选择。</span></div>
      ${o.plan && o.plan.estimate ? `<label class="section checkline"><input type="checkbox" id="skipKnown" ${o.plan.skip_rank ? 'checked' : ''}>跳过测试显示你已经认识的常用词${o.plan.test_skip ? `（词频前 ${o.plan.test_skip} 位）` : ''}，按词频的词书不受影响</label>` : ''}
      <div class="section row savebar"><button class="btn primary" id="savePlan">${o.plan ? '保存' : '开始背'}</button><a class="btn ghost" href="#/cards">取消</a></div>
      <div class="section card flat stack-s" id="remind"><h2 class="h2">复习提醒</h2>
        <span class="muted tiny">遗忘曲线最怕"到期没人提醒"。选一个每天方便的时间：</span>
        <div class="row"><select id="rHour" aria-label="提醒时间">${Array.from({ length: 18 }, (_, k) => k + 6).map(h => `<option value="${h}" ${h === o.reminder.hour ? 'selected' : ''}>每天 ${h}:00</option>`).join('')}</select></div>
        <label class="checkline"><input type="checkbox" id="rMail" ${o.reminder.enabled ? 'checked' : ''} ${o.reminder.has_email ? '' : 'disabled'}><span>到点发邮件提醒（只在有词要复习时发）${o.reminder.has_email ? '' : '<br><span class="muted tiny">账号还没绑定邮箱：可以在<a class="link" href="#/me">「我的」</a>里绑定，或者先用下面的日历提醒。</span>'}</span></label>
        <div class="row"><a class="btn small" id="rCal" href="/api/next/vocab/reminder.ics?hour=${o.reminder.hour}">加到手机日历</a><span class="muted tiny">日历每天到点提醒，不依赖任何 App</span></div></div>`;
    const meta = id => o.books.find(b => b.id === id) || {};
    // Days left: words not yet studied, minus the ones this plan skips (everyday words; for exam and data books, what the test showed you know).
    const hint = () => {
      const sk = document.getElementById('skipKnown'), b = meta(book);
      const skip = book === 'core' || (sk ? sk.checked : true) ? (b.skippable || 0) : 0;
      const done = o.book && o.book.id === book ? o.book.started : 0;
      const days = Math.ceil(Math.max(0, (b.size || 0) - skip - done) / daily);
      document.getElementById('bookNow').textContent = b.title ? `已选《${b.title}》，${(b.count || b.size || 0).toLocaleString()} 词` : '还没选词书';
      document.getElementById('bookSelInfo').innerHTML = b.title ? `${b.blurb ? `<span class="small">${esc(b.blurb)}</span>` : ''}${book === o.suggested_book ? ' <span class="pill green">推荐</span>' : ''}
        ${b.basis ? `<details class="basis"><summary>这份词书怎么来的</summary><p class="tiny muted">${esc(b.basis)}</p></details>` : ''}` : '<span class="small muted">点上面的考试，或点「换一本」挑一本。</span>';
      document.getElementById('dnHint').textContent = !b.title ? '先在上面选一本词书。' : `学完《${b.title}》大约需要 ${days} 天${skip ? `（跳过 ${skip} 个常用词）` : ''}；每天 ${daily} 个新词，一个月后每天大约要复习 ${daily * 3}–${daily * 5} 个${daily >= 50 ? '，量很大，记得留出时间' : ''}。`;
    };
    // The exam chips follow the chosen book: its exam, or 「不考试」 for a book by frequency; another book (学术、商务…) lights none.
    const syncGoal = () => view.querySelectorAll('[data-goal]').forEach(x => x.setAttribute('aria-pressed', String(x.dataset.goal ? x.dataset.goal === book : meta(book).group === '按词频')));
    const choose = id => { book = id; view.querySelectorAll('[data-book]').forEach(x => x.setAttribute('aria-pressed', String(x.dataset.book === id))); syncGoal(); hint(); };
    view.querySelectorAll('[data-book]').forEach(b => b.onclick = () => choose(b.dataset.book));
    view.querySelectorAll('[data-goal]').forEach(b => b.onclick = () => choose(b.dataset.goal || o.suggested_book));
    const more = document.getElementById('moreBooks'), all = document.getElementById('allBooks');
    more.onclick = () => { const open = all.hidden; all.hidden = !open; more.setAttribute('aria-expanded', String(open)); more.textContent = open ? '收起' : `换一本（共 ${o.books.length} 本）`; };
    syncGoal();
    const pick = (sel, set) => view.querySelectorAll(sel + ' [data-v]').forEach(b => b.onclick = () => { set(Number(b.dataset.v)); view.querySelectorAll(sel + ' [data-v]').forEach(x => x.setAttribute('aria-pressed', String(x === b))); hint(); });
    pick('#dn', v => { daily = v; document.getElementById('dnOwn').value = ''; }); pick('#rt', v => { ret = v; });
    document.getElementById('dnOwn').oninput = e => {
      const v = Math.round(Number(e.target.value));
      if (v >= 1 && v <= 200) { daily = v; view.querySelectorAll('#dn [data-v]').forEach(x => x.setAttribute('aria-pressed', String(Number(x.dataset.v) === v))); hint(); }
    };
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
      document.onkeydown = null; swipeOff(); document.body.classList.remove('reviewing');
      view.innerHTML = `<p class="loading"><span class="spin"></span> 正在估算…</p>`;
      const r = await api('/api/next/vocab/test', { answers });
      if (!S.user) save('flow-next-guest-test', { answers, at: Date.now() });  // kept, and saved to the account after signing in
      const o = S.user ? await api('/api/next/vocab') : null;
      const titles = r.titles || {}, title = titles[r.suggest] || r.suggest;
      view.innerHTML = `<div class="card done-card enter stack"><div class="kicker">词汇量估计</div><div class="huge">${r.estimate.toLocaleString()}</div>
        <p class="muted small">${r.guessing ? '你选了不少假词，估计可能偏高，已经按比例扣除。' : '按词频分段抽样估算，误差约几百词。'}</p>
        <div class="vt-bands">${Object.entries(r.bands).map(([k, v]) => `<div class="row between small"><span>${esc(titles[k] || k)}</span><span class="vbar"><i data-w="${v * 100}"></i></span><span class="muted">${Math.round(v * 100)}%</span></div>`).join('')}</div>
        <p>${r.ceiling ? `常用的 2 万词你几乎都认识，超出了这个测试能测的范围。建议用《${esc(title)}》这类考试词表${o && o.books.some(b => b.group === '英语专业') ? '，或在「背词计划」里选英语专业的词书' : ''}，也可以导入自己的词表。` : `建议从《${esc(title)}》开始。`}</p>
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
    swipeOn(() => (i < items.length ? { right: () => answer(true), left: () => answer(false) } : null));  // as on the buttons: ← 不认识, 认识 →
    show();
  }

  /* ---------- review: recognise -> recall -> spell as an item gets stronger ---------- */
  // Swiping a card (the review, the vocabulary test): right and left call what acts() returns at that moment
  // ({ right, left }, either may be missing). The whole screen takes the swipe, not only the card: on a wide screen (an
  // iPad sideways) the card is a column in the middle and the thumb rests beside it, or below it. Not from a link or a
  // field, and not while a sheet is open. A swipe is mostly sideways, without a strict
  // height limit (on a big screen it drifts). Leaving the page takes it off (swipeOff, in route()).
  function swipeOn(acts) {
    let sx = null;
    const cardEl = () => view.querySelector('.review');
    const settle = () => { const card = cardEl(); if (card) card.style.transform = ''; };
    document.ontouchstart = e => {
      // The card's own buttons count (on a phone the answer buttons are where the thumb rests; a finger that moves does
      // not press them); links, fields and buttons elsewhere (撤销) are left to themselves.
      const t = e.target, off = t.closest('a,input,select,textarea,label,.sheet') || (t.closest('button') && !t.closest('.review'));
      sx = e.touches.length === 1 && sheetEl.hidden && !isTyping(e) && !off ? [e.touches[0].clientX, e.touches[0].clientY] : null;
    };
    document.ontouchmove = e => {
      if (!sx || !acts()) return; const t = e.touches[0], dx = t.clientX - sx[0], card = cardEl();
      if (card && Math.abs(dx) > Math.abs(t.clientY - sx[1])) card.style.transform = `translateX(${dx * 0.35}px) rotate(${dx * 0.02}deg)`;
    };
    document.ontouchend = e => {
      settle(); const a = acts();
      if (!sx || !a) return; const t = e.changedTouches[0], dx = t.clientX - sx[0], dy = t.clientY - sx[1]; sx = null;
      if (Math.abs(dx) > 80 && Math.abs(dx) > Math.abs(dy) * 1.4) { const f = dx > 0 ? a.right : a.left; if (f) f(); }
    };
    document.ontouchcancel = () => { sx = null; settle(); };  // the browser took the gesture (a scroll, the system): the card goes back
  }
  function swipeOff() { document.ontouchstart = document.ontouchmove = document.ontouchend = document.ontouchcancel = null; }
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
    let i = 0, doneN = 0, left = first, farthest = 0; const tally = { again: 0, hard: 0, good: 0, easy: 0, known: 0 };
    const OUTCOME = { passed: '过关！这张错题卡完成了，不会再出现', reread: '这题先放下：回原文把那一段再读一遍更有用', later: '后天带着原文再做一次',
      tomorrow: '今天先到这儿，明天再见它', 'once-more': '答对了，下次再换一道题确认一次' };
    // Progress counts cards, not answers: a card shown again to consolidate it does not grow the total.
    const uniq = new Set(items.map(x => x.id)), doneIds = new Set();
    // How long the rest will take, from this session's own pace (about 9 seconds a card until there is one).
    const started = Date.now(); let spent = 0;
    const eta = () => { const rest = uniq.size - doneIds.size; if (rest < 3) return ''; const per = doneN ? spent / doneN : 9000; return ` · 约 ${Math.max(1, Math.round(rest * per / 60000))} 分钟`; };
    const pos = () => c.repeat ? '再巩固一次' : `${Math.min(uniq.size, doneIds.size + 1)} / ${uniq.size}${c.source === 'book' && c.state === 'new' ? ' · 新词' : ''}${eta()}`;
    const foot = () => `<p class="muted tiny tc rfoot">${pos()}</p>`;
    let undo = null;  // the latest rating, while it can be taken back (撤销)
    const top = () => `<div class="rtop"><a class="link small" href="#/cards">结束</a><div class="bar-progress"><i id="rp"></i></div>${undo ? `<button class="link small undo" id="undo" type="button" aria-label="撤销上一张：${esc(undo.c.text)}">↶ 撤销</button>` : ''}</div>`;
    const badge = res => { const b = document.getElementById('dueBadge'); if (b && res && res.due != null) { const n = res.due + res.new; b.hidden = !n; b.textContent = n > 99 ? '99+' : n; } };
    // Touch: swipe the card right for "I know it" (or the main button), left for "I don't".
    let swipe = null;
    const onSwipe = (right, left2) => { swipe = { right, left: left2 }; };
    if (!items.length) {
      document.body.classList.remove('reviewing');
      view.innerHTML = `<div class="empty"><div class="big">✓</div><p>现在没有要复习的单词。</p><div class="row center"><a class="btn" href="#/cards">单词</a><a class="btn primary" href="#/">回到今日</a></div></div>`; return;
    }
    let c, t0, claim;
    const bar = () => {
      const rp = document.getElementById('rp'); if (rp) rp.style.width = (doneIds.size / Math.max(1, uniq.size) * 100) + '%';
      const u = document.getElementById('undo'); if (u) u.onclick = takeBack;
    };
    const keys = map => { document.onkeydown = e => { if (!sheetEl.hidden || e.metaKey || e.ctrlKey || e.altKey) return; if (e.target.matches && e.target.matches('input,textarea')) { if (e.key === 'Enter' && map.Enter && ['spellIn', 'fixIn'].includes(e.target.id)) { e.preventDefault(); map.Enter(); } return; } const f = map[e.key] || map[e.key.toLowerCase()]; if (f) { e.preventDefault(); f(); } }; };
    swipeOn(() => swipe);
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
      const ex = c.extra || {}, src = { reading: '理解题', writing: '写作', speaking: '口语', translation: '翻译', pronunciation: '发音', vocabulary: '词汇辨析', grammar: '语法' }[c.skill] || '错题';
      const tag = `<span class="pill amber rtag">错题 · ${esc(src)}</span>`;
      let body = '';
      if (c.mode === 'question' && c.variant) {
        // A grammar mistake comes back as a different question on the same point: the rule is practised, not one answer.
        const v = c.variant;
        body = `${tag}<div class="tiny muted">${v.kind === 'word' ? '同一组易混词，换一道题：' + esc(c.text) : '同一个语法点，换一道题' + (c.node ? '：' + esc(c.node.title) : '')}</div><div class="prompt-q">${esc(v.prompt)}</div>
          <div class="qopts">${v.options.map((o, k) => `<button class="qopt" data-o="${v.map ? v.map[k] : k}">${esc(o)}</button>`).join('')}</div>`;
      } else if (c.mode === 'question') {
        // A reading question comes back with its part of the text: it is answered by reading, not by remembering.
        const opts = ex.options || [], ps = c.passage;
        body = `${tag}${ps ? `<div class="passage-q"><div class="tiny muted">原文片段${ps.title ? ' · ' + esc(ps.title) : ''}</div><p class="ptext" id="ptext">${ps.start ? '… ' : ''}${esc(ps.text)}${ps.end ? ' …' : ''}</p></div>` : ''}
          <div class="prompt-q">${esc(c.text)}</div><div class="qopts">${opts.map((o, k) => `<button class="qopt" data-o="${k}">${esc(o)}</button>`).join('')}</div>`;
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
      // A question or a sentence to fix has no word to put in the middle of the screen: it starts at the top.
      view.innerHTML = `${top()}<div class="review enter${c.mode === 'sound' ? '' : ' q'}">${body}${foot()}</div>`;
      bar(); swipe = null;
      const after = (r, html) => {
        const ms = Date.now() - t0;
        view.querySelector('.review').insertAdjacentHTML('beforeend', `<div class="stack-s enter">${html}<div class="row center"><button class="btn primary" id="go">下一个</button></div></div>`);
        document.getElementById('go').onclick = () => rate(r, ms); keys({ Enter: () => rate(r, ms), ' ': () => rate(r, ms) });
      };
      if (c.mode === 'question' && c.variant) {
        view.querySelectorAll('[data-o]').forEach(b => b.onclick = async () => {
          view.querySelectorAll('[data-o]').forEach(x => { x.disabled = true; });
          let r;
          if (c.variant.kind === 'word') {  // a word group: checked here, the answer recorded for the group's progress
            r = { correct: Number(b.dataset.o) === c.variant.answer, answer: c.variant.answer, explanation: c.variant.explanation };
            api('/api/next/words/confuse/answer', { item: c.variant.id, correct: r.correct, from: 'review' }).catch(() => {});
          } else {
            try { r = await api('/api/next/node/answer', { question: c.variant.id, choice: Number(b.dataset.o), from: 'review' }); }
            catch (e) { toast(e.message); view.querySelectorAll('[data-o]').forEach(x => { x.disabled = false; }); return; }
          }
          view.querySelectorAll('[data-o]').forEach(x => { if (Number(x.dataset.o) === r.answer) x.classList.add('right'); });
          if (!r.correct) b.classList.add('wrong');
          after(r.correct ? 'good' : 'again', `<div class="${r.correct ? 'ok' : 'bad'}">${r.correct ? '✓ 换了一道题也答对了' : '这题没答对'}</div><div class="small">${esc(r.explanation || '')}</div>
            ${!r.correct && c.variant.kind === 'word' ? `<div class="tiny muted">${esc(c.meaning || '')}</div>` : ''}
            ${!r.correct && c.node ? `<a class="link small" href="#/graph/${encodeURIComponent(c.node.id)}">回到「${esc(c.node.title)}」看一遍讲解 →</a>` : ''}`);
        });
        keys({ 1: () => view.querySelector('.qopt:nth-child(1)').click(), 2: () => view.querySelector('.qopt:nth-child(2)').click(), 3: () => view.querySelector('.qopt:nth-child(3)').click(), 4: () => view.querySelector('.qopt:nth-child(4)').click() });
      } else if (c.mode === 'question') {
        view.querySelectorAll('[data-o]').forEach(b => b.onclick = () => {
          const k = Number(b.dataset.o), ok = k === ex.answer, ps = c.passage;
          view.querySelectorAll('[data-o]').forEach(x => { x.disabled = true; if (Number(x.dataset.o) === ex.answer) x.classList.add('right'); });
          if (!ok) b.classList.add('wrong');
          const pt = document.getElementById('ptext'); if (pt && ps && ps.evidence) pt.innerHTML = (ps.start ? '… ' : '') + highlight(ps.text, ps.evidence) + (ps.end ? ' …' : '');
          after(ok ? 'good' : 'again', `<div class="${ok ? 'ok' : 'bad'}">${ok ? '✓ 这次答对了，这道题过关' : '还是没答对'}</div>${ex.evidence && !(pt && ps) ? `<div class="small"><span class="muted">原文依据：</span>${esc(ex.evidence)}</div>` : ''}
            ${!ok && c.pack ? `<a class="link small" href="#/m/${encodeURIComponent(c.pack)}/read">回原文把这一段再读一遍 →</a>` : ''}`);
        });
        keys({ 1: () => view.querySelector('[data-o="0"]').click(), 2: () => view.querySelector('[data-o="1"]').click(), 3: () => view.querySelector('[data-o="2"]').click(), 4: () => view.querySelector('[data-o="3"]').click() });
      } else if (c.mode === 'fix') {
        const inp = document.getElementById('fixIn'); setTimeout(() => inp.focus(), 50);
        const norm = s => s.toLowerCase().replace(/[^a-z' ]+/g, ' ').replace(/\s+/g, ' ').trim();
        const done = v => {
          view.querySelectorAll('#fixGo,#fixNo').forEach(b => b.remove()); inp.disabled = true;
          const ok = !!v && norm(v) === norm(c.text);
          if (ok || !v) return after(ok ? 'good' : 'again', `<div class="${ok ? 'ok' : 'bad'}">${ok ? '✓ 改对了' : '应该是'}：<b>${esc(c.text)}</b></div>${c.meaning ? `<div class="small">${esc(c.meaning)}</div>` : ''}`);
          // Not the same words: often a correct other wording. The learner compares and decides; no loop over one word.
          const ms = Date.now() - t0;
          view.querySelector('.review').insertAdjacentHTML('beforeend', `<div class="stack-s enter"><div class="small"><span class="muted">你写的：</span>${esc(v)}</div>
            <div class="small"><span class="muted">参考改法：</span><b>${esc(c.text)}</b></div>${c.meaning ? `<div class="small muted">${esc(c.meaning)}</div>` : ''}
            <div class="row center"><button class="btn" id="fixSame">我写的也对</button><button class="btn primary" id="fixMiss">没写对，记下了</button></div></div>`);
          document.getElementById('fixSame').onclick = () => rate('good', ms); document.getElementById('fixMiss').onclick = () => rate('again', ms);
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
        const before = { c, r, i, had: doneIds.has(c.id), left, inserted: -1, offline: false, body };
        let res;
        try { res = await api('/api/next/review', body); }
        catch (e) {
          if (!e.network) throw e;
          OUTBOX.push({ path: '/api/next/review', body }); before.offline = true;  // offline: keep going, sync later
          const learning = c.state !== 'review' || r === 'again';
          res = { card: { ...c, state: learning && r !== 'easy' ? (c.state === 'review' ? 'relearning' : 'learning') : 'review' }, due: left ? left.due : 0, new: left ? left.new : 0 };
          if (r === 'good' && c.state === 'learning' && (c.step || 0) >= 1) res.card.state = 'review';
          res.card.step = (c.step || 0) + 1;
        }
        tally[r]++; doneN++; left = res; i++; doneIds.add(c.id); badge(res); spent += Math.min(ms, 60000); undo = before;
        const n = res.card;
        if (res.outcome && OUTCOME[res.outcome]) toast(OUTCOME[res.outcome]);
        if ((r === 'good' || r === 'easy') && n.due) farthest = Math.max(farthest, Math.round((n.due * 1000 - Date.now()) / 86400000));
        // Only what is due again within minutes (a miss, or a fuzzy new card) comes back in this session, a few cards later;
        // a card answered right waits for its next step (10 minutes, then days) and is picked up by "继续" or the next session.
        const soon = n.due ? n.due * 1000 - Date.now() < 5 * 60000 : r === 'again';
        // At most one more try in this session; a card missed again waits for tomorrow (the server moves it there too).
        const parked = ['tomorrow', 'later', 'passed', 'reread'].includes(res.outcome) || (c.tries || 0) >= 1;
        if ((n.state === 'learning' || n.state === 'relearning') && soon && !parked) {
          const again = { ...c, ...n, mode: c.kind === 'word' ? 'recognize' : c.mode, repeat: true, tries: (c.tries || 0) + 1 };
          before.inserted = Math.min(items.length, i + 4); items.splice(before.inserted, 0, again);
        }
        const el = view.querySelector('.review'); if (el) el.classList.add('out');
        setTimeout(ask, REDUCED ? 0 : 180);
      } catch (e) { toast(e.message); keys({}); }
      finally { busy = false; }
    }
    // 撤销: the latest rating taken back (a slip of the finger); the same card comes up again to answer.
    async function takeBack() {
      const u = undo; if (!u || busy) return; busy = true;
      try {
        let res = u.left;
        if (u.offline) OUTBOX.unpush({ path: '/api/next/review', body: u.body });
        else res = await api('/api/next/review/undo', { id: u.c.id });
        tally[u.r]--; doneN--; if (!u.had) doneIds.delete(u.c.id);
        if (u.inserted >= 0) items.splice(u.inserted, 1);
        i = u.i; left = res; undo = null; badge(res);
        toast('已撤销，再答一次这一张'); ask();
      } catch (e) { undo = null; toast(e.message); const b = document.getElementById('undo'); if (b) b.remove(); }
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
      swipeOff(); document.body.classList.remove('reviewing');
      undo = null;
      const rated = tally.again + tally.hard + tally.good + tally.easy, mins = Math.max(1, Math.round((Date.now() - started) / 60000));
      view.innerHTML = `<div class="card done-card enter">${doneRing}<h2 class="h2">这一轮复习了 ${doneIds.size} 个</h2>
        <p class="small rsum">用时约 ${mins} 分钟${rated ? ` · 记住了 ${Math.round((tally.good + tally.easy) / rated * 100)}%` : ''}<span id="tmr"></span></p>${doneN > doneIds.size ? `<p class="muted tiny">共作答 ${doneN} 次，其中 ${doneN - doneIds.size} 次是再巩固</p>` : ''}
        <p class="muted small">记得 ${tally.good + tally.easy} · 模糊 ${tally.hard} · 忘了 ${tally.again}${tally.known ? ' · 熟知 ' + tally.known : ''}。</p>
        <p class="small cheer">${tally.good + tally.easy ? `记得的都往后推了${farthest > 1 ? `，最远的要 ${farthest} 天后才再见` : ''}。` : ''}${tally.again ? `忘了的 ${tally.again} 个明天再来：忘了再想起来，正是记牢的过程。` : tally.good + tally.easy ? '这一轮全都记得，很稳。' : ''}</p>
        ${left && (left.due + left.new) ? `<p class="small">还有 ${left.due + left.new} 个可以继续。</p>` : ''}
        <div class="row center"><a class="btn" href="#/cards">单词</a>${left && (left.due + left.new) ? '<button class="btn primary" id="again">继续</button>' : '<a class="btn primary" href="#/">回到今日</a>'}</div>
        ${left && !(left.due + left.new) ? '<div class="row center"><button class="btn ghost small" id="moreNew">还想多背：再学 10 个新词</button></div>' : ''}</div>`;
      api('/api/next/vocab').then(o => { const t = document.getElementById('tmr'); if (t && o.forecast && o.forecast[1] != null) t.textContent = ` · 明天大约复习 ${o.forecast[1]} 个`; }).catch(() => {});
      const ag = document.getElementById('again'); if (ag) ag.onclick = () => reviewView();
      const mn = document.getElementById('moreNew');
      if (mn) mn.onclick = async () => { mn.disabled = true; try { const r = await api('/api/next/vocab/more', { n: 10 }); if (r.added) reviewView(); else { toast('词书里的词都学过了'); } } catch (e) { toast(e.message); mn.disabled = false; } };
    }
    ask();
  }

  /* ---------- learner model: ability profile, daily path, level suggestion ---------- */
  const LV_W = { A2: 25, B1: 50, B2: 75, C1: 100 };
  // Practice evidence of the last 45 days, skill by skill: shown folded at the foot of the ability radar.
  function abilityHTML(ab) {
    const ev = s => s.id === 'vocab' ? (s.size ? `词汇量约 ${s.size.toLocaleString()}` : (s.count ? `已掌握 ${s.count} 词` : '做一次词汇量测试'))
      : s.id === 'grammar' ? (s.count ? `${s.count} 个知识点用对或做对${s.watch ? ` · ${s.watch} 个要留意` : ''}` : '读和写的时候会点亮')
      : s.count ? `${s.count} 次练习 · 平均 ${Math.round((s.avg || 0) * 100)}%` : '还没练过';
    return `<div class="ab-list" id="ability">${ab.skills.map(s => `<div class="ab ${s.level ? '' : 'none'}"><span class="nm">${esc(s.label)}</span><span class="vbar"><i data-w="${s.level ? LV_W[s.level] : 3}"></i></span>
        <span class="lv">${s.level || '—'}</span><span class="tiny muted ev">${esc(ev(s))}</span></div>`).join('')}</div>
      <p class="muted small">不用专门测：做理解题、听写、跟读和写作时自动记下。做一次测评会更准。</p>`;
  }
  function suggestHTML(sg) {
    return sg ? `<div class="card sunk section suggest row between"><div class="small">${esc(sg.reason)}</div>
      <div class="row"><button class="btn small primary" id="sgYes" data-tap="notice-level">换到 ${esc(sg.to)}</button><button class="btn small ghost" id="sgNo">先不用</button></div></div>` : '';
  }
  function bindSuggest(h, after) {
    const y = document.getElementById('sgYes'), n = document.getElementById('sgNo');
    if (y) y.onclick = async () => { try { await api('/api/next/profile', { ...h.profile, level: h.suggest.to }); toast('已换到 ' + h.suggest.to + '，推荐会跟着变'); await refreshHome(); S.homeFresh = true; route(); } catch (e) { toast(e.message); } };
    if (n) n.onclick = () => { save('flow-next-suggest-skip', Date.now()); if (after) after(); else n.closest('.suggest').remove(); };
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
      ${weekMoreHTML(r)}
      <div class="card flat section stack-s"><b>错题</b><span class="small">新进错题本 ${r.mistakes_new} 个，改对 ${r.mistakes_fixed} 个。</span>
        ${r.watch.length ? `<span class="small">写作里要留意：${r.watch.map(n => nodeChip({ id: n.id, title: n.title, status: 'watch' })).join(' ')}</span>` : ''}
        ${r.focus ? `<div class="small"><b>下周重点：</b>${esc(r.focus)}</div>` : ''}</div>
      <div class="section row"><button class="btn primary" id="share" data-tap="share-week">分享这周的学习</button><a class="btn" href="#/radar">能力雷达</a></div>`;
    requestAnimationFrame(() => requestAnimationFrame(() => view.querySelectorAll('.vbar i').forEach(i => { i.style.width = i.dataset.w + '%'; })));
    document.getElementById('share').onclick = () => shareSheet([{ label: '本周', draw: () => shareImage(r) }], '分享这周的学习');
  }
  function weekMoreHTML(r) {
    const e = r.easy || {}, sp = r.speaking || {}, ra = r.radar || { moves: [] };
    const speed = e.wpm ? `，平均每分钟 ${e.wpm} 词${e.wpm_before ? (e.wpm > e.wpm_before ? `（上周 ${e.wpm_before}，快了）` : `（上周 ${e.wpm_before}）`) : ''}` : '';
    const mv = m => m.before == null ? '' : m.now > m.before ? ` <span class="up">↑${m.now - m.before}</span>` : m.now < m.before ? ` <span class="tiny muted">↓${m.before - m.now}</span>` : '';
    const rl = r.relisten || {};
    return `${rl.count ? `<div class="card flat section stack-s"><b>复听</b><span class="small">把几天前学过的文章重听了 ${rl.count} 次，平均听懂${esc(rl.label)}。</span></div>` : ''}
      <div class="card flat section stack-s"><div class="row between"><b>轻松读</b><a class="link small" href="#/easy">去读</a></div>
        <span class="small">${e.texts ? `读了 ${e.texts} 篇，一共 ${e.words} 个词${speed}。` : '这周还没读。每天读一篇比你低一级的短文，阅读速度会慢慢提上来。'}</span></div>
      <div class="card flat section stack-s"><div class="row between"><b>口语情景</b><a class="link small" href="#/speak">去练</a></div>
        <span class="small">${sp.scenes_week ? `这周练了 ${sp.scenes_week} 个情景，` : '这周还没练情景对话，'}一共完成 ${sp.scenes_done || 0} / ${sp.scenes_total || 12} 个。</span></div>
      <div class="card flat section stack-s"><div class="row between"><b>能力雷达</b><a class="link small" href="#/radar">看雷达</a></div>
        ${ra.moves.length ? `<div class="ab-list">${ra.moves.map(m => `<div class="ab"><span class="nm">${esc(m.label)}</span><span class="vbar"><i data-w="${Math.max(3, Math.min(100, m.now))}"></i></span><span class="lv">${m.now} 分${mv(m)}</span></div>`).join('')}</div>
          <span class="tiny muted">100 分 = 达到你定的目标${ra.goals_chosen ? '' : '（还没定目标，先按默认目标算）'}。这周做了 ${ra.tests_week} 次测评。</span>`
          : '<span class="small">还没有雷达数据。做几次小测评，就能看到六项能力离目标还差多少。</span><div><a class="btn small" href="#/radar/test">去测一测</a></div>'}</div>`;
  }
  function shareImage(r) {
    const rows = r.skills.filter(s => s.now != null).slice(0, 5).length;
    const W = 1080, H = (rows ? 900 + rows * 70 + 170 : 860) + 230, cv = document.createElement('canvas'); cv.width = W; cv.height = H;
    const g = cv.getContext('2d'), green = '#1f9d55', ink = '#1b1d1a', muted = '#6f7369';
    g.fillStyle = '#fbfaf6'; g.fillRect(0, 0, W, H);
    const font = (s, w) => `${w || 600} ${s}px -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif`;
    g.fillStyle = ink; g.font = font(56, 800); g.fillText('本周学习', 80, 170);  // the brand is in the footer, with the QR code
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
    brandFoot(g, W, H, habitNote(false, true));  // logo, the weeks that reached the goal, and the QR code back to the site (86-share.js)
    return cv.toDataURL('image/png');
  }

  /* ---------- library ---------- */
  async function libraryView(f) {
    let saved = null; try { saved = JSON.parse(sessionStorage.getItem('flow-next-lib') || 'null'); } catch (e) { /* private mode */ }
    f = f || saved || { level: hasProfile() ? level() : '', theme: '', page: 1, featured: '1' };
    try { sessionStorage.setItem('flow-next-lib', JSON.stringify(f)); } catch (e) { /* private mode */ }
    const d = await api(libraryPath(f));  // the same address a touch of the link already preloaded
    const pages = Math.max(1, Math.ceil(d.total / d.per));
    view.innerHTML = `<div class="row between"><h1 class="h1">全部材料</h1><span class="row"><a class="btn small" href="#/easy">轻松读</a><a class="btn small" href="#/import">我的文章</a></span></div><span class="muted small">${d.total} 篇${f.featured === '1' ? ' · 精选' : ''}</span>
      <div class="filters"><select id="ff" aria-label="范围"><option value="1" ${f.featured === '1' ? 'selected' : ''}>精选</option><option value="" ${f.featured !== '1' ? 'selected' : ''}>全部材料</option></select>
        <select id="fl" aria-label="难度"><option value="">全部难度</option>${['A2', 'B1', 'B2', 'C1'].map(l => `<option ${f.level === l ? 'selected' : ''}>${l}</option>`).join('')}</select>
        <select id="ft" aria-label="话题"><option value="">全部话题</option>${Object.entries(d.themes).map(([k, v]) => `<option value="${k}" ${f.theme === k ? 'selected' : ''}>${esc(v)}</option>`).join('')}</select></div>
      ${d.series && d.series.length ? `<section class="section"><h2 class="h2 mhead">连载故事</h2><div class="mlist">${d.series.map(s => `<a class="mrow" href="#/series/${encodeURIComponent(s.id)}">
        <span class="t"><b>《${esc(s.title)}》${esc(s.title_en)}</b><span class="tiny muted">${esc(s.level)} · ${s.done ? `已读 ${s.done} / ${s.of} 集${s.next ? ` · 继续第 ${s.next_part} 集` : ' · 读完了'}` : `共 ${s.of} 集 · 从第 1 集开始`}</span></span>
        <span class="pill green">连载</span><span class="go" aria-hidden="true">›</span></a>`).join('')}</div></section>` : ''}
      <section class="section">${d.series && d.series.length ? '<h2 class="h2 mhead">单篇</h2>' : ''}<div class="mlist" id="lib">${d.items.map(m => mrow(m, m.daily ? ['热点', 'amber'] : null)).join('') || '<div class="empty">这个筛选下还没有材料。</div>'}</div></section>
      ${pages > 1 ? `<div class="pager"><button class="btn small" id="pv" ${f.page <= 1 ? 'disabled' : ''}>上一页</button><span class="muted small">${f.page} / ${pages}</span><button class="btn small" id="nx" ${f.page >= pages ? 'disabled' : ''}>下一页</button></div>` : ''}`;
    const again = nf => libraryView(nf).then(() => enter(document.getElementById('lib')));
    document.getElementById('ff').onchange = e => again({ ...f, featured: e.target.value, page: 1 });
    document.getElementById('fl').onchange = e => again({ ...f, level: e.target.value, page: 1 });
    document.getElementById('ft').onchange = e => again({ ...f, theme: e.target.value, page: 1 });
    const pv = document.getElementById('pv'), nx = document.getElementById('nx');
    if (pv) pv.onclick = () => { scrollTo(0, 0); again({ ...f, page: f.page - 1 }); };
    if (nx) nx.onclick = () => { scrollTo(0, 0); again({ ...f, page: f.page + 1 }); };
  }

  /* ---------- a serial story: its episodes in order, and where to carry on ---------- */
  async function seriesView(sid) {
    const s = await api('/api/next/series?id=' + encodeURIComponent(sid));
    const next = s.episodes.find(e => e.id === s.next);
    view.innerHTML = `<div><a class="link small" href="#/library">← 全部材料</a></div>
      <div><span class="kicker">连载故事 · ${esc(s.level)} · 共 ${s.of} 集</span><h1 class="h1">${esc(s.title)}</h1><div class="title-en">${esc(s.title_en)}</div>
        <p class="muted small">${esc(s.blurb)}</p></div>
      ${next ? `<a class="btn primary block" href="#/m/${encodeURIComponent(next.id)}">${s.done ? `继续：第 ${next.part} 集` : '从第 1 集开始'}<span aria-hidden="true">→</span></a>` : '<p class="small">六集都读完了。可以回到任意一集，再听一遍或者重写输出任务。</p>'}
      <div class="serial section">${s.episodes.map(e => `<a class="ep${e.read ? ' done' : ''}${e.id === s.next ? ' next' : ''}" href="#/m/${encodeURIComponent(e.id)}">
        <span class="n" aria-hidden="true">${e.read ? '✓' : e.part}</span><span class="t"><b>${esc(e.title.replace(/^.*?[：:]/, ''))}</b><span class="tiny muted">${esc(e.preview.replace(/^连载第\s*\d+\s*集(（完）)?[：:]\s*/, ''))}</span></span>
        <span class="tiny muted">${e.minutes} 分钟</span></a>`).join('')}</div>
      <p class="tiny muted section">每集约 300 词，C1 难度，原创连载。每集都有听、读、理解和输出四步，读完理解题就算读过这一集。</p>`;
  }
  /* ---------- me: one grouped list, like a phone's settings; each row opens a page or a sheet ---------- */
  // A row: a link (to starts with # or /) or a button (to is its id); the value sits on the right, greyed.
  function grow(to, label, value, vid, tapKey) {
    const tag = to[0] === '#' || to[0] === '/' ? 'a' : 'button';
    return `<${tag} class="grow" ${tag === 'a' ? `href="${to}"` : `type="button" id="${to}"`}${tapKey ? ` data-tap="${tapKey}"` : ''}><span class="t">${label}</span><span class="v small muted"${vid ? ` id="${vid}"` : ''}>${value || ''}</span><span class="go" aria-hidden="true">›</span></${tag}>`;
  }
  async function meView() {
    if (!S.meta) S.meta = await api('/api/next/meta');
    const p = (S.home && S.home.profile) || S.guest || {}, u = S.user, st = S.home && S.home.stats;
    const lv = S.meta.levels.find(l => l.id === p.level), goal = S.meta.goals.find(g => g.id === p.goal);
    const installed = matchMedia('(display-mode: standalone)').matches || navigator.standalone;
    const groups = [
      u && ['进步', [grow('#/radar', '能力雷达', '离目标还差多少', '', 'me-radar'), grow('#/growth', '我的进步', '每月对比和里程碑', '', 'me-growth'), grow('#/report', '这周的报告', '', '', 'me-report'), grow('#/cards/mistake', '错题本', '', '', 'me-mistake')]],
      ['设置', [grow('#/welcome/edit', '学习目标和水平', [goal && esc(goal.label), lv && lv.id].filter(Boolean).join(' · ') || '未设置', '', 'me-level'),
        u ? grow('meHabit', '每周目标', `每周 ${(st && st.habit && st.habit.goal) || 4} 天`, 'meHabitV', 'me-habit') : '', grow('meVoice', '朗读声音', VOICE_LABELS[S.voice] || VOICE_LABELS['us-f'], 'meVoiceV', 'me-voice'), grow('meText', '字号和行距', textLabel(), 'meTextV', 'me-text'), grow('meRemind', '每天提醒', '加到手机日历', '', 'me-remind'),
        u ? grow('meMail', '每周进度邮件', weeklyMailLabel(), 'meMailV', 'me-weekly-mail') : '',
        installed ? '' : grow('meInstall', '添加到桌面', '像 App 一样打开', '', 'me-install')]],
      u && ['账号', [grow('bindMail', '邮箱', '<span class="spin"></span>', 'acctEmail'), grow('chPw', '修改密码'), grow('outAll', '退出所有设备'),
        grow('meData', '导出我的数据', '单词本 · 学习记录', '', 'me-data'), grow('meDelete', '注销账号', '', '', 'me-delete')],
        '绑定邮箱后，可以用验证码登录，忘记密码时自己找回。30 天内来过就一直保持登录；在别人的手机或电脑上用完，记得退出。'],
      ['帮助', [grow('#/guide', '操作指南', '每个页面怎么用', '', 'me-guide'), grow('#/feedback', '问题反馈', '页面不对、功能用不了，告诉我们', '', 'me-feedback'), grow('/survey', '匿名问卷', '你想要什么样的英语学习网站', '', 'me-survey')]],
    ].filter(Boolean);
    view.innerHTML = `<div class="card flat me-head"><div class="me-id">${u ? `<span class="avatar" aria-hidden="true">${esc([...u.username][0].toUpperCase())}</span>` : ''}
        <div class="t"><h1 class="h1">${u ? esc(u.username) : '我的'}</h1><span class="small muted">${lv ? `${esc(lv.label)}（${lv.id}）` : '还没有设置水平'} · 每天 ${p.minutes || 10} 分钟</span></div></div>
        ${st ? `<div class="me-nums">${[[st.habit ? st.habit.done : st.week.filter(d => d.active).length, '本周学习天数'], [st.materials_done, '学完的材料'], [st.cards, '单词与表达']].map(([n, l]) => `<div><b>${n}</b><span class="tiny muted">${l}</span></div>`).join('')}</div>`
          : u ? '' : `<div class="stack-s"><span class="muted small">登录后才能保存进度、收藏表达和使用 AI。</span><div><button class="btn primary small" id="lg">登录 / 注册</button></div></div>`}</div>
      ${groups.map(([h, rows, foot]) => `<section class="gsec" aria-label="${h}"><h2 class="ghead">${h}</h2><div class="glist">${rows.join('')}</div>${foot ? `<p class="tiny muted gfoot">${foot}</p>` : ''}</section>`).join('')}
      ${u ? '<div class="glist gsec"><button class="grow danger" id="out" type="button"><span class="t">退出登录</span></button></div>' : ''}`;
    const lg = document.getElementById('lg'); if (lg) lg.onclick = () => openLogin();
    document.getElementById('meVoice').onclick = voiceSheet;
    document.getElementById('meText').onclick = textSheet;
    const mh = document.getElementById('meHabit'); if (mh) mh.onclick = habitSheet;
    document.getElementById('meRemind').onclick = () => remindSheet(p.minutes || 10);
    const mm = document.getElementById('meMail'); if (mm) mm.onclick = weeklyMailSheet;  // 11-progress.js
    const mi = document.getElementById('meInstall'); if (mi) mi.onclick = installSheet;
    if (u) {
      const b = document.getElementById('bindMail'); b.disabled = true;
      api('/api/account').then(a => {
        const el = document.getElementById('acctEmail'); if (!el) return;
        el.textContent = a.email || '还没有绑定';
        if (a.mail_enabled) { b.disabled = false; b.setAttribute('aria-label', a.email ? '邮箱：' + a.email + '，点这里更换' : '绑定邮箱'); b.onclick = () => bindEmailSheet(a.email); }
        else if (!a.email) el.textContent += '（邮件服务暂未开启）';
      }).catch(() => { const el = document.getElementById('acctEmail'); if (el) el.textContent = ''; });
      document.getElementById('chPw').onclick = () => changePasswordSheet();
      document.getElementById('outAll').onclick = () => signOutEverywhere();
      document.getElementById('meData').onclick = dataSheet;
      document.getElementById('meDelete').onclick = deleteAccountSheet;
      document.getElementById('out').onclick = async () => { await OUTBOX.flush(); try { await api('/api/logout', {}); } catch (e) { /* ignore */ } snapClear(); S.user = null; S.csrf = ''; await refreshHome(); toast('已退出'); route(); };
    }
  }
  // 字号和行距: the reading text (a material, the listening lines, review sentences, questions, the guide, meanings)
  // larger and with more room between lines; menus and buttons stay as they are. Kept on the phone (applyText, 02-shell.js).
  const TEXT_SIZES = [['m', '标准'], ['l', '大'], ['xl', '特大']], TEXT_LH = [['n', '标准'], ['w', '宽松']];
  function textLabel() { return [TEXT_SIZES.find(x => x[0] === TEXT.size)[1], TEXT.lh === 'w' ? '行距宽松' : ''].filter(Boolean).join(' · '); }
  function textSheet() {
    const chips = (list, key, cur) => list.map(([k, l]) => `<button class="chip" type="button" role="radio" data-${key}="${k}" aria-checked="${cur === k}">${l}</button>`).join('');
    openSheet(`<div class="stack"><h2 class="h2" id="sheetTitle">字号和行距</h2>
      <div class="stack-s"><b>字号</b><div class="chips" role="radiogroup" aria-label="字号">${chips(TEXT_SIZES, 'ts', TEXT.size)}</div></div>
      <div class="stack-s"><b>行距</b><div class="chips" role="radiogroup" aria-label="行距">${chips(TEXT_LH, 'tl', TEXT.lh)}</div></div>
      <p class="text tsample">Reading a little every day is how a new language slowly becomes your own.</p>
      <p class="muted small">课文、听力句子、讲解和释义的字会变大，菜单和按钮不变。</p><button class="btn ghost" data-close type="button">完成</button></div>`, card => {
      card.querySelectorAll('[data-ts], [data-tl]').forEach(b => b.onclick = () => {
        const k = 'ts' in b.dataset ? 'size' : 'lh'; TEXT[k] = b.dataset.ts || b.dataset.tl; save('flow-next-text', TEXT); applyText();
        card.querySelectorAll(k === 'size' ? '[data-ts]' : '[data-tl]').forEach(x => x.setAttribute('aria-checked', String(x === b)));
        const v = document.getElementById('meTextV'); if (v) v.textContent = textLabel();
      });
    });
  }
  function voiceSheet() {
    openSheet(`<div class="stack"><h2 class="h2" id="sheetTitle">朗读声音</h2>${voiceChips(null)}
      <p class="muted small">精选材料用真人声（Kokoro）朗读。学一篇材料时，也可以在「听」这一步随时切换。</p><button class="btn ghost" data-close type="button">完成</button></div>`, card => {
      card.querySelectorAll('[data-voice]').forEach(b => b.onclick = async () => {
        await setVoice(b.dataset.voice);
        card.querySelectorAll('[data-voice]').forEach(x => { x.setAttribute('aria-pressed', String(x === b)); x.setAttribute('aria-checked', String(x === b)); });
        const v = document.getElementById('meVoiceV'); if (v) v.textContent = VOICE_LABELS[b.dataset.voice];
        toast('朗读声音：' + VOICE_LABELS[b.dataset.voice]);
      });
    });
  }
  function remindSheet(minutes) {
    const ics = h => `/api/next/vocab/reminder.ics?kind=plan&hour=${h}&minutes=${minutes}`;
    openSheet(`<div class="stack"><h2 class="h2" id="sheetTitle">每天提醒</h2>
      <p class="muted small">加到手机日历：每天到点提醒你打开今天的计划。不用装 App、不用邮箱，iPhone 和安卓都能用。</p>
      <div class="row"><select id="mHour" aria-label="提醒时间">${Array.from({ length: 18 }, (_, k) => k + 6).map(h => `<option value="${h}" ${h === 20 ? 'selected' : ''}>每天 ${h}:00</option>`).join('')}</select>
        <a class="btn primary" id="mCal" href="${ics(20)}">加到手机日历</a></div>
      <p class="tiny muted">打开下载的文件，选「添加到日历」即可；不想要了就在日历里删掉这个日程。</p><button class="btn ghost" data-close type="button">完成</button></div>`, card => {
      const hour = card.querySelector('#mHour'), cal = card.querySelector('#mCal');
      hour.onchange = () => { cal.href = ics(hour.value); };
    });
  }
  /* ---------- on the home screen: two steps for the phone in hand, or one tap where the browser offers it ---------- */
  const STANDALONE = () => matchMedia('(display-mode: standalone)').matches || navigator.standalone === true;
  const IN_WECHAT = /MicroMessenger/i.test(navigator.userAgent);  // WeChat cannot install; its own bar says how to leave it
  function installKind() {
    const ua = navigator.userAgent, ipad = /iPad/.test(ua) || (/Macintosh/.test(ua) && navigator.maxTouchPoints > 1);  // iPadOS says Mac
    if (IN_WECHAT && !/iPhone|iPod/.test(ua) && !ipad) return 'wechat';
    if (/iPhone|iPod/.test(ua) || ipad) return /CriOS|FxiOS|EdgiOS|OPiOS|MicroMessenger|QQ\//.test(ua) ? 'ios-other' : ipad ? 'ipad' : 'iphone';
    if (installPrompt) return 'prompt';
    return /Android/i.test(ua) ? 'android' : 'desktop';
  }
  addEventListener('appinstalled', () => { save('flow-installed', Date.now()); installPrompt = null; const n = document.getElementById('installNudge'); if (n) n.remove(); });
  // The 今日 notice: a phone browser (not WeChat, not already on the home screen) of a learner who has studied once.
  function installNudgeDue(h) {
    return !!(S.user && TOUCH && !IN_WECHAT && !STANDALONE() && !load('flow-installed') && h.stats && (h.stats.materials_done || 0) >= 1
      && Date.now() - (load('flow-install-later') || 0) > 30 * 864e5);
  }
  function installSheet() {
    const k = installKind(), share = '<svg class="ishare" viewBox="0 0 24 24" aria-label="分享按钮"><path d="M12 15V3M8 7l4-4 4 4"/><path d="M7 10H6v10h12V10h-1"/></svg>';
    const steps = {
      iphone: [`点屏幕<b>底部中间</b>的分享按钮 ${share}`, '往下滑，点「<b>添加到主屏幕</b>」，再点右上角的「添加」'],
      ipad: [`点<b>右上角</b>的分享按钮 ${share}`, '往下滑，点「<b>添加到主屏幕</b>」，再点「添加」'],
      'ios-other': ['苹果手机要用 <b>Safari</b> 才能放到桌面：点下面的「复制网址」，打开 Safari，粘贴并前往', `在 Safari 里点底部中间的分享按钮 ${share}，选「<b>添加到主屏幕</b>」`],
      wechat: ['微信里不能放到桌面：点右上角「<b>···</b>」，选「<b>在浏览器打开</b>」', '在浏览器里打开「我的 → 添加到桌面」，按那里的两步做'],
      android: ['点浏览器右上角的 <b>⋮</b>（有的浏览器在底部，是 <b>≡</b>）', '选「<b>添加到主屏幕</b>」或「<b>安装应用</b>」（有的手机叫「添加到桌面」）'],
      desktop: ['用 Chrome 或 Edge 打开语流，点地址栏右边的「安装」图标', '装好以后，可以从开始菜单或程序坞打开'],
    }[k];
    openSheet(`<div class="stack"><h2 class="h2" id="sheetTitle">把语流放到桌面</h2>
      <p class="muted small">像 App 一样从桌面一点就开，界面全屏；听过的音频会缓存下来，网络差的时候也能复习。</p>
      ${k === 'prompt' ? '<button class="btn primary" id="doInstall" type="button">安装到桌面</button>' : `<ol class="isteps">${steps.map(x => `<li>${x}</li>`).join('')}</ol>`}
      ${k === 'ios-other' ? '<button class="btn" id="copyUrl" type="button">复制网址</button>' : ''}
      <button class="btn ghost" data-close type="button">${k === 'prompt' ? '取消' : '知道了'}</button></div>`, card => {
      const di = card.querySelector('#doInstall');
      if (di) di.onclick = async () => {
        const p = installPrompt; if (!p) return closeSheet();
        let ok = false; p.prompt(); try { ok = (await p.userChoice).outcome === 'accepted'; } catch (e) { /* dismissed */ }
        installPrompt = null; closeSheet();
        if (ok) { save('flow-installed', Date.now()); toast('放好了，在桌面上找「语流」'); }
        route(true);
      };
      const cu = card.querySelector('#copyUrl');
      if (cu) cu.onclick = () => { const u = location.origin + '/'; (navigator.clipboard ? navigator.clipboard.writeText(u) : Promise.reject()).then(() => toast('网址已复制，去 Safari 粘贴打开'), () => prompt('复制这个网址，到 Safari 里打开', u)); };
    });
  }

  // Binding an email: the current password, then a 6-digit code sent to the new address (as at sign-up).
  function bindEmailSheet(cur) {
    openSheet(`<div class="stack"><h2 class="h2" id="sheetTitle">${cur ? '更换' : '绑定'}邮箱</h2>
      <p class="muted small">先输入当前密码确认是你本人，再把发到新邮箱的 6 位验证码填回来。</p>
      <form id="bm" class="stack" novalidate><label class="field">邮箱<input name="email" type="email" autocomplete="email" inputmode="email" autocapitalize="off" spellcheck="false" required></label>
        ${pwField('当前密码', 'password', 'current-password')}
        <div class="code-row"><label class="field">验证码<input name="code" type="text" inputmode="numeric" autocomplete="one-time-code" maxlength="6" required></label>
          <button class="btn small" type="button" data-send>发送验证码</button></div>
        <button class="btn primary" type="submit">完成绑定</button></form>
      <p class="err" id="bmErr" role="alert"></p><button class="btn ghost" data-close type="button">取消</button></div>`, card => {
      bindEyes(card);
      const form = card.querySelector('#bm'), err = card.querySelector('#bmErr'), send = card.querySelector('[data-send]');
      send.onclick = async () => {
        err.textContent = ''; send.disabled = true;
        try { const r = await api('/api/account/email/request', { email: form.email.value.trim(), password: form.password.value, mode: 'code' }); toast(r.message || '验证码已发送'); countdown(send); form.code.focus(); }
        catch (x) { fieldError(form, err, { message: x.message, field: x.field || 'email' }); send.disabled = false; }
      };
      form.onsubmit = async e => {
        e.preventDefault(); err.textContent = '';
        if (!/^\d{6}$/.test(form.code.value.trim())) return fieldError(form, err, { message: '请先发送验证码，再填邮件里的 6 位数字', field: 'code' });
        const b = form.querySelector('[type=submit]'); b.disabled = true;
        try { await api('/api/account/email/confirm', { email: form.email.value.trim(), code: form.code.value.trim() }); closeSheet(); toast('邮箱已绑定，忘记密码时可以自己找回了'); await refreshHome(); route(true); }
        catch (x) { fieldError(form, err, x); b.disabled = false; }
      };
    });
  }
  // A new password ends every session, this one too: sign in again with it.
  function changePasswordSheet() {
    openSheet(`<div class="stack"><h2 class="h2" id="sheetTitle">修改密码</h2>
      <p class="muted small">改好以后，所有手机和电脑上的登录都会退出，用新密码重新登录就行。</p>
      <form id="cp" class="stack" novalidate>${pwField('原密码', 'old', 'current-password')}${pwField('新密码', 'new', 'new-password', '至少 10 位，最好是一句只有你知道的话')}
        ${pwField('再输一次新密码', 'again', 'new-password')}<button class="btn primary" type="submit">保存新密码</button></form>
      <p class="err" id="cpErr" role="alert"></p><button class="btn ghost" data-close type="button">取消</button></div>`, card => {
      bindEyes(card);
      const form = card.querySelector('#cp'), err = card.querySelector('#cpErr');
      form.onsubmit = async e => {
        e.preventDefault(); err.textContent = '';
        if (form.new.value.length < 10) return fieldError(form, err, { message: '新密码至少 10 位', field: 'new' });
        if (form.new.value !== form.again.value) return fieldError(form, err, { message: '两次输入的新密码不一样', field: 'again' });
        const b = form.querySelector('[type=submit]'); b.disabled = true;
        try {
          await api('/api/password', { old_password: form.old.value, new_password: form.new.value });
          S.user = null; S.csrf = ''; closeSheet(); await refreshHome(); route();
          openLogin('密码已修改，请用新密码登录。', 'pw');
        } catch (x) { fieldError(form, err, { message: x.message, field: /原密码/.test(x.message) ? 'old' : /新密码/.test(x.message) ? 'new' : '' }); b.disabled = false; }
      };
    });
  }
  // 我的数据 (account_data.py): the word book for Excel/WPS/Numbers or for Anki, or every record of the account. Plain
  // links: the server sends them as files. WeChat does not save files, so there the way out is the phone's browser.
  const EXPORTS = [['/api/next/export/cards.csv', '单词本 · Excel 表格', '.csv', 'export-csv'],
    ['/api/next/export/cards-anki.txt', '单词本 · 导入 Anki', '.txt', 'export-anki'],
    ['/api/next/export/records.json', '全部学习记录', '.json', 'export-json']];
  function dataSheet() {
    const n = S.home && S.home.stats ? S.home.stats.cards : null;
    openSheet(`<div class="stack"><h2 class="h2" id="sheetTitle">导出我的数据</h2>
      ${IN_WECHAT ? '<p class="small card sunk">微信里不能保存文件：点右上角「…」，选「在浏览器打开」，再到「我的 → 导出我的数据」。</p>' : ''}
      <div class="glist">${EXPORTS.map(([href, label, ext, tap], k) => `<a class="grow" href="${href}" download data-tap="${tap}"><span class="t">${label}</span><span class="v small muted">${k < 2 && n != null ? n + ' 条 · ' : ''}${ext}</span><span class="go" aria-hidden="true">↓</span></a>`).join('')}</div>
      <p class="tiny muted">表格用 Excel、WPS 或 Numbers 直接打开：英文、中文意思、原文例句、来源和复习情况各占一列。Anki：在电脑上「文件 → 导入」选这个文件，正面是英文，背面是中文意思和原文例句。全部学习记录是一个 JSON 文件，有单词本、每次复习、学过的材料、测评和设置，留底或换地方用。</p>
      <button class="btn ghost" data-close type="button">完成</button></div>`);
  }
  // 注销账号: what goes (all of it, for good), a copy first if wanted, the password once more. Afterwards this phone
  // forgets the account too.
  function deleteAccountSheet() {
    openSheet(`<div class="stack"><h2 class="h2" id="sheetTitle">注销账号</h2>
      <p class="small">注销后，这个账号和它的全部学习记录都会删除，<b>不能恢复</b>：单词本和复习安排、学过的材料、测评和能力雷达、写作和口语的批改记录、发过的问题反馈和截图。同样的用户名和邮箱以后可以重新注册，但会从头开始。</p>
      <p class="small">想留一份？<button class="link" id="dlFirst" type="button">先导出单词本和学习记录</button></p>
      <form id="da" class="stack" novalidate>${pwField('输入密码确认', 'password', 'current-password')}
        <button class="btn danger-btn" type="submit">永久注销这个账号</button></form>
      <p class="err" id="daErr" role="alert"></p><button class="btn ghost" data-close type="button">取消</button></div>`, card => {
      bindEyes(card);
      card.querySelector('#dlFirst').onclick = dataSheet;
      const form = card.querySelector('#da'), err = card.querySelector('#daErr');
      form.onsubmit = async e => {
        e.preventDefault(); err.textContent = '';
        if (!form.password.value) return fieldError(form, err, { message: '请输入密码', field: 'password' });
        const b = form.querySelector('[type=submit]'); b.disabled = true;
        try {
          await api('/api/account/delete', { password: form.password.value });
          forgetAccountHere(); S.user = null; S.csrf = ''; closeSheet(); await refreshHome();
          location.hash = '#/'; route(); toast('账号已注销，学习记录已全部删除');
        } catch (x) { fieldError(form, err, { message: x.message, field: 'password' }); b.disabled = false; }
      };
    });
  }
  // What this phone kept for the account: the copies (snapClear) and the small notes of where the learner was.
  // The phone's own choices (voice, text size, 复读) stay.
  function forgetAccountHere() {
    snapClear();
    try {
      ['flow-habit-lastweek', 'flow-habit-cheered', 'flow-next-mail-nudge', 'flow-next-suggest-skip', 'flow-words-stats'].forEach(k => localStorage.removeItem(k));
      Object.keys(localStorage).filter(k => k.startsWith('flow-next-steps-')).forEach(k => localStorage.removeItem(k));
    } catch (e) { /* private mode */ }
  }
  // A lost phone, a shared computer: end the account's sessions everywhere, this one included.
  function signOutEverywhere() {
    openSheet(`<div class="stack"><h2 class="h2" id="sheetTitle">退出所有设备？</h2>
      <p class="small">所有手机、平板和电脑上的语流都会退出登录，包括这一台。学习记录不会丢，重新登录就回来了。</p>
      <button class="btn primary" id="soAll" type="button">退出所有设备</button><button class="btn ghost" data-close type="button">取消</button></div>`, card => {
      card.querySelector('#soAll').onclick = async e => {
        e.currentTarget.disabled = true;
        await OUTBOX.flush(); try { await api('/api/logout', { all: true }); } catch (x) { /* signed out already */ } snapClear();
        S.user = null; S.csrf = ''; closeSheet(); await refreshHome(); toast('已在所有设备上退出'); route();
      };
    });
  }


  /* ---------- 问题反馈: what happened, the page it happened on, and up to three screenshots ---------- */
  // Anyone can send one, signed in or not (the server limits guests by a hashed address). The report carries the page
  // the learner came from, the site's version, the phone and browser, and the last few script errors: a page that
  // broke often says why in the console (ERRS, kept by 84-field.js). Read and closed in the operator console; nothing is
  // sent back.
  const FB_KINDS = [['display', '页面显示不对'], ['broken', '功能用不了'], ['content', '内容有错'], ['idea', '建议'], ['other', '其他']];
  const ASSET = (((document.querySelector('script[src*="next.js"]') || {}).src || '').split('v=')[1] || '').slice(0, 20);

  // A phone screenshot is large (1290 × 2796 on an iPhone): drawn at most 1600 px on its long side and sent as JPEG
  // under 650 KB, so three fit in one request. Read as a data: URL (the page's CSP allows data: images, not blob:).
  function shrinkShot(file) {
    return new Promise((ok, no) => {
      if (file.type && !/^image\//.test(file.type)) return no(new Error('只能添加图片'));
      const fr = new FileReader();
      fr.onerror = () => no(new Error('读不出这张图片，请换一张'));
      fr.onload = () => {
        const img = new Image();
        img.onerror = () => no(new Error('这个文件打不开，请换一张截图'));
        img.onload = () => {
          const k = Math.min(1, 1600 / Math.max(img.naturalWidth, img.naturalHeight, 1));
          const cv = document.createElement('canvas');
          cv.width = Math.max(1, Math.round(img.naturalWidth * k)); cv.height = Math.max(1, Math.round(img.naturalHeight * k));
          const g = cv.getContext('2d'); g.fillStyle = '#fff'; g.fillRect(0, 0, cv.width, cv.height); g.drawImage(img, 0, 0, cv.width, cv.height);
          for (const q of [0.82, 0.7, 0.55, 0.4]) { const d = cv.toDataURL('image/jpeg', q); if (d.length * 0.75 <= 650000) return ok(d); }
          no(new Error('这张图太大了，请裁小一点'));
        };
        img.src = fr.result;
      };
      fr.readAsDataURL(file);
    });
  }

  async function feedbackView() {
    const from = S.prevRoute && !/^feedback/.test(S.prevRoute) ? '#/' + S.prevRoute : '';
    let kind = 'display';
    const shots = [];
    view.innerHTML = `<div class="stack"><div><h1 class="h1">问题反馈</h1><span class="muted small">页面显示不对、功能用不了、内容有错，或者有建议，都可以告诉我们。</span></div>
      <form class="card stack fb" id="fbForm" novalidate>
        <div class="chips" role="radiogroup" aria-label="反馈类型">${FB_KINDS.map(([k, l]) => `<button type="button" class="chip" role="radio" data-k="${k}" aria-checked="${k === kind}">${l}</button>`).join('')}</div>
        <label class="stack-s" for="fbText"><b>发生了什么</b><span class="tiny muted">在哪个页面、点了什么、看到了什么。</span></label>
        <textarea id="fbText" rows="5" maxlength="1000" placeholder="比如：在「单词」页往下滑，底部的按钮跑到了屏幕中间。"></textarea>
        <div class="row between"><span class="tiny err" id="fbErr" role="alert"></span><span class="tiny muted" id="fbCount">0 / 1000</span></div>
        <div class="stack-s"><b>截图 <span class="tiny muted">可选，最多 3 张</span></b>
          <div class="fb-shots" id="fbShots"></div>
          <div><label class="btn" id="fbAdd">添加截图<input type="file" id="fbFile" accept="image/*" multiple class="sr-only"></label></div></div>
        ${S.user ? '' : `<label class="stack-s" for="fbContact"><b>联系方式 <span class="tiny muted">可不填</span></b></label>
        <input type="text" id="fbContact" maxlength="100" autocomplete="email" placeholder="邮箱或微信，方便我们问你细节">`}
        <label class="sr-only" aria-hidden="true">网址<input name="website" id="fbHp" tabindex="-1" autocomplete="off"></label>
        <p class="tiny muted">会一起发送：${from ? '你刚才在的页面、' : ''}网站版本、手机和浏览器型号${S.user ? '、你的账号' : ''}。截图只有管理员能看。</p>
        <button class="btn primary block" id="fbSend" type="submit">提交</button>
      </form></div>`;
    const form = document.getElementById('fbForm'), ta = document.getElementById('fbText'), box = document.getElementById('fbShots');
    const file = document.getElementById('fbFile'), add = document.getElementById('fbAdd'), send = document.getElementById('fbSend');
    const say = m => { document.getElementById('fbErr').textContent = m || ''; };
    form.querySelectorAll('[data-k]').forEach(b => b.onclick = () => {
      kind = b.dataset.k; form.querySelectorAll('[data-k]').forEach(x => x.setAttribute('aria-checked', String(x === b)));
    });
    ta.oninput = () => { document.getElementById('fbCount').textContent = `${ta.value.length} / 1000`; say(''); };
    const drawShots = () => {
      box.innerHTML = shots.map((d, k) => `<div class="fb-shot"><img src="${d}" alt="截图 ${k + 1}"><button type="button" data-rm="${k}" aria-label="去掉截图 ${k + 1}">×</button></div>`).join('');
      box.querySelectorAll('[data-rm]').forEach(b => b.onclick = () => { shots.splice(Number(b.dataset.rm), 1); drawShots(); });
      add.hidden = shots.length >= 3;
    };
    file.onchange = async () => {
      const list = [...file.files].slice(0, 3 - shots.length); file.value = '';
      add.classList.add('busy');
      for (const f of list) { try { shots.push(await shrinkShot(f)); say(''); } catch (x) { say(x.message); } }
      add.classList.remove('busy'); drawShots();
    };
    form.onsubmit = async e => {
      e.preventDefault();
      const text = ta.value.trim();
      if (text.length < 4) { say('请写几句发生了什么（至少 4 个字）'); ta.focus(); return; }
      send.disabled = true; send.textContent = '正在提交…';
      const c = document.getElementById('fbContact');
      try {
        await api('/api/feedback', { kind, text, contact: c ? c.value.trim() : '', page: from, images: shots, website: document.getElementById('fbHp').value,
          device: { ua: navigator.userAgent, w: innerWidth, h: innerHeight, dpr: devicePixelRatio || 1, lang: navigator.language || '', asset: ASSET,
            theme: matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light', standalone: STANDALONE(), wechat: IN_WECHAT, errors: ERRS.slice() } });
        view.innerHTML = `<div class="card done-card enter stack fb-done"><div class="big" aria-hidden="true">✓</div><h1 class="h1">已收到，谢谢！</h1>
          <p class="muted">${shots.length ? `连同 ${shots.length} 张截图一起收到了。` : ''}我们会尽快看，修好后会在新版本里更新。</p>
          <div class="row center"><a class="btn primary" href="${esc(from || '#/me')}">${from ? '回到刚才的页面' : '返回「我的」'}</a><button class="btn ghost" id="fbMore" type="button">再提一个</button></div></div>`;
        document.getElementById('fbMore').onclick = () => feedbackView();
      } catch (x) { say(x.message); send.disabled = false; send.textContent = '提交'; }
    };
  }
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
        repeat: !!(navigator.serviceWorker && navigator.serviceWorker.controller), snap: DATA.fromSnap, standalone: STANDALONE(),
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
  /* ---------- 分享卡片: a picture of what was learned, to keep or to send ---------- */
  // A learned expression (with the sentence it came in) or the week, drawn on a canvas as a 1080 px picture with a QR code
  // back to the site. In WeChat a long press saves or sends it; other phones get the system's share sheet; computers a
  // download. Nothing leaves the phone until the learner sends it.
  const SHARE_URL = 'https://flowlang.cn/?f=card';
  const shareFont = (s, w, serif) => `${w || 500} ${s}px ${serif ? "'Flow Serif', Georgia, 'Songti SC', serif" : "-apple-system, 'PingFang SC', 'Microsoft YaHei', sans-serif"}`;
  // Lines no wider than max: English breaks between words, Chinese between characters.
  function wrapLines(g, text, max) {
    const parts = String(text || '').match(/[　-〿㐀-鿿＀-￯]|[^\s　-〿㐀-鿿＀-￯]+\s*|\s+/g) || [];
    const lines = []; let line = '';
    parts.forEach(p => { if (line && g.measureText(line + p).width > max) { lines.push(line.trimEnd()); line = p.trimStart(); } else line += p; });
    if (line.trim()) lines.push(line.trimEnd());
    return lines;
  }
  function brandFoot(g, W, H, note) {
    const green = '#1f9d55';
    g.fillStyle = green; g.beginPath(); g.roundRect ? g.roundRect(80, H - 260, 84, 84, 22) : g.rect(80, H - 260, 84, 84); g.fill();
    g.strokeStyle = '#fff'; g.lineWidth = 8; g.lineCap = 'round';
    [[101, 37, 79], [117, 21, 95], [133, 29, 87], [149, 37, 71]].forEach(([x, a, b]) => { g.beginPath(); g.moveTo(x, H - 260 + a); g.lineTo(x, H - 260 + b); g.stroke(); });
    g.fillStyle = '#1b1d1a'; g.font = shareFont(40, 700); g.fillText('语流 Flow', 184, H - 222);
    g.fillStyle = '#6f7369'; g.font = shareFont(28, 400); g.fillText('每天一篇，学了就能用', 184, H - 180);
    if (note) { g.fillStyle = green; g.font = shareFont(28, 600); g.fillText(note, 80, H - 110); }
    QR.draw(g, SHARE_URL, W - 300, H - 300, 220, '#13261b', '#ffffff');
    g.fillStyle = '#6f7369'; g.font = shareFont(24, 400); g.textAlign = 'center'; g.fillText('扫码一起学', W - 190, H - 52); g.textAlign = 'left';
  }
  // The week, said only when there is something to say: the weeks that reached the goal (counted up, never a run that
  // breaks), or the days of this one. Shared right after studying (studiedNow), today counts even before 今日 is
  // fetched again. The week's card has its days already (weeksOnly; its seven days are not the calendar week either).
  function habitNote(studiedNow, weeksOnly) {
    const hb = S.user && S.home && S.home.stats && S.home.stats.habit;
    if (!hb) return '';
    const t = (hb.days || []).find(d => d.today), done = hb.done + (studiedNow && t && !t.active ? 1 : 0);
    const weeks = (hb.weeks || 0) + (done >= hb.goal && !hb.met ? 1 : 0);
    return weeks > 1 ? `一共有 ${weeks} 周达成了学习目标` : done > 0 && !weeksOnly ? `这周学了 ${done} 天` : '';
  }
  // A learned expression: big, its meaning, the sentence it came in, and where from.
  function sentenceCard(x, from, title) {
    const W = 1080, H = 1440, cv = document.createElement('canvas'); cv.width = W; cv.height = H;
    const g = cv.getContext('2d'), green = '#1f9d55', ink = '#1b1d1a', muted = '#6f7369';
    const bg = g.createLinearGradient(0, 0, 0, H); bg.addColorStop(0, '#f6fbf7'); bg.addColorStop(1, '#e6f2ea'); g.fillStyle = bg; g.fillRect(0, 0, W, H);
    // measured first (each block with its own font), then drawn as one block centred above the footer
    let size = 84, big;
    do { g.font = shareFont(size, 700, true); big = wrapLines(g, x.text, W - 160).slice(0, 4); size -= 6; } while (big.length > 3 && size > 48);
    size += 6;
    g.font = shareFont(38, 500); const mean = x.meaning ? wrapLines(g, x.meaning, W - 160).slice(0, 3) : [];
    g.font = shareFont(34, 400, true); const quote = from ? wrapLines(g, from, W - 200).slice(0, 4) : [];
    const height = 60 + big.length * size * 1.25 + (mean.length ? 20 + mean.length * 56 : 0) + (quote.length ? 56 + quote.length * 50 : 0) + (title ? 70 : 0);
    let y = Math.max(150, Math.round((H - 330 - height) / 2) + 40);
    g.fillStyle = green; g.font = shareFont(32, 700); g.fillText('今天学会的一句', 80, y); y += 60 + size;
    g.fillStyle = ink; g.font = shareFont(size, 700, true); big.forEach((l, k) => { if (k) y += size * 1.25; g.fillText(l, 80, y); });
    if (mean.length) { y += 76; g.fillStyle = '#3c4038'; g.font = shareFont(38, 500); mean.forEach((l, k) => { if (k) y += 56; g.fillText(l, 80, y); }); }
    if (quote.length) {
      y += 90; g.fillStyle = green; g.fillRect(80, y - 36, 6, (quote.length - 1) * 50 + 48);
      g.fillStyle = '#3c4038'; g.font = shareFont(34, 400, true); quote.forEach((l, k) => { if (k) y += 50; g.fillText(l, 110, y); });
    }
    if (title) { y += 70; g.fillStyle = muted; g.font = shareFont(28, 400); g.fillText(`出自《${title}》`, 80, y); }
    brandFoot(g, W, H, habitNote(true));
    return cv.toDataURL('image/png');
  }
  // The preview, and the ways out: a long press in WeChat, the share sheet where there is one, else a download.
  function shareSheet(pictures, title) {
    let k = 0;
    const filesOK = !IN_WECHAT && !!(navigator.canShare && window.File);
    openSheet(`<div class="stack"><h2 class="h2" id="sheetTitle">${esc(title)}</h2>
      ${pictures.length > 1 ? `<div class="chips share-pick" role="radiogroup" aria-label="选一句">${pictures.map((p, i) => `<button class="chip" type="button" role="radio" data-pic="${i}" aria-checked="${i === 0}">${esc(p.label)}</button>`).join('')}</div>` : ''}
      <img class="share-img" id="shareImg" alt="分享图片预览">
      <p class="small muted">${IN_WECHAT ? '长按图片，选「保存图片」或「发送给朋友」。' : '长按图片可以保存；也可以用下面的按钮。'}</p>
      <div class="row">${filesOK ? '<button class="btn primary" id="shareGo" type="button">分享…</button>' : ''}${IN_WECHAT ? '' : '<a class="btn" id="shareSave" download="语流-学习卡片.png">保存图片</a>'}<button class="btn ghost" data-close type="button">关闭</button></div></div>`, card => {
      const show = () => {
        const url = pictures[k].url || (pictures[k].url = pictures[k].draw());
        card.querySelector('#shareImg').src = url;
        const a = card.querySelector('#shareSave'); if (a) a.href = url;
      };
      card.querySelectorAll('[data-pic]').forEach(b => b.onclick = () => { k = Number(b.dataset.pic); card.querySelectorAll('[data-pic]').forEach(x => x.setAttribute('aria-checked', String(x === b))); show(); });
      const go = card.querySelector('#shareGo');
      if (go) go.onclick = async () => {
        try {
          const bin = atob(pictures[k].url.split(',')[1]), u = new Uint8Array(bin.length);  // a data: URL, read without fetch (the page's CSP)
          for (let i = 0; i < bin.length; i++) u[i] = bin.charCodeAt(i);
          const file = new File([u], '语流-学习卡片.png', { type: 'image/png' });
          if (navigator.canShare({ files: [file] })) await navigator.share({ files: [file], title: '语流 Flow' }); else toast('这个浏览器不能直接分享，长按图片保存吧');
        } catch (e) { if (e && e.name !== 'AbortError') toast('没有分享出去，长按图片保存吧'); }
      };
      show();
    });
  }
  // From a material: up to three of its expressions, each with the sentence of the text it is in.
  function shareFromMaterial(m) {
    const xs = (m.expressions || []).slice(0, 3); if (!xs.length) return toast('这篇没有可以分享的表达');
    const ls = m.sentences || [];
    shareSheet(xs.map(x => ({ label: x.text, draw: () => sentenceCard(x, ls.find(s => s.toLowerCase().includes(x.text.toLowerCase())) || '', m.title) })), '分享今天学会的一句');
  }
  /* ---------- boot ---------- */
  (async function boot() {
    wechatBar();
    if ('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js').catch(() => {});
    // The copy of the last 今日 kept on the phone (05-data.js): the page is drawn from it at once, then from the
    // server's answer, quietly, if anything changed. Offline, the copy stays on screen. The first visit waits.
    const snap = snapGet(), drawn = () => { firstViewDrawn(); prefetchTabs(); keepTodayOffline(); };
    if (snap && snap.home && snap.home.session) {
      S.home = snap.home; S.user = snap.home.session.user || null; S.csrf = ''; DATA.fromSnap = true; S.homeFresh = true; setDueBadge();
      const drawnFor = location.hash;
      route().then(drawn);
      try { if (await refreshHome()) redrawQuietly(drawnFor); } catch (e) { DATA.ok(); }
    } else {
      try { await refreshHome(); S.homeFresh = true; } catch (e) { DATA.ok(); /* offline: route() asks again and offers a retry */ }
      route().then(drawn);  // the opening time ends when the first page is drawn
    }
    OUTBOX.flush();
  })();
})();

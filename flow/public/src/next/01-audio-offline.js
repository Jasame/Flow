  /* ---------- speech (with word boundaries for read-along highlighting) ---------- */
  // WeChat's built-in browser (and some other in-app browsers) cannot use the browser voice, and plays sound only when it
  // starts inside a tap; the way out it offers is 「在浏览器打开」.
  const WECHAT = /MicroMessenger/i.test(navigator.userAgent);
  function noSound(what) { toast(WECHAT ? `微信里${what}：点右上角「···」，选「在浏览器打开」就能听` : `这个浏览器${what}，换 Safari 或 Chrome 试试`); }
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
    gaveUp() { if (!this.raf && !this.onEnd) return; toast('音频暂时没加载出来，稍后再点一次'); this.finish(); },
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
      const m = await api('/api/next/material?id=' + encodeURIComponent(id) + (S.user ? '' : '&level=' + encodeURIComponent(level())));
      MAT[id] = m; m._preloaded = Date.now();
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


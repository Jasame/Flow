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
    // A short sentence with no word highlighting goes to the server voice when it is on (SV below: CosyVoice, made once
    // and stored, works in WeChat too); reading a text along word by word keeps the browser voice, which reports words.
    say(text, onend, onword) {
      if (!onword && SV.on() && text && text.length <= SV.MAX) { SV.say(text, onend); return; }
      this.browser(text, onend, onword);
    },
    browser(text, onend, onword) {
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
    stop() { this.token++; if (this.ok) speechSynthesis.cancel(); if (SV.active) { SV.active = false; CLIP.stop(); } },
    can() { return this.ok || SV.on(); },  // some voice can say a sentence here
  };
  if (TTS.ok) speechSynthesis.onvoiceschanged = () => TTS.pick();

  /* ---------- server voice (tts_service): what the browser would say, in CosyVoice, made once and stored for everyone ---------- */
  // The first tap on a sentence asks the server for it (made then, 1–4 s, or already stored: at once); the file is played
  // on the short-clip player, which the first tap anywhere has unlocked (WeChat plays only sound started that way).
  // A guest gets only stored sentences; anything the server cannot give falls back to the browser voice.
  const SV = {
    MAX: 1500, urls: new Map(), active: false, off: false,
    on() { const s = S.home && S.home.session; return !!(s && s.tts) && !this.off; },
    async say(text, onend) {
      const t = ++TTS.token; if (TTS.ok) speechSynthesis.cancel();
      const key = S.voice + '|' + text;
      let u = this.urls.get(key);
      if (!u) {
        try { await DATA.ready; u = (await request('/api/next/tts', { text, voice: S.voice }, true)).j.url; this.urls.set(key, u); }  // not api(): it empties the data layer
        catch (e) {
          if (e.status === 503 || e.status === 429) this.off = true;  // off, or today's share is used: the browser voice from now on
          if (t === TTS.token) TTS.browser(text, onend);
          return;
        }
      }
      if (t !== TTS.token) return;  // stopped, or something else spoke, while the sentence was being made
      CLIP.play(u, 0, 1e6, text, () => { this.active = false; if (onend) onend(); }, null, { url: u, from: 0, to: Infinity, title: '语流' });
      this.active = true; TTS.token = t;  // CLIP.play stops the browser voice (a new token); keep this one current
    },
  };
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
    // server-voice files and word clips (.aac, cut by this server from a sprite) are not in R2
    if (!m || !m.base || !/^\/audio\//.test(url || '') || /^\/audio\/tts\//.test(url) || /\.aac(\?|$)/.test(url)) return '';
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
      this.stopLoop(); this.stopAt = to; this.onTick = onTick; this.onEnd = onEnd; this.paused = false;
      const a = this.audio, asked = a.src;
      this.name();
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
    finish() { this.stopLoop(); this.audio.dataset.want = ''; this.paused = false; MS.release('nar'); const cb = this.onEnd; this.onEnd = null; this.onTick = null; if (cb) cb(); },
    // the lock screen and the Dynamic Island: 「语流 · 标题」, play/pause, and previous/next sentence while a whole text plays
    name() {
      const id = (this.key.split('/')[1] || '').split('@')[0]; let m = null;
      try { m = MAT[id]; } catch (e) { /* the study page's cache (20-study.js) */ }
      MS.claim('nar', '语流 · ' + ((m && m.title) || '朗读'), {
        play: () => this.resume(), pause: () => this.audio.pause(), stop: () => { this.stop(); MINI.end(); },
        previoustrack: this.stopAt == null ? () => this.step(-1) : null, nexttrack: this.stopAt == null ? () => this.step(1) : null });
    },
    resume() { if (this.audio.dataset.want === '1') this.audio.play().catch(() => {}); },
    // previous / next sentence of a whole text (the page follows: onTick lights the sentence playing)
    step(d) {
      if (this.stopAt != null || !this.meta) return;
      const ss = this.meta.sentences, t = this.audio.currentTime;
      let i = ss.findIndex(x => t < x.e + 0.25); if (i < 0) i = ss.length - 1;
      if (d < 0 && t - ss[i].s > 1.5) d = 0;  // well into a sentence: back to its start first, as players do
      const j = Math.max(0, Math.min(ss.length - 1, i + d));
      try { this.audio.currentTime = ss[j].s; } catch (e) { /* not seekable yet */ }
    },
    gaveUp() { if (!this.raf && !this.onEnd) return; noteIssue('audio', '全文录音没加载出来', this.net ? this.net.split('?')[0] : ''); toast('音频暂时没加载出来，稍后再点一次'); this.finish(); },
    stopLoop() { cancelAnimationFrame(this.raf); this.raf = 0; },
    stop() { this.stopLoop(); this.audio.dataset.want = ''; this.paused = false; MS.release('nar'); this.onEnd = null; this.onTick = null; try { this.audio.pause(); } catch (e) { /* ignore */ } },
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
  // Paused by something other than the page (a call, the lock screen, another app's sound): the page says so (MINI:
  // 已暂停 and 继续) instead of showing it still playing; playing again (继续, the lock screen) takes it back.
  NAR.audio.addEventListener('pause', () => {
    const a = NAR.audio; if (a.dataset.want !== '1' || a.ended || (NAR.stopAt != null && a.currentTime >= NAR.stopAt)) return;
    NAR.paused = true; MS.state('paused'); MINI.pause(true, () => NAR.resume());
  });
  NAR.audio.addEventListener('play', () => { if (!NAR.paused || NAR.audio.dataset.want !== '1') return; NAR.paused = false; NAR.name(); MINI.pause(false); });
  function lightAt(container, charOffset) {
    container.querySelectorAll('.cur').forEach(el => el.classList.remove('cur'));
    if (charOffset == null) return;
    const el = container.querySelector(`[data-c="${charOffset}"]`); if (el) el.classList.add('cur');
  }
  /* ---------- what the lock screen and the Dynamic Island show while 语流 makes a sound (navigator.mediaSession) ---------- */
  // One owner at a time: 'nar' (a whole text, with play/pause and previous/next sentence) or 'short' (Web Audio below).
  // Without it iOS shows the page's address; with it, 「语流 · 标题」 and controls that act on the page.
  const MS = {
    owner: null, ACTIONS: ['play', 'pause', 'stop', 'previoustrack', 'nexttrack'],
    claim(owner, title, handlers) {
      this.owner = owner; const ms = navigator.mediaSession; if (!ms) return;
      try { ms.metadata = window.MediaMetadata ? new MediaMetadata({ title, artist: '语流 Flow' }) : null; } catch (e) { /* ignore */ }
      this.ACTIONS.forEach(k => { try { ms.setActionHandler(k, (handlers && handlers[k]) || null); } catch (e) { /* not supported */ } });
      this.state('playing');
    },
    state(st) { try { if (navigator.mediaSession) navigator.mediaSession.playbackState = st; } catch (e) { /* ignore */ } },
    release(owner) {
      if (this.owner !== owner) return; this.owner = null; const ms = navigator.mediaSession; if (!ms) return;
      try { ms.metadata = null; } catch (e) { /* ignore */ }
      this.ACTIONS.forEach(k => { try { ms.setActionHandler(k, null); } catch (e) { /* ignore */ } });
      this.state('none');
    },
  };

  /* ---------- short sounds on iPhones and iPads: Web Audio, so a word is heard from its first sound ---------- */
  // An <audio> is a media session for iOS: every play() sets one up (the Dynamic Island and Now Playing show it and take
  // it away again), and the moment that takes ate the start of a word (the owner, 2026-11-24). A buffer source starts
  // on the AudioContext's own clock, so nothing is lost. What WebKit does (its source, read 2026-11-25):
  //  - an AudioContext alone is in the Ambient category, which the ringer switch mutes, unless navigator.audioSession.type
  //    is 'playback' (or 'play-and-record'); under those it is eligible for Now Playing (AudioContext::isNowPlayingEligible)
  //    while it runs, so it is named 「语流」 (MS) and suspended 20 s after the last sound;
  //  - an <audio> shorter than 0.95 s is never shown in Now Playing (MediaElementSession, YouveGotMailDuration);
  //  - setting the type is refused where the page may not use the microphone: then this player is not used, and the
  //    short <audio> clips below are (the ringer switch does not mute those);
  //  - iOS 26 home-screen apps: a context may stay silent after the app comes back (WebKit bug 291892): it is closed when
  //    the page is hidden and made again for the next sound. ?audio=element turns this player off (?audio=auto: on again).
  const WORD_CLIPS = /iPhone|iPad|iPod/.test(navigator.userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  const CLIP_LEAD = 0.3;  // the silence in front of a cut clip (word_clip.LEAD)
  (() => { const m = /[?&]audio=(element|auto)\b/.exec(location.search); if (m) save('flow-audio', m[1] === 'auto' ? null : m[1]); })();
  const AUDIO = {
    ctx: null, src: null, done: null, own: null, token: 0, bufs: new Map(), idle: 0, off: false,
    AC: window.AudioContext || window.webkitAudioContext,
    usable() { return WORD_CLIPS && !!this.AC && !!navigator.audioSession && !this.off && load('flow-audio') !== 'element'; },
    // The page's audio session type, for this player and for recording (语流 9): AUDIO.session('play-and-record') before
    // the microphone, AUDIO.session('playback') after. Returns the type in effect ('playback', 'play-and-record', 'auto'…),
    // or null where the browser has no navigator.audioSession (then nothing is changed). A type WebKit refuses (no
    // microphone allowed) stays as it was: compare the result with what was asked.
    session(type) {
      const as = navigator.audioSession; if (!as) return null;
      try { if (type && as.type !== type) as.type = type; } catch (e) { /* refused */ }
      return as.type || null;
    },
    context() {
      if (!this.ctx) {
        try { this.ctx = new this.AC(); } catch (e) { this.off = true; return null; }
        this.ctx.onstatechange = () => {  // a call or another app took the sound: what was playing is over
          const c = this.ctx; if (!c || !this.src || c.state === 'running') return;
          const end = this.done; this.stop(); if (end) end();
        };
      }
      return this.ctx;
    },
    // the first tap anywhere: the context is started once inside it (later sounds may start it outside a tap: a word
    // said when its look-up arrives), then rests, so nothing shows in the Dynamic Island until a sound plays
    wake() {
      if (!this.usable()) return;
      const c = this.context(); if (!c || c.state === 'running') return;
      c.resume().then(() => { if (!this.src && !this.own) c.suspend().catch(() => {}); }).catch(() => {});
    },
    buffer(url) {
      if (this.bufs.has(url)) { const b = this.bufs.get(url); this.bufs.delete(url); this.bufs.set(url, b); return b; }  // most recent last
      const c = this.ctx;
      const p = fetch(url).then(r => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.arrayBuffer(); })
        .then(data => new Promise((ok, no) => { const q = c.decodeAudioData(data, ok, no); if (q && q.then) q.then(ok, no); }));
      p.catch(() => this.bufs.delete(url));
      this.bufs.set(url, p); while (this.bufs.size > 40) this.bufs.delete(this.bufs.keys().next().value);
      return p;
    },
    // url from `from` to `to` seconds (Infinity: to its end) at `rate`. onend when it is over; onfail(error) when it
    // cannot (the caller then plays it the old way). False at once when this player is not to be used here.
    // own: a second slot that does not stop the first (the learner's recording after the original).
    play(url, from, to, rate, onend, onfail, title, own) {
      if (!this.usable()) return false;
      if (this.session('playback') !== 'playback') { this.off = true; return false; }  // refused: the ringer switch would mute it
      const c = this.context(); if (!c) return false;
      if (!own) this.stop();
      const t = own ? 0 : ++this.token;
      clearTimeout(this.idle);
      if (c.state !== 'running') c.resume().catch(() => {});
      MS.claim('short', title || '语流', { pause: () => this.halt(), stop: () => this.halt() });
      this.buffer(url).then(buf => {
        if (!own && t !== this.token) return;
        const s = c.createBufferSource(); s.buffer = buf; s.playbackRate.value = rate || 1; s.connect(c.destination);
        const start = Math.max(0, from || 0), end = Math.min(buf.duration, to === Infinity || to == null ? buf.duration : to);
        s.onended = () => {
          if (own ? this.own !== s : this.src !== s) return;
          if (own) this.own = null; else { this.src = null; this.done = null; }
          this.rest(); if (onend) onend();
        };
        if (own) { if (this.own) { this.own.onended = null; try { this.own.stop(); } catch (e) { /* ignore */ } } this.own = s; } else { this.src = s; this.done = onend; }
        s.start(c.currentTime + 0.03, start, Math.max(0.01, end - start));
        // a context that would not run (refused outside a tap, or broken): the old way, once
        setTimeout(() => { if ((own ? this.own : this.src) === s && c.state !== 'running') { if (own) this.own = null; else this.stop(); if (onfail) onfail(new Error('not running')); } }, 1500);
      }).catch(e => { if ((own || t === this.token) && onfail) onfail(e); });
      return true;
    },
    stop() { this.token++; const s = this.src; this.src = null; this.done = null; if (s) { s.onended = null; try { s.stop(); } catch (e) { /* not started */ } } },
    halt() { this.stop(); if (this.own) { this.own.onended = null; try { this.own.stop(); } catch (e) { /* ignore */ } this.own = null; } this.rest(); },
    // 20 s after the last sound the context rests: WebKit takes 语流 out of Now Playing (and the Dynamic Island)
    rest() {
      clearTimeout(this.idle);
      this.idle = setTimeout(() => { if (this.src || this.own || !this.ctx) return; if (this.ctx.state === 'running') this.ctx.suspend().catch(() => {}); MS.release('short'); }, 20000);
    },
    drop() { this.halt(); clearTimeout(this.idle); const c = this.ctx; this.ctx = null; if (c) c.close().catch(() => {}); MS.release('short'); },
  };
  document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'hidden') AUDIO.drop(); });

  /* ---------- short clips: a word's pronunciation, one sentence of a narration, a sentence of the server voice ---------- */
  // On iPhones and iPads these play on AUDIO (above). Where it is not used, or fails, an <audio> plays them: there a word
  // is its own small file, cut by the server with 0.3 s of silence in front (word_clip.py), played from its start, so
  // the waking of the sound happens in the silence; elsewhere the sprite is played as before.
  const CLIP = {
    audio: new Audio(), raf: 0, metas: {}, want: null,
    accent() { return (S.voice || 'us-f').startsWith('uk') ? 'uk' : 'us'; },
    stop() { AUDIO.stop(); cancelAnimationFrame(this.raf); this.want = null; this.audio.dataset.want = ''; try { this.audio.pause(); } catch (e) { /* not playing */ } },
    // play() is called right away, inside the tap: in-app browsers (WeChat) and iPhones refuse a play() that starts
    // later, when the file has loaded. A new file plays muted until it has jumped to the clip.
    // text: said by the browser voice if neither line can play the clip.
    // to: Infinity plays a file to its end (a word clip). fallback: [src, from, to] played instead if src fails.
    // wa: {url, from, to, title}: what AUDIO plays instead, where it is used.
    play(src, from, to, text, onend, fallback, wa) {
      NAR.stop(); TTS.stop(); this.stop();
      const want = this.want = { from, to, text, onend, fallback };
      if (wa && AUDIO.play(wa.url, wa.from, wa.to, TTS.rate, () => { if (this.want === want) { this.want = null; if (onend) onend(); } },
        () => { if (this.want === want) this.element(src, from, to, text, onend, fallback, want); }, wa.title)) { want.wa = true; return; }
      this.element(src, from, to, text, onend, fallback, want);
    },
    element(src, from, to, text, onend, fallback, want) {
      const a = this.audio;
      const loop = () => { if (this.want !== want) return; if (a.currentTime >= to || a.ended) { a.pause(); this.want = null; if (onend) onend(); return; } this.raf = requestAnimationFrame(loop); };
      const refused = e => { if (this.want === want && e && e.name === 'NotAllowedError') noSound('没有放出声音'); };
      claim(a); a.playbackRate = TTS.rate; a.dataset.want = '1'; a._from = from;
      if (a.dataset.src === src && a.readyState >= 1) {
        try { a.currentTime = from; } catch (e) { /* not seekable yet */ }
        a.muted = false; a.play().catch(refused); this.raf = requestAnimationFrame(loop); return;
      }
      mediaSrc(a, src);
      if (!from && to === Infinity) { a.muted = false; a.play().catch(refused); this.raf = requestAnimationFrame(loop); return; }  // from its start: no jump to wait for
      a.muted = true;
      a.addEventListener('loadedmetadata', () => { if (this.want === want) { try { a.currentTime = from; } catch (e) { /* ignore */ } } }, { once: true });
      a.addEventListener('seeked', () => { if (this.want !== want) return; a.muted = false; this.raf = requestAnimationFrame(loop); }, { once: true });
      a.play().catch(refused);
    },
    // c: {text, audio: {us: [sprite, start, end], uk: [...]}}; falls back to the browser voice
    word(c) {
      const au = c.audio || {}, ac = au[this.accent()] ? this.accent() : au.us ? 'us' : au.uk ? 'uk' : null;
      if (!ac) { TTS.say(c.text); return; }
      const w = au[ac], sprite = `/audio/words/${ac}/${w[0]}.mp4`, clip = `/audio/words/${ac}/${w[0]}.aac?s=${w[1]}&e=${w[2]}`;
      if (WORD_CLIPS) this.play(clip, 0, Infinity, c.text, null, [sprite, w[1], w[2]], { url: clip, from: CLIP_LEAD - 0.02, to: CLIP_LEAD + w[2] - w[1] + 0.04, title: '语流 · 单词' });
      else this.play(sprite, w[1], w[2], c.text);
    },
    // the file word(c) plays: the word's own clip on an iPhone or iPad, its sprite elsewhere (prefetched by the review)
    wordSrc(c) {
      const au = (c && c.audio) || {}, ac = au[this.accent()] ? this.accent() : au.us ? 'us' : au.uk ? 'uk' : null;
      if (!ac) return null;
      const w = au[ac];
      return WORD_CLIPS ? `/audio/words/${ac}/${w[0]}.aac?s=${w[1]}&e=${w[2]}` : `/audio/words/${ac}/${w[0]}.mp4`;
    },
    // ex: {pack, i, text, audio: narration version or 0}
    async sentence(ex) {
      if (!ex.audio) { TTS.say(ex.text); return; }
      const key = S.voice + '/' + ex.pack;
      try {
        if (!this.metas[key]) this.metas[key] = await mediaJSON(`/audio/${S.voice}/${encodeURIComponent(ex.pack)}.json?v=${ex.audio}`);
        const s = this.metas[key].sentences[ex.i]; if (!s) throw new Error('no sentence');
        const base = `/audio/${S.voice}/${encodeURIComponent(ex.pack)}`, e = s.e + 0.05;
        this.play(`${base}.mp4?v=${ex.audio}`, s.s, e, ex.text, null, null,
          { url: `${base}.aac?v=${ex.audio}&s=${s.s}&e=${e}`, from: CLIP_LEAD - 0.02, to: CLIP_LEAD + e - s.s + 0.02, title: '语流 · 例句' });
      } catch (e) { TTS.say(ex.text); }
    },
    // the learner's own recording (a blob: URL), after or beside the original: it does not stop what plays
    mine(url, onend) {
      if (AUDIO.play(url, 0, Infinity, 1, onend, () => this.mineElement(url, onend), '语流 · 我的录音', true)) return;
      this.mineElement(url, onend);
    },
    mineElement(url, onend) { const a = new Audio(url); if (onend) a.onended = () => onend(); a.play().catch(() => { if (onend) onend(); }); },
  };
  CLIP.audio.addEventListener('error', () => {
    const w = CLIP.want; if (!w || !mediaGaveUp(CLIP.audio)) return;
    if (w.fallback) { const n = CLIP.want = { ...w, fallback: null }; CLIP.element(w.fallback[0], w.fallback[1], w.fallback[2], w.text, w.onend, null, n); return; }  // no clip from the server: the sprite, as before (once)
    CLIP.stop(); if (w.text) TTS.browser(w.text, w.onend);  // not TTS.say: that may be this player again (the server voice); onend still runs (对比回放 plays the recording then)
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
    AUDIO.wake();
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
    update(label) { if (this.el && !this.el.hidden && !this.el.classList.contains('paused')) this.el.querySelector('.lbl').textContent = label; },
    hide() { if (this.el) { this.el.hidden = true; this.el.classList.remove('paused'); } document.body.classList.remove('playing'); },
    // paused from outside the page (a call…): 已暂停, and 继续 next to 停止
    pause(on, resume) {
      if (!this.el || this.el.hidden) return;
      this.el.classList.toggle('paused', !!on);
      let b = this.el.querySelector('.resume');
      if (on) {
        this.label = this.label || this.el.querySelector('.lbl').textContent; this.el.querySelector('.lbl').textContent = '已暂停';
        if (!b) { b = document.createElement('button'); b.type = 'button'; b.className = 'resume'; b.innerHTML = `${playIcon(false, 15)}<span>继续</span>`; this.el.insertBefore(b, this.el.querySelector('.stop')); }
        b.onclick = resume;
      } else { if (b) b.remove(); if (this.label) this.el.querySelector('.lbl').textContent = this.label; this.label = null; }
    },
    end() { const b = this.el && !this.el.hidden && this.el.querySelector('.stop'); if (b) b.click(); },
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


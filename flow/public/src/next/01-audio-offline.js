  /* ---------- speech (with word boundaries for read-along highlighting) ---------- */
  // WeChat's built-in browser (and some other in-app browsers) cannot use the browser voice, and plays sound only when it
  // starts inside a tap; the way out it offers is 「在浏览器打开」.
  const WECHAT = /MicroMessenger/i.test(navigator.userAgent);
  // the voice a page falls back to: in a browser its own, in 语流's apps the system's (iOS, Android, desktop: B3, 2026-11-25)
  const SYS_VOICE = () => (window.FlowApp ? '系统自带的声音' : '浏览器的声音');
  function noSound(what) { noteIssue('audio', what + (WECHAT ? '（微信）' : '')); toast(WECHAT ? `微信里${what}：点右上角「···」，选「在浏览器打开」就能听` : `这个浏览器${what}，换 Safari 或 Chrome 试试`); }
  const TTS = {
    ok: 'speechSynthesis' in window, rate: Number(load('flow-next-rate')) || 1, voice: null, token: 0,
    // the browser's English voice in the accent of 朗读声音 (S.voice: us-… or uk-…)
    pick() {
      if (!this.ok) return null;
      const uk = (S.voice || '').startsWith('uk'), vs = speechSynthesis.getVoices().filter(v => /^en[-_]/i.test(v.lang));
      const pref = uk ? ['Daniel', 'Kate', 'Serena', 'Google UK English Female', 'Google UK English Male', 'Microsoft Sonia', 'Microsoft Libby']
        : ['Samantha', 'Google US English', 'Microsoft Aria', 'Microsoft Jenny', 'Karen', 'Daniel', 'Google UK English Female'];
      this.voice = pref.map(n => vs.find(v => v.name.includes(n))).find(Boolean) || vs.find(v => (uk ? /en[-_]GB/i : /en[-_]US/i).test(v.lang)) || vs[0] || null;
      this.accent = uk ? 'uk' : 'us';
      return this.voice;
    },
    // A sentence goes to the server voice whenever it is on (SV below: CosyVoice, made once and stored, works in WeChat
    // too), word highlighting or not: the owner hears the browser voice as a robot (2026-11-25), so a text is lit sentence
    // by sentence rather than read by it. onword counts only where the browser voice reads. o: {pack, voice, title}.
    say(text, onend, onword, o) {
      if (SV.on() && text && text.length <= SV.MAX) { SV.say(text, onend, { ...(o || {}), onword }); return; }
      this.browser(text, onend, onword);
    },
    // onfail: the sentence was not said (no voice, or iOS dropped it twice); without it, onend is called then, so whoever
    // waits on the sentence goes on (a whole text pauses instead: LONG). onstart: the voice has begun this sentence.
    browser(text, onend, onword, onfail, onstart) {
      LONG.other();
      if (!this.ok) { noSound('不能用电脑朗读的声音'); if (onfail) onfail(); return; }
      const t = ++this.token, busy = speechSynthesis.speaking || speechSynthesis.pending;
      if (busy) speechSynthesis.cancel();
      // iOS sometimes drops an utterance spoken right after cancel() (语流 07 on the iPhone 17e and iPad simulators,
      // 2026-11-25): it ends at once without starting, or it never starts. So: cancel only what is speaking, speak a beat
      // later when something was cancelled, and take an end without a start as a dropped sentence: try it once more,
      // then give up (onfail) rather than count it as said (a whole text would race to its end and be marked heard).
      let tries = 0;
      const say = () => {
        if (t !== this.token) return;
        const u = new SpeechSynthesisUtterance(text), uk = (S.voice || '').startsWith('uk');
        u.lang = uk ? 'en-GB' : 'en-US'; u.rate = this.rate; const v = this.voice && this.accent === (uk ? 'uk' : 'us') ? this.voice : this.pick(); if (v) u.voice = v;
        let started = false, ended = false, poll = 0, heard = 0, reach = -1;
        const give = () => { ended = true; clearTimeout(watch); clearInterval(poll); if (t !== this.token) return; if (onfail) onfail(); else if (onend) onend(); };  // final: an end the cancel brings later is not counted
        const again = () => { clearTimeout(watch); clearInterval(poll); if (t !== this.token) return; if (++tries < 2) setTimeout(say, 250); else give(); };
        const done = () => { if (ended) return; ended = true; clearInterval(poll); if (t === this.token && onend) onend(); };
        // Word boundaries say how far the voice really got (each word as it is said): kept whether or not words are lit
        const words = [...text.matchAll(/\S+/g)], lastWord = words.length ? words[words.length - 1].index : 0;
        u.onboundary = e => {
          if (e.name === 'sentence') return;
          heard = Date.now(); reach = Math.max(reach, e.charIndex);
          if (onword && t === this.token) onword(e.charIndex);
        };
        u.onstart = () => {
          started = true; clearTimeout(watch); if (t === this.token && onstart) onstart();
          // Started, then never said it ended. Two kinds (语流 B5's runs, 2026-11-25), told apart by the word boundaries:
          // - the voice went quiet without an end (speaking false): after half a second the sentence counts as said;
          // - the voice says "speaking" on and on: with the words reported up to the last one and then nothing for a
          //   moment, it was said (end not reported); stuck part-way (an iPad offline: two words, then nothing, the next
          //   sentence pending for ever) it was not: stop it and let the text wait at that sentence, saying why.
          //   A voice that reports no words at all is let go after the longest the sentence could take.
          let quiet = 0;
          const rate = this.rate || 1, t0 = Date.now(), lull = Math.max(2500, 2000 / rate);
          const cap = t0 + Math.max(8000, words.length * 700 / rate + 3000);
          poll = setInterval(() => {
            if (t !== this.token || ended) { clearInterval(poll); return; }
            if (!speechSynthesis.speaking && !speechSynthesis.pending) { if (++quiet >= 2) done(); return; }
            quiet = 0;
            const now = Date.now();
            if (heard && reach >= lastWord && now - heard > 1500 / rate) { clearInterval(poll); speechSynthesis.cancel(); done(); return; }  // all said
            if ((heard && reach < lastWord && now - heard > lull) || now > cap) { clearInterval(poll); speechSynthesis.cancel(); give(); }  // stuck
          }, 250);
        };
        u.onend = () => { clearTimeout(watch); if (t !== this.token || ended) return; if (started) done(); else again(); };
        u.onerror = e => { if (e && /interrupted|canceled/.test(e.error || '')) { clearTimeout(watch); clearInterval(poll); return; } if (!ended) again(); };  // ours: stopped, or a new sentence
        // A browser with speechSynthesis but no voice to speak with (WeChat on Android) neither starts nor fails: after
        // 2.5 s without a start, say so (and stop counting on it) instead of waiting in silence. One that has voices but
        // did not start this time (an iPad offline, 语流 B5's run 2026-11-25) is no reason to send anyone to another
        // browser: a whole text says why at its sentence (onfail), a single sentence asks for one more tap.
        const watch = setTimeout(() => {
          if (t !== this.token || started) return;
          speechSynthesis.cancel();
          if (!speechSynthesis.getVoices().length) { this.ok = false; noSound('不能用电脑朗读的声音'); } else if (!onfail) toast(`${SYS_VOICE()}这次没读出来，再点一次试试`);
          give();
        }, 2500);
        try { speechSynthesis.speak(u); } catch (e) { again(); }  // refused outright: as a dropped sentence
      };
      if (busy) setTimeout(say, 60); else say();
    },
    stop() { this.token++; if (this.ok) speechSynthesis.cancel(); SV.note(''); if (SV.active) { SV.active = false; CLIP.stop(); } },
    can() { return this.ok || SV.on(); },  // some voice can say a sentence here
  };
  if (TTS.ok) speechSynthesis.onvoiceschanged = () => TTS.pick();

  /* ---------- server voice (tts_service): what the browser would say, in CosyVoice, made once and stored for everyone ---------- */
  // The first tap on a sentence asks the server for it (made then, 1–4 s, or already stored: at once); the file is played
  // on the short-clip player, which the first tap anywhere has unlocked (WeChat plays only sound started that way).
  // One address book for every page (听, 读, 跟读, 口语, 雅思…): a sentence is asked for once in a voice, and the answer is
  // kept on this phone for 30 days (at most 600), so what was heard before plays offline too (sw.js keeps the files). A
  // sentence of the learner's own article goes with its pack, so its file is the owner's only (/audio/own/).
  // While a sentence is being made a line says so (after 0.6 s); when the browser voice has to read instead, one line
  // says why (today's share used, offline, the network, too slow), once per reason while the page is open.
  const SV = {
    MAX: 1500, urls: new Map(), active: false, off: '', told: new Set(), KEY: 'flow-sv-urls', KEEP: 600, DAYS: 30, SLOW: 20000,
    on() { const s = S.home && S.home.session; return !!(s && s.tts) && !this.off; },
    key(text, o) { return ((o && o.voice) || S.voice || 'us-f') + '|' + ((o && o.pack) || '') + '|' + text; },
    hash(k) {  // a short name for the address book (cyrb53)
      let a = 0xdeadbeef, b = 0x41c6ce57;
      for (let i = 0; i < k.length; i++) { const c = k.charCodeAt(i); a = Math.imul(a ^ c, 2654435761); b = Math.imul(b ^ c, 1597334677); }
      a = Math.imul(a ^ (a >>> 16), 2246822507) ^ Math.imul(b ^ (b >>> 13), 3266489909); b = Math.imul(b ^ (b >>> 16), 2246822507) ^ Math.imul(a ^ (a >>> 13), 3266489909);
      return (b >>> 0).toString(36) + (a >>> 0).toString(36);
    },
    kept() {
      if (!this._kept) { const o = load(this.KEY) || {}, cut = Date.now() - this.DAYS * 864e5; for (const k of Object.keys(o)) if (!Array.isArray(o[k]) || o[k][1] < cut) delete o[k]; this._kept = o; }
      return this._kept;
    },
    keep(k, u) {
      const o = this.kept(); o[this.hash(k)] = [u, Date.now()];
      const ks = Object.keys(o); if (ks.length > this.KEEP) ks.sort((x, y) => o[x][1] - o[y][1]).slice(0, ks.length - this.KEEP).forEach(x => delete o[x]);
      clearTimeout(this._save); this._save = setTimeout(() => save(this.KEY, o), 400);
    },
    // -> Promise of the sentence's address; rejects with an Error whose .code says why (off, cap, import_cap, busy,
    // guest, store, gateway, offline, net). Online the server is always asked (a stored sentence answers at once); the
    // address kept on the phone is used when it cannot be reached.
    url(text, o) {
      const k = this.key(text, o);
      if (this.urls.has(k)) return this.urls.get(k);
      const p = (async () => {
        await DATA.ready;
        try {
          const u = (await request('/api/next/tts', { text, voice: (o && o.voice) || S.voice, ...(o && o.pack ? { pack: o.pack } : {}) }, true)).j.url;  // not api(): it empties the data layer
          this.keep(k, u); return u;
        } catch (e) {
          const old = this.kept()[this.hash(k)];
          if (e.network && old) return old[0];
          const err = new Error(e.message); err.server = e.message;
          err.code = e.network ? (navigator.onLine === false ? 'offline' : 'net') : (e.code || (e.status >= 500 ? 'gateway' : 'other'));
          // the day's AI stop (ai_day_full) is not switched off here: sentences made already still come from the server
          if (err.code === 'off' || err.code === 'cap') this.off = err.code;  // today's share used (or switched off): the browser voice from now on
          throw err;
        }
      })();
      this.urls.set(k, p); p.catch(() => this.urls.delete(k));  // a failure is asked again next time
      return p;
    },
    // what is made already, in one request (an article's sentences; an import is made in the background after importing)
    async have(texts, o) {
      if (!this.on() || !texts.length) return 0;
      try {
        await DATA.ready;
        const r = await request('/api/next/tts/have', { voice: S.voice, texts, ...(o && o.pack ? { pack: o.pack } : {}) }, true);
        let n = 0;
        r.j.urls.forEach((u, i) => { if (!u) return; n += 1; const k = this.key(texts[i], o); if (!this.urls.has(k)) this.urls.set(k, Promise.resolve(u)); this.keep(k, u); });
        return n;
      } catch (e) { return 0; }
    },
    // one line on why the browser voice reads this time; once per reason while the page is open
    why(e) {
      const code = (e && e.code) || 'other';
      this.lines = this.lines || {};
      const v = SYS_VOICE();
      const line = this.lines[code] || { offline: `离线中，这句还没存到本机，先用${v}`, net: `网络不好，这句先用${v}`, slow: `自然人声这次生成得太慢，先用${v}`,
        guest: `登录后能听 AI 朗读（自然人声），现在先用${v}`, off: `AI 朗读（自然人声）暂时没开，先用${v}`,
        ai_day_full: `今天的 AI 用量已满，北京时间早上 8 点恢复；新的句子先用${v}，已经生成过的照常放` }[code]
        || (e && e.server) || `AI 朗读（自然人声）这次没生成出来，先用${v}`;
      this.lines[code] = line;
      if (!this.told.has(code)) { this.told.add(code); toast(line); noteIssue('audio', '服务器朗读退回浏览器声音', code); }
      return line;
    },
    slow(p) { return Promise.race([p, new Promise((ok, no) => setTimeout(() => no(Object.assign(new Error('slow'), { code: 'slow' })), this.SLOW))]); },
    // 「正在准备朗读…」 over the page, from 0.6 s until the sentence is ready (or something else speaks)
    note(text) {
      let el = document.getElementById('svWait');
      if (!text) { if (el) el.hidden = true; return; }
      if (!el) { el = document.createElement('div'); el.id = 'svWait'; el.className = 'sv-wait'; el.setAttribute('role', 'status'); document.body.appendChild(el); }
      el.textContent = text; el.hidden = false;
    },
    async say(text, onend, o) {
      o = o || {};
      const t = ++TTS.token; if (TTS.ok) speechSynthesis.cancel();
      const k = this.key(text, o), ready = this.urls.has(k);
      const late = ready ? 0 : setTimeout(() => { if (t === TTS.token) this.note('正在准备朗读…'); }, 600);
      let u = null, err = null;
      try { u = await this.slow(this.url(text, o)); } catch (e) { err = e; }
      clearTimeout(late);
      if (t !== TTS.token) return;  // stopped, or something else spoke, while the sentence was being made
      this.note('');
      if (!u) { this.why(err); TTS.browser(text, onend, o.onword); return; }
      CLIP.play(u, 0, 1e6, text, () => { this.active = false; if (onend) onend(); }, null, { url: u, from: 0, to: Infinity, title: o.title || '语流' });
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
    // server-voice files, a learner's own articles' voice (private: never asked of another host) and word clips (.aac, cut
    // by this server from a sprite) are not in R2
    if (!m || !m.base || !/^\/audio\//.test(url || '') || /^\/audio\/(tts|own)\//.test(url) || /\.aac(\?|$)/.test(url)) return '';
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
      LONG.other();
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
    NAR.paused = true; MS.state('paused');
    if (LONG.nar()) LONG.held(); else MINI.pause(true, () => NAR.resume());
  });
  NAR.audio.addEventListener('play', () => {
    if (!NAR.paused || NAR.audio.dataset.want !== '1') return;
    NAR.paused = false; NAR.name();
    if (LONG.nar()) LONG.going(); else MINI.pause(false);
  });
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
      // 「AI 朗读」 on the lock screen, the notification shade and a desktop's media controls too (they draw from this, not
      // the page; 《标识办法》): every voice 语流 plays is synthesized (Kokoro, CosyVoice). The same as the desktop app's #199
      try { ms.metadata = window.MediaMetadata ? new MediaMetadata({ title, artist: '语流 Flow · AI 朗读' }) : null; } catch (e) { /* ignore */ }
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

  /* ---------- short sounds on iPhones and iPads ---------- */
  // An <audio> is a media session for iOS: every play() sets one up (the Dynamic Island and Now Playing show it and take
  // it away again), and the moment that takes ate the start of a word (the owner, 2026-11-24). Two ways, both on the
  // 内测版 until the owner has tried them on an iPhone and chosen one before the next release (语流 1, 2026-11-25):
  //  - 连续 (the default): Web Audio (AUDIO, here). A buffer source starts on the context's own clock, so nothing is
  //    lost; the island shows 「语流 · 单词」 while words are being played, and goes 20 s after the last.
  //  - 标准 (我的 → 设置 → 单词读音方式, or ?audio=element in Safari): short <audio> clips cut by the server with
  //    silence in front (CLIP below). Under 0.95 s an <audio> is not shown in Now Playing: about 66% of the American
  //    and 55% of the British words are, with 0.2 s in front.
  // Neither is silenced by the ringer switch. What WebKit does (its source, read 2026-11-25):
  //  - an AudioContext alone is in the Ambient category, which the ringer switch mutes, unless navigator.audioSession.type
  //    is 'playback' (or 'play-and-record'); under those it is eligible for Now Playing (AudioContext::isNowPlayingEligible)
  //    while it runs, so it is named 「语流」 (MS) and suspended 20 s after the last sound;
  //  - an <audio> shorter than 0.95 s is never shown in Now Playing (MediaElementSession, YouveGotMailDuration);
  //  - setting the type is refused where the page may not use the microphone: then this player is not used, and the
  //    short <audio> clips below are (the ringer switch does not mute those);
  //  - iOS 26 home-screen apps: a context may stay silent after the app comes back (WebKit bug 291892): it is closed when
  //    the page is hidden and made again for the next sound.
  const WORD_CLIPS = /iPhone|iPad|iPod/.test(navigator.userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  (() => {  // switches for trying in Safari: ?audio=element|compat|auto|webaudio, ?lead=0.05–0.4|auto (silence before a word)
    const q = location.search, a = /[?&]audio=(webaudio|element|compat|auto)\b/.exec(q), l = /[?&]lead=([\d.]+|auto)\b/.exec(q);
    if (a) save('flow-audio', a[1] === 'element' || a[1] === 'compat' ? 'compat' : null);
    if (l) save('flow-lead', l[1] === 'auto' ? null : Number(l[1]));
  })();
  // the silence in front of a cut clip: long enough for an iPhone to wake its sound, short enough that most words stay
  // under 0.95 s (word_clip.LEAD; with 0.2 s, 66% of the American and 55% of the British words do)
  // (我的 → 设置 → 单词读音方式 sets it too; read at each play, so a change counts at once)
  const LEADS = [0.1, 0.15, 0.2, 0.25, 0.3], LEAD_DEFAULT = 0.2;
  const clipLead = () => (v => (v >= 0.05 && v <= 0.4 ? v : LEAD_DEFAULT))(Number(load('flow-lead')));
  const AUDIO = {
    ctx: null, src: null, done: null, own: null, token: 0, bufs: new Map(), idle: 0, off: false,
    AC: window.AudioContext || window.webkitAudioContext,
    // not while the page is hidden (the screen locked): the context is closed then (below), and an <audio> plays on there
    // (继续 on the lock screen for a whole text read sentence by sentence)
    usable() { return WORD_CLIPS && !!this.AC && !!navigator.audioSession && !this.off && this.mode() !== 'compat' && document.visibilityState !== 'hidden'; },
    // 我的 → 设置 → 单词读音方式 (iPhones and iPads), kept on this phone (the home-screen app has no address bar for
    // ?audio= and ?lead=, and keeps its own storage): 'auto' = 连续 (Web Audio where it works) or 'compat' = 标准 (the
    // <audio> clips), and the silence in front of a clip
    mode() { return load('flow-audio') === 'compat' ? 'compat' : 'auto'; },
    setMode(m) { save('flow-audio', m === 'compat' ? 'compat' : null); if (m === 'compat') this.drop(); this.off = false; },
    lead() { return clipLead(); },
    setLead(v) { save('flow-lead', LEADS.includes(v) && v !== LEAD_DEFAULT ? v : null); },
    LEADS, LEAD_DEFAULT,
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
        this.ctx.onstatechange = () => {  // a call or another app took the sound: what was playing is over (or, for a
          // whole text being read, paused: cut)
          const c = this.ctx; if (!c || !this.src || c.state === 'running') return;
          const end = this.done, cut = this.cut; this.stop(); if (cut) cut(); else if (end) end();
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
    play(url, from, to, rate, onend, onfail, title, own, cut) {
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
        if (own) { if (this.own) { this.own.onended = null; try { this.own.stop(); } catch (e) { /* ignore */ } } this.own = s; } else { this.src = s; this.done = onend; this.cut = cut || null; }
        s.start(c.currentTime + 0.03, start, Math.max(0.01, end - start));
        // a context that would not run (refused outside a tap, or broken): the old way, once
        setTimeout(() => { if ((own ? this.own : this.src) === s && c.state !== 'running') { if (own) this.own = null; else this.stop(); if (onfail) onfail(new Error('not running')); } }, 1500);
      }).catch(e => { if ((own || t === this.token) && onfail) onfail(e); });
      return true;
    },
    stop() { this.token++; const s = this.src; this.src = null; this.done = null; this.cut = null; if (s) { s.onended = null; try { s.stop(); } catch (e) { /* not started */ } } },
    halt() { this.stop(); if (this.own) { this.own.onended = null; try { this.own.stop(); } catch (e) { /* ignore */ } this.own = null; } this.rest(); },
    // 20 s after the last sound the context rests: WebKit takes 语流 out of Now Playing (and the Dynamic Island)
    rest() {
      clearTimeout(this.idle);
      this.idle = setTimeout(() => { if (this.src || this.own || !this.ctx) return; if (this.ctx.state === 'running') this.ctx.suspend().catch(() => {}); MS.release('short'); }, 20000);
    },
    drop() { const cut = this.src && this.cut; this.halt(); clearTimeout(this.idle); const c = this.ctx; this.ctx = null; if (c) c.close().catch(() => {}); MS.release('short'); if (cut) cut(); },
  };
  document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'hidden') AUDIO.drop(); });

  /* ---------- short clips: a word's pronunciation, one sentence of a narration, a sentence of the server voice ---------- */
  // On iPhones and iPads a word (and a sentence of a narration) is its own small file, cut by the server with clipLead()
  // seconds of silence in front (word_clip.py), played from its start on an <audio>: the waking of the sound happens in
  // the silence. Its source is let go when it ends, so WebKit no longer counts it for Now Playing (a page that once was
  // the Now Playing app shows even short sounds there until it has nothing left to show; a paused whole text may still
  // count, which only a phone can tell). Unless 标准 is chosen they play on AUDIO instead, where it works.
  // Elsewhere the sprite and the narration are played as before.
  const CLIP = {
    audio: new Audio(), raf: 0, metas: {}, want: null,
    accent() { return (S.voice || 'us-f').startsWith('uk') ? 'uk' : 'us'; },
    stop() { AUDIO.stop(); cancelAnimationFrame(this.raf); this.want = null; this.audio.dataset.want = ''; try { this.audio.pause(); } catch (e) { /* not playing */ } },
    // play() is called right away, inside the tap: in-app browsers (WeChat) and iPhones refuse a play() that starts
    // later, when the file has loaded. A new file plays muted until it has jumped to the clip.
    // text: said by the browser voice if neither line can play the clip.
    // to: Infinity plays a file to its end (a word clip). fallback: [src, from, to] played instead if src fails.
    // wa: {url, from, to, title}: what AUDIO plays instead, where it is used.
    // wa.cut: called instead of onend when a call (or the page hidden) cuts the sound off: a whole text pauses there
    play(src, from, to, text, onend, fallback, wa) {
      LONG.other();
      NAR.stop(); TTS.stop(); this.stop();
      const want = this.want = { from, to, text, onend, fallback, title: wa && wa.title, cut: wa && wa.cut };
      if (wa && AUDIO.play(wa.url, wa.from, wa.to, TTS.rate, () => { if (this.want === want) { this.want = null; if (onend) onend(); } },
        () => { if (this.want === want) this.element(src, from, to, text, onend, fallback, want); }, wa.title, false,
        wa.cut && (() => { if (this.want === want) { this.want = null; wa.cut(); } }))) { want.wa = true; return; }
      this.element(src, from, to, text, onend, fallback, want);
    },
    element(src, from, to, text, onend, fallback, want) {
      const a = this.audio; want.src = src;  // what was asked for: the error below says why a word was not heard
      const loop = () => {
        if (this.want !== want) return;
        if (a.currentTime >= to || a.ended) { a.pause(); this.want = null; if (to === Infinity && WORD_CLIPS) { this.letGo(); MS.release('short'); } if (onend) onend(); return; }
        this.raf = requestAnimationFrame(loop);
      };
      const refused = e => { if (this.want === want && e && e.name === 'NotAllowedError') noSound('没有放出声音'); };
      claim(a); a.playbackRate = TTS.rate; a.dataset.want = '1'; a._from = from;
      // a word longer than 0.95 s still shows in the Dynamic Island: named, not an address (metadata changes nothing else)
      if (WORD_CLIPS && want.title) MS.claim('short', want.title, { pause: () => this.stop(), stop: () => this.stop() });
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
    letGo() { const a = this.audio; a.dataset.src = ''; a.removeAttribute('src'); try { a.load(); } catch (e) { /* ignore */ } },
    // c: {text, audio: {us: [sprite, start, end], uk: [...]}}; falls back to the browser voice
    word(c) {
      const au = c.audio || {}, ac = au[this.accent()] ? this.accent() : au.us ? 'us' : au.uk ? 'uk' : null;
      if (!ac) { TTS.say(c.text); return; }
      const w = au[ac], sprite = `/audio/words/${ac}/${w[0]}.mp4`, clip = this.wordSrc(c);
      if (WORD_CLIPS) this.play(clip, 0, Infinity, c.text, null, [sprite, w[1], w[2]], { url: clip, from: clipLead() - 0.02, to: clipLead() + w[2] - w[1] + 0.04, title: '语流 · 单词' });
      else this.play(sprite, w[1], w[2], c.text);
    },
    // the file word(c) plays: the word's own clip on an iPhone or iPad, its sprite elsewhere (prefetched by the review)
    wordSrc(c) {
      const au = (c && c.audio) || {}, ac = au[this.accent()] ? this.accent() : au.us ? 'us' : au.uk ? 'uk' : null;
      if (!ac) return null;
      const w = au[ac];
      return WORD_CLIPS ? `/audio/words/${ac}/${w[0]}.aac?s=${w[1]}&e=${w[2]}&l=${clipLead()}` : `/audio/words/${ac}/${w[0]}.mp4`;
    },
    // ex: {pack, i, text, audio: narration version or 0}; onend when it has been said (对比回放 plays the recording then)
    async sentence(ex, onend) {
      if (!ex.audio) { TTS.say(ex.text, onend); return; }
      const key = S.voice + '/' + ex.pack;
      try {
        if (!this.metas[key]) this.metas[key] = await mediaJSON(`/audio/${S.voice}/${encodeURIComponent(ex.pack)}.json?v=${ex.audio}`);
        const s = this.metas[key].sentences[ex.i]; if (!s) throw new Error('no sentence');
        const base = `/audio/${S.voice}/${encodeURIComponent(ex.pack)}`, e = s.e + 0.05, cut = `${base}.aac?v=${ex.audio}&s=${s.s}&e=${e}&l=${clipLead()}`;
        const wa = { url: cut, from: clipLead() - 0.02, to: clipLead() + e - s.s + 0.02, title: '语流 · 例句' };
        if (WORD_CLIPS) this.play(cut, 0, Infinity, ex.text, onend, [`${base}.mp4?v=${ex.audio}`, s.s, e], wa);
        else this.play(`${base}.mp4?v=${ex.audio}`, s.s, e, ex.text, onend);
      } catch (e) { TTS.say(ex.text, onend); }
    },
    // the learner's own recording (a blob: URL), after or beside the original: it does not stop what plays
    mine(url, onend) {
      if (AUDIO.play(url, 0, Infinity, 1, onend, () => this.mineElement(url, onend), '语流 · 我的录音', true)) return;
      this.mineElement(url, onend);
    },
    mineElement(url, onend) { const a = new Audio(url); if (onend) a.onended = () => onend(); a.play().catch(() => { if (onend) onend(); }); },
  };
  // paused by something other than the page (a call) while a whole text's sentence plays: it waits there (LONG)
  CLIP.audio.addEventListener('pause', () => {
    const w = CLIP.want, a = CLIP.audio; if (!w || !w.cut || w.wa || a.dataset.want !== '1' || a.ended || a.currentTime >= w.to) return;
    CLIP.want = null; cancelAnimationFrame(CLIP.raf); a.dataset.want = ''; w.cut();
  });
  CLIP.audio.addEventListener('error', () => {
    const w = CLIP.want; if (!w || !mediaGaveUp(CLIP.audio)) return;
    if (w.fallback) { const n = CLIP.want = { ...w, fallback: null }; CLIP.element(w.fallback[0], w.fallback[1], w.fallback[2], w.text, w.onend, null, n); return; }  // no clip from the server: the sprite, as before (once)
    CLIP.stop();
    if (!w.text) return;
    // the clip and the sprite both failed: say why before the browser's voice (audio-inventory.md, 语流 9: never a
    // silent switch to a machine voice); a word has its own two lines, apart from a sentence's (SV.why: once per reason).
    // No browser voice either (WeChat): TTS.browser says how to hear it instead, and nothing is said about a voice.
    const off = navigator.onLine === false;
    if (TTS.ok) SV.why(/\/audio\/words\//.test(w.src || '')
      ? { code: off ? 'word_offline' : 'word_net', server: off ? `离线中，这个词的读音还没存到本机，先用${SYS_VOICE()}` : `网络不好，这个词的读音没加载出来，先用${SYS_VOICE()}` }
      : { code: off ? 'offline' : 'net' });
    TTS.browser(w.text, w.onend);  // not TTS.say: that may be this player again (the server voice); onend still runs (对比回放 plays the recording then)
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

  /* ---------- mini player: while a whole text plays, its control stays on screen however far the text scrolls ---------- */
  // A whole text (LONG): 暂停 / 继续, and ✕ to close it (where it was is kept). A sentence repeating: 停止. Paused from
  // outside the page (a call, the lock screen): 已暂停, and the button says 继续.
  const pauseIcon = size => `<svg width="${size || 18}" height="${size || 18}" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="5" width="4.5" height="14" rx="1.2"/><rect x="13.5" y="5" width="4.5" height="14" rx="1.2"/></svg>`;
  const MINI = {
    el: null, h: null, label: '', resumeFn: null, dk: null,
    box() {
      if (!this.el) { this.el = document.createElement('div'); this.el.className = 'mini-player'; this.el.setAttribute('role', 'region'); this.el.setAttribute('aria-label', '播放控制'); document.body.appendChild(this.el); }
      this.el.classList.toggle('docked', !!this.dk); document.body.classList.toggle('docked', !!this.dk);
      return this.el;
    },
    // 精听 (the user's pick of 语流 B9's design, 2026-11-25): with nothing playing the bar stays above the tabs with the
    // page's start button (#playAll, 「播放全文」 or 「从第 N 句继续」), 「AI 合成」 and the speed; playing, it is the usual
    // player, its 暂停 / 继续 still #playAll for that text. dk: {key, ai, paint(), play(), rate()}. Other pages: only while playing.
    dock(dk) { this.dk = dk; if (!this.h) this.idle(); else this.box(); NATIVE.adopt(); },  // the app playing this text: taken back
    undock() { this.dk = null; document.body.classList.remove('docked'); if (this.el) this.el.classList.remove('docked'); if (!this.h) this.hide(); },
    idle() {
      const dk = this.dk, el = this.box();
      el.innerHTML = `<button type="button" class="toggle" id="playAll"></button>${dk.ai ? aiVoiceNote('AI 合成', 'span') : ''}<span class="sp"></span>`
        + '<button type="button" class="speed-set" aria-label="播放设置：语速、每句几遍、句后停顿"></button>';
      el.querySelector('#playAll').onclick = () => dk.play();
      el.querySelector('.speed-set').onclick = () => dk.rate();
      el.classList.remove('paused'); el.classList.add('idle'); el.hidden = false; document.body.classList.add('playing');
      dk.paint();
    },
    show(label, h) {
      if (typeof h === 'function') h = { stop: h };
      this.h = h; this.label = label; this.resumeFn = null;
      const el = this.box(), mine = !!(this.dk && h.key && h.key === this.dk.key);
      el.innerHTML = `<span class="eq" aria-hidden="true"><i></i><i></i><i></i></span><span class="lbl"></span>${h.ai === false ? '' : aiVoiceNote('AI 合成', 'span')}`
        + (h.toggle ? `<button type="button" class="toggle"${mine ? ' id="playAll"' : ''}></button>${mine ? '<button type="button" class="speed-set" aria-label="播放设置：语速、每句几遍、句后停顿"></button>' : ''}<button type="button" class="stop close" aria-label="关闭播放（记住读到哪里）">✕</button>`
          : `<button type="button" class="stop">${playIcon(true, 15)}<span>停止</span></button>`);
      el.querySelector('.lbl').textContent = label;
      el.querySelector('.stop').onclick = () => { const st = this.h && this.h.stop; this.hide(); if (st) st(); };
      if (h.toggle) el.querySelector('.toggle').onclick = () => this.h.toggle();
      if (mine) { const dk = this.dk; el.querySelector('.speed-set').onclick = () => dk.rate(); }
      el.classList.remove('paused', 'idle'); el.hidden = false; document.body.classList.add('playing');
      this.paint();
      if (mine) this.dk.paint();
    },
    paint() {
      if (!this.el || this.el.hidden || !this.h) return;
      const on = this.el.classList.contains('paused'), t = this.el.querySelector('.toggle');
      this.el.querySelector('.lbl').textContent = on ? '已暂停' : this.label;
      if (t) { t.innerHTML = on ? `${playIcon(false, 15)}<span>继续</span>` : `${pauseIcon(15)}<span>暂停</span>`; t.classList.toggle('resume', on); t.setAttribute('aria-label', on ? '继续' : '暂停'); }
      let b = this.el.querySelector('.resume:not(.toggle)');
      if (!t && on && !b) { b = document.createElement('button'); b.type = 'button'; b.className = 'resume'; b.innerHTML = `${playIcon(false, 15)}<span>继续</span>`; this.el.insertBefore(b, this.el.querySelector('.stop')); }
      if (b) { if (!t && on) b.onclick = () => { if (this.resumeFn) this.resumeFn(); }; else b.remove(); }
    },
    update(label) { this.label = label; this.paint(); },
    paused(on) { if (this.el && !this.el.hidden && this.h) { this.el.classList.toggle('paused', !!on); this.paint(); } },
    // a recording paused from outside, with no whole text around it: 已暂停, and 继续 calls resume
    pause(on, resume) { if (!this.el || this.el.hidden || !this.h) return; this.resumeFn = resume || null; this.paused(on); },
    // stopped: 精听's bar goes back to its start button; anywhere else the bar goes
    hide() {
      this.h = null;
      if (this.dk) { this.idle(); return; }
      if (this.el) { this.el.hidden = true; this.el.classList.remove('paused', 'idle'); } document.body.classList.remove('playing');
    },
    end() { const b = this.el && !this.el.hidden && this.el.querySelector('.stop'); if (b) b.click(); },
  };

  /* ---------- where a whole text was left: per text and per page (听 / 读), on this phone for 30 days ---------- */
  const PROG = {
    KEY: 'flow-progress', DAYS: 30, MAX: 100,
    all() { const o = load(this.KEY) || {}, cut = Date.now() - this.DAYS * 864e5; for (const k of Object.keys(o)) if (!o[k] || !(o[k].at > cut)) delete o[k]; return o; },
    get(k) { return (k && this.all()[k]) || null; },
    // the sentence to go on from, when it is not the first and the text still has it
    at(k, n) { const p = this.get(k); return p && p.i > 0 && p.i < n ? p.i : 0; },
    set(k, i) {
      if (!k) return; const o = this.all(); if (i > 0) o[k] = { i, at: Date.now() }; else delete o[k];
      const ks = Object.keys(o); if (ks.length > this.MAX) ks.sort((x, y) => o[x].at - o[y].at).slice(0, ks.length - this.MAX).forEach(x => delete o[x]);
      save(this.KEY, o);
    },
    clear(k) { if (k) { const o = this.all(); delete o[k]; save(this.KEY, o); } },
  };

  /* ---------- in 语流's iOS app the app plays a whole text (ios/README.md, 「网页和 App 之间的桥」) ---------- */
  // window.FlowApp is there only inside the app (Safari, the home-screen app and WeChat do as before). LONG keeps its own
  // state (where it is, MINI, PROG, onState / onWord) and the app plays: on with the screen locked and while this page
  // sleeps, the lock screen's buttons, on again after a call. Its news ('audio') moves LONG along; 'audio-tick' (four a
  // second, the page in front) lights the word of a recording, smoothed between ticks.
  const NATIVE = {
    tick: null, raf: 0, sent: '', lone: null, last: null, watcher: null,
    on() { return !!(window.FlowApp && FlowApp.has && FlowApp.has('audio')); },
    // 复读 (times, the pause after each sentence) and 语速, as the page has them now (docs/native-bridge.md §3 set)
    knobs(r) { return { rep: r.rep ? r.rep() : 1, gap: r.texts.map((_, k) => (r.gap ? r.gap(k) : 0)), rate: TTS.rate || 1 }; },
    // changed while the app plays (a 复读 or 语速 chip, or meanwhile): the app gets them at once
    retune(force) {
      const r = LONG.r; if (!r || !r.native) return;
      const k = JSON.stringify(this.knobs(r));
      if (force || k !== this.sent) { this.sent = k; FlowApp.audio.set(this.knobs(r)).catch(() => {}); }
    },
    start(r) {
      const d = this.last;
      if (this.lone === r.key && d && d.key === r.key && d.state !== 'idle') {
        // this page loaded again while the app went on with this very text: take it back where the app is, no new start
        // (r.auto: 精听 took it back by itself, MINI.dock / adopt: a paused text stays paused; a tap on 继续 resumes it)
        const keep = !!r.auto && d.state === 'paused';
        this.lone = null; if (typeof d.i === 'number') r.i = d.i; r.state = d.state === 'paused' && !keep ? 'playing' : d.state; r.note = '';
        if (d.state === 'paused' && !keep) FlowApp.audio.resume().catch(() => {});
        MINI.paused(keep); this.retune(true); LONG.save(); LONG.emit(); this.loop(); return;
      }
      const o = { key: r.key, title: r.title || '', from: r.i, ...this.knobs(r) };
      if (S.csrf) o.csrf = S.csrf;
      if (r.nm) { o.src = NAR.net; o.sentences = r.nm.sentences.map(x => [x.s, x.e]); o.loop = !!r.loop; const alt = mediaAlt(NAR.net); if (alt) o.alt = alt; }
      else {  // no recording: each sentence with the address this phone already has for it (SV address book), else null (§3 items)
        const voice = r.voice || S.voice, pack = r.pack;
        o.items = r.texts.map(text => ({ text, url: (SV.kept()[SV.hash(SV.key(text, { voice, pack }))] || [])[0] || null }));
        o.voice = voice; if (pack) o.pack = pack;
      }
      this.sent = JSON.stringify(this.knobs(r));
      FlowApp.audio.play(o).then(x => { if (!(x && x.ok) && LONG.r === r) this.fail(r, x && x.message); }, () => { if (LONG.r === r) this.fail(r); });
    },
    // the app could not (a call going on): this page reads it, as in Safari
    fail(r, why) { r.native = false; if (why) toast(why); LONG.go(); },
    news(d) {
      const r = LONG.r;
      if (!r || !r.native || d.key !== r.key) { this.orphan(d); return; }
      if (d.state === 'idle') { if (d.why === 'ended') LONG.finish(); else if (d.why !== 'user') LONG.stop(); return; }
      if (typeof d.i === 'number' && d.i !== r.i) { r.i = d.i; r.n = 0; LONG.save(); }
      // the app fell back to the phone's own voice: why, said by the page as everywhere on the site (SV.why: once a reason)
      r.state = d.state; r.note = d.fail ? SV.why(d.fail) : (d.note || '');
      MINI.paused(d.state === 'paused');
      this.retune();  // 复读 or 语速 changed meanwhile
      LONG.emit(); this.loop();
    },
    // the app made a sentence this phone had no address for: kept in the SV address book (§3 audio-made), so it is
    // not made twice and the page finds it too (offline, in Safari)
    made(d) {
      const r = LONG.r;
      if (!d || !d.url || !r || !r.native || d.key !== r.key || !(d.i >= 0) || d.i >= r.texts.length) return;
      SV.keep(SV.key(r.texts[d.i], { voice: r.voice || S.voice, pack: r.pack }), d.url);
    },
    // the sentence moved on between two 'audio' news (they come with each new sentence, §3; a tick says it as well)
    ticked(d) {
      this.tick = d;
      const r = LONG.r;
      if (r && r.native && d && d.key === r.key && typeof d.i === 'number' && d.i !== r.i) { r.i = d.i; r.n = 0; LONG.save(); LONG.emit(); }
    },
    // the app's news kept on this phone too (PROG), so 「从第 N 句继续」 is where the app got to, also after this page
    // loaded again; read to the end clears it, any other stop keeps it (§3 进度)
    keep(d) {
      if (!d || !d.key) return;
      this.last = d;
      if (d.state === 'idle' && d.why === 'ended') PROG.clear(d.key); else if (typeof d.i === 'number') PROG.set(d.key, d.i);
      const w = this.watcher; if (w && w.key === d.key && !LONG.of(d.key)) w.paint();
    },
    // the page with this text's 播放全文 / 伴读 button: in the app the button says where the app got to, its stored place
    // when the page opens and its news while it plays this text without this page (loaded again meanwhile)
    follow(key, paint) {
      this.watcher = { key, paint };
      this.reconcile(key).then(() => { if (!LONG.of(key)) paint(); });
    },
    // where the app got to in a text against this phone's PROG, the newer one counts (§3: the app played on while this
    // page slept, or read it to the end): true when PROG changed, so the page can say 「从第 N 句继续」 again
    reconcile(key) {
      if (!this.on() || !key) return Promise.resolve(false);
      return Promise.resolve(FlowApp.audio.progress(key)).then(p => {
        if (!p || !(p.at > 0)) return false;
        const mine = PROG.get(key);
        if (mine && mine.at >= p.at) return false;
        if (p.ended || !(p.i > 0)) { if (!mine) return false; PROG.clear(key); return true; }
        if (mine && mine.i === p.i) return false;
        PROG.set(key, p.i); return true;
      }, () => false);
    },
    loop() {
      cancelAnimationFrame(this.raf);
      const r = LONG.r; if (!r || !r.native || !r.nm || r.state !== 'playing' || !r.onWord) return;
      const f = () => {
        const k = this.tick; if (LONG.r !== r || r.state !== 'playing') return;
        if (k && k.key === r.key && NAR.meta === r.nm) { const [si, wc] = NAR.locate(k.t + Math.max(0, Date.now() - k.at) / 1000 * (k.rate || 1)); if (si >= 0 && si === r.i) r.onWord(si, wc); }  // only the app's sentence: an older tick never lights the one before
        this.raf = requestAnimationFrame(f);
      };
      this.raf = requestAnimationFrame(f);
    },
    // the app's text, which this page did not start, after the router hid MINI for a new page: on screen again
    reshow() { const d = this.last; if (!LONG.r && this.lone && d && d.key === this.lone && d.state !== 'idle') this.orphan(d); },
    // the app plays the very text whose 精听 page is open (loaded again, or come back to): the page takes it back by
    // itself, so its one bar is that text's player, the sentence lit; true when it did
    adopt() {
      const d = this.last, dk = MINI.dk;
      if (!dk || !dk.attach || LONG.r || !d || this.lone !== d.key || d.key !== dk.key || d.state === 'idle') return false;
      dk.attach(); return true;
    },
    // this page loaded again (a new version, iOS ended it in the background) while the app goes on: its control is back
    orphan(d) {
      this.keep(d);
      if (LONG.r) return;
      if (d.state === 'idle') { if (this.lone) { this.lone = null; MINI.hide(); } return; }
      if (MINI.dk && MINI.dk.key === d.key) { this.lone = d.key; if (this.adopt()) return; }
      const label = (d.title || '朗读') + (d.n ? ` · 第 ${d.i + 1} / ${d.n} 句` : '');
      if (this.lone !== d.key || !MINI.el || MINI.el.hidden || !MINI.h) {  // !MINI.h: 精听's idle bar is there, not the app's player
        this.lone = d.key;
        MINI.show(label, { toggle: () => (MINI.el.classList.contains('paused') ? FlowApp.audio.resume() : FlowApp.audio.pause()), stop: () => { this.lone = null; FlowApp.audio.stop(); } });
      } else MINI.update(label);
      MINI.paused(d.state === 'paused');
    },
  };
  if (NATIVE.on()) {
    FlowApp.on('audio', d => NATIVE.news(d));
    FlowApp.on('audio-tick', d => NATIVE.ticked(d));
    FlowApp.on('audio-made', d => NATIVE.made(d));
    FlowApp.audio.state().then(d => { if (d && d.state !== 'idle') NATIVE.news(d); }, () => {});
  }

  /* ---------- a whole text read aloud: 听's 播放全文 and 读's 伴读 (owner, 2026-11-25) ---------- */
  // The recording (Kokoro) when there is one, straight through (or sentence by sentence when 复读 is set); otherwise the
  // server voice sentence by sentence, the next two asked for while one plays, a line while one is being made (never the
  // browser voice for being slow), and the browser voice only for a sentence the server could not give, with the reason.
  // 暂停 / 继续: a recording goes on from the second it stopped, a sentence-by-sentence reading from the start of the
  // sentence it stopped in. The same from the mini player, the lock screen and the Dynamic Island, after a call, the page
  // hidden, or another sound (a word, a recording) started meanwhile. Where it was left is kept per text and page (PROG)
  // until its end is reached: 「从第 N 句继续」. One text at a time.
  // o: {key, texts, nm (Kokoro timings, or null), pack, title, loop (sentence by sentence even with a recording),
  //     rep() (times each sentence, 0 = until stopped), gap(i) (ms after sentence i), label(i),
  //     onState(state, i, note) ('waiting' | 'playing' | 'paused' | 'idle'), onWord(i, charOffset | null), onDone()}
  const LONG = {
    r: null, self: false,
    of(key) { return this.r && this.r.key === key ? this.r : null; },
    nar() { return !!(this.r && this.r.nm && NAR.audio.dataset.want === '1'); },
    start(o, from) {
      this.stop();
      const n = o.texts.length, r = this.r = { ...o, i: Math.max(0, Math.min(from || 0, n - 1)), n: 0, tok: 0, state: o.nm ? 'playing' : 'waiting', note: '', at: null };
      r.cont = !!o.nm && !o.loop;
      r.native = NATIVE.on();
      MINI.show(this.label(), { key: r.key, ai: !!(o.nm || SV.on()), toggle: () => this.toggle(), stop: () => this.stop() });  // ai: 语流's own voices, not the browser's
      if (r.native) { this.emit(); NATIVE.start(r); return; }  // 语流's iOS app plays it (NATIVE)
      if (o.nm) { this.emit(); this.go(); return; }  // inside the tap: WeChat plays a recording only when it starts there
      this.emit();
      const tok = r.tok;
      SV.have(o.texts, o).then(() => { if (this.r === r && r.tok === tok && r.state !== 'paused') this.go(); });
    },
    label() { const r = this.r; return r.state === 'waiting' ? `准备第 ${r.i + 1} 句…` : (r.label ? r.label(r.i) : `第 ${r.i + 1} / ${r.texts.length} 句`); },
    emit() { const r = this.r; if (!r) return; MINI.update(this.label()); if (r.onState) r.onState(r.state, r.i, r.note); },
    claim() {  // the lock screen for a sentence-by-sentence reading (a recording names itself: NAR.name)
      const r = this.r; if (!r || r.nm || r.native) return;
      MS.claim('long', '语流 · ' + (r.title || '朗读'), { play: () => this.resume(), pause: () => this.pause(), stop: () => { this.stop(); MINI.hide(); },
        previoustrack: () => this.step(-1), nexttrack: () => this.step(1) });
      if (r.state === 'paused') MS.state('paused');
    },
    // inside LONG: what it plays is not "another sound"
    own(f) { this.self = true; try { f(); } finally { this.self = false; } },
    go() {
      const r = this.r; if (!r) return;
      const tok = ++r.tok, s = r.nm && r.nm.sentences[r.i];
      if (r.cont) {
        const from = r.at != null ? r.at : s.s; r.at = null; r.state = 'playing'; this.emit();
        this.own(() => NAR.play(from, null, t => this.tick(t), () => { if (this.r === r && r.tok === tok) this.ended(); }));
        return;
      }
      if (r.nm) {
        r.state = 'playing'; this.emit();
        this.own(() => NAR.play(s.s, s.e, t => { const [si, wc] = NAR.locate(t); if (si === r.i && r.onWord) r.onWord(si, wc); }, () => { if (this.r === r && r.tok === tok) this.after(); }));
        return;
      }
      this.sentence(tok);
    },
    tick(t) {  // a recording straight through: which sentence, which word
      const r = this.r; if (!r) return;
      const [si, wc] = NAR.locate(t);
      if (si >= 0 && si !== r.i) { r.i = si; this.emit(); this.save(); }
      if (si >= 0 && r.onWord) r.onWord(si, wc);
    },
    ended() {  // the recording stopped by itself: the end, or a file that would not load (then where it was is kept)
      const r = this.r, a = NAR.audio, last = r.nm.sentences[r.nm.sentences.length - 1];
      if (a.ended || a.currentTime >= last.s) this.finish(); else this.stop();
    },
    async sentence(tok) {
      const r = this.r, i = r.i, text = r.texts[i];
      for (const k of [i + 1, i + 2]) if (k < r.texts.length && SV.on()) SV.url(r.texts[k], r).then(u => PRELOAD.warm(u), () => {});
      let u = null, err = null;
      if (SV.on()) {
        const ready = SV.urls.has(SV.key(text, r));
        const late = ready ? 0 : setTimeout(() => { if (this.r === r && r.tok === tok) { r.state = 'waiting'; r.note = `正在准备朗读第 ${i + 1} 句…`; this.emit(); } }, 400);
        try { u = await SV.slow(SV.url(text, r)); } catch (e) { err = e; }
        clearTimeout(late);
        if (this.r !== r || r.tok !== tok) return;  // paused, stopped or moved on while it was being made
      }
      r.state = 'playing'; r.note = u ? '' : err ? SV.why(err) : SV.off ? SV.why({ code: SV.off }) : ''; this.emit();
      const next = () => { if (this.r === r && r.tok === tok) this.after(); };
      if (u) {
        this.own(() => CLIP.play(u, 0, 1e6, text, next, null, { url: u, from: 0, to: Infinity, title: '语流 · ' + (r.title || '朗读'), cut: () => { if (this.r === r && r.tok === tok) this.held(); } }));
        this.claim();
      } else {
        // the browser voice could not say it (none here, or iOS dropped it twice): the text waits there, paused, with why
        const failed = () => { clearTimeout(stall); if (this.r !== r || r.tok !== tok) return; this.held(); r.note = `${SYS_VOICE()}没有读出这一句，点「继续」再试一次`; this.emit(); };
        // and if nothing at all comes back from it (never asked: something else spoke or stopped it in between; or no
        // event of any kind, which an iPad did once offline: 语流 07, 2026-11-25), it is not left "playing" there either
        const stall = setTimeout(failed, 4000);
        this.own(() => TTS.browser(text, () => { clearTimeout(stall); next(); }, c => { if (this.r === r && r.onWord) r.onWord(i, c); }, failed, () => clearTimeout(stall)));
      }
    },
    // one sentence said: again (复读), or the next, after its pause. The pause is the one after the sentence just said
    // (「留时间跟说」 is as long as that sentence), so it is taken before moving on
    after() {
      const r = this.r, rep = r.rep ? r.rep() : 1, g = r.gap ? r.gap(r.i) : 0;
      r.n += 1;
      if (!(rep === 0 || r.n < rep)) {
        r.n = 0; r.i += 1;
        if (r.i >= r.texts.length) { this.finish(); return; }
        this.save();
      }
      const tok = r.tok;
      if (g) r.timer = setTimeout(() => { if (this.r === r && r.tok === tok && r.state !== 'paused') this.go(); }, g); else this.go();
    },
    toggle() { if (!this.r) return; if (this.r.state === 'paused') this.resume(); else this.pause(); },
    pause() {
      const r = this.r; if (!r || r.state === 'paused') return;
      if (r.native) { FlowApp.audio.pause().catch(() => {}); r.state = 'paused'; r.note = ''; MINI.paused(true); this.save(); this.emit(); return; }
      if (r.cont && NAR.audio.dataset.want === '1') { r.at = NAR.audio.currentTime; NAR.audio.pause(); this.held(); return; }  // the listener calls held() too
      if (r.nm && NAR.audio.dataset.want === '1') { NAR.audio.pause(); this.held(); return; }  // 复读 on a recording: that sentence waits at its second
      r.tok++; clearTimeout(r.timer); this.own(() => { TTS.stop(); CLIP.stop(); });
      this.held();
    },
    held() {  // paused (by the learner, a call, the lock screen, the page hidden, another sound): where it was is kept
      const r = this.r; if (!r || r.state === 'paused') return;
      if (r.cont && r.at == null && NAR.audio.dataset.want === '1') r.at = NAR.audio.currentTime;
      if (!r.nm) { r.tok++; clearTimeout(r.timer); }
      r.state = 'paused'; r.note = ''; MINI.paused(true); MS.state('paused'); this.save(); this.emit();
    },
    going() { const r = this.r; if (!r || r.state !== 'paused') return; r.state = 'playing'; r.at = null; MINI.paused(false); MS.state('playing'); this.emit(); },
    resume() {
      const r = this.r; if (!r || r.state !== 'paused') return;
      if (r.native) {  // the app may have let it go meanwhile (closed by iOS): then it starts again where it was
        r.state = 'playing'; MINI.paused(false); this.emit();
        FlowApp.audio.resume().then(x => { if (this.r === r && (!x || x.key !== r.key || x.state === 'idle')) NATIVE.start(r); }, () => {});
        return;
      }
      if (r.nm && NAR.audio.dataset.want === '1') { this.going(); NAR.resume(); return; }  // still there, paused: on from that second
      r.state = 'playing'; MINI.paused(false); this.go();
    },
    // another sound is about to start (a word looked up, a sentence tapped, the microphone): the text waits, paused
    other() {
      const r = this.r; if (!r || this.self || r.state === 'paused') return;
      if (r.native) { this.pause(); return; }
      if (r.cont && NAR.audio.dataset.want === '1') r.at = NAR.audio.currentTime;
      if (r.nm) r.tok++;  // the recording is taken over: 继续 plays it again from r.at
      this.held();
    },
    step(d) {  // previous / next sentence (the lock screen)
      const r = this.r; if (!r) return;
      if (r.native) { FlowApp.audio.step(d).catch(() => {}); return; }
      if (r.cont) { NAR.step(d); return; }
      r.tok++; clearTimeout(r.timer); this.own(() => { TTS.stop(); CLIP.stop(); NAR.stop(); });
      r.i = Math.max(0, Math.min(r.texts.length - 1, r.i + d)); r.n = 0; r.at = null; r.state = 'playing'; MINI.paused(false); this.go();
    },
    save() { const r = this.r; if (r && r.key) PROG.set(r.key, r.i); },
    finish() {
      const r = this.r; if (!r) return;
      this.r = null; r.tok++; PROG.clear(r.key); MINI.hide(); MS.release('long'); cancelAnimationFrame(NATIVE.raf);
      if (r.onState) r.onState('idle', -1, '');
      if (r.onDone) r.onDone();
    },
    // stop reading (✕, leaving the page, another text): where it was is kept
    stop() {
      const r = this.r;
      if (!r) { if (NATIVE.lone) setTimeout(() => NATIVE.reshow(), 0); return; }  // a new page (the router hides MINI): the app's text keeps its control
      if (r.cont && NAR.audio.dataset.want === '1') { const [si] = NAR.locate(NAR.audio.currentTime); if (si >= 0) r.i = si; }
      this.save(); this.r = null; r.tok++; clearTimeout(r.timer);
      if (r.native) { cancelAnimationFrame(NATIVE.raf); FlowApp.audio.stop().catch(() => {}); }
      this.own(() => { TTS.stop(); CLIP.stop(); NAR.stop(); });
      MINI.hide(); MS.release('long');
      if (r.onState) r.onState('idle', -1, '');
    },
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


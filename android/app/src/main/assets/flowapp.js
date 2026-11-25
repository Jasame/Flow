/* window.FlowApp: 语流's Android app, for the page (docs/native-bridge.md, FlowApp v1). Put in place by the app at
   document start, on the site's own origin, before the page's own scripts. The page checks
   `window.FlowApp && FlowApp.has('audio' | 'rec' | 'notify' | 'speech')` and otherwise does what it does in a browser.
   The same shape as the iOS app's FlowBridge.js; only the transport differs: the app's WebMessageListener `flowNative`
   ({id, cmd, args} in; {id, ok, result | error} back; {ev, detail} for events). */
(() => {
  'use strict';
  const port = window.flowNative;
  if (!port || window.FlowApp) return;
  const cfg = __FLOW_CONFIG__;

  let seq = 0;
  const pending = new Map(), subs = {};
  const call = (cmd, args) => new Promise((ok, no) => {
    const id = ++seq;
    pending.set(id, [ok, no]);
    port.postMessage(JSON.stringify({ id, cmd, args: args === undefined ? {} : args }));
  });
  const FlowApp = {
    v: cfg.v || 1, app: cfg.app || '', build: cfg.build || '', beta: !!cfg.beta,
    platform: 'android',
    features: Object.freeze((cfg.features || []).slice()),
    has(f) { return this.features.includes(f); },
    call,
    on(type, fn) { (subs[type] = subs[type] || []).push(fn); return () => this.off(type, fn); },
    off(type, fn) { subs[type] = (subs[type] || []).filter(x => x !== fn); },
    _emit(type, detail) {
      (subs[type] || []).slice().forEach(fn => { try { fn(detail); } catch (e) { console.error('FlowApp', type, e); } });
      try { window.dispatchEvent(new CustomEvent('flowapp:' + type, { detail })); } catch (e) { /* ignore */ }
    },
    // a whole text, played by the app (lock screen, calls, the screen off): play(o) → {ok, state}
    audio: Object.freeze({
      play: o => call('audio.play', o), pause: () => call('audio.pause'), resume: () => call('audio.resume'),
      stop: () => call('audio.stop'), step: d => call('audio.step', { d }), seek: i => call('audio.seek', { i }),
      set: o => call('audio.set', o), state: () => call('audio.state'), progress: key => call('audio.progress', { key }),
    }),
    // the microphone: ask() → true/false; start({max, format}) → {ok, format, max}; stop() → {ok, mime_type, data (base64), ms, bytes, cut}
    rec: Object.freeze({
      permission: () => call('rec.permission'), ask: () => call('rec.ask'), start: o => call('rec.start', o), stop: () => call('rec.stop'),
      cancel: () => call('rec.cancel'),
    }),
    // review reminders as local notifications: sync(reminder) after the page changed one; sync(null) / off() turns them off
    notify: Object.freeze({
      permission: () => call('notify.permission'), ask: () => call('notify.ask'), sync: r => call('notify.sync', r === null ? { app: false } : r),
      pending: () => call('notify.pending'), off: () => call('notify.off'), settings: () => call('notify.settings'),
    }),
    // the system back button (Android only): a listener may take it (preventDefault); an open sheet is closed; else the page before
    _back() {
      const ev = new CustomEvent('flowapp:back', { cancelable: true });
      window.dispatchEvent(ev);
      if (ev.defaultPrevented) return true;
      const sheet = document.getElementById('sheet');
      if (sheet && !sheet.hidden) { const x = sheet.querySelector('[data-close]'); if (x) { x.click(); return true; } }
      return false;
    },
  };
  port.onmessage = e => {
    let m; try { m = JSON.parse(e.data); } catch (x) { return; }
    if (m.ev) {
      if (m.ev === 'speech') speechEvent(m.detail); else if (m.ev === 'speech-voices') setVoices(m.detail); else FlowApp._emit(m.ev, m.detail);
      return;
    }
    const p = pending.get(m.id); if (!p) return;
    pending.delete(m.id);
    if (m.ok) p[0](m.result); else { const err = new Error(m.error || 'error'); err.code = m.code; p[1](err); }
  };
  Object.defineProperty(window, 'FlowApp', { value: Object.freeze(FlowApp), enumerable: false, configurable: false, writable: false });
  if (document.documentElement) document.documentElement.classList.add('flow-android');
  // back on screen: the app sends what is playing now (it went on while the page slept)
  document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'visible') call('app.visible').catch(() => {}); });

  /* ---- speechSynthesis on the phone's own voice (§7). Android's WebView has the object but no voice behind it, so the
     page's 「浏览器的声音」 never spoke here (as in WeChat on Android). The same API and events: start before end, boundary with
     charIndex, error 'interrupted' / 'canceled' for what cancel() cuts (never end), speaking and pending as they are. */
  let voices = [], queue = [], cur = null, uid = 0;
  function Utter(text) {
    this.text = text == null ? '' : String(text); this.lang = ''; this.voice = null; this.rate = 1; this.pitch = 1; this.volume = 1;
    this.onstart = this.onend = this.onerror = this.onboundary = this.onpause = this.onresume = this.onmark = null; this._l = {};
  }
  Utter.prototype.addEventListener = function (t, f) { (this._l[t] = this._l[t] || []).push(f); };
  Utter.prototype.removeEventListener = function (t, f) { this._l[t] = (this._l[t] || []).filter(g => g !== f); };
  const later = e => setTimeout(() => { throw e; });
  function fire(u, type, extra) {
    const ev = Object.assign({ type, utterance: u, target: u, charIndex: 0, charLength: 0, elapsedTime: 0, name: '' }, extra || {});
    const h = u['on' + type]; if (h) try { h.call(u, ev); } catch (e) { later(e); }
    (u._l[type] || []).slice().forEach(f => { try { f.call(u, ev); } catch (e) { later(e); } });
  }
  const synth = {
    speaking: false, pending: false, paused: false, onvoiceschanged: null, _l: {},
    getVoices() { return voices.slice(); },
    speak(u) { if (!(u instanceof Utter)) return; queue.push(u); synth.pending = !!cur || queue.length > 1; if (!cur) next(); },
    cancel() {
      const q = queue; queue = [];
      q.forEach(u => fire(u, 'error', { error: 'canceled' }));
      if (cur) { const c = cur; cur = null; synth.speaking = false; call('speech.cancel').catch(() => {}); fire(c, 'error', { error: 'interrupted' }); }
      synth.pending = false;
    },
    pause() { synth.cancel(); },  // TextToSpeech cannot pause in the middle of a sentence
    resume() {},
    addEventListener(t, f) { (synth._l[t] = synth._l[t] || []).push(f); },
    removeEventListener(t, f) { synth._l[t] = (synth._l[t] || []).filter(g => g !== f); },
    dispatchEvent() { return true; },
  };
  function next() {
    cur = queue.shift() || null;
    synth.pending = queue.length > 0;
    if (!cur) { synth.speaking = false; return; }
    synth.speaking = true;
    cur._id = 's' + (++uid);
    call('speech.speak', { id: cur._id, text: cur.text, lang: cur.lang || '', voice: cur.voice ? cur.voice.name : '', rate: cur.rate, pitch: cur.pitch })
      .catch(() => { /* no engine: neither start nor end, as the WebView's own speechSynthesis (the page checks after 2.5 s) */ });
  }
  function speechEvent(d) {
    if (!cur || !d || d.id !== cur._id) return;
    const u = cur;
    if (d.type === 'start') fire(u, 'start');
    else if (d.type === 'boundary') fire(u, 'boundary', { name: d.name || 'word', charIndex: d.charIndex || 0, charLength: d.charLength || 0 });
    else if (d.type === 'end' || d.type === 'error') {
      cur = null; synth.speaking = false;
      if (d.type === 'end') fire(u, 'end'); else if (d.error !== 'interrupted') fire(u, 'error', { error: d.error || 'synthesis-failed' });
      next();
    }
  }
  function setVoices(list) {
    voices = (list || []).map(v => Object.freeze({ voiceURI: v.voiceURI, name: v.name, lang: v.lang, localService: !!v.localService, default: !!v.default }));
    const ev = { type: 'voiceschanged', target: synth };
    if (synth.onvoiceschanged) try { synth.onvoiceschanged(ev); } catch (e) { later(e); }
    (synth._l.voiceschanged || []).slice().forEach(f => { try { f(ev); } catch (e) { later(e); } });
  }
  if (FlowApp.has('speech')) {
    try {
      Object.defineProperty(window, 'speechSynthesis', { value: synth, configurable: true, enumerable: true, writable: false });
      Object.defineProperty(window, 'SpeechSynthesisUtterance', { value: Utter, configurable: true, enumerable: false, writable: true });
    } catch (e) { /* left as it was */ }
  }

  /* ---- the test switch (§9): no sound from the page either (the app's own player and voice are at volume 0) */
  if (cfg.mute) {
    const P = HTMLMediaElement.prototype, play = P.play;
    P.play = function () { try { this.muted = true; this.volume = 0; } catch (e) { /* ignore */ } return play.apply(this, arguments); };
    const AC = window.BaseAudioContext || window.AudioContext, d = AC && Object.getOwnPropertyDescriptor(AC.prototype, 'destination');
    if (d && d.get) {
      Object.defineProperty(AC.prototype, 'destination', { configurable: true, get() {
        if (!this.__flowMute) { const g = this.createGain(); g.gain.value = 0; g.connect(d.get.call(this)); this.__flowMute = g; }
        return this.__flowMute;
      } });
    }
  }

  // hello: the app learns where to send events, says what is playing, and gives the phone's voices
  call('hello', { url: location.href }).then(r => { if (r && r.voices) setVoices(r.voices); }).catch(() => {});
})();

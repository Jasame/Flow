/* The Android app's own lines for window.FlowApp (docs/native-bridge.md §2, 「共用的包装」). They come first; the shared
   native/flowapp.js (copied into the assets when the app is built) comes right after them and makes window.FlowApp.
   Transport: the app's WebMessageListener `flowNative` ({id, cmd, args} in; {id, ok, result | error} back; {ev, detail}
   for events). Android's own: the back button (_back), speechSynthesis on the phone's own voice (§7), and the test switch
   (no sound from the page, §9). Nothing else is put on window. */
(() => {
  'use strict';
  const port = window.flowNative;
  if (!port || window.FlowApp) return;
  const cfg = __FLOW_CONFIG__;
  let seq = 0;
  const pending = new Map();
  let speechEvent = () => {}, setVoices = () => {};

  window.__flowAppTransport = {
    cfg,
    send(cmd, args) {
      return new Promise((ok, no) => {
        const id = ++seq;
        pending.set(id, [ok, no]);
        port.postMessage(JSON.stringify({ id, cmd, args }));
      });
    },
    // the system back button (Android only): a listener may take it (preventDefault); an open sheet is closed; else the
    // app goes back a page (MainActivity), or to the background
    extend(FlowApp) {
      FlowApp._back = () => {
        const ev = new CustomEvent('flowapp:back', { cancelable: true });
        window.dispatchEvent(ev);
        if (ev.defaultPrevented) return true;
        const sheet = document.getElementById('sheet');
        if (sheet && !sheet.hidden) { const x = sheet.querySelector('[data-close]'); if (x) { x.click(); return true; } }
        return false;
      };
    },
    ready(FlowApp) {
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
      if (FlowApp.has('speech')) speech(FlowApp.call);
      if (cfg.mute) mute();
      // hello: the app learns where to send events, says what is playing, and gives the phone's voices
      FlowApp.call('hello', { url: location.href }).then(r => { if (r && r.voices) setVoices(r.voices); }).catch(() => {});
    },
  };

  /* ---- speechSynthesis on the phone's own voice (§7). Android's WebView has the object but no voice behind it, so the
     page's 「浏览器的声音」 never spoke here (as in WeChat on Android). The same API and events: start before end, boundary
     with charIndex, error 'interrupted' / 'canceled' for what cancel() cuts (never end), speaking and pending as they are. */
  function speech(call) {
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
    speechEvent = d => {
      if (!cur || !d || d.id !== cur._id) return;
      const u = cur;
      if (d.type === 'start') fire(u, 'start');
      else if (d.type === 'boundary') fire(u, 'boundary', { name: d.name || 'word', charIndex: d.charIndex || 0, charLength: d.charLength || 0 });
      else if (d.type === 'end' || d.type === 'error') {
        cur = null; synth.speaking = false;
        if (d.type === 'end') fire(u, 'end'); else if (d.error !== 'interrupted') fire(u, 'error', { error: d.error || 'synthesis-failed' });
        next();
      }
    };
    setVoices = list => {
      voices = (list || []).map(v => Object.freeze({ voiceURI: v.voiceURI, name: v.name, lang: v.lang, localService: !!v.localService, default: !!v.default }));
      const ev = { type: 'voiceschanged', target: synth };
      if (synth.onvoiceschanged) try { synth.onvoiceschanged(ev); } catch (e) { later(e); }
      (synth._l.voiceschanged || []).slice().forEach(f => { try { f(ev); } catch (e) { later(e); } });
    };
    try {
      Object.defineProperty(window, 'speechSynthesis', { value: synth, configurable: true, enumerable: true, writable: false });
      Object.defineProperty(window, 'SpeechSynthesisUtterance', { value: Utter, configurable: true, enumerable: false, writable: true });
    } catch (e) { /* left as it was */ }
  }

  /* ---- the test switch (§9): no sound from the page either (the app's own player and voice are at volume 0) */
  function mute() {
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
})();

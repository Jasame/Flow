/* window.FlowApp in the Android app (docs/native-bridge.md). Put in place by the app before the page's own scripts,
   on the site's own origin only. The page asks `window.FlowApp && FlowApp.has(...)` and otherwise does what it does in
   a browser. Calls return Promises; events come by FlowApp.on(type, fn) and as window events 'flowapp:<type>'.
   Transport: the app's WebMessageListener `flowNative` — {id, cmd, args} in, {id, ok, result | error} back, and
   {ev, detail} for events. */
(function () {
  'use strict';
  if (window.FlowApp) return;
  var port = window.flowNative;
  if (!port) return;
  var CAPS = __FLOW_CAPS__, APP = __FLOW_APP__;

  var seq = 0, pending = {}, subs = {};
  function call(cmd, args) {
    return new Promise(function (ok, no) {
      var id = ++seq;
      pending[id] = [ok, no];
      port.postMessage(JSON.stringify({ id: id, cmd: cmd, args: args === undefined ? null : args }));
    });
  }
  function emit(type, detail) {
    (subs[type] || []).slice().forEach(function (fn) { try { fn(detail); } catch (e) { setTimeout(function () { throw e; }); } });
    try { window.dispatchEvent(new CustomEvent('flowapp:' + type, { detail: detail })); } catch (e) { /* old engine */ }
  }
  port.onmessage = function (e) {
    var m; try { m = JSON.parse(e.data); } catch (x) { return; }
    if (m.ev) { if (m.ev === 'speech') speechEvent(m.detail); else if (m.ev === 'speech-voices') setVoices(m.detail); else emit(m.ev, m.detail); return; }
    var p = pending[m.id]; if (!p) return;
    delete pending[m.id];
    if (m.ok) p[0](m.result); else { var err = new Error(m.error || 'error'); err.code = m.code; p[1](err); }
  };

  var app = {
    v: 1, app: APP, platform: 'android',
    has: function (k) { return CAPS.indexOf(k) >= 0; },
    on: function (type, fn) { (subs[type] = subs[type] || []).push(fn); return function () { app.off(type, fn); }; },
    off: function (type, fn) { subs[type] = (subs[type] || []).filter(function (f) { return f !== fn; }); },
    audio: {
      play: function (o) { return call('audio.play', o || {}); },
      pause: function (o) { return call('audio.pause', o || {}); },
      resume: function () { return call('audio.resume'); },
      stop: function () { return call('audio.stop'); },
      step: function (d) { return call('audio.step', d); },
      seek: function (i) { return call('audio.seek', i); },
      set: function (o) { return call('audio.set', o || {}); },
      state: function () { return call('audio.state'); },
      progress: function (key) { return call('audio.progress', key); }
    },
    rec: {
      permission: function () { return call('rec.permission'); },
      ask: function () { return call('rec.ask'); },
      start: function (o) { return call('rec.start', o || {}); },
      stop: function () { return call('rec.stop'); },
      cancel: function () { return call('rec.cancel'); }
    },
    notify: {
      permission: function () { return call('notify.permission'); },
      ask: function () { return call('notify.ask'); },
      sync: function (r) { return call('notify.sync', r || {}); },
      off: function () { return call('notify.off'); },
      settings: function () { return call('notify.settings'); }
    },
    // The system back button / gesture: a listener may take it (e.preventDefault()); an open sheet is closed;
    // otherwise the app goes back a page, or leaves.
    _back: function () {
      var ev = new CustomEvent('flowapp:back', { cancelable: true });
      window.dispatchEvent(ev);
      if (ev.defaultPrevented) return true;
      var sheet = document.getElementById('sheet');
      if (sheet && !sheet.hidden) { var x = sheet.querySelector('[data-close]'); if (x) { x.click(); return true; } }
      return false;
    },
    _emit: emit
  };
  window.FlowApp = Object.freeze(app);

  /* ---- speechSynthesis on the phone's own voice. Android's WebView has the object but no voice behind it, so the
     page's 「浏览器的声音」 never spoke here (as in WeChat on Android). Same API, same events (start, boundary with
     charIndex, end, error); no pause in the middle of a sentence (Android's TextToSpeech has none). */
  var voices = [], queue = [], cur = null, uid = 0;
  function Utter(text) {
    this.text = text == null ? '' : String(text); this.lang = ''; this.voice = null; this.rate = 1; this.pitch = 1; this.volume = 1;
    this.onstart = this.onend = this.onerror = this.onboundary = this.onpause = this.onresume = this.onmark = null; this._l = {};
  }
  Utter.prototype.addEventListener = function (t, f) { (this._l[t] = this._l[t] || []).push(f); };
  Utter.prototype.removeEventListener = function (t, f) { this._l[t] = (this._l[t] || []).filter(function (g) { return g !== f; }); };
  function fire(u, type, extra) {
    var ev = { type: type, utterance: u, target: u, charIndex: 0, charLength: 0, elapsedTime: 0, name: '' };
    for (var k in extra || {}) ev[k] = extra[k];
    var h = u['on' + type]; if (h) try { h.call(u, ev); } catch (e) { setTimeout(function () { throw e; }); }
    (u._l[type] || []).slice().forEach(function (f) { try { f.call(u, ev); } catch (e) { setTimeout(function () { throw e; }); } });
  }
  var synth = {
    speaking: false, pending: false, paused: false, onvoiceschanged: null, _l: {},
    getVoices: function () { return voices.slice(); },
    speak: function (u) { if (!(u instanceof Utter)) return; queue.push(u); synth.pending = !!cur || queue.length > 1; if (!cur) next(); },
    cancel: function () {
      var q = queue; queue = [];
      q.forEach(function (u) { fire(u, 'error', { error: 'canceled' }); });
      if (cur) { var c = cur; cur = null; synth.speaking = false; call('speech.cancel').catch(function () {}); fire(c, 'error', { error: 'interrupted' }); }
      synth.pending = false;
    },
    pause: function () { synth.cancel(); },
    resume: function () {},
    addEventListener: function (t, f) { (synth._l[t] = synth._l[t] || []).push(f); },
    removeEventListener: function (t, f) { synth._l[t] = (synth._l[t] || []).filter(function (g) { return g !== f; }); },
    dispatchEvent: function () { return true; }
  };
  function next() {
    cur = queue.shift() || null;
    synth.pending = queue.length > 0;
    if (!cur) { synth.speaking = false; return; }
    synth.speaking = true;
    cur._id = 's' + (++uid);
    call('speech.speak', { id: cur._id, text: cur.text, lang: cur.lang || '', voice: cur.voice ? cur.voice.name : '', rate: cur.rate, pitch: cur.pitch })
      .catch(function () { /* no engine: neither start nor end, as the WebView's own speechSynthesis (the page checks after 2.5 s) */ });
  }
  function speechEvent(d) {
    if (!cur || !d || d.id !== cur._id) return;
    var u = cur;
    if (d.type === 'start') fire(u, 'start');
    else if (d.type === 'boundary') fire(u, 'boundary', { name: d.name || 'word', charIndex: d.charIndex || 0, charLength: d.charLength || 0 });
    else if (d.type === 'end' || d.type === 'error') {
      cur = null; synth.speaking = false;
      if (d.type === 'end') fire(u, 'end'); else if (d.error !== 'interrupted') fire(u, 'error', { error: d.error || 'synthesis-failed' });
      next();
    }
  }
  function setVoices(list) {
    voices = (list || []).map(function (v) { return Object.freeze({ voiceURI: v.voiceURI, name: v.name, lang: v.lang, localService: !!v.localService, 'default': !!v['default'] }); });
    var ev = { type: 'voiceschanged', target: synth };
    if (synth.onvoiceschanged) try { synth.onvoiceschanged(ev); } catch (e) { setTimeout(function () { throw e; }); }
    (synth._l.voiceschanged || []).slice().forEach(function (f) { try { f(ev); } catch (e) { setTimeout(function () { throw e; }); } });
  }
  if (CAPS.indexOf('speech') >= 0) {
    try {
      Object.defineProperty(window, 'speechSynthesis', { value: synth, configurable: true, enumerable: true, writable: false });
      Object.defineProperty(window, 'SpeechSynthesisUtterance', { value: Utter, configurable: true, enumerable: false, writable: true });
    } catch (e) { /* left as it was */ }
  }

  // hello: the app learns where to send events, and says what is going on (a text playing, the voices)
  call('hello', { url: location.href }).then(function (r) { if (r && r.voices) setVoices(r.voices); }).catch(function () {});
})();

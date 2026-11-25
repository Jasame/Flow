/* 语流 desktop app: window.FlowApp, the same bridge as the iOS and Android apps (shared notes ios-app.md, v1).
 * Injected before the page's own scripts, on the app's own site only. The page checks
 * `window.FlowApp && FlowApp.has(...)` and keeps its web behaviour otherwise.
 *
 * Desktop specifics:
 *  - has('notify'): the review reminders as system notifications (permission / ask / sync, as on iOS).
 *  - has('media'): the system's media controls (Windows SMTC, macOS 「正在播放」, the media keys) follow the
 *    page's navigator.mediaSession; a key runs the action the page registered. The page plays its own audio.
 *  - no 'audio' / 'rec': a desktop webview plays and records like a browser.
 *  - FLOW_MUTE=1 (and every --smoke-test): the page makes no sound — <audio>/<video> muted, Web Audio through a
 *    silent gain, browser speech at volume 0. Everything else (events, timing, media controls) runs as usual.
 */
(() => {
  'use strict';
  if (window.FlowApp || location.origin !== __FLOW_ORIGIN__) return;
  const T = window.__TAURI_INTERNALS__;
  if (!T || typeof T.invoke !== 'function') return;
  const invoke = (cmd, args) => T.invoke(cmd, args || {});
  const MUTE = __FLOW_MUTE__;
  if (MUTE) {
    const conn = AudioNode.prototype.connect;
    AudioNode.prototype.connect = function (dest, ...rest) {
      if (typeof AudioDestinationNode !== 'undefined' && dest instanceof AudioDestinationNode) {
        const ctx = dest.context;
        if (!ctx.__flowSilent) { const g = ctx.createGain(); g.gain.value = 0; conn.call(g, dest); ctx.__flowSilent = g; }
        conn.call(this, ctx.__flowSilent, ...rest);
        return dest;
      }
      return conn.call(this, dest, ...rest);
    };
    if (window.speechSynthesis) {
      const speak = speechSynthesis.speak.bind(speechSynthesis);
      speechSynthesis.speak = u => { try { u.volume = 0; } catch (e) { /* ignore */ } return speak(u); };
    }
  }
  const CAPS = ['notify', 'media'];
  const subs = new Map();
  const emit = (type, detail) => {
    (subs.get(type) || []).slice().forEach(fn => { try { fn(detail); } catch (e) { console.error(e); } });
    try { dispatchEvent(new CustomEvent('flowapp:' + type, { detail })); } catch (e) { /* ignore */ }
  };

  /* ---------- media: follow navigator.mediaSession ---------- */
  const media = { handlers: {}, md: null, state: 'none', el: null, sent: '' };
  let timer = 0;
  const send = () => {
    timer = 0;
    const el = media.el, md = media.md;
    const s = {
      title: md && md.title ? String(md.title) : null,
      artist: md && md.artist ? String(md.artist) : null,
      state: md ? media.state : 'none',
      actions: Object.keys(media.handlers).filter(k => typeof media.handlers[k] === 'function'),
      position: el && isFinite(el.currentTime) ? el.currentTime : null,
      duration: el && isFinite(el.duration) ? el.duration : null,
    };
    const key = JSON.stringify(s);
    if (key === media.sent) return;
    media.sent = key;
    invoke('media_update', { s }).catch(() => {});
  };
  const push = () => { if (!timer) timer = setTimeout(send, 40); };
  const ms = navigator.mediaSession;
  if (ms) {
    const proto = Object.getPrototypeOf(ms);
    const wrap = (name, after) => {
      const d = Object.getOwnPropertyDescriptor(proto, name);
      if (!d || !d.set) return;
      Object.defineProperty(ms, name, {
        configurable: true, enumerable: true,
        get() { return d.get.call(ms); },
        set(v) { try { d.set.call(ms, v); } catch (e) { /* the webview's own check */ } after(v); push(); },
      });
    };
    wrap('metadata', v => { media.md = v ? { title: v.title, artist: v.artist } : null; });
    wrap('playbackState', v => { media.state = String(v || 'none'); });
    const set0 = typeof ms.setActionHandler === 'function' ? ms.setActionHandler.bind(ms) : null;
    ms.setActionHandler = (action, fn) => {
      media.handlers[action] = typeof fn === 'function' ? fn : null;
      // the webview may not know an action (stop, …): the app still does
      try { if (set0) set0(action, fn); } catch (e) { /* ignore */ }
      push();
    };
  } else {
    // a webview without the Media Session API: give the page one, so MS.claim works the same
    if (!window.MediaMetadata) {
      window.MediaMetadata = class MediaMetadata { constructor(o) { Object.assign(this, { title: '', artist: '', album: '', artwork: [] }, o || {}); } };
    }
    let md = null, st = 'none';
    const fake = {
      get metadata() { return md; }, set metadata(v) { md = v; media.md = v ? { title: v.title, artist: v.artist } : null; push(); },
      get playbackState() { return st; }, set playbackState(v) { st = String(v); media.state = st; push(); },
      setActionHandler(a, fn) { media.handlers[a] = typeof fn === 'function' ? fn : null; push(); },
      setPositionState() {},
    };
    try { Object.defineProperty(navigator, 'mediaSession', { value: fake, configurable: true }); } catch (e) { /* ignore */ }
  }
  // which <audio> is playing: for the position and length in the system's controls
  const P = HTMLMediaElement.prototype, play0 = P.play, seen = new WeakSet();
  P.play = function () {
    if (MUTE) this.muted = true;
    media.el = this;
    if (!seen.has(this)) {
      seen.add(this);
      ['playing', 'pause', 'ended', 'seeked', 'ratechange', 'durationchange', 'emptied'].forEach(ev =>
        this.addEventListener(ev, () => { if (media.el === this) { media.sent = ''; push(); } }));
    }
    push();
    return play0.apply(this, arguments);
  };

  /* ---------- the review reminders (docs/native-bridge.md §5) ----------
   * The app plans them from the whole /api/next/vocab answer (due, later, forecast, the book's new words …), fetched
   * here with the page's own login: when the app opens, when it comes back to the front (at most every 30 minutes),
   * and whenever the page calls sync(r) — the page's r says something changed; the server has the details. */
  let planning = null;
  const replan = force => planning || (planning = (async () => {
    try {
      if (!force && !(await invoke('notify_due'))) return { ok: true, planned: 0, why: 'off' };
      const r = await fetch('/api/next/vocab', { credentials: 'same-origin' });
      if (r.status === 401) return await invoke('notify_signed_out');  // signed out: no word reminders
      if (!r.ok) return { ok: false, planned: 0, why: 'http ' + r.status };
      return await invoke('notify_plan', { v: await r.json() });
    } catch (e) {
      return { ok: false, planned: 0, why: 'offline' };  // the ones already planned stay
    } finally { planning = null; }
  })());
  const quietly = () => { if (document.visibilityState === 'visible') replan(false); };
  addEventListener('load', () => setTimeout(quietly, 4000));
  document.addEventListener('visibilitychange', () => setTimeout(quietly, 1500));

  const FlowApp = {
    v: 1,
    app: __FLOW_VERSION__,
    build: __FLOW_BUILD__,
    beta: __FLOW_BETA__,
    platform: __FLOW_PLATFORM__,
    has: k => CAPS.includes(k),
    on(type, fn) {
      if (typeof fn !== 'function') return () => {};
      const l = subs.get(type) || []; l.push(fn); subs.set(type, l);
      return () => FlowApp.off(type, fn);
    },
    off(type, fn) { const l = subs.get(type); if (l) subs.set(type, l.filter(f => f !== fn)); },
    call(name) {
      if (name === 'hello') return Promise.resolve({ v: 1, app: FlowApp.app, build: FlowApp.build, platform: FlowApp.platform, features: CAPS.slice() });
      // the page is visible again: send the media state once more (the system's controls follow it)
      if (name === 'app.visible') { media.sent = ''; push(); return Promise.resolve({ ok: true }); }
      return Promise.reject(new Error('FlowApp: no command ' + name));
    },
    notify: Object.freeze({
      permission: () => invoke('notify_permission'),
      ask: () => invoke('notify_ask'),
      // null or {app: false}: the learner turned the app's reminders off; anything else: plan again
      sync: r => (!r || r.app === false) ? invoke('notify_off') : replan(true),
      pending: () => invoke('notify_pending'),
    }),
    // the app → the page
    _media(action) {
      const fn = media.handlers[action];
      if (typeof fn === 'function') { try { fn({ action }); } catch (e) { console.error(e); } }
      emit('media', { action });
    },
    _replan: () => replan(true),
    _emit: emit,
  };
  Object.defineProperty(window, 'FlowApp', { value: Object.freeze(FlowApp), configurable: false, writable: false });
})();

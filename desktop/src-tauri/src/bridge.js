/* 语流 desktop app: window.FlowApp, the same bridge as the iOS and Android apps (shared notes ios-app.md, v1).
 * Injected before the page's own scripts, on the app's own site only. The page checks
 * `window.FlowApp && FlowApp.has(...)` and keeps its web behaviour otherwise.
 *
 * Desktop specifics:
 *  - has('notify'): the review reminders as system notifications (permission / ask / sync, as on iOS).
 *  - has('media'): the system's media controls (Windows SMTC, macOS 「正在播放」, the media keys) follow the
 *    page's navigator.mediaSession; a key runs the action the page registered. The page plays its own audio.
 *  - no 'audio' / 'rec': a desktop webview plays and records like a browser.
 */
(() => {
  'use strict';
  if (window.FlowApp || location.origin !== __FLOW_ORIGIN__) return;
  const T = window.__TAURI_INTERNALS__;
  if (!T || typeof T.invoke !== 'function') return;
  const invoke = (cmd, args) => T.invoke(cmd, args || {});
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
    media.el = this;
    if (!seen.has(this)) {
      seen.add(this);
      ['playing', 'pause', 'ended', 'seeked', 'ratechange', 'durationchange', 'emptied'].forEach(ev =>
        this.addEventListener(ev, () => { if (media.el === this) { media.sent = ''; push(); } }));
    }
    push();
    return play0.apply(this, arguments);
  };

  /* ---------- the review reminders: the app re-plans them when it opens and comes back to the front ---------- */
  let resyncing = false;
  const resync = async () => {
    if (resyncing || document.visibilityState !== 'visible') return;
    resyncing = true;
    try {
      if (!(await invoke('notify_due'))) return;
      const r = await fetch('/api/next/vocab', { credentials: 'same-origin' });
      if (r.status === 401) { await invoke('notify_sync', { r: null }); return; }  // signed out: no reminders
      if (!r.ok) return;
      const j = await r.json();
      if (j && j.reminder) await invoke('notify_sync', { r: Object.assign({}, j.reminder, { forecast: j.forecast }) });
    } catch (e) { /* offline: the ones already planned stay */ } finally { resyncing = false; }
  };
  addEventListener('load', () => setTimeout(resync, 4000));
  document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'visible') setTimeout(resync, 1500); });

  const FlowApp = {
    v: 1,
    app: __FLOW_VERSION__,
    platform: __FLOW_PLATFORM__,
    has: k => CAPS.includes(k),
    on(type, fn) { if (typeof fn !== 'function') return; const l = subs.get(type) || []; l.push(fn); subs.set(type, l); },
    off(type, fn) { const l = subs.get(type); if (l) subs.set(type, l.filter(f => f !== fn)); },
    notify: Object.freeze({
      permission: () => invoke('notify_permission'),
      ask: () => invoke('notify_ask'),
      sync: r => invoke('notify_sync', { r: r ? Object.assign({}, r) : null }),
    }),
    // the app → the page
    _media(action) {
      const fn = media.handlers[action];
      if (typeof fn === 'function') { try { fn({ action }); } catch (e) { console.error(e); } }
      emit('media', { action });
    },
    _emit: emit,
  };
  Object.defineProperty(window, 'FlowApp', { value: Object.freeze(FlowApp), configurable: false, writable: false });
})();

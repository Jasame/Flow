/* window.FlowApp: 语流's iOS app, for the page. Injected at document start in the main frame of the site only, before
   the page's own scripts. The page checks `window.FlowApp && FlowApp.has('audio' | 'rec' | 'notify')` and otherwise does
   what it does in Safari. Calls answer with a Promise; the app's news comes as FlowApp.on(type, fn) and as a
   `flowapp:<type>` event on window. Interface: ios/README.md, 「网页和 App 之间的桥」. */
(() => {
  'use strict';
  const cfg = window.__flowAppConfig || {};
  try { delete window.__flowAppConfig; } catch (e) { /* ignore */ }
  const h = window.webkit && window.webkit.messageHandlers && window.webkit.messageHandlers.flow;
  if (!h || window.FlowApp) return;
  const call = (cmd, args) => h.postMessage({ cmd, args: args || {} });
  const subs = {};
  const FlowApp = {
    v: cfg.v || 1, app: cfg.app || '', build: cfg.build || '', beta: !!cfg.beta,
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
    // the microphone: ask() → true/false (iOS's question, once); start({max, format}) → {ok}; stop() → {ok, mime_type, data (base64), ms}
    rec: Object.freeze({
      permission: () => call('rec.permission'), ask: () => call('rec.ask'), start: o => call('rec.start', o), stop: () => call('rec.stop'),
      cancel: () => call('rec.cancel'),
    }),
    // review reminders as local notifications: sync(reminder) after the page changed one
    notify: Object.freeze({
      permission: () => call('notify.permission'), ask: () => call('notify.ask'), sync: r => call('notify.sync', r), pending: () => call('notify.pending'),
    }),
  };
  Object.defineProperty(window, 'FlowApp', { value: Object.freeze(FlowApp), enumerable: false, configurable: false, writable: false });
  if (document.documentElement) document.documentElement.classList.add('flow-ios');
  // back on screen: the app sends what is playing now (it went on while the page slept)
  document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'visible') call('app.visible').catch(() => {}); });
})();

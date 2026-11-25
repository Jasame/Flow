/* window.FlowApp v1: the one wrapper that 语流's iOS, Android and desktop apps put in the page (docs/native-bridge.md §2).
   Each app adds this file at document start, in the main frame of the site's own origin only, before the page's own
   scripts, and right after its own few lines of transport:

     window.__flowAppTransport = {
       cfg: { v, app, build, beta, platform, features },  // what the app says about itself (platform: ios | android | windows | macos)
       send(cmd, args),          // one command to the app ('audio.play', {…}): its answer, as a value or a Promise
       extend(FlowApp, call),    // optional: the platform's own members, added before FlowApp is frozen (Android: _back)
       ready(FlowApp),           // optional: once window.FlowApp is there (Android: the port's messages, hello)
     };

   The page checks `window.FlowApp && FlowApp.has('audio' | 'rec' | 'notify' | 'media' | 'speech')` and otherwise does
   what it does in a browser. Every command answers a Promise (the page awaits it); expected failures resolve with
   {ok: false, why}. The app's news comes through FlowApp._emit(type, detail): FlowApp.on(type, fn) and a
   `flowapp:<type>` event on window. The apps take this file as it is: iOS bundles it (ios/Flow.xcodeproj, group
   Shared), Android copies it into its assets when it builds. A change here is a change for all three apps. */
(() => {
  'use strict';
  const t = window.__flowAppTransport;
  try { delete window.__flowAppTransport; } catch (e) { /* ignore */ }
  if (!t || typeof t.send !== 'function' || window.FlowApp) return;
  const cfg = t.cfg || {};
  const call = (cmd, args) => {
    try { return Promise.resolve(t.send(cmd, args == null ? {} : args)); } catch (e) { return Promise.reject(e); }
  };
  const subs = Object.create(null);
  let features = Object.freeze((cfg.features || []).slice());
  const FlowApp = {
    v: cfg.v || 1, app: cfg.app || '', build: cfg.build || '', beta: !!cfg.beta, platform: cfg.platform || '',
    get features() { return features; },
    has: f => features.includes(f),  // follows the app: a 'features' event (a switch of the app's own page) replaces the list  (§2)
    call,
    on(type, fn) {
      if (typeof fn !== 'function') return () => {};
      (subs[type] = subs[type] || []).push(fn);
      return () => FlowApp.off(type, fn);
    },
    off(type, fn) { if (subs[type]) subs[type] = subs[type].filter(x => x !== fn); },
    _emit(type, detail) {
      if (type === 'features' && detail && Array.isArray(detail.features)) features = Object.freeze(detail.features.slice());
      (subs[type] || []).slice().forEach(fn => { try { fn(detail); } catch (e) { console.error('FlowApp', type, e); } });
      try { window.dispatchEvent(new CustomEvent('flowapp:' + type, { detail })); } catch (e) { /* ignore */ }
    },
    // a whole text, played by the app (the screen locked, calls, other apps): play(o) → {ok, state}  (§3)
    audio: Object.freeze({
      play: o => call('audio.play', o), pause: () => call('audio.pause'), resume: () => call('audio.resume'),
      stop: () => call('audio.stop'), step: d => call('audio.step', { d }), seek: i => call('audio.seek', { i }),
      set: o => call('audio.set', o), state: () => call('audio.state'), progress: key => call('audio.progress', { key }),
    }),
    // the microphone: ask() → true/false; start({max, format}) → {ok}; stop() → {ok, mime_type, data (base64), ms, bytes, cut}  (§4)
    rec: Object.freeze({
      permission: () => call('rec.permission'), ask: () => call('rec.ask'), start: o => call('rec.start', o),
      stop: () => call('rec.stop'), cancel: () => call('rec.cancel'),
      // iOS, has('localcheck'): the take just stopped, heard on the phone with no network → {ok, heard} (§4)
      localcheck: o => call('rec.localcheck', o),
    }),
    // review reminders as the system's notifications: sync(reminder) after the page changed one; sync(null) or off()
    // turns the app's reminders off; permission() is 'granted' only while they are on  (§5)
    notify: Object.freeze({
      permission: () => call('notify.permission'), ask: () => call('notify.ask'),
      sync: r => call('notify.sync', r === null ? { app: false } : r),
      pending: () => call('notify.pending'), off: () => call('notify.off'), settings: () => call('notify.settings'),
    }),
  };
  if (typeof t.extend === 'function') { try { t.extend(FlowApp, call); } catch (e) { console.error('FlowApp', e); } }
  Object.defineProperty(window, 'FlowApp', { value: Object.freeze(FlowApp), enumerable: false, configurable: false, writable: false });
  if (document.documentElement && FlowApp.platform) document.documentElement.classList.add('flow-' + FlowApp.platform);
  // back on screen: the app sends what is playing now (it went on while the page slept)
  document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'visible') call('app.visible').catch(() => {}); });
  if (typeof t.ready === 'function') { try { t.ready(FlowApp); } catch (e) { console.error('FlowApp', e); } }
})();

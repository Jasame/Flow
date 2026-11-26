/* The HarmonyOS app's own lines for window.FlowApp (docs/native-bridge.md §2, 「共用的包装」). They come first; the
   shared native/flowapp.js (copied into rawfile when the app is built, entry/hvigorfile.ts) comes right after them and
   makes window.FlowApp. Both are put in at document start on the site's own origin only (javaScriptOnDocumentStart).
   Transport: page → app through the ArkWeb proxy `flowNative.post(json)` ({id, cmd, args}); app → page through
   runJavaScript, which calls the receiver named in the config with {id, ok, result | error} or {ev, detail}.
   HarmonyOS's own: the back gesture (_back, as Android's back button) and the test switch (no sound from the page, §9).
   Nothing else is put on window. */
(() => {
  'use strict';
  const nat = window.flowNative;
  if (!nat || typeof nat.post !== 'function' || window.FlowApp) return;
  const cfg = __FLOW_CONFIG__;
  let seq = 0, app = null;
  const pending = new Map(), early = [];

  // app → page. Not enumerable; named per app start, so nothing on the page calls it by chance.
  const recv = m => {
    if (typeof m === 'string') { try { m = JSON.parse(m); } catch (e) { return; } }
    if (!m) return;
    if (m.ev) { if (app) app._emit(m.ev, m.detail); else early.push(m); return; }
    const p = pending.get(m.id);
    if (!p) return;
    pending.delete(m.id);
    if (m.ok) p[0](m.result); else { const err = new Error(m.error || 'error'); err.code = m.code; p[1](err); }
  };
  try { Object.defineProperty(window, cfg.recv, { value: recv, enumerable: false, configurable: false, writable: false }); } catch (e) { return; }

  window.__flowAppTransport = {
    cfg,
    send(cmd, args) {
      return new Promise((ok, no) => {
        const id = ++seq;
        pending.set(id, [ok, no]);
        try { nat.post(JSON.stringify({ id, cmd, args })); } catch (e) { pending.delete(id); no(e); }
      });
    },
    // the back gesture (swipe in from the edge): a listener may take it (preventDefault); an open sheet is closed;
    // else the app goes back a page (pages/Index.ets), or to the background — as Android's back button
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
      app = FlowApp;
      early.splice(0).forEach(m => FlowApp._emit(m.ev, m.detail));
      if (cfg.mute) mute();
      // hello: the app learns that this page is on the bridge, and says what is playing
      FlowApp.call('hello', { url: location.href }).catch(() => {});
    },
  };

  /* ---- the test switch (§9): no sound from the page either (the app's own player is at volume 0) */
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
    if (window.speechSynthesis) { try { window.speechSynthesis.speak = function () {}; } catch (e) { /* ignore */ } }
  }
})();

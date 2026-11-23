'use strict';
/* Flow — one learning loop: listen → read → check → use it → review what you saved,
   steered by the knowledge graph (18 grammar nodes) and AI. See NEXT.md. */
(function () {
  const view = document.getElementById('view');
  const bar = document.getElementById('bar');
  const sheetEl = document.getElementById('sheet');
  const sheetCard = document.getElementById('sheetCard');
  const toastEl = document.getElementById('toast');
  const S = { user: null, csrf: '', meta: null, home: null, homeFresh: false, placed: '', guest: load('flow-next-guest'), lastRoute: '', voice: load('flow-next-voice') || 'us-f' };
  const VOICE_LABELS = { 'us-f': '美音 · 女', 'us-m': '美音 · 男', 'uk-f': '英音 · 女', 'uk-m': '英音 · 男' };
  const STEP = { listen: '听', read: '读', check: '理解', output: '用出来' };
  const STEPS = Object.keys(STEP);
  const REDUCED = matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* ---------- utilities ---------- */
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])); }
  function load(k) { try { return JSON.parse(localStorage.getItem(k) || 'null'); } catch (e) { return null; } }
  function save(k, v) { try { v == null ? localStorage.removeItem(k) : localStorage.setItem(k, JSON.stringify(v)); } catch (e) { /* private mode */ } }
  function rid(prefix) { return prefix + '-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 10); }
  function toast(msg) { toastEl.textContent = msg; toastEl.classList.add('show'); clearTimeout(toast.t); toast.t = setTimeout(() => toastEl.classList.remove('show'), 2400); }
  async function api(path, body) {
    const opt = { credentials: 'same-origin', headers: {} };
    if (body !== undefined) { opt.method = 'POST'; opt.headers['Content-Type'] = 'application/json'; if (S.csrf) opt.headers['X-CSRF-Token'] = S.csrf; opt.body = JSON.stringify(body); }
    let r;
    try { r = await fetch(path, opt); } catch (x) { noteIssue('api', '网络连接失败', path.split('?')[0]); const e = new Error('网络连接失败，请检查网络'); e.network = true; throw e; }
    const j = await r.json().catch(() => ({}));
    if (!r.ok) {
      if (r.status >= 500) noteIssue('api', `服务器返回 ${r.status}`, path.split('?')[0]);  // 4xx are answers (a wrong password …), not faults
      const e = new Error(j.error || ('请求失败（' + r.status + '）')); e.status = r.status; e.field = j.field; e.code = j.code;
      // Signed out on the server (30 days away, a password change, 退出所有设备): say so and offer to sign in again.
      if (r.status === 401 && S.user && !/^\/api\/(login|register|auth\/)/.test(path)) {
        S.user = null; S.csrf = ''; e.message = '登录已过期，请重新登录';
        if (sheetEl.hidden) setTimeout(() => openLogin('登录已过期，请重新登录。登录后会回到这一页。'), 0);
      }
      throw e;
    }
    return j;
  }
  const ICON = {
    play: '<svg viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>',
    speak: '<svg viewBox="0 0 24 24"><path d="M4 10v4h4l5 4V6L8 10zM16 9a4 4 0 0 1 0 6M18.5 6.5a8 8 0 0 1 0 11"/></svg>',
    eye: '<svg viewBox="0 0 24 24"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/></svg>',
    star: '<svg viewBox="0 0 24 24"><path d="m12 3 2.8 5.8 6.2.9-4.5 4.4 1 6.2L12 17.4l-5.5 2.9 1-6.2L3 9.7l6.2-.9z"/></svg>',
    trash: '<svg viewBox="0 0 24 24"><path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13"/></svg>',
    stop: '<svg viewBox="0 0 24 24"><rect x="6.5" y="6.5" width="11" height="11" rx="2"/></svg>',
  };
  const playIcon = (on, size) => (on ? ICON.stop : ICON.play).replace('<svg', `<svg width="${size || 18}" height="${size || 18}" fill="currentColor"`);
  const skeleton = () => '<div class="skeleton" aria-hidden="true"><i class="t"></i><i class="s"></i><i class="b"></i><i></i><i></i><i class="s"></i></div>';
  const doneRing = '<svg class="done-ring" viewBox="0 0 72 72" aria-hidden="true"><circle cx="36" cy="36" r="30"/><path d="M24 37l8 8 16-17"/></svg>';
  function level() { return (S.home && S.home.level) || (S.guest && S.guest.level) || 'B1'; }
  function hasProfile() { return S.user ? !!(S.home && S.home.profile) || !!(S.guest && S.guest.level) : !!(S.guest && S.guest.level); }
  function guestQuery(first) {
    if (S.user) return '';
    const g = S.guest || {};
    return (first ? '?' : '&') + 'level=' + encodeURIComponent(g.level || 'B1') + (g.themes && g.themes.length ? '&themes=' + encodeURIComponent(g.themes.join(',')) : '');
  }
  function enter(el) { if (!el) return; el.classList.remove('enter'); void el.offsetWidth; el.classList.add('enter'); }
  function nodeChip(n) { return `<a class="node-chip st st-${esc(n.status || 'untouched')}" href="#/graph/${encodeURIComponent(n.id || n.node)}">${esc(n.title)}</a>`; }
  // Input: coarse pointer = finger. Hover-only affordances and keyboard hints are adjusted for it.
  const TOUCH = matchMedia('(pointer: coarse)').matches;
  const isTyping = e => !!(e && e.target && e.target.closest && e.target.closest('input:not([type=checkbox]):not([type=radio]),textarea,select,[contenteditable]'));
  const srEl = document.getElementById('sr');
  function announce(t) { if (!srEl || !t) return; srEl.textContent = ''; setTimeout(() => { srEl.textContent = t; }, 40); }
  // Scroll so an element sits just below the sticky header (and the study step bar when there is one).
  function bringIntoView(el, smooth) {
    if (!el) return;
    const steps = view.querySelector('.steps');
    const off = bar.offsetHeight + (steps && !steps.contains(el) ? steps.offsetHeight : 0) + 10;
    scrollTo({ top: Math.max(0, el.getBoundingClientRect().top + scrollY - off), behavior: smooth === false || REDUCED ? 'auto' : 'smooth' });
  }


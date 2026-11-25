  /* ---------- drafts: what a learner wrote is still there after leaving the page ---------- */
  // A writing box with data-draft="<key>" keeps its text on this device while it is typed, and gets it back when the
  // box is drawn again (a tab tapped, a back swipe, the app closed), with a line under it: 「已恢复上次没写完的内容」 and
  // 「清空」 (which can be undone for a few seconds). The page calls draftDone(key) once what was written has been sent.
  // A draft belongs to the account that wrote it and is only given back to it (one written before signing in goes to
  // whoever signs in: write first, then 「登录后 AI 会…」);
  // signing out clears every draft on the device (snapClear, 05-data.js), so the next person on a shared computer
  // finds none. A draft not touched for 14 days is dropped. The essay and the model sentence (24-study-output.js) keep
  // their own drafts as before; signing out clears those too.
  const DRAFT_PRE = 'flow-next-draft-box-', DRAFT_DAYS = 14;
  const draftSlot = k => DRAFT_PRE + k;
  const draftHash = s => { let h = 5381; for (const ch of String(s)) h = (h * 33 + ch.charCodeAt(0)) >>> 0; return h.toString(36); };  // a key for a long question
  const draftNotes = k => document.querySelectorAll(`.draft-note[data-for="${CSS.escape(k)}"]`);
  function draftDone(k) { save(draftSlot(k), null); draftNotes(k).forEach(n => n.remove()); }
  function draftClearAll() {
    try { Object.keys(localStorage).filter(k => k.startsWith('flow-next-draft-') || k.startsWith('flow-next-essay-')).forEach(k => localStorage.removeItem(k)); } catch (e) { /* private mode */ }
  }
  document.addEventListener('input', e => {
    const t = e.target;
    if (!t || !t.dataset || !t.dataset.draft) return;
    save(draftSlot(t.dataset.draft), t.value.trim() ? { v: t.value, at: Date.now(), who: snapOwner() } : null);
  });
  // Fill a new box from its draft, unless its page has already put text in it. An input event follows, so the
  // page's own counter ("0 / 1000", "12 词") and checks see the text as if it had been typed.
  function draftFill(t) {
    if (t.value || t.dataset.draftFilled) return;
    t.dataset.draftFilled = '1';
    const k = t.dataset.draft, d = load(draftSlot(k));
    if (!d || !d.v) return;
    // written by someone else on this device: never shown (written before signing in: given to the account signed in now)
    if ((d.who !== snapOwner() && d.who !== 'guest') || Date.now() - (d.at || 0) > DRAFT_DAYS * 864e5) { save(draftSlot(k), null); return; }
    t.value = d.v;
    t.dispatchEvent(new Event('input', { bubbles: true }));
    const note = document.createElement('p');
    note.className = 'draft-note tiny muted'; note.dataset.for = k; note.setAttribute('role', 'status');
    const say = (msg, btn, act) => { note.innerHTML = `<span>${msg}</span><button type="button" class="link small">${btn}</button>`; note.querySelector('button').onclick = act; };
    const gone = () => note.remove();  // typing again after 清空: the undo is no longer offered
    const restored = () => say('已恢复上次没写完的内容', '清空', () => {
      const was = t.value;
      t.value = ''; t.dispatchEvent(new Event('input', { bubbles: true }));
      t.addEventListener('input', gone, { once: true });
      say('已清空', '撤销', () => { t.removeEventListener('input', gone); t.value = was; t.dispatchEvent(new Event('input', { bubbles: true })); restored(); });
      clearTimeout(note.t); note.t = setTimeout(() => { if (!t.value) gone(); }, 6000);
      if (!TOUCH) t.focus();
    });
    restored();
    t.insertAdjacentElement('afterend', note);
  }
  new MutationObserver(ms => {
    for (const m of ms) for (const n of m.addedNodes) {
      if (n.nodeType !== 1) continue;
      if (n.matches('textarea[data-draft]')) draftFill(n);
      else if (n.firstElementChild) n.querySelectorAll('textarea[data-draft]').forEach(draftFill);
    }
  }).observe(document.body, { childList: true, subtree: true });
  (function draftSweep() {  // old drafts, once per start
    try {
      for (let i = localStorage.length - 1; i >= 0; i--) {
        const k = localStorage.key(i);
        if (!k || !k.startsWith(DRAFT_PRE)) continue;
        const d = load(k);
        if (!d || Date.now() - (d.at || 0) > DRAFT_DAYS * 864e5) localStorage.removeItem(k);
      }
    } catch (e) { /* private mode */ }
  })();

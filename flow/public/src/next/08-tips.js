  /* ---------- 使用提示: said the first time, then not again on any phone or computer (the user, 2026-11-25) ---------- */
  // tipSlot(name, text): where a page used to keep an instruction for good (「点词查词…」 on 读), a line with 知道了 the
  // first time. An account keeps what it put away on the server (/api/next/tips, tour_service.TIPS), so another device
  // does not say it again; a guest, this browser. 我的 → 帮助 → 更多 →「重新显示使用提示」 brings them all back.
  // Drawn with the page, never after it: what this account has put away is kept on the phone too (flow-tips-<who>) and
  // fetched once the account is known (boot, sign-in); until the phone knows, the tip waits for the next visit rather
  // than pushing the text down when the answer comes (语流 B8, 2026-11-25: 54 px, 2 s after the page on a slow line).
  const TIPS = {
    seen: null, who: undefined,
    me() { return S.user ? String(S.user.id || S.user.username) : 'guest'; },
    key(who) { return 'flow-tips-' + who; },
    // what is known for this account right now, without waiting: null when the phone does not know yet
    now() {
      const who = this.me();
      if (this.seen && this.who === who) return this.seen;
      const kept = load(this.key(who)) || (who === 'guest' ? load('flow-tips') : null);  // flow-tips: a guest's list before this
      if (Array.isArray(kept)) { this.who = who; this.seen = new Set(kept); return this.seen; }
      return who === 'guest' ? (this.who = who, this.seen = new Set()) : null;
    },
    // once at a time; 'flow-tips' on document when it is known (the 内测版's line and sheet wait for it, 03-channel.js)
    load() {
      if (this.busy) return this.busy;
      const who = this.me();
      this.busy = (async () => {
        if (who !== 'guest') {
          try {
            const seen = new Set((await api('/api/next/tips')).seen || []);
            // what was put away on this browser before signing in counts for the account too
            (load(this.key('guest')) || []).filter(n => !seen.has(n)).forEach(n => { seen.add(n); api('/api/next/tips', { tip: n }).catch(() => {}); });
            if (this.me() === who) { this.who = who; this.seen = seen; save(this.key(who), [...seen]); }
          } catch (e) { /* offline: the phone's copy stands */ }
        }
        this.busy = null;
        try { document.dispatchEvent(new CustomEvent('flow-tips')); } catch (e) { /* very old browsers: nothing waits */ }
        return this.now();
      })();
      return this.busy;
    },
    mark(name) {
      const seen = this.now() || new Set(); if (seen.has(name)) return;
      seen.add(name); this.seen = seen; this.who = this.me(); save(this.key(this.who), [...seen]);
      if (S.user) api('/api/next/tips', { tip: name }).catch(() => {});
    },
    unmark(name) {  // one back on its own (「下次复习时再看一次」)
      const seen = this.now(); if (seen) { seen.delete(name); save(this.key(this.me()), [...seen]); }
      if (S.user) api('/api/next/tips', { tip: name, seen: false }).catch(() => {});
    },
    async reset() {
      const who = this.me(); this.who = who; this.seen = new Set(); save(this.key(who), []); if (who === 'guest') save('flow-tips', null);
      TIP_LOCAL.forEach(k => save(k, null));  // put away on this phone before they were kept on the account
      if (S.user) await api('/api/next/tips', { reset: true });
    },
  };
  // 一次性入口 (the user, 2026-11-26: 「第一次用才需要的按钮，点过一次就不要再出现」): put away on this phone before they were
  // kept with the tips; each still counts, and is copied to the account the first time it is asked about
  const TIP_LOCAL = ['flow-tap-guide', 'flow-tap-guide-back', 'flow-next-swipe-tip', 'flow-know-tip', 'flow-beta-bar'];
  // true: this account (a guest: this browser) has put it away; false: not yet; null: the phone does not know yet, and
  // whatever asks says nothing this time rather than pushing the page about when the answer comes
  function tipSeen(name, local) {
    const seen = TIPS.now();
    if (local && load(local)) { if (seen && !seen.has(name)) TIPS.mark(name); return true; }
    if (!seen) { TIPS.load(); return null; }
    return seen.has(name);
  }
  function tipSlot(name, text) {
    const seen = TIPS.now();
    if (!seen) { TIPS.load(); return ''; }  // not known on this phone yet: next visit, never a jump now
    if (seen.has(name)) return '';
    return `<div class="tip-once" id="tip-${name}" role="note"><span>${esc(text)}</span><button class="link small" type="button" data-tip-ok="${name}">知道了</button></div>`;
  }
  document.addEventListener('click', e => {
    const o = e.target.closest && e.target.closest('[data-tip-seen]'); if (o) TIPS.mark(o.dataset.tipSeen);  // a one-time entry used
    const b = e.target.closest && e.target.closest('[data-tip-ok]'); if (!b) return;
    TIPS.mark(b.dataset.tipOk); const t = b.closest('.tip-once'); if (t) t.remove();
  });

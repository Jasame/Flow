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
    async load() {
      const who = this.me(); if (who === 'guest') return this.now();
      try {
        const seen = new Set((await api('/api/next/tips')).seen || []);
        if (this.me() === who) { this.who = who; this.seen = seen; save(this.key(who), [...seen]); }
      } catch (e) { /* offline: the phone's copy stands */ }
      return this.now();
    },
    mark(name) {
      const seen = this.now() || new Set(); seen.add(name); this.seen = seen; this.who = this.me(); save(this.key(this.who), [...seen]);
      if (S.user) api('/api/next/tips', { tip: name }).catch(() => {});
    },
    async reset() {
      const who = this.me(); this.who = who; this.seen = new Set(); save(this.key(who), []); if (who === 'guest') save('flow-tips', null);
      if (S.user) await api('/api/next/tips', { reset: true });
    },
  };
  function tipSlot(name, text) {
    const seen = TIPS.now();
    if (!seen) { TIPS.load(); return ''; }  // not known on this phone yet: next visit, never a jump now
    if (seen.has(name)) return '';
    return `<div class="tip-once" id="tip-${name}" role="note"><span>${esc(text)}</span><button class="link small" type="button" data-tip-ok="${name}">知道了</button></div>`;
  }
  document.addEventListener('click', e => {
    const b = e.target.closest && e.target.closest('[data-tip-ok]'); if (!b) return;
    TIPS.mark(b.dataset.tipOk); const t = b.closest('.tip-once'); if (t) t.remove();
  });

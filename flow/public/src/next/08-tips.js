  /* ---------- 使用提示: said the first time, then not again on any phone or computer (the user, 2026-11-25) ---------- */
  // tipSlot(name, text): where a page used to keep an instruction for good (「点词查词…」 on 读), a line with 知道了 the
  // first time. An account keeps what it put away on the server (/api/next/tips, tour_service.TIPS), so another device
  // does not say it again; a guest, this browser. 我的 → 帮助 → 更多 →「重新显示使用提示」 brings them all back.
  const TIPS = {
    seen: null, who: undefined,
    async load() {
      const who = S.user ? S.user.id || S.user.username : null;
      if (this.seen && this.who === who) return this.seen;
      this.who = who; this.seen = new Set(who ? [] : load('flow-tips') || []);
      if (who) { try { this.seen = new Set((await api('/api/next/tips')).seen || []); } catch (e) { /* offline: shown once more, no harm */ } }
      return this.seen;
    },
    mark(name) {
      if (!this.seen) this.seen = new Set(); this.seen.add(name);
      if (S.user) api('/api/next/tips', { tip: name }).catch(() => {}); else save('flow-tips', [...this.seen]);
    },
    async reset() { this.seen = new Set(); save('flow-tips', null); if (S.user) await api('/api/next/tips', { reset: true }); },
  };
  function tipSlot(name, text) {
    const id = 'tip-' + name;
    TIPS.load().then(seen => {
      const el = document.getElementById(id); if (!el || seen.has(name)) return;
      el.innerHTML = `<span>${esc(text)}</span><button class="link small" type="button">知道了</button>`; el.hidden = false;
      el.querySelector('button').onclick = () => { TIPS.mark(name); el.remove(); };
    });
    return `<div class="tip-once" id="${id}" role="note" hidden></div>`;
  }

  /* ---------- 主题色 (我的 → 使用习惯): 松绿 (配色 A, the default) or 靛蓝; only the accent changes (99-accent.css) ---------- */
  // Signed in, it is kept with the account (/api/next/accent → profile.accent) and follows to another device; before
  // signing in, on this device. The device also keeps the last one, so the first screen is already drawn in it.
  // Right / wrong, the logo and the AI marks do not change with it (--ok, --red, --brand in 00-base.css).
  const ACCENTS = [['green', '松绿'], ['indigo', '靛蓝']];
  function applyAccent(a) {
    a = ACCENTS.some(x => x[0] === a) ? a : 'green';
    if (a === 'green') document.documentElement.removeAttribute('data-accent'); else document.documentElement.dataset.accent = a;
    save('flow-accent', a === 'green' ? null : a);
    return a;
  }
  applyAccent(load('flow-accent'));
  // The account's choice when the home data comes (refreshHome, 02-shell.js). One made on this device before signing in
  // goes to the account first, once, so signing in does not undo it.
  function accentFromAccount(p) {
    const g = load('flow-accent-guest');
    if (g) {
      save('flow-accent-guest', null);
      if (g !== (p.accent || 'green')) { p.accent = g; api('/api/next/accent', { accent: g }).catch(() => { /* the device keeps it */ }); }
    }
    applyAccent(p.accent);
  }
  const accentNow = () => document.documentElement.dataset.accent || 'green';
  const accentLabel = () => ACCENTS.find(x => x[0] === accentNow())[1];
  async function setAccent(a) {
    const was = accentNow(); applyAccent(a);
    if (!S.user) { save('flow-accent-guest', a); return; }  // chosen before signing in: given to the account once (below)
    try { await api('/api/next/accent', { accent: a }); if (S.home && S.home.profile) S.home.profile.accent = a; }
    catch (e) { applyAccent(was); toast(e.message); }
  }

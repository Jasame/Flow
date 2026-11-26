  /* ---------- 使用习惯 kept with the account (我的 → 使用习惯, the user and B9, 2026-11-26) ---------- */
  // The pages read this device's copy (KNOW in 50-words.js, TEXT in 02-shell.js), so they draw at once and offline.
  // Signed in, each choice is also kept with the account (/api/next/prefs → profile.prefs, next_service.PREFS), and
  // another phone or computer takes it from there. 主题色 is kept the same way by 07-accent.js; 今日的样子 by 10-*.js.
  const PREF_IO = {
    // the value on this device, or null when nothing was chosen here (the page's default); put(v) writes it here only
    know: { get: () => { try { return localStorage.getItem('flow-know-side') === 'left' ? 'left' : null; } catch (e) { return null; } },
            put: v => { try { if (v === 'left') localStorage.setItem('flow-know-side', 'left'); else localStorage.removeItem('flow-know-side'); } catch (e) { /* private mode */ } } },
    card_new: { get: () => { try { return localStorage.getItem('flow-card-view-new'); } catch (e) { return null; } },
                put: v => { try { localStorage.setItem('flow-card-view-new', v); } catch (e) { /* private mode */ } } },
    card_review: { get: () => { try { return localStorage.getItem('flow-card-view-review'); } catch (e) { return null; } },
                   put: v => { try { localStorage.setItem('flow-card-view-review', v); } catch (e) { /* private mode */ } } },
    tap: { get: () => { try { const v = localStorage.getItem('flow-tap-zones'); return v ? (v === '1' ? 'on' : 'off') : null; } catch (e) { return null; } },
           put: v => { try { localStorage.setItem('flow-tap-zones', v === 'on' ? '1' : '0'); } catch (e) { /* private mode */ } } },
    size: { get: () => (load('flow-next-text') || {}).size || null, put: v => { TEXT.size = v; save('flow-next-text', TEXT); } },
    lh: { get: () => (load('flow-next-text') || {}).lh || null, put: v => { TEXT.lh = v; save('flow-next-text', TEXT); } },
  };
  // one choice made on this device: kept with the account too (a guest: here only, handed over after signing in)
  function prefSave(key, value) {
    if (S.user && S.home && S.home.profile) {
      S.home.profile.prefs = Object.assign({}, S.home.profile.prefs, { [key]: value });
      api('/api/next/prefs', { [key]: value }).catch(() => { /* this device keeps it; the next sign-in hands it over */ });
    }
  }
  // signed in (02-shell.js, with the profile): what the account keeps comes to this device; what was chosen here and the
  // account does not have yet (before signing in, or before 2026-11-26 when these were kept on the device only) goes to it
  function prefsFromAccount(p) {
    const kept = p.prefs || {}, mine = {};
    Object.keys(PREF_IO).forEach(k => {
      const io = PREF_IO[k], here = io.get();
      if (kept[k] != null) { if (here !== kept[k]) io.put(kept[k]); }
      else if (here != null) mine[k] = here;
    });
    if (Object.keys(mine).length) { p.prefs = Object.assign({}, kept, mine); api('/api/next/prefs', mine).catch(() => {}); }
    applyText();
  }

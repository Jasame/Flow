  /* ---------- 存到手机: materials kept on the phone, to study without a connection ---------- */
  // Today's article and the next two are kept by themselves (when the phone is idle; not with Save-Data or on 2G), any
  // other with 「存到手机」 on its page; ten at most, per account. A kept material has its text, its questions with the
  // answers (graded on the phone without a connection) and its narration (kept by the service worker). What is done
  // offline (steps, answers) waits in the outbox and is sent when the phone is back online, so progress and the
  // mistake book are recorded as usual.
  const OFF = {
    key: 'flow-offline', max: 10,
    all() { const s = load(this.key); return s && s.v === 1 && s.owner === snapOwner() ? s : { v: 1, owner: snapOwner(), mats: {} }; },
    get(id) { const s = this.all(); return s.mats[id] ? s.mats[id].m : null; },
    has(id) { return !!this.all().mats[id]; },
    count() { return Object.keys(this.all().mats).length; },
    list() { const s = this.all(); return Object.keys(s.mats).map(id => s.mats[id].m).filter(Boolean); },
    put(id, m) {
      const s = this.all(); s.mats[id] = { at: Date.now(), m };
      Object.keys(s.mats).sort((a, b) => s.mats[b].at - s.mats[a].at).slice(this.max).forEach(k => delete s.mats[k]);
      try { save(this.key, s); } catch (e) { /* full: the oldest stays out */ }
    },
    clear() { save(this.key, null); },
  };
  async function keepOffline(id, quiet) {
    try {
      const m = await dataGet(materialPath(id) + '&offline=1', quiet);
      OFF.put(id, m);
      if (MAT[id] && !MAT[id].answers) MAT[id].answers = m.answers;  // the page open now can grade offline too
      const vs = (m.audio && m.audio.voices) || [], sw = navigator.serviceWorker && navigator.serviceWorker.controller;
      if (vs.length && sw) {  // the narration and its timings, kept by the service worker like any audio it has served
        const base = `/audio/${vs.includes(S.voice) ? S.voice : vs[0]}/${encodeURIComponent(id)}`;
        sw.postMessage({ type: 'prefetch', urls: [`${base}.json?v=${m.audio.version}`, `${base}.mp4?v=${m.audio.version}`] });
      }
      return true;
    } catch (e) { if (!quiet) toast(e.network ? '现在没网，存不了' : e.message); return false; }
  }
  function keepTodayOffline() {
    if (PRELOAD.frugal() || !S.home) return;
    const h = S.home, ids = [], read = h.path && h.path.steps && h.path.steps.find(s => s.key === 'read');
    if (read) ids.push(decodeURIComponent(read.href.split('/')[2] || ''));
    (h.today || []).forEach(m => ids.push(m.id));
    idle(() => [...new Set(ids)].filter(Boolean).slice(0, 3).forEach(id => { if (!OFF.has(id)) keepOffline(id, true); }));
  }
  // On a material's page: 存到手机, or that it is kept.
  function offChip(id) {
    // a phone with a down arrow in front: set apart from 怎么写的 on the source line, on the same line or the next
    const icon = '<svg class="offi" viewBox="0 0 24 24" aria-hidden="true"><rect x="6" y="2.5" width="12" height="19" rx="2.5"/><path d="M12 7.5v7m-3-3 3 3 3-3"/></svg>';
    return OFF.has(id) ? '<span class="offk on" id="keepOff">✓ 已存到手机，没网也能学</span>' : `<button class="link small offk" id="keepOff" type="button" data-tap="study-keep">${icon}存到手机，没网也能学</button>`;
  }
  function bindOffChip(id) {
    const b = document.getElementById('keepOff'); if (!b || b.tagName !== 'BUTTON') return;
    b.onclick = async () => { b.disabled = true; b.textContent = '正在存…'; const ok = await keepOffline(id); b.outerHTML = offChip(id); if (!ok) bindOffChip(id); };
  }
  // Losing and finding the connection: said once each way; what waited is sent.
  addEventListener('offline', () => { const n = OFF.count(); toast(n ? `现在没网：已存到手机的 ${n} 篇还能学` : '现在没网：复习单词还能做，联网后自动同步'); });
  addEventListener('online', () => { OUTBOX.flush(); });  // it says how much was synced

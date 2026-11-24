  /* ---------- 年龄段和监护人同意 (privacy_service.py): a band, never a birthday; under 14, a guardian's agreement ---------- */
  const AGE_BANDS = [['u14', '不满 14 岁'], ['14-17', '14–17 岁'], ['18+', '18 岁及以上']];
  const GUARD_WHY = '你写的作文和说的录音会交给 AI 批改，所以需要家长知道。';
  const PRIVACY = '/#/guide/privacy';
  function ageLabel(a) { const x = AGE_BANDS.find(b => b[0] === a); return x ? x[1] : '没填'; }
  // The three bands as chips (radio buttons) and, for 不满 14 岁 without an agreement on record, the box to tick.
  function ageFields(cur, onRecord) {
    return `<fieldset class="agefs"><legend>年龄段<span class="hint">只用来保护未成年人的信息，不问生日。</span></legend>
      <div class="chips" role="radiogroup" aria-label="年龄段">${AGE_BANDS.map(([k, l]) => `<label class="chip agechip"><input type="radio" name="age" value="${k}"${cur === k ? ' checked' : ''}><span>${l}</span></label>`).join('')}</div>
      <div class="guard" ${cur === 'u14' && !onRecord ? '' : 'hidden'}><label class="checkline"><input type="checkbox" name="guardian"><span>我已经告诉家长（或监护人），他们同意我用语流</span></label>
        <span class="hint">${GUARD_WHY}<a class="link" href="${PRIVACY}" target="_blank" rel="noopener">看隐私说明</a></span></div></fieldset>`;
  }
  function bindAge(root, onRecord) {
    const g = root.querySelector('.guard'), radios = root.querySelectorAll('input[name=age]');
    const show = () => radios.forEach(x => x.parentNode.dataset.on = String(x.checked));  // the chips' look (no :has)
    radios.forEach(r => { r.onchange = () => { if (r.checked) g.hidden = !(r.value === 'u14' && !onRecord); show(); }; });
    show();
  }
  function readAge(root) {
    const r = root.querySelector('input[name=age]:checked'), g = root.querySelector('input[name=guardian]');
    return { age: r ? r.value : '', guardian: !!(g && g.checked) };
  }
  // The same check the server makes, said at once: '' when fine. need: under 14, the tick is required here.
  function ageProblem(a, need, onRecord) {
    if (!a.age) return '请选一个年龄段';
    if (need && a.age === 'u14' && !a.guardian && !onRecord) return '不满 14 岁需要先告诉家长（或监护人）并得到同意，勾选后才能继续';
    return '';
  }
  // An account without a band (made before 2026-11-24, or by an older page) is asked once, the next time it opens the
  // site; the sheet stays until a band is chosen. locked: no 关闭, the scrim, Esc and a swipe down do nothing.
  let ageAsked = false;
  function askAgeOnce() {
    if (!S.user || S.user.age || ageAsked || !sheetEl.hidden) return;
    ageAsked = true; ageSheet(true);
  }
  function ageSheet(locked) {
    const u = S.user; if (!u) return;
    openSheet(`<div class="stack"${locked ? ' data-lock' : ''}><h2 class="h2" id="sheetTitle">${locked ? '补充一个问题：你现在多大？' : '年龄段'}</h2>
      <form id="ageF" class="stack" novalidate>${ageFields(u.age, u.guardian)}
        <p class="small muted">不满 14 岁、还没告诉家长的，可以先选；学材料、背单词、做题都照常，要交给 AI 批改的作文和录音等家长同意以后再用。</p>
        <button class="btn primary" type="submit">好了</button></form>
      <p class="err" id="ageErr" role="alert"></p>${locked ? '' : '<button class="btn ghost" data-close type="button">取消</button>'}</div>`, card => {
      const form = card.querySelector('#ageF'), err = card.querySelector('#ageErr');
      bindAge(card, u.guardian);
      form.onsubmit = async e => {
        e.preventDefault(); err.textContent = '';
        const a = readAge(form), p = ageProblem(a, false, u.guardian);
        if (p) { err.textContent = p; const r = form.querySelector('input[name=age]'); if (r) r.focus(); return; }
        try { Object.assign(S.user, await api('/api/account/age', a)); closeSheet(); toast(S.user.age === 'u14' && !S.user.guardian ? '好了。家长同意以后，在「我的 → 年龄段」里勾选' : '好了，谢谢'); const v = document.getElementById('meAgeV'); if (v) v.textContent = ageLabel(S.user.age); }
        catch (x) { err.textContent = x.message; }
      };
    });
  }
  // A feature that hands the learner's own words or voice to AI answered 403 code 'guardian' (privacy_service.gate).
  function guardianSheet() {
    openSheet(`<div class="stack"><h2 class="h2" id="sheetTitle">先告诉家长</h2>
      <p class="small">这一步会把你写的或说的交给 AI 处理。不满 14 岁，需要先告诉家长（或监护人），得到同意以后再用。学材料、背单词、做题不受影响。</p>
      <form id="guardF" class="stack" novalidate><label class="checkline"><input type="checkbox" name="guardian"><span>我已经告诉家长（或监护人），他们同意我用语流</span></label>
        <a class="link small" href="${PRIVACY}" target="_blank" rel="noopener">看隐私说明：数据存在哪里、交给哪家 AI</a>
        <button class="btn primary" type="submit">继续</button></form>
      <p class="err" id="guardErr" role="alert"></p><button class="btn ghost" data-close type="button">先不用</button></div>`, card => {
      const form = card.querySelector('#guardF'), err = card.querySelector('#guardErr');
      form.onsubmit = async e => {
        e.preventDefault(); err.textContent = '';
        if (!form.guardian.checked) { err.textContent = '勾选以后才能继续'; form.guardian.focus(); return; }
        try { Object.assign(S.user, await api('/api/account/age', { age: 'u14', guardian: true })); closeSheet(); toast('好了，再点一次刚才的按钮'); }
        catch (x) { err.textContent = x.message; }
      };
    });
  }

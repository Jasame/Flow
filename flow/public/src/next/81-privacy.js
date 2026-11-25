  /* ---------- 年龄段和监护人同意 (privacy_service.py): a band, never a birthday; under 14, a guardian's agreement ---------- */
  const AGE_BANDS = [['u14', '不满 14 岁'], ['14-17', '14–17 岁'], ['18+', '18 岁及以上']];
  const GUARD_WHY = '你的账号和学习数据存放在香港的服务器上，你写的作文和说的录音会交给 AI 批改（录音不保存），所以需要家长知道。';
  const PRIVACY = '/#/guide/privacy';
  function ageLabel(a) { const x = AGE_BANDS.find(b => b[0] === a); return x ? x[1] : '没填'; }
  // The three bands as chips (radio buttons) and, for 不满 14 岁 without an agreement on record, the box to tick.
  function ageFields(cur, onRecord) {
    return `<fieldset class="agefs"><legend>年龄段<span class="hint">只用来保护未成年人的信息，不问生日。</span></legend>
      <div class="chips" role="radiogroup" aria-label="年龄段">${AGE_BANDS.map(([k, l]) => `<label class="chip agechip"><input type="radio" name="age" value="${k}"${cur === k ? ' checked' : ''}><span>${l}</span></label>`).join('')}</div>
      <div class="guard" ${cur === 'u14' && !onRecord ? '' : 'hidden'}><label class="checkline"><input type="checkbox" name="guardian"><span>我已经告诉家长（或监护人），他们同意我用语流，也同意我的账号和学习数据存放在香港的服务器上</span></label>
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
    if (!S.user || S.user.age || ageAsked || !sheetEl.hidden || S.user.storage !== 'ok' || S.user.terms !== 'ok') return;  // the consents first (storageView)
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
      <form id="guardF" class="stack" novalidate><label class="checkline"><input type="checkbox" name="guardian"><span>我已经告诉家长（或监护人），他们同意我用语流，也同意我的账号和学习数据存放在香港的服务器上</span></label>
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

  /* ---------- 数据存放在香港的单独同意 (privacy_service.py, 2026-11-25): its own tick at sign-up; an older account is asked
     once on a page of its own; 不同意 or 撤回 pauses the account (only agree again, export, delete, sign out) ---------- */
  // The wording is privacy_service.STORAGE_VERSION: change it, change that version too (语流 23 reviewed this one).
  const STORAGE_TEXT = '我同意语流在香港的服务器上存放和处理我的账号和学习数据';
  const STORAGE_WHY = '语流的网站和数据库都在香港的服务器上运行。你的账号、学习记录、写的作文和练习的文字、问题反馈都存在那里。你说的录音不保存，但批改时会经过香港的服务器转给 AI。这些数据由语流的运营者处理，只用来给你提供学习服务。香港在中国内地以外，所以单独问你。';
  const STORAGE_RIGHTS = '你可以随时在「我的 → 账号」里导出数据、注销账号或撤回同意；有问题请用「我的 → 问题反馈」，或写信到 i@jasa.hk。';
  // A tick is ticked by its box or its words, at once; only a document's name opens it (docOver, over the page: the form
  // underneath keeps what was typed and ticked). The box takes a 44px tap (.tickbox); the names are not .link, so 99-tap.css
  // puts no wider tap area of theirs over the box (the user, 2026-11-25: 「一般都是直接勾选」).
  const tickbox = name => `<span class="tickbox"><input type="checkbox" name="${name}"></span>`;
  const docLink = (href, id, text) => `<a class="doc-link" href="${href}" data-doc="${id}">${text}</a>`;
  function storageField() {
    return `<div class="storagefs"><label class="checkline">${tickbox('storage')}<span>${STORAGE_TEXT}</span></label>
      <span class="hint">${STORAGE_WHY}不满 14 岁的，要家长（或监护人）也同意。${STORAGE_RIGHTS}${docLink(PRIVACY, 'privacy', '看隐私说明')}</span></div>`;
  }
  async function storageAnswer(agree) {
    const r = await api('/api/account/storage', { agree });
    Object.assign(S.user, r); S.homeFresh = false; await refreshHome();
  }
  // #/ and every page but the guide, while the account has not agreed: one short page (asked) or the paused page.
  // The 用户协议 and 隐私和数据 tick (privacy_service.TERMS_TEXT): at sign-up next to the storage one, never merged with it;
  // both names open the full text.
  const TERMS = '/#/guide/terms';
  function termsField() {
    return `<div class="storagefs"><label class="checkline">${tickbox('terms')}<span>我已阅读并同意${docLink(TERMS, 'terms', '《用户协议》')}和${docLink(PRIVACY, 'privacy', '《隐私和数据》')}</span></label></div>`;
  }
  // a document's full text over the page (the guide's chapter), 返回 to the form as it was; its links to other chapters stay
  // in this layer, so nothing typed is lost (in the apps too, where a new tab would leave the page)
  const DOC_NAME = { terms: '语流用户协议', privacy: '隐私和数据' };
  function docOver(id) {
    const back = document.activeElement, el = document.createElement('div');
    el.className = 'doc-over'; el.setAttribute('role', 'dialog'); el.setAttribute('aria-modal', 'true');
    const frame = (title, body) => {
      el.setAttribute('aria-label', title);
      el.innerHTML = `<div class="doc-bar"><button class="btn small" type="button" data-doc-close>← 返回</button><b>${esc(title)}</b></div>
        <div class="guide-body doc-body">${body}</div><div class="doc-foot"><button class="btn primary block" type="button" data-doc-close>返回</button></div>`;
      el.scrollTop = 0;
    };
    // just this chapter (/api/next/guide?chapter=, open before any agreement too), kept for the page's life; shown at
    // once as 「正在打开」, and a failure says so with 再试一次, never a page that keeps retrying
    const show = async cid => {
      const name = DOC_NAME[cid] || '操作指南';
      S.docs = S.docs || {};
      if (!S.docs[cid]) frame(name, '<p class="muted">正在打开…</p>');
      try {
        const ch = S.docs[cid] || (S.docs[cid] = (await api('/api/next/guide?chapter=' + encodeURIComponent(cid))).chapter);
        if (el.isConnected) frame(ch.title, ch.html);
        const at = ch.anchor && el.querySelector('#g-' + CSS.escape(ch.anchor)); if (at) at.scrollIntoView({ block: 'start' });
      } catch (x) {
        frame(name, `<p>暂时打不开。请检查网络后再试一次；也可以稍后在「操作指南」里看《语流用户协议》和《隐私和数据》两章。</p><button class="btn" type="button" data-doc-retry="${esc(cid)}">再试一次</button>`);
      }
      const f = el.querySelector('[data-doc-close]'); if (f) f.focus();
    };
    const close = () => { el.remove(); document.removeEventListener('keydown', key, true); if (back && back.focus) back.focus(); };
    // over the sign-up sheet: Esc closes this layer only, and Tab stays here (the sheet would pull focus back into itself)
    const key = e => { if (e.key === 'Escape') { e.stopImmediatePropagation(); e.preventDefault(); close(); } else if (e.key === 'Tab') e.stopImmediatePropagation(); };
    el.onclick = e => {
      if (e.target.closest('[data-doc-close]')) return close();
      const again = e.target.closest('[data-doc-retry]'); if (again) return show(again.dataset.docRetry);
      const a = e.target.closest('a[href]'); if (!a) return;
      const h = a.getAttribute('href'), m = h.match(/^\/?#\/guide\/([\w-]+)/);
      if (m) { e.preventDefault(); show(m[1]); } else if (h.startsWith('#') || h.startsWith('/#')) e.preventDefault(); else { a.target = '_blank'; a.rel = 'noopener'; }
    };
    document.addEventListener('keydown', key, true);
    document.body.appendChild(el); show(id);
  }
  document.addEventListener('click', e => {
    const a = e.target.closest && e.target.closest('a[data-doc]');
    if (a) { e.preventDefault(); docOver(a.dataset.doc); }
  });
  // #/ and every page but the guide, while an answer is missing: the storage in Hong Kong (asked, or paused) and/or the
  // current 用户协议 and 隐私和数据 (never agreed, or a new version since). One page, one button.
  async function storageView() {
    const paused = S.user.storage === 'no', needStorage = S.user.storage !== 'ok', needTerms = S.user.terms !== 'ok';
    const termsOnly = needTerms && !needStorage;
    view.innerHTML = `<div class="stack storage-page"><div><span class="kicker">${termsOnly ? '用户协议和隐私说明' : '数据存放'}</span><h1 class="h1">${paused ? '这个账号已暂停' : '补一个同意'}</h1></div>
      ${paused ? `<div class="card flat stack-s"><p>你没有同意（或者撤回了同意）在香港的服务器上存放和处理你的数据，所以语流暂停了这个账号的学习：不会再给你发邮件，班级的数字里也不算你。</p>
        <p>你的数据还在，没有删除。30 天内重新同意，就能接着学${S.user.storage_until ? `（${esc(S.user.storage_until)} 以前）` : ''}；30 天后还没有重新同意，语流会删除这个账号和数据，备份里的副本 14 天内清除。</p></div>` : ''}
      <form class="card flat stack-s" id="stoF" novalidate>${paused ? '<b>想继续用这个账号</b>' : termsOnly ? '<p>我们更新了《用户协议》和《隐私和数据》，勾选同意后继续。</p>' : `<p>${STORAGE_WHY}</p>`}${needTerms ? termsField() : ''}${needStorage ? storageField() : ''}
        <button class="btn primary" type="submit">${paused ? '同意，继续学习' : termsOnly ? '继续' : '同意并继续'}</button><p class="err" id="stoErr" role="alert"></p></form>
      ${termsOnly ? `<p class="tiny muted sto-quiet">不想同意：<a class="doc-link" href="/api/next/export/records.json" download>导出我的数据</a> · <button class="doc-link" id="stoDel" type="button">注销账号</button> · <button class="doc-link" id="stoOut" type="button">退出登录</button></p>`
        : `<div class="card flat stack-s">${paused ? '<b>不想继续</b>' : '<b>不同意存放在香港的话</b><p class="small muted">这个账号会暂停，不能学习。30 天内可以回来同意或导出数据；30 天后，语流会删除这个账号和数据。</p>'}
        <div class="row wrap">${paused ? '' : '<button class="btn" id="stoNo" type="button">不同意</button>'}<a class="btn ghost" href="/api/next/export/records.json" download>导出我的数据</a>
          <button class="btn ghost" id="stoDel" type="button">注销账号</button><button class="btn ghost" id="stoOut" type="button">退出登录</button></div>
        <p class="tiny muted">退出登录后，也可以不登录先看看语流：那时的进度只存在这台设备上。</p></div>`}</div>`;
    const f = document.getElementById('stoF'), err = document.getElementById('stoErr');
    f.onsubmit = async e => {
      e.preventDefault(); err.textContent = '';
      if (needTerms && !f.terms.checked) return fieldError(f, err, { message: '请先勾选同意《用户协议》和《隐私和数据》', field: 'terms' });
      if (needStorage && !f.storage.checked) return fieldError(f, err, { message: '勾选同意以后才能继续', field: 'storage' });
      const b = f.querySelector('[type=submit]'); b.disabled = true;
      try {
        if (needTerms) Object.assign(S.user, await api('/api/account/terms', { agree: true }));
        if (needStorage) await storageAnswer(true); else { S.homeFresh = false; await refreshHome(); }
        toast('好了，谢谢'); route();
      } catch (x) { err.textContent = x.message; b.disabled = false; }
    };
    const no = document.getElementById('stoNo');
    if (no) no.onclick = async () => { no.disabled = true; try { await storageAnswer(false); route(); } catch (x) { err.textContent = x.message; no.disabled = false; } };
    document.getElementById('stoDel').onclick = deleteAccountSheet;
    document.getElementById('stoOut').onclick = async () => { try { await api('/api/logout', {}); } catch (x) { /* signed out already */ } snapClear(); S.user = null; S.csrf = ''; await refreshHome(); route(); };
  }
  // 我的 → 设置 → 按我的学习记录推荐 (next_service.personal; 个保法第二十四条, 算法推荐规定第十七条: an option not aimed
  // at the person, that really switches it off). On by default; off, 今日 recommends by the chosen level only.
  const personalizeLabel = () => (S.home && S.home.profile && S.home.profile.personalize === false ? '已关闭' : '已打开');
  function personalizeSheet() {
    const p = (S.home && S.home.profile) || {}, on = p.personalize !== false;
    openSheet(`<div class="stack"><h2 class="h2" id="sheetTitle">按我的学习记录推荐</h2>
      <p class="small">打开时，语流按你的学习记录给你挑内容：今日的「今天这篇」和「也可以读」（看你学过哪些、哪些语法要补、收藏和在背的词）、今日好句、今日计划里练哪一项，以及级别建议和周报里的建议。</p>
      <p class="small">关掉以后，只按你自己选的水平推荐：精选的在前，新的在前，不再看你的学习记录。复习单词、复听和「接着学」还是按你学过的安排，那是在复习你自己的内容。</p>
      <div class="chips" role="radiogroup" aria-label="按我的学习记录推荐">${[[true, '打开'], [false, '关闭']].map(([v, l]) => `<button class="chip" type="button" role="radio" data-pers="${v}" aria-checked="${on === v}">${l}</button>`).join('')}</div>
      <a class="link small" href="#/guide/personalize" data-doc="personalize">用到了哪些记录（隐私说明）</a>
      <button class="btn ghost" data-close type="button">完成</button></div>`, card => {
      card.querySelectorAll('[data-pers]').forEach(b => b.onclick = async () => {
        try {
          const r = await api('/api/next/personalize', { on: b.dataset.pers === 'true' });
          if (S.home && S.home.profile) S.home.profile.personalize = r.personalize;
          S.homeFresh = false;  // 今日 is asked again, ranked the new way
          card.querySelectorAll('[data-pers]').forEach(x => x.setAttribute('aria-checked', String(x === b)));
          const v = document.getElementById('mePersV'); if (v) v.textContent = personalizeLabel();
          toast(r.personalize ? '已打开：按你的学习记录推荐' : '已关闭：只按你选的水平推荐');
        } catch (e) { toast(e.message); }
      });
    });
  }
  // 我的 → 账号 → 数据存放: what was agreed, and 撤回同意 (the account is paused at once).
  function storageSheet() {
    openSheet(`<div class="stack"><h2 class="h2" id="sheetTitle">数据存放</h2>
      <p class="small">你已经同意语流在香港的服务器上存放和处理你的账号和学习数据。${STORAGE_WHY}</p>
      <a class="link small" href="${PRIVACY}" target="_blank" rel="noopener">看隐私说明：存了什么、存多久、怎么删</a>
      <div id="stoW" class="stack-s"><button class="btn" id="stoWithdraw" type="button">撤回同意</button></div>
      <p class="err" id="stoErr" role="alert"></p><button class="btn ghost" data-close type="button">完成</button></div>`, card => {
      const box = card.querySelector('#stoW'), err = card.querySelector('#stoErr');
      card.querySelector('#stoWithdraw').onclick = () => {
        box.innerHTML = `<p class="small">撤回以后，这个账号马上暂停：不能学习，不再收邮件，班级的数字里也不算你。30 天内可以重新同意或导出数据；30 天后，语流会删除这个账号和数据。</p>
          <div class="row"><button class="btn danger-btn" id="stoYes" type="button">确定撤回</button><button class="btn ghost" id="stoKeep" type="button">不撤回</button></div>`;
        box.querySelector('#stoKeep').onclick = closeSheet;
        box.querySelector('#stoYes').onclick = async e => {
          e.target.disabled = true;
          try { await storageAnswer(false); closeSheet(); route(); } catch (x) { err.textContent = x.message; e.target.disabled = false; }
        };
      };
    });
  }

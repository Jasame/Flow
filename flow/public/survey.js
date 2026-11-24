'use strict';
// Anonymous learner survey. No login, no cookies; a draft is kept only in this tab's storage.
(function () {
  const root = document.getElementById('survey');
  let started = Date.now();
  let def = null;
  let answers = {};
  const DRAFT = 'flow-survey-draft';

  const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const all = () => def.sections.flatMap(s => s.questions);
  const store = {
    load() { try { return JSON.parse(sessionStorage.getItem(DRAFT) || '{}'); } catch (e) { return {}; } },
    save() { try { sessionStorage.setItem(DRAFT + ':id', def.id); sessionStorage.setItem(DRAFT + ':start', String(started)); sessionStorage.setItem(DRAFT, JSON.stringify(answers)); } catch (e) { /* private mode */ } },
    start() { try { return Number(sessionStorage.getItem(DRAFT + ':start')) || 0; } catch (e) { return 0; } },
    clear() { try { sessionStorage.removeItem(DRAFT); sessionStorage.removeItem(DRAFT + ':start'); } catch (e) { /* ignore */ } },
    sameSurvey() { try { return sessionStorage.getItem(DRAFT + ':id') === def.id; } catch (e) { return false; } },
  };

  function done(q) {
    const v = answers[q.id];
    if (q.type === 'matrix') return v && Object.keys(v).length === q.rows.length;
    if (q.type === 'multi') return Array.isArray(v) && v.length > 0;
    return v != null && String(v).trim() !== '';
  }

  function progress() {
    const req = all().filter(q => q.required);
    const n = req.filter(done).length;
    root.querySelector('.sv-bar i').style.width = Math.round(100 * n / req.length) + '%';
    root.querySelector('.sv-progress small').textContent = `必答题已完成 ${n} / ${req.length}`;
  }

  function optionHTML(q, o, i) {
    const type = q.type === 'single' ? 'radio' : 'checkbox';
    const v = answers[q.id];
    const checked = q.type === 'single' ? v === o : Array.isArray(v) && v.includes(o);
    return `<label class="sv-opt"><input type="${type}" name="${esc(q.id)}" value="${esc(o)}" data-i="${i}" ${checked ? 'checked' : ''}><span>${esc(o)}</span></label>`;
  }

  function questionHTML(q) {
    const req = q.required ? '<span class="sv-req" aria-hidden="true">*</span>' : '';
    const hint = q.type === 'multi' && q.max ? ` <span class="sv-hint">（最多 ${q.max} 项）</span>` : '';
    if (q.type === 'text') {
      const v = answers[q.id] || '';
      return `<div class="sv-q" data-q="${esc(q.id)}"><label class="sv-label" for="q-${esc(q.id)}">${esc(q.label)}${req}</label>
        <textarea id="q-${esc(q.id)}" name="${esc(q.id)}" maxlength="1000" placeholder="${esc(q.placeholder || '')}">${esc(v)}</textarea>
        <div class="sv-count">${v.length} / 1000</div></div>`;
    }
    if (q.type === 'matrix') {
      const v = answers[q.id] || {};
      const rows = q.rows.map((r, ri) => `<div class="sv-row"><span class="sv-row-label" id="r-${esc(q.id)}-${ri}">${esc(r)}</span>
        <div><div class="sv-scale" role="radiogroup" aria-labelledby="r-${esc(q.id)}-${ri}">${[1, 2, 3, 4, 5].map(n =>
          `<label><input type="radio" name="${esc(q.id)}-${ri}" value="${n}" data-row="${esc(r)}" aria-label="${n} 分" ${v[r] === n ? 'checked' : ''}><span>${n}</span></label>`).join('')}</div>
        <div class="sv-ends"><span>不需要</span><span>非常需要</span></div></div></div>`).join('');
      return `<div class="sv-q" data-q="${esc(q.id)}"><fieldset><legend>${esc(q.label)}${req}</legend><div class="sv-matrix">${rows}</div></fieldset></div>`;
    }
    const two = q.options.length > 5 ? ' two' : '';
    return `<div class="sv-q" data-q="${esc(q.id)}"><fieldset><legend>${esc(q.label)}${req}${hint}</legend>
      <div class="sv-opts${two}">${q.options.map((o, i) => optionHTML(q, o, i)).join('')}</div></fieldset></div>`;
  }

  function enforceMax(q) {
    if (q.type !== 'multi' || !q.max) return;
    const box = root.querySelector(`[data-q="${CSS.escape(q.id)}"]`);
    const full = (answers[q.id] || []).length >= q.max;
    box.querySelectorAll('input').forEach(i => { i.disabled = full && !i.checked; });
  }

  function render() {
    root.innerHTML = `<section class="sv-hero"><h1>${esc(def.title)}</h1><p>${esc(def.intro)}</p></section>
      <div class="sv-progress"><div class="sv-bar"><i></i></div><small></small></div>
      <form id="sv-form" novalidate>
        ${def.sections.map(s => `<section class="sv-section"><h2>${esc(s.title)}</h2>${s.questions.map(questionHTML).join('')}</section>`).join('')}
        <div class="sv-trap" aria-hidden="true"><label>网站<input name="website" tabindex="-1" autocomplete="off"></label></div>
        <div class="sv-actions"><p class="sv-error" id="sv-error" role="alert"></p>
          <button class="sv-btn" type="submit">提交问卷</button>
          <p class="sv-privacy">提交内容不包含你的账号、姓名、邮箱、手机号或 IP 地址。为防止刷票，服务器只临时保存一个无法还原的校验值，两天后自动删除。</p></div>
      </form>`;
    all().forEach(enforceMax);
    progress();
  }

  function onChange(e) {
    const t = e.target;
    const box = t.closest('[data-q]');
    if (!box) return;
    const q = all().find(x => x.id === box.dataset.q);
    if (q.type === 'single') answers[q.id] = t.value;
    else if (q.type === 'multi') answers[q.id] = [...box.querySelectorAll('input:checked')].map(i => i.value);
    else if (q.type === 'matrix') { answers[q.id] = Object.assign({}, answers[q.id], { [t.dataset.row]: Number(t.value) }); }
    else if (q.type === 'text') { answers[q.id] = t.value; box.querySelector('.sv-count').textContent = `${t.value.length} / 1000`; }
    box.classList.remove('missing');
    enforceMax(q);
    store.save();
    progress();
  }

  async function submit(e) {
    e.preventDefault();
    const err = document.getElementById('sv-error');
    const missing = all().filter(q => q.required && !done(q));
    root.querySelectorAll('.sv-q.missing').forEach(x => x.classList.remove('missing'));
    if (missing.length) {
      missing.forEach(q => root.querySelector(`[data-q="${CSS.escape(q.id)}"]`).classList.add('missing'));
      err.textContent = `还有 ${missing.length} 道必答题没完成`;
      root.querySelector(`[data-q="${CSS.escape(missing[0].id)}"]`).scrollIntoView({ behavior: 'smooth', block: 'center' });
      return;
    }
    const btn = root.querySelector('.sv-btn');
    btn.disabled = true; btn.textContent = '正在提交…'; err.textContent = '';
    const payload = { survey: def.id, answers: {}, seconds: Math.round((Date.now() - started) / 1000), website: root.querySelector('[name=website]').value };
    all().forEach(q => { if (done(q)) payload.answers[q.id] = q.type === 'text' ? answers[q.id].trim() : answers[q.id]; });
    try {
      const r = await fetch('/api/survey', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload), credentials: 'omit' });
      const j = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(j.error || '提交失败，请稍后再试');
      store.clear();
      // the trial survey: 今日 stops offering it on this phone (only a note that it was answered, never what)
      if (def.thanks) { try { localStorage.setItem('flow-trial-survey', '"done"'); } catch (x) { /* private mode */ } }
      root.innerHTML = def.thanks ? `<div class="sv-done"><h1>谢谢你！</h1><p class="sv-muted">${esc(def.thanks)}</p><a href="/">回到语流 →</a></div>`
        : `<div class="sv-done"><h1>谢谢你！</h1><p class="sv-muted">你的回答已经匿名保存。它会直接影响语流 Flow 接下来做什么。</p>
        <p class="sv-muted">如果身边有在学英语的朋友，也欢迎把这份问卷转给他们。</p><a href="/">去看看语流 Flow →</a></div>`;
      window.scrollTo(0, 0);
    } catch (x) {
      err.textContent = x.message; btn.disabled = false; btn.textContent = '提交问卷';
    }
  }

  const which = new URLSearchParams(location.search).get('s') || '';  // /survey?s=trial: the class trial survey
  fetch('/api/survey' + (which ? '?s=' + encodeURIComponent(which) : ''), { credentials: 'omit' })
    .then(r => r.ok ? r.json() : Promise.reject(new Error('问卷暂时无法打开')))
    .then(d => {
      def = d;
      if (store.sameSurvey()) { answers = store.load(); started = Math.min(started, store.start() || started); }
      render();
      root.addEventListener('change', onChange);
      root.addEventListener('input', e => { if (e.target.tagName === 'TEXTAREA') onChange(e); });
      root.addEventListener('submit', submit);
    })
    .catch(e => { root.innerHTML = `<p class="sv-error">${esc(e.message)}，请刷新重试。</p>`; });
})();

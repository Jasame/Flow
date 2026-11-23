  /* ---------- study ---------- */
  let selbar = null;
  function hideSelbar() { if (selbar) { selbar.remove(); selbar = null; } }
  const MAT = {}; // the material being studied: step changes reuse it instead of refetching and re-animating the header
  // Under the title: where the text comes from and how AI took part (r20). The writing rules of the originals, or the
  // sources of a news text, are one tap away.
  function originHTML(m) {
    const o = m.origin || { kind: 'original', label: m.source, ai: '', reviewed: null, url: '', references: m.provenance || [] };
    return `<div class="origin tiny"><span class="muted">来源：${o.url ? `<a class="link" href="${esc(o.url)}" target="_blank" rel="noopener noreferrer">${esc(o.label)}</a>` : esc(o.label)}</span>${o.ai ? `<span class="otag">${esc(o.ai)}</span>` : ''}${o.reviewed === false ? '<span class="otag warn">未经人工审核</span>' : ''}${o.kind === 'import' ? '' : `<button class="link tiny" type="button" id="originMore" data-tap="study-origin">${o.references.length ? `${o.kind === 'news' ? '来源' : '参考资料'} ${o.references.length} 条` : '怎么写的'}</button>`}</div>`;
  }
  function originSheet(m) {
    const o = m.origin, news = o.kind === 'news';
    openSheet(`<div class="stack"><h2 class="h2" id="sheetTitle">这篇材料从哪来</h2>
      ${news ? '<p class="small">今日热点是 AI 联网检索新闻后改写成的学习材料，<b>没有经过人工审核</b>。下面是它检索到的来源，事实以原文为准。</p>'
        : m.featured ? `<p class="small">精选材料由 Flow 编辑部按统一的写作规范原创${o.ai ? `（${esc(o.ai)}）` : ''}：</p>
          <ul class="small origin-rules"><li>不抄、不改写已有的文章、书籍和影视台词；</li><li>只写广为人知、稳定的常识，不写具体的统计数字、年份、价格和研究结论；</li><li>不写在世的真实人物，也不写时事新闻；</li><li>每道理解题的答案都要在原文里找得到依据，发布前由程序逐篇检查。</li></ul>`
        : `<p class="small">这是 Flow 编辑部较早编写的练习材料${o.ai ? `（${esc(o.ai)}）` : ''}。</p>`}
      ${o.references.length ? `<div class="stack-s"><b class="small">${news ? '来源' : '核对事实用的参考资料'}</b>${o.references.map(r => `<a class="link small" href="${esc(r.url)}" target="_blank" rel="noopener noreferrer">${esc(r.title)}</a>`).join('')}</div>` : ''}
      <button class="btn ghost" data-close type="button">知道了</button></div>`);
  }

  async function study(id, step, same) {
    let m = (same || (MAT[id] && Date.now() - (MAT[id]._preloaded || 0) < 6e5)) && MAT[id];
    if (m) delete m._preloaded;
    if (!m) { m = await api('/api/next/material?id=' + encodeURIComponent(id) + (S.user ? '' : '&level=' + encodeURIComponent(level()))); MAT[id] = m; }
    const done = new Set(m.steps.concat(load('flow-next-steps-' + id) || []));
    const st = { step: STEPS.includes(step) ? step : 'listen', showOriginal: !!m._showOriginal, blind: false };
    const lines = () => st.showOriginal && m.original ? m.original : m.sentences;

    function markStep(s) {
      if (done.has(s)) return;
      done.add(s); save('flow-next-steps-' + id, Array.from(done));
      if (S.user) api('/api/next/progress', { pack: id, step: s }).catch(() => {});
      const tab = view.querySelector(`[data-step="${s}"]`); if (tab && !tab.querySelector('.ok')) tab.insertAdjacentHTML('beforeend', '<span class="ok">✓</span>');
    }
    function go(s) { location.hash = `#/m/${encodeURIComponent(id)}/${s}`; }

    if (!same) {
      view.innerHTML = `<div class="study-head"><span class="kicker">${m.series ? `<a class="link" href="#/series/${encodeURIComponent(m.series.id)}">连载《${esc(m.series.title)}》第 ${m.series.part} / ${m.series.of} 集</a> · ${m.level}` : `${esc(m.theme_label)} · ${m.level}${m.variant ? ' → ' + m.variant.level : ''}${m.featured ? ' · 精选' : ''}`}</span>
        <h1 class="h1">${esc(m.title)}</h1>${m.title_en ? `<div class="title-en">${esc(m.title_en)}</div>` : ''}
        ${originHTML(m)}</div>
        <div class="steps" role="tablist"><span class="ind" aria-hidden="true"></span>${STEPS.map(s => `<button role="tab" data-step="${s}" aria-selected="false">${STEP[s]}${done.has(s) ? '<span class="ok">✓</span>' : ''}</button>`).join('')}</div>
        <section id="pane"></section>`;
      view.querySelectorAll('[data-step]').forEach(b => b.onclick = () => go(b.dataset.step));
      const om = view.querySelector('#originMore'); if (om) om.onclick = () => originSheet(m);
    }
    // Slide the tab indicator, and slide the pane in from the direction of travel.
    const tabs = [...view.querySelectorAll('[data-step]')];
    const prev = tabs.findIndex(b => b.getAttribute('aria-selected') === 'true');
    tabs.forEach(b => b.setAttribute('aria-selected', String(b.dataset.step === st.step)));
    const head = view.querySelector('.study-head'); if (head) head.dataset.at = st.step;  // phones: a shorter header once past listen and read
    const active = tabs.find(b => b.dataset.step === st.step), ind = view.querySelector('.steps .ind');
    const place = () => { ind.style.width = active.offsetWidth + 'px'; ind.style.transform = `translateX(${active.offsetLeft}px)`; };
    if (prev < 0) { ind.style.transition = 'none'; place(); requestAnimationFrame(() => { ind.style.transition = ''; }); } else requestAnimationFrame(place);
    const pane = view.querySelector('#pane');
    pane.style.setProperty('--dir', (prev > STEPS.indexOf(st.step) ? -14 : 14) + 'px');
    pane.classList.remove('pane-enter'); void pane.offsetWidth; pane.classList.add('pane-enter');
    // Switching steps far down the page: jump so the step bar sits under the header and the new content starts right below
    // it (the header comes back when scrolling up, so its height is always allowed for).
    if (same) { const top = view.querySelector('.study-head').getBoundingClientRect().bottom + scrollY - bar.offsetHeight; if (scrollY > top) scrollTo({ top, behavior: 'auto' }); }


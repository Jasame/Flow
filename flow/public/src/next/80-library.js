  /* ---------- library ---------- */
  // The pill on a row says only what the page above does not (B9's audit P2-E7): 一读 always; under the 精选 filter
  // nothing more, since every row is one; under 全部材料 a light 精选 (not the black one, the strongest thing on the page)
  // or 简版. The 「AI 生成」 tag stays on every row (B7).
  function libTag(m, f) {
    if (m.daily) return ['一读', 'amber'];
    if (f.featured === '1') return false;
    return m.featured ? ['精选', ''] : null;
  }
  async function libraryView(f) {
    let saved = null; try { saved = JSON.parse(sessionStorage.getItem('flow-next-lib') || 'null'); } catch (e) { /* private mode */ }
    f = f || saved || { level: hasProfile() ? level() : '', theme: '', page: 1, featured: '1' };
    try { sessionStorage.setItem('flow-next-lib', JSON.stringify(f)); } catch (e) { /* private mode */ }
    const d = await api(libraryPath(f));  // the same address a touch of the link already preloaded
    const pages = Math.max(1, Math.ceil(d.total / d.per));
    // The page in the order a learner picks (B9, 2026-11-26; the user on the mock-ups: 完全做，按照现在的效果图, and on the
    // filter row: 留空太多 / 这里按照舒服的方式改): two ways out on top (轻松读, 我的文章), the serial stories as cards
    // to swipe sideways, then 单篇: its count and the two small filters on one line, the level as a switch under it.
    const LV = ['', 'A2', 'B1', 'B2', 'C1'];
    view.innerHTML = `<h1 class="h1">全部材料</h1>
      <div class="lib-two"><a class="lib-way" href="#/easy">${fi('read')}<b>轻松读</b><span class="tiny muted">低一级</span></a><a class="lib-way" href="#/import">${fi('docpen')}<b>我的文章</b><span class="tiny muted">导入</span></a></div>
      ${d.series && d.series.length ? `<section class="lib-sec"><h2 class="lib-cap">连载故事</h2><div class="lib-sers">${d.series.map(s => `<a class="lib-ser" href="#/series/${encodeURIComponent(s.id)}">
        <b>${uiLang() === 'en' && !s.title_en ? esc(s.title) : `《${esc(s.title)}》`}</b><span class="en" lang="en">${esc(s.title_en)}</span><span class="tiny muted">${esc(s.level)} · 共 ${s.of} 集 ${aiTag()}</span>
        <span class="lib-bar" aria-hidden="true"><i data-w="${Math.round((s.done || 0) / s.of * 100)}"></i></span>
        <span class="tiny muted">${s.done ? (s.next ? `读到第 ${s.done} 集 · 继续第 ${s.next_part} 集` : '读完了') : '从第 1 集开始'}</span></a>`).join('')}</div></section>` : ''}
      <section class="lib-sec"><div class="lib-caprow"><h2 class="lib-cap">单篇 · ${d.total} 篇</h2><span class="lib-filt">
          <select id="ft" aria-label="话题"><option value="">全部话题</option>${Object.entries(d.themes).map(([k, v]) => `<option value="${k}" ${f.theme === k ? 'selected' : ''}>${esc(v)}</option>`).join('')}</select>
          <select id="ff" aria-label="范围"><option value="1" ${f.featured === '1' ? 'selected' : ''}>精选</option><option value="" ${f.featured !== '1' ? 'selected' : ''}>全部材料</option></select></span></div>
        <div class="seg lib-lv" id="fl" role="radiogroup" aria-label="难度">${LV.map(l => `<button type="button" role="radio" aria-checked="${(f.level || '') === l}" data-l="${l}">${l || '全部'}</button>`).join('')}</div>
        <div class="mlist" id="lib">${d.items.map(m => mrow(m, libTag(m, f))).join('') || '<div class="empty">这个筛选下还没有材料。</div>'}</div></section>
      ${pages > 1 ? `<div class="pager lib-pager"><button class="icon-btn" id="pv" type="button" aria-label="上一页" ${f.page <= 1 ? 'disabled' : ''}><svg viewBox="0 0 12 12" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M7.5 2.5 4 6l3.5 3.5"/></svg></button><span class="muted small">${f.page} / ${pages}</span><button class="icon-btn" id="nx" type="button" aria-label="下一页" ${f.page >= pages ? 'disabled' : ''}><svg viewBox="0 0 12 12" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4.5 2.5 8 6 4.5 9.5"/></svg></button></div>` : ''}`;
    view.querySelectorAll('.lib-bar i').forEach(i => { i.style.width = i.dataset.w + '%'; });
    const again = nf => libraryView(nf).then(() => enter(document.getElementById('lib')));
    document.getElementById('ff').onchange = e => again({ ...f, featured: e.target.value, page: 1 });
    document.getElementById('fl').querySelectorAll('button').forEach(b => b.onclick = () => { if (b.dataset.l !== (f.level || '')) again({ ...f, level: b.dataset.l, page: 1 }); });
    document.getElementById('ft').onchange = e => again({ ...f, theme: e.target.value, page: 1 });
    const pv = document.getElementById('pv'), nx = document.getElementById('nx');
    if (pv) pv.onclick = () => { scrollTo(0, 0); again({ ...f, page: f.page - 1 }); };
    if (nx) nx.onclick = () => { scrollTo(0, 0); again({ ...f, page: f.page + 1 }); };
  }

  /* ---------- a serial story: its episodes in order, and where to carry on ---------- */
  async function seriesView(sid) {
    const s = await api('/api/next/series?id=' + encodeURIComponent(sid));
    const next = s.episodes.find(e => e.id === s.next);
    view.innerHTML = `<div><a class="link small" href="#/library">← 全部材料</a></div>
      <div><span class="kicker">连载故事 · ${esc(s.level)} · 共 ${s.of} 集</span><h1 class="h1">${esc(s.title)}</h1><div class="title-en">${esc(s.title_en)}</div>
        <p class="muted small" data-zh>${esc(s.blurb)}</p>${aiCheckLink(aiMark('经规范检查'))}</div>
      ${next ? `<a class="btn primary block" href="#/m/${encodeURIComponent(next.id)}">${s.done ? `继续：第 ${next.part} 集` : '从第 1 集开始'}<span aria-hidden="true">→</span></a>` : '<p class="small">六集都读完了。可以回到任意一集，再听一遍或者重写输出任务。</p>'}
      <div class="serial section">${s.episodes.map(e => `<a class="ep${e.read ? ' done' : ''}${e.id === s.next ? ' next' : ''}" href="#/m/${encodeURIComponent(e.id)}">
        <span class="n" aria-hidden="true">${e.read ? '✓' : e.part}</span><span class="t"><b>${esc(e.title.replace(/^.*?[：:]/, ''))}</b><span class="tiny muted">${esc(e.preview.replace(/^连载第\s*\d+\s*集(（完）)?[：:]\s*/, ''))}</span></span>
        <span class="tiny muted">${e.minutes} 分钟</span></a>`).join('')}</div>
      <p class="tiny muted section">每集约 300 词，C1 难度，原创连载。每集都有听、读、理解和输出四步，读完理解题就算读过这一集。</p>`;
  }

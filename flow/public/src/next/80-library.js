  /* ---------- library ---------- */
  async function libraryView(f) {
    let saved = null; try { saved = JSON.parse(sessionStorage.getItem('flow-next-lib') || 'null'); } catch (e) { /* private mode */ }
    f = f || saved || { level: hasProfile() ? level() : '', theme: '', page: 1, featured: '1' };
    try { sessionStorage.setItem('flow-next-lib', JSON.stringify(f)); } catch (e) { /* private mode */ }
    const d = await api(libraryPath(f));  // the same address a touch of the link already preloaded
    const pages = Math.max(1, Math.ceil(d.total / d.per));
    view.innerHTML = `<div class="row between"><h1 class="h1">全部材料</h1><span class="row"><a class="btn small" href="#/easy">轻松读</a><a class="btn small" href="#/import">我的文章</a></span></div><span class="muted small">${d.total} 篇${f.featured === '1' ? ' · 精选' : ''}</span>
      <div class="filters"><select id="ff" aria-label="范围"><option value="1" ${f.featured === '1' ? 'selected' : ''}>精选</option><option value="" ${f.featured !== '1' ? 'selected' : ''}>全部材料</option></select>
        <select id="fl" aria-label="难度"><option value="">全部难度</option>${['A2', 'B1', 'B2', 'C1'].map(l => `<option ${f.level === l ? 'selected' : ''}>${l}</option>`).join('')}</select>
        <select id="ft" aria-label="话题"><option value="">全部话题</option>${Object.entries(d.themes).map(([k, v]) => `<option value="${k}" ${f.theme === k ? 'selected' : ''}>${esc(v)}</option>`).join('')}</select></div>
      ${d.series && d.series.length ? `<section class="section"><h2 class="h2 mhead">连载故事</h2><div class="mlist">${d.series.map(s => `<a class="mrow" href="#/series/${encodeURIComponent(s.id)}">
        <span class="t"><b>《${esc(s.title)}》${esc(s.title_en)}</b><span class="tiny muted">${esc(s.level)} · ${s.done ? `已读 ${s.done} / ${s.of} 集${s.next ? ` · 继续第 ${s.next_part} 集` : ' · 读完了'}` : `共 ${s.of} 集 · 从第 1 集开始`}</span></span>
        <span class="pill green">连载</span><span class="go" aria-hidden="true">›</span></a>`).join('')}</div></section>` : ''}
      <section class="section">${d.series && d.series.length ? '<h2 class="h2 mhead">单篇</h2>' : ''}<div class="mlist" id="lib">${d.items.map(m => mrow(m, m.daily ? ['热点', 'amber'] : null)).join('') || '<div class="empty">这个筛选下还没有材料。</div>'}</div></section>
      ${pages > 1 ? `<div class="pager"><button class="btn small" id="pv" ${f.page <= 1 ? 'disabled' : ''}>上一页</button><span class="muted small">${f.page} / ${pages}</span><button class="btn small" id="nx" ${f.page >= pages ? 'disabled' : ''}>下一页</button></div>` : ''}`;
    const again = nf => libraryView(nf).then(() => enter(document.getElementById('lib')));
    document.getElementById('ff').onchange = e => again({ ...f, featured: e.target.value, page: 1 });
    document.getElementById('fl').onchange = e => again({ ...f, level: e.target.value, page: 1 });
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
        <p class="muted small">${esc(s.blurb)}</p></div>
      ${next ? `<a class="btn primary block" href="#/m/${encodeURIComponent(next.id)}">${s.done ? `继续：第 ${next.part} 集` : '从第 1 集开始'}<span aria-hidden="true">→</span></a>` : '<p class="small">六集都读完了。可以回到任意一集，再听一遍或者重写输出任务。</p>'}
      <div class="serial section">${s.episodes.map(e => `<a class="ep${e.read ? ' done' : ''}${e.id === s.next ? ' next' : ''}" href="#/m/${encodeURIComponent(e.id)}">
        <span class="n" aria-hidden="true">${e.read ? '✓' : e.part}</span><span class="t"><b>${esc(e.title.replace(/^.*?[：:]/, ''))}</b><span class="tiny muted">${esc(e.preview.replace(/^连载第\s*\d+\s*集(（完）)?[：:]\s*/, ''))}</span></span>
        <span class="tiny muted">${e.minutes} 分钟</span></a>`).join('')}</div>
      <p class="tiny muted section">每集约 300 词，C1 难度，原创连载。每集都有听、读、理解和输出四步，读完理解题就算读过这一集。</p>`;
  }

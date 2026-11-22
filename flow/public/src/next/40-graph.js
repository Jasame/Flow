  /* ---------- knowledge graph ---------- */
  const STATUS_ORDER = ['solid', 'used', 'met', 'watch', 'untouched'];
  // Radial map: 18 nodes evenly on an outer ring (grouped by topic, one empty slot between topics),
  // topic hubs on an inner ring, labels pointing outward so they never collide.
  function graphSVG(g, compact) {
    const C = 200, RH = 74, RN = 142, RL = 160;
    const slots = g.topics.reduce((n, t) => n + t.nodes.length + 1, 0), step = 2 * Math.PI / slots;
    let edges = '', pre = '', hubs = '', nodes = '', k = 0, slot = 0;
    const pos = {}, f = v => v.toFixed(1);
    g.topics.forEach((t, ti) => {
      const first = slot, angles = t.nodes.map((_, i) => -Math.PI / 2 + (first + i + 0.5) * step);
      slot += t.nodes.length + 1;
      const ha = angles.reduce((s, a) => s + a, 0) / angles.length;
      const hx = C + RH * Math.cos(ha), hy = C + RH * Math.sin(ha);
      edges += `<line class="edge" x1="${C}" y1="${C}" x2="${f(hx)}" y2="${f(hy)}" data-delay="${ti * 0.05}"/>`;
      hubs += `<g class="hub"><circle cx="${f(hx)}" cy="${f(hy)}" r="21"/><text x="${f(hx)}" y="${f(hy)}">${esc(t.title)}</text></g>`;
      t.nodes.forEach((n, ni) => {
        const a = angles[ni], x = C + RN * Math.cos(a), y = C + RN * Math.sin(a);
        const lx = C + RL * Math.cos(a), ly = C + RL * Math.sin(a), cos = Math.cos(a);
        const anchor = cos > 0.25 ? 'start' : cos < -0.25 ? 'end' : 'middle';
        const dy = Math.sin(a) > 0.6 ? 10 : Math.sin(a) < -0.6 ? -4 : 3.5;
        pos[n.id] = [x, y];
        edges += `<line class="edge" x1="${f(hx)}" y1="${f(hy)}" x2="${f(x)}" y2="${f(y)}" data-delay="${0.25 + k * 0.02}"/>`;
        nodes += `<g class="gn st st-${n.status}${n.focus ? ' focus' : ''}" tabindex="0" role="link" data-node="${esc(n.id)}" data-delay="${0.35 + k * 0.035}" aria-label="${esc(n.title)}：${esc(n.label)}">
          <circle class="ring" cx="${f(x)}" cy="${f(y)}" r="13"/><circle class="dot" cx="${f(x)}" cy="${f(y)}" r="8.5"/>
          <text x="${f(lx)}" y="${f(ly + dy)}" text-anchor="${anchor}">${esc(n.title)}</text></g>`;
        k++;
      });
    });
    g.topics.forEach(t => t.nodes.forEach(n => { if (n.prereq && pos[n.prereq]) { const [x1, y1] = pos[n.prereq], [x2, y2] = pos[n.id]; pre += `<path class="pre" d="M${f(x1)},${f(y1)} Q${C},${C} ${f(x2)},${f(y2)}"/>`; } }));
    const vb = compact ? '30 30 340 340' : '-78 -22 556 444';
    if (compact) nodes = nodes.replace(/<text[^>]*>[^<]*<\/text><\/g>/g, '</g>');
    return `<svg class="gmap${compact ? ' compact' : ''}" viewBox="${vb}" role="img" aria-label="知识图谱：6 类、18 个语法知识点">
      <circle class="hub-ring" cx="${C}" cy="${C}" r="${RN}"/>${pre}${edges}
      <g class="hub"><circle cx="${C}" cy="${C}" r="27"/><text x="${C}" y="${C}">语法</text></g>${hubs}${nodes}</svg>`;
  }
  async function graphView() {
    const g = await api('/api/next/graph' + guestQuery(true));
    const s = g.summary;
    view.innerHTML = `<div><span class="kicker">知识图谱</span><h1 class="h1">你的英语语法地图</h1>
        <p class="muted small">18 个知识点分成 6 类。读到过、用出来、做题做对，都会点亮它；AI 在你写作里发现的问题也会标在这里。外圈呼吸的点，是「${esc(g.level)}」现在适合重点建立的。</p></div>
      <div class="gsum section">${[['solid', '已验证'], ['used', '用出来过'], ['met', '读到过'], ['watch', '要留意']].map(([k, l]) => `<div class="st st-${k}"><b>${s[k]}</b><span>${l}</span></div>`).join('')}</div>
      ${graphSVG(g, innerWidth < 560)}
      <div class="glegend">${STATUS_ORDER.map(k => `<span class="st st-${k}">${esc(g.labels[k])}</span>`).join('')}</div>
      <div class="topic-list section">${g.topics.map(t => `<div class="card flat topic"><div class="row between"><b>${esc(t.title)}</b><span class="tiny muted">${t.nodes.filter(n => n.status !== 'untouched').length} / ${t.nodes.length}</span></div>
        <div class="nodes">${t.nodes.map(n => nodeChip(n)).join('')}</div></div>`).join('')}</div>
      ${S.user ? '' : '<p class="muted small section">登录后，你读过、写过的内容会实时点亮这张图。</p>'}`;
    // CSP forbids inline style attributes, so animation delays are applied through the CSSOM.
    view.querySelectorAll('.gmap [data-delay]').forEach(el => { el.style.animationDelay = el.dataset.delay + 's'; });
    view.querySelectorAll('.gn').forEach(el => {
      const goNode = () => { location.hash = '#/graph/' + encodeURIComponent(el.dataset.node); };
      el.addEventListener('click', goNode); el.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); goNode(); } });
    });
  }
  async function nodeView(nid) {
    const n = await api('/api/next/node?id=' + encodeURIComponent(nid) + guestQuery(false));
    view.innerHTML = `<div><a class="link small" href="#/graph">← 知识图谱</a></div>
      <div><span class="kicker">${esc(n.topic)}</span><h1 class="h1">${esc(n.title)}</h1>
        <div class="row section"><span class="node-chip st st-${n.status}">${esc(n.label)}</span><span class="tiny muted">读到过 ${n.met} 篇 · 用出来 ${n.used} 次${n.flags ? ' · 写作中被指出 ' + n.flags + ' 次' : ''}${n.evidence ? ' · 做题：' + esc(n.evidence) : ''}</span></div></div>
      ${n.lesson ? `<div class="card flat stack-s"><b>要点</b><div class="small">${esc(n.lesson)}</div>${n.example ? `<div class="text small">${esc(n.example)}</div>` : ''}</div>` : ''}
      ${(n.prereq || n.unlocks.length) ? `<div class="row">${n.prereq ? `<span class="tiny muted">先学</span>${nodeChip({ id: n.prereq.id, title: n.prereq.title, status: 'met' })}` : ''}${n.unlocks.length ? `<span class="tiny muted">接下来</span>${n.unlocks.map(u => nodeChip({ id: u.id, title: u.title, status: 'untouched' })).join('')}` : ''}</div>` : ''}
      ${n.notes.length ? `<div class="stack-s"><h2 class="h2">AI 在你写作里看到的</h2>${n.notes.map(x => `<div class="knote"><span class="small">${x.kind === 'flag' ? '需要留意：' : '用对了'}${esc((x.detail.split('|')[1] || ''))}</span><span class="tiny muted">${new Date(x.created * 1000).toLocaleDateString('zh-CN')}</span></div>`).join('')}</div>` : ''}
      ${n.examples.length ? `<div class="stack-s"><h2 class="h2">在真实句子里看它</h2>${n.examples.map(x => `<a class="ex-quote" href="#/m/${encodeURIComponent(x.pack)}/read"><span>${esc(x.quote)}</span><div class="small muted">${esc(x.explanation)}</div></a>`).join('')}</div>` : ''}
      ${n.materials.length ? `<div><div class="section-head"><h2 class="h2">练这个知识点</h2></div><div class="grid-list">${n.materials.map(m => miniCard(m)).join('')}</div></div>` : ''}`;
  }


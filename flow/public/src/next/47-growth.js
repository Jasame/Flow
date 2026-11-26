  /* ---------- my progress: this month against the last, and milestones that only count up ---------- */
  async function growthView(month) {
    if (!S.user) return needLogin('登录后可以看到每个月的进步。');
    const d = await api('/api/next/growth' + (month ? '?month=' + encodeURIComponent(month) : ''));
    // The page in four blocks (B9, 2026-11-26; the user on the mock-ups: 完全做，按照现在的效果图): one sentence for the month,
    // the other seven figures a row each, the three milestones nearest to done (the rest folded under them), the way to
    // 周报. The theme colour marks what grew and the bars; the month is changed with the two arrows on the right.
    const n = d.now, b = d.before, num = v => v == null ? '—' : v.toLocaleString();
    const more = k => b[k] == null || n[k] == null ? '' : n[k] > b[k] ? `多 ${(n[k] - b[k]).toLocaleString()}` : n[k] < b[k] ? `上月 ${b[k].toLocaleString()}` : '';
    const row = (k, icon, label, text) => `<div class="gtile grow-row">${fi(icon)}<span class="t">${label}</span><b>${n[k] == null ? '—' : text(num(n[k]))}</b><span class="d tiny muted">${more(k)}</span></div>`;
    const thisMonth = new Date(); const cur = `${thisMonth.getFullYear()}-${String(thisMonth.getMonth() + 1).padStart(2, '0')}`;
    const ym = d.month.split('-').map(Number), nextYm = ym[1] === 12 ? `${ym[0] + 1}-01` : `${ym[0]}-${String(ym[1] + 1).padStart(2, '0')}`, atNow = d.month >= cur;
    const arrow = p => `<svg viewBox="0 0 12 12" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${p}"/></svg>`;
    const days = n.days == null || b.days == null ? '' : n.days > b.days ? `<span class="up">比上个月多 ${n.days - b.days} 天</span>` : n.days < b.days ? `上个月 ${b.days} 天` : '和上个月一样';
    const mile = (m, k) => `<div class="mile${m.done ? ' done' : ''} pop-in" data-k="${k}"><div class="r"><b>${m.done ? '<span class="mi" aria-hidden="true">✓</span>' : ''}${esc(m.title)}</b><span class="tiny muted">${m.have.toLocaleString()} / ${m.need.toLocaleString()} ${esc(m.unit)}</span></div>
      <span class="vbar"><i data-w="${Math.min(100, Math.round(m.have / m.need * 100))}"></i></span></div>`;
    const open = d.milestones.filter(m => !m.done).sort((x, y) => y.have / y.need - x.have / x.need), near = open.slice(0, 3);
    const rest = d.milestones.filter(m => near.indexOf(m) < 0);
    view.innerHTML = `<div class="stack grow-page"><div><h1 class="h1">我的进步</h1>
        <div class="grow-top"><span class="small muted">${d.month === cur ? '只和自己的上个月比' : `<a class="link" href="#/growth">回到本月</a>`}</span>
          <span class="grow-mon"><a href="#/growth/${encodeURIComponent(d.prev)}" aria-label="上个月">${arrow('M7.5 2.5 4 6l3.5 3.5')}</a><b>${esc(d.label)}</b>${atNow ? `<span class="off" aria-hidden="true">${arrow('M4.5 2.5 8 6 4.5 9.5')}</span>` : `<a href="#/growth/${encodeURIComponent(nextYm)}" aria-label="下个月">${arrow('M4.5 2.5 8 6 4.5 9.5')}</a>`}</span></div></div>
      <section class="card flat gtile grow-hero"><p class="tiny muted">${d.month === cur ? '这个月' : esc(d.label)}</p><h2>${n.days == null ? '还没有记录' : `学了 ${n.days} 天`}</h2>${days ? `<p class="small muted">${days}</p>` : ''}</section>
      <section class="card flat grow-rows">${row('words_read', 'read', '读了', v => v + ' 词')}${row('materials', 'layers', '学完的材料', v => v + ' 篇')}${row('wpm', 'gauge', '阅读速度', v => '每分钟 ' + v + ' 词')}
        ${row('reviews', 'again', '复习', v => v + ' 次')}${row('new_words', 'spark', '新学的词', v => v + ' 个')}${row('grammar_checks', 'graph', '语法做题', v => v + ' 题')}${row('speaking', 'mic', '开口说', v => v + ' 次')}</section>
      <section class="card flat grow-miles"><div class="row between"><h2>${near.length ? '快到的里程碑' : '里程碑'}</h2><span class="small muted">已达成 ${d.reached} / ${d.total}</span></div>
        <div class="miles">${near.map(mile).join('')}</div>
        ${rest.length ? `<details class="grow-all"${near.length ? '' : ' open'}><summary>全部 ${d.total} 个<svg viewBox="0 0 12 12" width="12" height="12" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M2.5 4.5 6 8l3.5-3.5"/></svg></summary><div class="miles">${rest.map((m, k) => mile(m, k + near.length)).join('')}</div></details>` : ''}</section>
      <a class="grow-link" href="#/report">${fi('week')}<b>周报</b><span class="go">最近 7 天 ›</span></a>
      <p class="tiny muted grow-note">${esc(d.note)}</p></div>`;
    view.querySelectorAll('.pop-in').forEach(el => el.style.setProperty('--d', Math.min(10, Number(el.dataset.k)) * 60 + 'ms'));
    requestAnimationFrame(() => requestAnimationFrame(() => view.querySelectorAll('.vbar i').forEach(i => { i.style.width = i.dataset.w + '%'; })));
  }

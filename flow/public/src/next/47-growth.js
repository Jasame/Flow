  /* ---------- my progress: this month against the last, and milestones that only count up ---------- */
  async function growthView(month) {
    if (!S.user) return needLogin('登录后可以看到每个月的进步。');
    const d = await api('/api/next/growth' + (month ? '?month=' + encodeURIComponent(month) : ''));
    const n = d.now, b = d.before;
    const cmp = (k, unit) => b[k] == null || n[k] == null ? '' : n[k] > b[k] ? `<span class="up">比上月多 ${(n[k] - b[k]).toLocaleString()}${unit}</span>` : n[k] < b[k] ? `<span class="tiny muted">上月 ${b[k].toLocaleString()}</span>` : '';
    const tile = (k, label, unit) => `<div class="gtile"><b>${n[k] == null ? '—' : n[k].toLocaleString()}</b><span class="tiny muted">${label}</span>${cmp(k, unit)}</div>`;
    const thisMonth = new Date(); const cur = `${thisMonth.getFullYear()}-${String(thisMonth.getMonth() + 1).padStart(2, '0')}`;
    view.innerHTML = `<div class="stack"><div><span class="kicker">我的进步</span><h1 class="h1">${esc(d.label)}</h1><p class="muted small">${esc(d.note)}</p></div>
      <div class="row"><a class="btn small" href="#/growth/${encodeURIComponent(d.prev)}">← 上个月</a>${d.month !== cur ? `<a class="btn small" href="#/growth">回到本月</a>` : ''}<a class="btn small ghost" href="#/report">这周的报告</a></div>
      <div class="gtiles">${tile('days', '学习天数', ' 天')}${tile('words_read', '读了（词）', ' 词')}${tile('materials', '学完的材料', ' 篇')}${tile('wpm', '阅读速度（词/分钟）', '')}
        ${tile('reviews', '复习次数', ' 次')}${tile('new_words', '新学的词', ' 个')}${tile('grammar_checks', '语法做题', ' 题')}${tile('speaking', '开口说', ' 次')}</div>
      <section class="section stack-s"><div class="row between"><h2 class="h2">里程碑</h2><span class="small muted">已达成 ${d.reached} / ${d.total}</span></div>
        <div class="miles">${d.milestones.map((m, k) => `<div class="mile${m.done ? ' done' : ''} pop-in" data-k="${k}"><span class="mi" aria-hidden="true">${m.done ? '✓' : ''}</span>
          <span class="t"><b>${esc(m.title)}</b><span class="vbar"><i data-w="${Math.round(m.have / m.need * 100)}"></i></span><span class="tiny muted">${m.have.toLocaleString()} / ${m.need.toLocaleString()} ${esc(m.unit)}</span></span></div>`).join('')}</div></section></div>`;
    view.querySelectorAll('.pop-in').forEach(el => el.style.setProperty('--d', Math.min(10, Number(el.dataset.k)) * 60 + 'ms'));
    requestAnimationFrame(() => requestAnimationFrame(() => view.querySelectorAll('.vbar i').forEach(i => { i.style.width = i.dataset.w + '%'; })));
  }

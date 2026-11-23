  /* ---------- weekly report, with a picture to share ---------- */
  async function reportView() {
    if (!S.user) return needLogin('登录后可以看每周学习报告。');
    const r = await api('/api/next/report');
    const arrow = s => s.now == null ? '—' : `${Math.round(s.now * 100)}%${s.before != null ? (s.now > s.before + 0.02 ? ' ↑' : s.now < s.before - 0.02 ? ' ↓' : '') : ''}`;
    view.innerHTML = `<h1 class="h1">这周的学习</h1><span class="muted small">${esc(r.from)} – ${esc(r.to)}</span>
      <div class="stat-grid section"><div class="card flat stat"><b>${r.days}</b><span class="tiny muted">学习天数</span></div><div class="card flat stat"><b>${r.minutes}</b><span class="tiny muted">分钟（估算）</span></div>
        <div class="card flat stat"><b>${r.materials}</b><span class="tiny muted">学完的材料</span></div><div class="card flat stat"><b>${r.outputs}</b><span class="tiny muted">输出练习</span></div>
        <div class="card flat stat"><b>${r.learned}</b><span class="tiny muted">新学的词</span></div><div class="card flat stat"><b>${r.mastered}</b><span class="tiny muted">进入长期记忆</span></div></div>
      <div class="card flat section stack-s"><b>各项练习的平均分</b><div class="ab-list">${r.skills.filter(s => s.count || s.before != null).map(s => `<div class="ab"><span class="nm">${esc(s.label)}</span>
        <span class="vbar"><i data-w="${Math.max(3, (s.now || 0) * 100)}"></i></span><span class="lv">${arrow(s)}</span><span class="tiny muted ev">${s.count} 次</span></div>`).join('') || '<p class="muted small">这周还没有练习记录。</p>'}</div></div>
      ${weekMoreHTML(r)}
      <div class="card flat section stack-s"><b>错题</b><span class="small">新进错题本 ${r.mistakes_new} 个，改对 ${r.mistakes_fixed} 个。</span>
        ${r.watch.length ? `<span class="small">写作里要留意：${r.watch.map(n => nodeChip({ id: n.id, title: n.title, status: 'watch' })).join(' ')}</span>` : ''}
        ${r.focus ? `<div class="small"><b>下周重点：</b>${esc(r.focus)}</div>` : ''}</div>
      <div class="section row"><button class="btn primary" id="share">生成分享图</button><a class="btn" href="#/radar">能力雷达</a></div><div id="shareOut" class="section"></div>`;
    requestAnimationFrame(() => requestAnimationFrame(() => view.querySelectorAll('.vbar i').forEach(i => { i.style.width = i.dataset.w + '%'; })));
    document.getElementById('share').onclick = () => {
      const url = shareImage(r);
      document.getElementById('shareOut').innerHTML = `<img class="share-img" src="${url}" alt="本周学习分享图"><div class="row"><a class="btn small primary" download="flow-week.png" href="${url}">保存图片</a><span class="muted tiny">${TOUCH ? '也可以长按图片保存' : '或右键图片另存为'}</span></div>`;
      bringIntoView(document.getElementById('shareOut'));
    };
  }
  function weekMoreHTML(r) {
    const e = r.easy || {}, sp = r.speaking || {}, ra = r.radar || { moves: [] };
    const speed = e.wpm ? `，平均每分钟 ${e.wpm} 词${e.wpm_before ? (e.wpm > e.wpm_before ? `（上周 ${e.wpm_before}，快了）` : `（上周 ${e.wpm_before}）`) : ''}` : '';
    const mv = m => m.before == null ? '' : m.now > m.before ? ` <span class="up">↑${m.now - m.before}</span>` : m.now < m.before ? ` <span class="tiny muted">↓${m.before - m.now}</span>` : '';
    return `<div class="card flat section stack-s"><div class="row between"><b>轻松读</b><a class="link small" href="#/easy">去读</a></div>
        <span class="small">${e.texts ? `读了 ${e.texts} 篇，一共 ${e.words} 个词${speed}。` : '这周还没读。每天读一篇比你低一级的短文，阅读速度会慢慢提上来。'}</span></div>
      <div class="card flat section stack-s"><div class="row between"><b>口语情景</b><a class="link small" href="#/speak">去练</a></div>
        <span class="small">${sp.scenes_week ? `这周练了 ${sp.scenes_week} 个情景，` : '这周还没练情景对话，'}一共完成 ${sp.scenes_done || 0} / ${sp.scenes_total || 12} 个。</span></div>
      <div class="card flat section stack-s"><div class="row between"><b>能力雷达</b><a class="link small" href="#/radar">看雷达</a></div>
        ${ra.moves.length ? `<div class="ab-list">${ra.moves.map(m => `<div class="ab"><span class="nm">${esc(m.label)}</span><span class="vbar"><i data-w="${Math.max(3, Math.min(100, m.now))}"></i></span><span class="lv">${m.now} 分${mv(m)}</span></div>`).join('')}</div>
          <span class="tiny muted">100 分 = 达到你定的目标${ra.goals_chosen ? '' : '（还没定目标，先按默认目标算）'}。这周做了 ${ra.tests_week} 次测评。</span>`
          : '<span class="small">还没有雷达数据。做几次小测评，就能看到六项能力离目标还差多少。</span><div><a class="btn small" href="#/radar/test">去测一测</a></div>'}</div>`;
  }
  function shareImage(r) {
    const rows = r.skills.filter(s => s.now != null).slice(0, 5).length;
    const W = 1080, H = rows ? 900 + rows * 70 + 170 : 860, cv = document.createElement('canvas'); cv.width = W; cv.height = H;
    const g = cv.getContext('2d'), green = '#1f9d55', ink = '#1b1d1a', muted = '#6f7369';
    g.fillStyle = '#fbfaf6'; g.fillRect(0, 0, W, H);
    g.fillStyle = green; g.beginPath(); g.roundRect ? g.roundRect(80, 90, 96, 96, 26) : g.rect(80, 90, 96, 96); g.fill();
    g.strokeStyle = '#fff'; g.lineWidth = 9; g.lineCap = 'round';
    [[103, 133, 151], [121, 115, 169], [139, 124, 160], [157, 133, 145]].forEach(([x, a, b]) => { g.beginPath(); g.moveTo(x, a); g.lineTo(x, b); g.stroke(); });
    const font = (s, w) => `${w || 600} ${s}px -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif`;
    g.fillStyle = ink; g.font = font(44, 700); g.fillText('语流 Flow · 本周学习', 200, 152);
    g.fillStyle = muted; g.font = font(30, 400); g.fillText(`${r.from} – ${r.to}`, 80, 250);
    const stats = [[r.days, '学习天数'], [r.minutes, '分钟'], [r.materials, '篇材料'], [r.learned, '个新词'], [r.mastered, '个词记牢了'], [r.outputs, '次输出练习']];
    stats.forEach(([v, l], k) => {
      const x = 80 + (k % 3) * 320, y = 320 + Math.floor(k / 3) * 220;
      g.fillStyle = '#ffffff'; g.fillRect(x, y, 290, 190); g.fillStyle = green; g.font = font(84, 800); g.fillText(String(v), x + 30, y + 110);
      g.fillStyle = muted; g.font = font(30, 500); g.fillText(l, x + 30, y + 160);
    });
    let y = 820; g.fillStyle = ink; g.font = font(36, 700); if (rows) g.fillText('各项练习', 80, y); y += 30;
    r.skills.filter(s => s.now != null).slice(0, 5).forEach(s => {
      y += 70; g.fillStyle = ink; g.font = font(32, 500); g.fillText(s.label, 80, y);
      g.fillStyle = '#e7e3d8'; g.fillRect(240, y - 24, 600, 22); g.fillStyle = green; g.fillRect(240, y - 24, 600 * s.now, 22);
      g.fillStyle = muted; g.fillText(Math.round(s.now * 100) + '%', 870, y);
    });
    g.fillStyle = muted; g.font = font(30, 400); g.fillText('每天一篇，学了就能用 · flow.jasa.hk', 80, H - 90);
    return cv.toDataURL('image/png');
  }


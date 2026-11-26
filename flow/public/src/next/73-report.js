  /* ---------- weekly report, with a picture to share ---------- */
  async function reportView() {
    if (!S.user) return needLogin('登录后可以看周报。');
    const r = await api('/api/next/report');
    const arrow = s => s.now == null ? '—' : `${Math.round(s.now * 100)}%${s.before != null ? (s.now > s.before + 0.02 ? ' ↑' : s.now < s.before - 0.02 ? ' ↓' : '') : ''}`;
    // 周报 in blocks (B9, 2026-11-26; the user on the mock-ups: 完全做，按照现在的效果图): the six figures as one sentence with
    // seven dots (as many filled as days studied), then a block a subject with its title inside, the things to open as
    // rows, and the one full-width button. The theme colour: the days, the bars, what went up, the small texts to tap.
    const days = Math.max(0, Math.min(7, r.days || 0));
    view.innerHTML = `<div class="stack rep-page"><div><h1 class="h1">周报</h1><span class="muted small">${esc(r.from)} – ${esc(r.to)} · 最近 7 天</span></div>
      <section class="card flat rep-hero"><p class="tiny muted">这 7 天</p><h2>学了 ${r.days} 天，约 ${r.minutes} 分钟</h2>
        <p class="small muted">学完 ${r.materials} 篇 · 新学 ${r.learned} 个词 · 输出练习 ${r.outputs} 次 · ${r.mastered} 个词进入长期记忆</p>
        <div class="rep-days" aria-hidden="true">${[0, 1, 2, 3, 4, 5, 6].map(k => `<i${k < days ? ' class="on"' : ''}></i>`).join('')}</div></section>
      ${weekPairHTML(r.progress)}
      <section class="card flat rep-blk"><h2>各项练习的平均分</h2><div class="ab-list rep-skills">${r.skills.filter(s => s.count || s.before != null).map(s => `<div class="ab"><span class="nm">${esc(s.label)}</span>
        <span class="vbar"><i data-w="${Math.max(3, (s.now || 0) * 100)}"></i></span><span class="lv">${arrow(s)}</span><span class="tiny muted ev">${s.count} 次</span></div>`).join('') || '<p class="muted small">这 7 天还没有练习记录。</p>'}</div></section>
      ${weekMoreHTML(r)}
      ${r.focus || r.watch.length ? `<section class="card flat rep-blk"><h2>接下来的重点</h2>${r.focus ? `<p class="rep-p">${esc(r.focus)}</p>` : ''}
        ${r.watch.length ? `<p class="small muted rep-watch">写作里要留意：${r.watch.map(n => nodeChip({ id: n.id, title: n.title, status: 'watch' })).join(' ')}</p>` : ''}</section>` : ''}
      <button class="btn primary block rep-go" id="share" data-tap="share-week">分享这 7 天的学习</button></div>`;
    requestAnimationFrame(() => requestAnimationFrame(() => view.querySelectorAll('.vbar i').forEach(i => { i.style.width = i.dataset.w + '%'; })));
    document.getElementById('share').onclick = () => shareSheet([{ label: '这 7 天', draw: () => shareImage(r) }], '分享这 7 天的学习');
    const w = r.progress && r.progress.waiting, tryBtn = document.getElementById('wpTry');
    if (w && tryBtn) tryBtn.onclick = () => { S.tryNode = { pack: w.pack, title: w.title, fixed: wpPut(w.sentence, w.from, w.to) }; };
  }
  /* ---------- 这周的一次进步 (r29 第 3 项, the user's pick 2026-11-26) ----------
     One grammar point: the sentence the AI corrected before and one the learner wrote right since (dates, which
     practice, with or without a hint); with none yet, the last correction and 现在用它写一句 (仿写 on that text, the point
     named on the page: tryHintHTML); then 还要接着练, only points that keep coming back, only when the records may pick. */
  function wpPut(s, from, to) {  // s with its first `from` (any case) put right
    const i = from ? s.toLowerCase().indexOf(from.toLowerCase()) : -1;
    return i < 0 ? s : s.slice(0, i) + to + s.slice(i + from.length);
  }
  function wpFixed(b) {  // the sentence as written, the part changed struck out and the correction after it (words both share stay plain)
    const s = b.sentence || '', f = b.from || '', i = f ? s.toLowerCase().indexOf(f.toLowerCase()) : -1;
    if (i < 0) return `${esc(s)}<br>${f ? `<s>${esc(f)}</s> → ` : '→ '}<ins>${esc(b.to)}</ins>`;
    const fw = s.slice(i, i + f.length).split(' '), tw = (b.to || '').split(' ');
    let a = 0;
    while (a < fw.length - 1 && a < tw.length - 1 && fw[a].toLowerCase() === tw[a].toLowerCase()) a++;
    return `${esc(s.slice(0, i))}${esc(fw.slice(0, a).join(' '))}${a ? ' ' : ''}<s>${esc(fw.slice(a).join(' '))}</s> <ins>${esc(tw.slice(a).join(' '))}</ins>${esc(s.slice(i + f.length))}`;
  }
  function wpMark(s, part) {  // the corrected form where the learner used it
    const i = part ? s.toLowerCase().indexOf(part.toLowerCase()) : -1;
    return i < 0 ? esc(s) : `${esc(s.slice(0, i))}<b>${esc(s.slice(i, i + part.length))}</b>${esc(s.slice(i + part.length))}`;
  }
  function weekPairHTML(g) {
    if (!g) return '';
    const p = g.pair, w = g.waiting, rec = g.recurring;
    const help = { 1: '看了提示', 0: '没看提示，自己写的' }, how = { 1: '看了提示后', 0: '自己' };
    const line = xs => xs.filter(Boolean).map(esc).join(' · ');
    const top = p ? `<div class="card flat wp stack-s"><b class="wp-t">${esc(p.title)}</b>
        <span class="small muted">${line([p.before.date, p.before.label, 'AI 帮你改过'])}</span><p class="wp-s" lang="en">${wpFixed(p.before)}</p>
        <span class="small muted">${line([p.after.date, p.after.label, help[p.after.assisted]])}</span><p class="wp-s" lang="en">${wpMark(p.after.sentence, p.before.to)}</p>
        <p class="small wp-end">之前要 AI 改，这周${how[p.after.assisted] || ''}用对了一次。</p></div>`
      : w ? `<div class="card flat wp stack-s"><b class="wp-t">这周还看不出来</b>
        <p class="small">${esc(w.date)}的${esc(w.label)}里，「${esc(w.title)}」要 AI 帮你改。这周还没有再用到它，看不出有没有进步。</p>
        <span class="small muted">那时写的</span><p class="wp-s" lang="en">${wpFixed(w)}</p>
        <p class="small wp-end">下次写到「${esc(w.title)}」的时候，再试一次。</p>
        ${w.pack ? `<a class="btn block" id="wpTry" href="#/m/${encodeURIComponent(w.pack)}/output" data-tap="week-try">现在用它写一句 →</a>` : ''}</div>`
      : `<div class="card flat wp stack-s"><b class="wp-t">这周还看不出来</b><p class="small">写作、翻译或仿写被 AI 改过以后，下次你自己写对了，这里会放一组前后对照。</p></div>`;
    const more = rec ? `<div class="card flat stack-s"><b>还要接着练</b>${rec.length ? rec.map(x => `<p class="small wp-rec">${esc(x.title)}：两周里在 ${x.outputs} 次不同的练习里出现过，明天的语法复习先练它。</p>`).join('')
      : '<p class="small wp-rec">这周没有反复出现的问题。</p>'}<span class="tiny muted">偶尔出一次的小错，当场提示过就算了，不放在这里。</span></div>` : '';
    return `<section class="section stack-s" aria-labelledby="wpH"><h2 class="h2" id="wpH">这周的一次进步</h2>${top}${more}</section>`;
  }
  function tryHintHTML(pid) {  // 仿写 opened from 现在用它写一句: the point to try, and the sentence as the AI put it right then
    const t = S.tryNode;
    return t && t.pack === pid ? `<div class="small try-node">这次试着用上「${esc(t.title)}」。那时 AI 帮你改成：<span lang="en">${esc(t.fixed)}</span></div>` : '';
  }
  function weekMoreHTML(r) {
    const e = r.easy || {}, sp = r.speaking || {}, ra = r.radar || { moves: [] };
    const speed = e.wpm ? `，平均每分钟 ${e.wpm} 词${e.wpm_before ? (e.wpm > e.wpm_before ? `（前 7 天 ${e.wpm_before}，快了）` : `（前 7 天 ${e.wpm_before}）`) : ''}` : '';
    const mv = m => m.before == null ? '' : m.now > m.before ? `<span class="up">↑${m.now - m.before}</span>` : m.now < m.before ? `<span class="down">↓${m.before - m.now}</span>` : '';
    const rl = r.relisten || {};
    // 能力 as six small figures (the radar itself is one tap away), then what the week had to open: a row each, the whole row a link
    return `${rl.count ? `<section class="card flat rep-blk"><h2>复听</h2><p class="rep-p">把几天前学过的文章重听了 ${rl.count} 次，平均听懂${esc(rl.label)}。</p></section>` : ''}
      <section class="card flat rep-blk"><div class="row between"><h2>能力</h2><a class="rep-more" href="#/radar">看雷达 ›</a></div>
        ${ra.moves.length ? `<div class="rep-ab">${ra.moves.map(m => `<div><span class="tiny muted">${esc(m.label)}</span><b>${m.now}</b>${mv(m)}</div>`).join('')}</div>
          <span class="tiny muted">100 分 = 达到你定的目标${ra.goals_chosen ? '' : '（还没定目标，先按默认目标算）'}。这 7 天做了 ${ra.tests_week} 次测评。</span>`
          : '<p class="rep-p">还没有雷达数据。做几次小测评，就能看到六项能力离目标还差多少。</p><div><a class="btn small" href="#/radar/test">去测一测</a></div>'}</section>
      <section class="card flat rep-rows">
        <a class="rep-row" href="#/easy">${fiTile('read')}<span class="t"><b>轻松读</b><span class="small muted">${e.texts ? `读了 ${e.texts} 篇，一共 ${e.words} 个词${speed}。` : '这 7 天还没读。每天读一篇比你低一级的短文，阅读速度会慢慢提上来。'}</span></span><span class="go" aria-hidden="true">›</span></a>
        <a class="rep-row" href="#/speak">${fiTile('chat')}<span class="t"><b>口语情景</b><span class="small muted">${sp.scenes_week ? `这 7 天练了 ${sp.scenes_week} 个情景，` : '这 7 天还没练情景对话，'}一共完成 ${sp.scenes_done || 0} / ${sp.scenes_total || 12} 个。</span></span><span class="go" aria-hidden="true">›</span></a>
        <a class="rep-row" href="#/cards/mistake">${fiTile('bookx')}<span class="t"><b>错题</b><span class="small muted">新进错题本 ${r.mistakes_new} 个，改对 ${r.mistakes_fixed} 个。</span></span><span class="go" aria-hidden="true">›</span></a></section>`;
  }
  function shareImage(r) {
    const rows = r.skills.filter(s => s.now != null).slice(0, 5).length;
    const W = 1080, H = (rows ? 900 + rows * 70 + 170 : 860) + 230, cv = document.createElement('canvas'); cv.width = W; cv.height = H;
    const g = cv.getContext('2d'), green = '#1f9d55', ink = '#1b1d1a', muted = '#6f7369';
    g.fillStyle = '#fbfaf6'; g.fillRect(0, 0, W, H);
    const font = (s, w) => `${w || 600} ${s}px -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif`;
    g.fillStyle = ink; g.font = font(56, 800); g.fillText('这 7 天的学习', 80, 170);  // the brand is in the footer, with the QR code
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
    brandFoot(g, W, H, habitNote(false, true));  // logo, the weeks that reached the goal, and the QR code back to the site (86-share.js)
    return cv.toDataURL('image/png');
  }


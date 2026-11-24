  /* ---------- 这篇完成了 (r27): after 用出来, three lines on what this text gave the learner ---------- */
  // The expressions and words saved from this text, and one grammar point to work on (progress_service.text_summary):
  // one the AI corrected in what was written for it, else one of its points that needs attention or has not been
  // checked with questions yet. Each line goes where that work continues. Shown after any of the five ways of 用出来,
  // once at the end of the step (a second answer draws it again with what has changed). The share card stays.
  function finishCard(m, id, remaining) {
    const share = (m.expressions || []).length ? '<button class="link small" id="shareDone" type="button" data-tap="share-material">把学会的一句做成卡片</button>' : '';
    const next = m.series && m.series.next ? `<a class="btn" href="#/">回到今日</a><a class="btn primary" href="#/m/${encodeURIComponent(m.series.next)}">下一集：第 ${m.series.part + 1} 集</a>`
      : '<a class="btn" href="#/graph">看知识图谱</a><a class="btn primary" href="#/">回到今日</a>';
    return `<div class="card done-card fin enter" id="finCard">${doneRing}<h2 class="h2">这篇完成了</h2>
      ${S.user ? '<div class="fin-sum" id="finSum" aria-live="polite" aria-busy="true"><span class="fin-wait"><span class="spin"></span> 正在整理这篇学到的…</span></div>' : ''}
      ${share}<p class="muted tiny">${remaining != null ? '今天还可以用 AI ' + remaining + ' 次。' : ''}收藏的表达和生词会按遗忘曲线安排复习。</p>
      <div class="row center">${next}</div></div>`;
  }
  function finishLines(s, id) {
    const row = (k, text, href, tap) => href ? `<a class="fin-row" href="${href}" data-tap="${tap}"><span class="k">${k}</span><span class="t">${text}</span><span class="go" aria-hidden="true">›</span></a>`
      : `<div class="fin-row"><span class="k">${k}</span><span class="t">${text}</span></div>`;
    const list = xs => xs.slice(0, 2).map(x => `<b lang="en">${esc(x.text || x)}</b>`).join('、');
    const e = s.expressions, w = s.words, g = s.grammar;
    const expr = e.count ? row('表达', `收藏了 ${e.count} 个：${list(e.saved)}${e.count > 2 ? ' 等' : ''}`, '#/cards/phrase', 'finish-expr')
      : e.key.length ? row('表达', `还没收藏。这篇的重点：${list(e.key)}`, `#/m/${encodeURIComponent(id)}/read`, 'finish-expr') : row('表达', '这篇没有收藏表达');
    const words = w.count ? row('新词', `收藏了 ${w.count} 个：${list(w.saved)}${w.count > 2 ? ' 等' : ''}，明天开始复习`, '#/cards/word', 'finish-words')
      : w.mine.length ? row('新词', `没有收藏生词；这篇里有你在背的 ${w.mine.length} 个：${list(w.mine)}${w.mine.length > 2 ? ' 等' : ''}`, '#/cards/word', 'finish-words')
      : row('新词', '这篇没有收藏生词');
    const node = g && g.id ? `#/graph/${encodeURIComponent(g.id)}` : '';
    const gram = !g ? row('语法', '这篇没有标出语法点')
      : g.all_solid ? row('语法', `这篇的 ${g.count} 个语法点都做题验证过了 ✓`)
      : g.why === 'flag' ? row('语法', `「${esc(g.title)}」写错了 ${g.times} 次${g.change ? `（<span lang="en">${esc(g.change)}</span>）` : ''}，做 4 题巩固`, node, 'finish-grammar')
      : g.why === 'watch' ? row('语法', `「${esc(g.title)}」需要留意，做 4 题巩固`, node, 'finish-grammar')
      : row('语法', `这篇用到了「${esc(g.title)}」，做 4 题验证一下`, node, 'finish-grammar');
    return expr + words + gram;
  }
  // The finish card at the end of the step's pane (one; drawn again after another answer), then its three lines.
  async function showFinish(pane, m, id, remaining) {
    let slot = pane.querySelector('#finSlot');
    if (!slot) { slot = document.createElement('div'); slot.id = 'finSlot'; slot.className = 'section'; pane.appendChild(slot); }
    slot.innerHTML = finishCard(m, id, remaining);
    const sd = slot.querySelector('#shareDone'); if (sd) sd.onclick = () => shareFromMaterial(m);
    const box = slot.querySelector('#finSum'); if (!box) return;
    try {
      const s = await api('/api/next/text-summary?pack=' + encodeURIComponent(id));
      if (box.isConnected) { box.innerHTML = finishLines(s, id); box.removeAttribute('aria-busy'); }
    } catch (e) { box.remove(); }
  }

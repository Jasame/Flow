  /* ---------- 练习记录 (B9, 2026-11-27) ----------
     The user: 「现在看过这个记录就消失了，但是我想要的是能够把这个留存下来，下次复习的时候还能再看一看」.
     What AI said after a practice, as it was then: the server's own copy of each AI answer (/api/next/history; nothing
     new is stored for this). Three ways in: 「之前练过」 under a practice page's main button (historyFold), 我的 → 进步 →
     练习记录 (#/history), and a mistake card's 「来自 …」 (#/history/<id>, the card is B2's). A record is not reviewed
     on its own: what was corrected is in 错题本 already, a sentence worth keeping is saved into 单词 (收藏).
     D2's rules: only the learner sees it; every record and all of them can be deleted, and deleting asks whether the
     mistakes it left go too (two buttons alike, no default); no recording is kept, so none is played. */
  const HIST_TYPES = [['', '全部'], ['speaking', '口语'], ['writing', '写作'], ['translation', '翻译'], ['assess', '测评'], ['exam', '考试']];
  // D2's sentence. The 180 days are the server's: AI results older than that are cleared every day (ai_quota, #525).
  const HIST_KEEP = '练习记录保存 180 天；录音不保存。';
  const HIST_GO = '<svg class="hist-go" viewBox="0 0 12 12" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4.5 2.5 8 6 4.5 9.5"/></svg>';
  const HIST_DOWN = '<svg class="hist-down" viewBox="0 0 12 12" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M2.5 4.5 6 8l3.5-3.5"/></svg>';
  const HIST_MARK = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round" aria-hidden="true"><path d="M7 4h10a1 1 0 0 1 1 1v15l-6-3.6L6 20V5a1 1 0 0 1 1-1z"/></svg>';
  // 「今天」, 「11月6日」, another year with its year; from the server's day (2026-11-06, Beijing time)
  function histDate(day) {
    const p = String(day || '').split('-').map(Number), n = new Date();
    if (p.length !== 3 || !p[0]) return '';
    if (n.getFullYear() === p[0] && n.getMonth() + 1 === p[1] && n.getDate() === p[2]) return '今天';
    return `${p[0] === n.getFullYear() ? '' : p[0] + '年'}${p[1]}月${p[2]}日`;
  }
  // A row: in the whole list it says which practice (口语情景 · 在咖啡店点单); under one practice, which time (11月6日 · 第 1 次)
  function histRow(x, whole) {
    const name = whole ? x.label + (x.title ? ' · ' + x.title : '') : histDate(x.day) + (x.round ? ` · 第 ${x.round} 次` : '');
    return `<a class="hist-row" href="${esc(x.open || '#/history/' + encodeURIComponent(x.id))}" data-tap="history-row"><span class="t"><b>${esc(name)}</b>${x.note ? `<span>${esc(x.note)}</span>` : ''}</span>${x.score ? `<span class="v">${esc(x.score)}</span>` : ''}${HIST_GO}</a>`;
  }
  const histGroups = items => {
    const by = [];
    items.forEach(x => { const g = by[by.length - 1]; if (g && g.day === x.day) g.items.push(x); else by.push({ day: x.day, items: [x] }); });
    return by.map(g => `<p class="hist-day">${histDate(g.day)}</p><div class="hist-list">${g.items.map(x => histRow(x, true)).join('')}</div>`).join('');
  };
  // 「之前练过」 under a practice page's main button: nothing until the learner has practised this before (能点的才有内容)
  async function historyFold(host, kind, pack) {
    if (!S.user || !host) return;
    let r;
    try { r = await api(`/api/next/history?kind=${encodeURIComponent(kind)}&pack=${encodeURIComponent(pack)}&limit=3`); } catch (e) { return; }
    if (!r || !r.total || !r.items.length || !host.isConnected) return;
    host.innerHTML = `<details class="hist-fold"><summary data-tap="history-fold"><span>之前练过</span><span class="r">${r.total} 次 · 最近 ${histDate(r.items[0].day)}</span>${HIST_DOWN}</summary>
      <div class="hist-list">${r.items.map(x => histRow(x)).join('')}${r.total > r.items.length ? `<a class="hist-more" href="#/history">全部 ${r.total} 次 ${HIST_GO}</a>` : ''}</div></details>`;
  }
  // 删除: one record (id) or all of them. The question about the mistakes has no default (D2, the user 2026-11-27).
  function historyDelete(rec, after) {
    const one = !!rec, n = one && rec.fixes ? rec.fixes.kept : 0;
    openSheet(`<div class="stack hist-del"><h2 class="h2" id="sheetTitle">${one ? `删除${histDate(rec.day)}的这次记录？` : '删除全部练习记录？'}</h2>
      <p>${one ? '删掉以后，这一次的反馈和你的回答就看不到了，不能恢复；分数会留着，用来算进步。' : '删掉以后，以前每一次的反馈和你的回答就都看不到了，不能恢复；分数会留着，用来算进步。测评和考试的成绩不在这里面。'}</p>
      ${!one || n ? `<p class="q">${one ? `这次练习留下的 ${n} 条错题也一起删掉吗？` : '这些练习留下的错题也一起删掉吗？'}</p>
        <div class="hist-two"><button class="btn" type="button" data-m="1">一起删</button><button class="btn" type="button" data-m="0">${one ? '只删这条记录' : '只删记录'}</button></div>`
        : '<button class="btn block" type="button" data-m="0">删除</button>'}
      <button class="btn ghost block" type="button" data-close>先不删</button><p class="tiny" id="histDelErr" role="alert"></p></div>`, card => {
      card.querySelectorAll('[data-m]').forEach(b => b.onclick = async () => {
        card.querySelectorAll('button').forEach(x => { x.disabled = true; });
        try {
          await api(one ? '/api/next/history/delete' : '/api/next/history/delete-all', one ? { id: rec.id, mistakes: b.dataset.m === '1' } : { mistakes: b.dataset.m === '1' });
          closeSheet(); toast(one ? '这次记录已删除' : '练习记录已全部删除'); after();
        } catch (e) { card.querySelectorAll('button').forEach(x => { x.disabled = false; }); card.querySelector('#histDelErr').textContent = e.message; }
      });
    });
  }
  // #/history: every record, newest first, a day a block; the kinds across the top
  async function historyView() {
    let type = historyView.type || '', items = [], more = false, total = 0;
    const load = async before => {
      const r = await api('/api/next/history?limit=20' + (type ? '&type=' + type : '') + (before ? '&before=' + before : ''));
      items = before ? items.concat(r.items) : r.items; more = !!r.more; total = r.total || 0;
    };
    const list = () => items.length ? histGroups(items)
      : `<div class="empty"><p>${type ? '这一类还没有记录。' : '还没有记录。口语情景、复述、作文、翻译这些练完以后，AI 的反馈会留在这里，以后还能再看。'}</p></div>`;
    const draw = () => {
      view.innerHTML = `<div><a class="link small hit44" href="#/me">← 我的</a></div>
        <div class="hist-head"><h1 class="h1">练习记录</h1><p>AI 给过反馈的练习都在这里</p></div>
        <div class="hist-chips" role="radiogroup" aria-label="按类型看">${HIST_TYPES.map(([id, l]) => `<button class="hist-chip" type="button" role="radio" aria-checked="${id === type}" data-type="${id}">${l}</button>`).join('')}</div>
        <div id="histList">${list()}</div>
        ${more ? `<button class="hist-more" id="histMore" type="button">更早的 ${HIST_DOWN}</button>` : ''}
        ${total ? `<p class="hist-foot">${HIST_KEEP}只有你自己看得到。<br><button class="hist-link" id="histAll" type="button" data-tap="history-delete-all">删除全部记录</button></p>` : ''}`;
      view.querySelectorAll('.hist-chip').forEach(b => b.onclick = async () => { type = historyView.type = b.dataset.type; try { await load(); } catch (e) { toast(e.message); return; } draw(); });
      const m = document.getElementById('histMore');
      if (m) m.onclick = async () => { m.disabled = true; try { await load(items[items.length - 1].at); } catch (e) { m.disabled = false; toast(e.message); return; } draw(); };
      const all = document.getElementById('histAll');
      if (all) all.onclick = () => historyDelete(null, async () => { try { await load(); } catch (e) { /* the page as it is */ } draw(); });
    };
    await load(); draw();
  }
  // #/history/<id>: that time's feedback as it was. The blocks follow the practice page's own names (说得好的句子,
  // 可以写得更好, 原文要点, 示范); 改过的地方 says how many are in 错题本 now (D2: by the real count, they may be fewer).
  async function historyRecord(id) {
    const r = await api('/api/next/history/' + encodeURIComponent(id));
    const x = r.result || {}, fixes = (x.fixes || x.changes || []).filter(f => f && f.to), kept = r.fixes ? r.fixes.kept : 0;
    const saved = new Set((r.saved || []).map(s => String(s).toLowerCase()));
    const keep = t => `<button class="hist-keep${saved.has(t.toLowerCase()) ? ' on' : ''}" type="button" data-keep="${esc(t)}"${saved.has(t.toLowerCase()) ? ' disabled' : ''}>${HIST_MARK}<span>${saved.has(t.toLowerCase()) ? '已收藏' : '收藏'}</span></button>`;
    const blk = (h, right, body) => `<section class="hist-blk"><div class="hist-blk-h"><h2>${h}</h2>${right ? `<span>${right}</span>` : ''}</div>${body}</section>`;
    const pair = f => `<div class="hist-fix">${f.from && f.from !== '—' ? `<div class="a" lang="en">${esc(f.from)}</div>` : ''}<div class="b" lang="en">${esc(f.to)}</div>${f.why ? `<div class="w">${esc(f.why)}</div>` : ''}</div>`;
    const summary = x.summary || x.comment || [x.accuracy, x.fluency].filter(Boolean).join(' ');
    const said = r.said && r.said.length ? r.said : x.transcript ? [x.transcript] : [];
    const points = x.points || [], good = x.good || [], better = (x.better || []).filter(b => b && b.to);
    const versions = (x.versions || []).filter(v => v && v.text);  // 仿写: other ways to write it
    view.innerHTML = `<div><a class="link small hit44" href="#/history">← 练习记录</a></div>
      <div class="hist-head"><span class="kicker"><span>${esc(r.label)}${r.title ? ' · ' + esc(r.title) : ''}</span>${r.round ? ` <span>· 第 ${r.round} 次</span>` : ''}</span><h1 class="h1">${histDate(r.day)}的练习</h1>${aiMark('这是当时的反馈，仅供参考')}</div>
      ${blk('这次的结果', r.minutes ? `约 ${r.minutes} 分钟` : '', `${r.score ? `<p class="hist-big">${esc(r.score)}</p>` : ''}${r.note ? `<p class="hist-note">${esc(r.note)}</p>` : ''}`)}
      ${summary ? blk('AI 的总结', '', `<p class="hist-p">${esc(summary)}</p>`) : ''}
      ${points.length ? blk('原文要点', `讲到 ${points.filter(p => p.covered).length} / ${points.length} 个`, points.map(p => `<p class="hist-pt${p.covered ? ' ok' : ''}"><i aria-hidden="true">${p.covered ? '✓' : '·'}</i><span>${esc(p.point)}</span><span class="sr-only">${p.covered ? '讲到了' : '没讲到'}</span></p>`).join('')) : ''}
      ${good.length ? blk('说得好的句子', '收藏后会在单词里复习', good.map(g => `<div class="hist-say"><span class="t"><b lang="en">${esc(g)}</b></span>${keep(g)}</div>`).join('')) : ''}
      ${fixes.length ? blk('改过的地方', `${fixes.length} 处${kept ? (kept >= fixes.length ? ' · 都在错题本里' : ` · 其中 ${kept} 处在错题本里`) : ''}`,
        fixes.map(pair).join('') + (kept ? `<a class="hist-more" href="#/cards/mistake" data-tap="history-mistakes">去错题本复习这 ${kept} 处 ${HIST_GO}</a>` : '')) : ''}
      ${better.length ? blk('可以写得更好', '收藏后会在单词里复习', better.map(b => `<div class="hist-say"><span class="t"><b lang="en">${esc(b.to)}</b>${b.why ? `<span>${esc(b.why)}</span>` : ''}</span>${keep(b.to)}</div>`).join('')) : ''}
      ${versions.length ? blk('可以这样写', '收藏后会在单词里复习', versions.map(v => `<div class="hist-say"><span class="t"><b lang="en">${esc(v.text)}</b>${v.why && v.why !== '—' ? `<span>${esc(v.why)}</span>` : ''}</span>${keep(v.text)}</div>`).join('')) : ''}
      ${x.reference ? blk('参考译文', '', `<p class="hist-p" lang="en">${esc(x.reference)}</p>`) : ''}
      ${x.model ? `<details class="hist-fold"><summary><span>示范</span><span class="r">AI 写的一版</span>${HIST_DOWN}</summary><div class="hist-list"><p class="hist-p" lang="en">${esc(x.model)}</p></div></details>` : ''}
      ${said.length ? `<details class="hist-fold"><summary><span>你说的话</span><span class="r">${r.said && r.said.length ? said.length + ' 句 · ' : ''}文字</span>${HIST_DOWN}</summary><div class="hist-list">${said.map(s => `<p class="hist-p" lang="en">${esc(s)}</p>`).join('')}</div></details>` : ''}
      ${r.again ? `<a class="btn primary block hist-main" href="${esc(r.again)}" data-tap="history-again">再练一次</a>` : ''}
      <p class="hist-foot">${HIST_KEEP}<br><button class="hist-link" id="histDel" type="button" data-tap="history-delete">删除这一次</button></p>`;
    view.querySelectorAll('[data-keep]').forEach(b => b.onclick = async () => {
      b.disabled = true;
      try { await api('/api/next/cards', { text: b.dataset.keep, meaning: '', context: r.title || '', pack: r.pack || null }); b.classList.add('on'); b.querySelector('span').textContent = '已收藏'; toast('已收藏，会在单词里复习'); }
      catch (e) { b.disabled = false; toast(e.message); }
    });
    document.getElementById('histDel').onclick = () => historyDelete(r, () => { location.hash = '#/history'; });
  }

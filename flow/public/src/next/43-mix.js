  /* ---------- mixed grammar rounds: several points interleaved (today's review, a confusable pair, a whole topic) ---------- */
  // Questions on different points mixed together make the learner decide which rule applies first: that decision is
  // what real use asks for, and it is what one-point-at-a-time practice never trains.
  async function mixView(kind, arg) {
    const q = kind === 'pair' ? '?pair=' + encodeURIComponent(arg) : kind === 'topic' ? '?topic=' + encodeURIComponent(arg) : kind === 'exam' ? '?exam=' + encodeURIComponent(arg) : kind === 'more' ? '?n=4' : guestQuery(true);  // more: 4 questions once 今日's plan is done (r28)
    const m = await api('/api/next/mix' + q);
    const TITLE = { due: '今天的语法复习', practice: '语法混合练习', pair: '辨析练习', topic: '这一类混着练', exam: '考点语法' };
    const intro = m.kind === 'due' ? `${m.nodes.length} 个点混在一起出题：先想清楚这题考的是哪条规则，再选。${m.left ? `还有 ${m.left} 个点明天接着练。` : ''}`
      : m.kind === 'pair' ? '两个容易混的点交替出题，做的时候先判断是哪一个。'
      : m.kind === 'practice' ? '今天没有到期要复习的点。先混着练几个你这个级别的，做对的会点亮。'
      : m.kind === 'exam' ? '这个考试常考的语法点混在一起出题，要你标出来的和到期该复习的排在前面。' : '这一类里的每个点各出一题。';
    const items = m.items, before = Object.fromEntries(m.nodes.map(n => [n.id, n.status])), after = {}, per = {};
    let i = 0, right = 0, streak = 0;
    view.innerHTML = `<div class="stack mix"><div><span class="kicker">${esc(TITLE[m.kind])}</span><h1 class="h1">${m.kind === 'pair' ? esc(m.nodes.map(n => n.title).join(' vs ')) : `${items.length} 道题，${m.nodes.length} 个点`}</h1>
        <p class="muted small">${esc(intro)}</p>${aiMark('题目和讲解由 AI 辅助编写')}</div>
      ${m.note ? `<div class="howto"><b>怎么区分</b><span class="small">${esc(m.note)}</span></div>` : ''}
      <div class="mix-dots" aria-hidden="true">${items.map(() => '<i></i>').join('')}</div>
      <div id="mixQ"></div></div>`;
    const dots = [...view.querySelectorAll('.mix-dots i')];
    function ask() {
      const it = items[i], box = document.getElementById('mixQ');
      dots.forEach((d, k) => d.classList.toggle('now', k === i));
      box.innerHTML = `<div class="q gq enter"><div class="tiny muted">第 ${i + 1} / ${items.length} 题</div><div class="prompt">${esc(it.prompt)}</div>
        ${it.options.map((o, j) => `<button class="ans" data-o="${it.map[j]}"><span class="k">${'ABCD'[j]}</span><span>${esc(o)}</span></button>`).join('')}<div class="fb" aria-live="polite"></div></div>`;
      box.querySelectorAll('.ans').forEach(b => b.onclick = () => answer(it, b, box));
      keys4(box);
    }
    function keys4(box) {
      document.onkeydown = e => { const k = Number(e.key); if (k >= 1 && k <= 4 && !e.metaKey && !e.ctrlKey) { const b = box.querySelectorAll('.ans')[k - 1]; if (b && !b.disabled) b.click(); } };
    }
    async function answer(it, b, box) {
      box.querySelectorAll('.ans').forEach(x => { x.disabled = true; });
      let r;
      try { r = await api('/api/next/node/answer', { question: it.id, choice: Number(b.dataset.o), from: m.kind === 'exam' ? 'exam' : 'mix' }); }
      catch (e) { toast(e.message); box.querySelectorAll('.ans').forEach(x => { x.disabled = false; }); return; }
      box.querySelectorAll('.ans').forEach(x => { if (Number(x.dataset.o) === r.answer) x.classList.add('right'); });
      if (!r.correct) b.classList.add('wrong');
      const p = per[it.node] = per[it.node] || { right: 0, of: 0 }; p.of++;
      if (r.correct) { right++; p.right++; streak++; } else streak = 0;
      if (r.status) after[it.node] = { status: r.status, label: r.label };
      dots[i].classList.add(r.correct ? 'ok' : 'no');
      box.querySelector('.fb').innerHTML = `<div class="${r.correct ? 'ok' : 'bad'}">${r.correct ? '✓ 对了' : '✗ 这题选错了'}${streak >= 3 ? ` · 连对 ${streak} 题` : ''}</div>
        <div class="small">${esc(r.explanation || '')}</div><div class="tiny muted">考的是：<a class="link" href="#/graph/${encodeURIComponent(it.node)}">${esc(it.node_title)}</a></div>
        <button class="btn primary block" id="mixNext">${i + 1 < items.length ? '下一题' : '看结果'}</button>`;
      announce(r.correct ? '答对了' : '答错了');
      const nx = document.getElementById('mixNext');
      nx.scrollIntoView({ block: 'nearest', behavior: REDUCED ? 'auto' : 'smooth' });  // the explanation and the next button, above the tab bar
      nx.onclick = () => { i++; if (i < items.length) ask(); else done(); };
      document.onkeydown = e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); nx.click(); } };
      nx.focus({ preventScroll: true });
    }
    function done() {
      document.onkeydown = null;
      const all = right === items.length, rows = m.nodes.filter(n => per[n.id]);
      const lit = rows.filter(n => before[n.id] !== 'solid' && (after[n.id] || {}).status === 'solid');
      const msg = all ? `全对！${S.user ? '这几个点都往后推了，到时间再抽查。' : ''}`
        : `${items.length - right} 题没做对。${S.user ? '它们明天会换一道题再来——错题是最值钱的题，弄懂一个就少一个。' : ''}`;
      view.innerHTML = `<div class="stack mix-done">${right * 2 >= items.length ? `<div class="done-burst${all ? ' all' : ''}" aria-hidden="true">${doneRing}</div>` : ''}
        <div class="tc"><span class="kicker">${esc(TITLE[m.kind])}</span><h1 class="h1">${items.length} 题做对 ${right} 题</h1><p class="small">${esc(msg)}</p>
        ${lit.length ? `<p class="small cheer">新点亮了 ${lit.length} 个点：${esc(lit.map(n => n.title).join('、'))}</p>` : ''}</div>
        <div class="plist">${rows.map((n, k) => { const a = after[n.id] || n, pr = per[n.id];
          return `<a class="nrow st st-${a.status} pop-in" data-k="${k}" href="#/graph/${encodeURIComponent(n.id)}"><i class="dot" aria-hidden="true"></i><span class="t"><b>${esc(n.title)}</b><span class="tiny muted">${esc(a.label || '')}</span></span><span class="lv">${pr.right}/${pr.of}</span><span class="go" aria-hidden="true">›</span></a>`; }).join('')}</div>
        ${S.user ? '' : '<p class="muted small">登录后，做对的点会点亮在你的语法地图里，错的会按遗忘曲线回来。</p>'}
        <div class="row center"><a class="btn" href="#/graph">语法地图</a>${m.kind === 'due' || m.kind === 'exam' ? '<a class="btn primary" href="#/">回到今日</a>' : '<button class="btn primary" id="mixAgain">再来一轮</button>'}</div></div>`;
      view.querySelectorAll('.pop-in').forEach(el => el.style.setProperty('--d', (Number(el.dataset.k) * 90 + 200) + 'ms'));
      const again = document.getElementById('mixAgain'); if (again) again.onclick = () => mixView(kind, arg);
      announce(`${items.length} 题做对 ${right} 题`);
      if (S.user) refreshHome().catch(() => {});
    }
    if (!items.length) {
      document.getElementById('mixQ').innerHTML = '<div class="empty"><p>这里暂时没有题。</p><a class="btn" href="#/graph">回到语法地图</a></div>';
      return;
    }
    ask();
  }

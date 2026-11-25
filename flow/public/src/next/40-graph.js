  /* ---------- knowledge graph ---------- */
  const STATUS_ORDER = ['solid', 'used', 'met', 'watch', 'untouched'];
  const LEVEL_ORDER = ['A2', 'B1', 'B2', 'C1'];
  // The point to practise next: one flagged in their writing or a wrong answer first, then one whose spaced re-check
  // has come (any level), then at the learner's level one they have met but not yet checked, then a new one; easier first.
  function nextPoint(g) {
    const all = g.topics.flatMap(t => t.nodes.map(n => ({ ...n, topic: t.title })));
    const rank = n => n.status === 'watch' ? 0 : n.due ? 1 : { met: 2, used: 3, untouched: 4 }[n.status];
    const open = all.filter(n => n.status === 'watch' || n.due || (n.focus && n.status !== 'solid'));
    open.sort((a, b) => rank(a) - rank(b) || LEVEL_ORDER.indexOf(a.level) - LEVEL_ORDER.indexOf(b.level) || b.materials - a.materials);
    return open[0] || all.find(n => n.status !== 'solid') || null;
  }
  // The learning route: the 44 points in the order to learn them, one line per level, like stops on a metro line.
  // Only the level being learnt is open (the one with the next stop, else the learner's level); the others fold.
  const BAND = { A2: '入门', B1: '进阶', B2: '中高级', C1: '高级' };
  function routeHTML(g, next) {
    const openBand = (next && (g.route.find(b => b.nodes.some(n => n.id === next.id)) || {}).band) || (g.route.some(b => b.band === g.level) ? g.level : g.route[0] && g.route[0].band);
    return `<div class="route">${g.route.map(b => {
      const lit = b.nodes.filter(n => n.status !== 'untouched').length;
      return `<details class="rband fold"${b.band === openBand ? ' open' : ''}><summary class="rband-h"><b>${b.band}</b><span class="small muted">${BAND[b.band]} · ${b.nodes.length} 个点 · 已点亮 ${lit}</span></summary>
        <ol class="rline">${b.nodes.map((n, k) => { const here = next && n.id === next.id;
          return `<li class="rnode st st-${n.status}${n.status !== 'untouched' ? ' lit' : ''}${here ? ' here' : ''}" data-k="${k}"><a href="#/graph/${encodeURIComponent(n.id)}">
            <i class="dot" aria-hidden="true"></i><span class="t">${esc(n.title)}${here ? '<span class="here-tag">下一站</span>' : ''}${n.due ? '<span class="due-tag">该复习</span>' : ''}</span><span class="go" aria-hidden="true">›</span></a></li>`; }).join('')}</ol></details>`;
    }).join('')}</div>`;
  }
  async function graphView() {
    const g = await api('/api/next/graph' + guestQuery(true));
    const s = g.summary, next = nextPoint(g);
    const focusAll = g.topics.flatMap(t => t.nodes).filter(n => n.focus), focusSolid = focusAll.filter(n => n.status === 'solid').length;
    view.innerHTML = `<div><h1 class="h1">知识图谱</h1>
        <p class="muted small">${g.total} 个语法点，分成 ${g.topics.length} 类。读到、用出来、做题做对都会点亮它；AI 在你写作里发现的问题也会标在这里。</p></div>
      ${next ? `<div class="gnext"><div class="small muted">「${esc(g.level)}」现在的重点 ${focusAll.length} 个，已验证 ${focusSolid} 个</div>
        <a class="btn primary block go-next" href="#/graph/${encodeURIComponent(next.id)}">下一个：${esc(next.title)}<span aria-hidden="true">→</span></a>
        <div class="tiny muted">${next.status === 'watch' ? '你在写作或做题里在这里出过错，先补上它。' : next.due ? '按遗忘曲线该复习它了：做 4 道题，记得更牢。' : next.status === 'untouched' ? '先看讲解，再做几道题验证。' : '你已经读到过它，做几道题把它变成“已验证”。'}</div>
        ${s.due > 1 ? `<div class="tiny muted">一共 ${s.due} 个点该复习了，每天做一个就好。</div>` : ''}</div>` : ''}
      ${s.solid + s.used + s.met + s.watch < 5 ? `<a class="card flat place-cta" href="#/placement"><b>不知道从哪开始？</b><span class="small muted">做 16 道题的语法小测，3–6 分钟：给你一个起点等级，做对的点直接点亮。</span></a>` : ''}
      <div class="seg two section" role="tablist" aria-label="看法"><button role="tab" data-gv="route">学习路线</button><button role="tab" data-gv="all">全部 ${g.total} 个点</button></div>
      <div id="gRoute">${routeHTML(g, next)}</div><div id="gAll">
      <div class="gsum section">${[['solid', '已验证'], ['used', '用出来过'], ['met', '读到过'], ['watch', '要留意']].map(([k, l]) => `<div class="st st-${k}"><b>${s[k]}</b><span>${l}</span></div>`).join('')}</div>
      <div class="tgrid section" role="list" aria-label="13 类语法">${g.topics.map(t => {
        const lit = t.nodes.filter(n => n.status !== 'untouched').length, watch = t.nodes.some(n => n.status === 'watch');
        const focus = t.nodes.some(n => n.focus && n.status !== 'solid');
        return `<a class="tile${focus ? ' focus' : ''}" role="listitem" href="#/graph" data-topic="${esc(t.id)}" aria-label="${esc(t.title)}：${lit} / ${t.nodes.length} 个点亮${watch ? '，有要留意的' : ''}">
          <span class="ring" data-p="${Math.round(lit / t.nodes.length * 100)}"><b>${lit}/${t.nodes.length}</b>${watch ? '<i class="warn" aria-hidden="true"></i>' : ''}</span><span class="tl">${esc(t.title)}</span></a>`;
      }).join('')}</div>
      <div class="glegend">${STATUS_ORDER.map(k => `<span class="st st-${k}">${esc(g.labels[k])}</span>`).join('')}<span class="fz">${esc(g.level)} 重点</span></div>
      <div class="topic-list section">${g.topics.map(t => `<section class="topic" id="topic-${esc(t.id)}"><div class="row between"><h2 class="h2">${esc(t.title)}</h2><span class="tiny muted">${t.nodes.filter(n => n.status !== 'untouched').length} / ${t.nodes.length}</span></div>
        <div class="plist">${t.nodes.map(n => `<a class="nrow st st-${n.status}${n.focus ? ' focus' : ''}" href="#/graph/${encodeURIComponent(n.id)}"><i class="dot" aria-hidden="true"></i>
          <span class="t"><b>${esc(n.title)}</b><span class="tiny muted">${esc(n.label)}${n.due ? ' · <span class="due-tag">该复习</span>' : ''}${n.materials ? ` · ${n.materials} 篇材料` : ''}</span></span><span class="lv">${esc(n.level || '')}</span><span class="go" aria-hidden="true">›</span></a>`).join('')}</div></section>`).join('')}</div>
      </div>${S.user ? '' : '<p class="muted small section">登录后，你读过、写过、做对的内容会实时点亮这张图。</p>'}`;
    const show = gv => {
      document.getElementById('gRoute').hidden = gv !== 'route'; document.getElementById('gAll').hidden = gv === 'route';
      view.querySelectorAll('[data-gv]').forEach(b => b.setAttribute('aria-selected', String(b.dataset.gv === gv)));
      try { localStorage.setItem('flow-graph-view', gv); } catch (e) { /* private mode */ }
      if (gv === 'route') view.querySelectorAll('.rnode').forEach(li => { li.classList.remove('drawn'); li.style.setProperty('--d', (Number(li.dataset.k) * 45) + 'ms'); requestAnimationFrame(() => requestAnimationFrame(() => li.classList.add('drawn'))); });
    };
    let gv = 'route'; try { gv = localStorage.getItem('flow-graph-view') === 'all' ? 'all' : 'route'; } catch (e) { /* private mode */ }
    view.querySelectorAll('[data-gv]').forEach(b => b.onclick = () => show(b.dataset.gv));
    show(gv);
    view.querySelectorAll('details.rband').forEach(d => d.addEventListener('toggle', () => {
      if (d.open) d.querySelectorAll('.rnode').forEach(li => { li.classList.remove('drawn'); requestAnimationFrame(() => requestAnimationFrame(() => li.classList.add('drawn'))); });
    }));
    // CSP forbids inline style attributes, so the ring fill is set through the CSSOM.
    view.querySelectorAll('.tile .ring').forEach(r => r.style.setProperty('--p', r.dataset.p + '%'));
    view.querySelectorAll('.tile').forEach(a => a.onclick = e => {
      e.preventDefault();
      const sec = document.getElementById('topic-' + a.dataset.topic); if (sec) scrollToEl(sec);
    });
  }
  function scrollToEl(el) {
    const head = document.getElementById('bar').getBoundingClientRect().bottom;
    window.scrollTo({ top: window.scrollY + el.getBoundingClientRect().top - Math.max(0, head) - 12, behavior: REDUCED ? 'auto' : 'smooth' });
  }
  async function nodeView(nid) {
    const n = await api('/api/next/node?id=' + encodeURIComponent(nid) + guestQuery(false));
    const pg = n.page && n.page.status === 'ready' ? n.page : null;
    const stats = `读到过 ${n.met} 篇 · 用出来 ${n.used} 次${n.flags ? ' · 写作中被指出 ' + n.flags + ' 次' : ''}${n.evidence ? ' · 做题：' + esc(n.evidence) : ''}`;
    const choice = (q, i, kind) => `<div class="q gq" data-kind="${kind}" data-i="${i}"><div class="prompt">${esc(q.prompt)}</div>
      ${q.options.map((o, j) => `<button class="ans" data-o="${q.map ? q.map[j] : j}"><span class="k">${'ABCD'[j]}</span><span>${esc(o)}</span></button>`).join('')}<div class="fb" aria-live="polite"></div></div>`;
    const reviewText = r => !r ? '' : r.is_due ? '按遗忘曲线，今天该复习这个点了' : `下次复习：${r.in_days} 天后（第 ${r.step + 1} / ${r.rungs} 轮）`;
    view.innerHTML = `<div><a class="link small" href="#/graph">← 知识图谱</a></div>
      <div class="node-head"><span class="kicker">${esc(n.topic)} · ${esc(n.level || '')}${n.focus ? ' · 你现在的重点' : ''}</span><h1 class="h1">${esc(n.title)}</h1>
        <div class="row"><span class="node-chip st st-${n.status}" id="nodeStatus">${esc(n.label)}</span>${n.practice.length ? `<button class="btn small" id="toPractice">做 ${n.practice.length} 题验证 ↓</button>` : ''}</div><div class="tiny muted">${stats}</div><div class="tiny muted" id="nodeReview">${esc(reviewText(n.review))}</div></div>
      <div class="lesson section stack-s">${aiMark('讲解和练习题由 AI 辅助编写')}
        <p class="goal">${esc(pg ? pg.goal : n.lesson)}</p>
        ${pg ? `<ol class="steps-list">${pg.steps.map(x => `<li>${esc(x)}</li>`).join('')}</ol>` : (n.example ? `<div class="text small">${esc(n.example)}</div>` : '')}
      </div>
      ${n.l1 ? `<div class="l1 section"><div class="kicker">中文思维陷阱</div><p class="small">${esc(n.l1.why)}</p>
        <div class="l1-rows"><div class="zh"><span class="tiny muted">中文</span>${esc(n.l1.zh)}</div><div class="bad"><span aria-label="常见错误">✗</span> ${esc(n.l1.wrong)}</div><div class="good"><span aria-label="正确">✓</span> ${esc(n.l1.right)}</div></div></div>` : ''}
      ${pg ? `<div class="section stack-s"><h2 class="h2">对比着看</h2><div class="plist">${pg.contrast.map(([en, zh]) => `<div class="crow"><button class="icon-btn" data-say="${esc(en)}" aria-label="朗读">${ICON.speak}</button><span><span class="en">${esc(en)}</span><span class="tiny muted">${esc(zh)}</span></span></div>`).join('')}</div></div>
      <div class="section stack-s"><h2 class="h2">常见错误</h2><div class="stack-s">${pg.pitfalls.map(([bad, good, why]) => `<div class="pit"><div class="bad"><span aria-label="错误">✗</span> ${esc(bad)}</div><div class="good"><span aria-label="正确">✓</span> ${esc(good)}</div><div class="tiny muted">${esc(why)}</div></div>`).join('')}</div></div>
      <div class="section stack-s"><div class="section-head"><h2 class="h2">先试一题</h2><span class="tiny muted">有提示，不计入验证</span></div>${choice(pg.guided, 0, 'guided')}</div>` : ''}
      ${n.practice.length ? `<div class="section stack-s" id="practice"><div class="section-head"><h2 class="h2">验证一下</h2><span class="tiny muted">${S.user ? '做对会点亮这个点；做错的会进错题本' : '登录后成绩会记进你的图谱'}</span></div>
        ${pg ? `<p class="small muted">做题前先问自己：${esc(pg.clue)}</p>` : ''}<div class="stack">${n.practice.map((q, i) => choice(q, i, 'check')).join('')}</div><div id="pscore" class="small"></div>
        <button class="btn" id="again" hidden>再来一组（题库 10 题，随机抽 4 题）</button></div>` : ''}
      <div class="section stack-s rel"><h2 class="h2">和它相连的点</h2>
        <div class="rel-flow">${n.prereq ? `<div class="rel-step"><span class="tiny muted">先学</span>${nodeChip(n.prereq)}</div><i class="rel-arrow" aria-hidden="true"></i>` : ''}
          <div class="rel-step me"><span class="tiny muted">现在</span><span class="node-chip st st-${n.status}">${esc(n.title)}</span></div>
          ${n.unlocks.length ? `<i class="rel-arrow" aria-hidden="true"></i><div class="rel-step"><span class="tiny muted">接下来</span><span class="chips">${n.unlocks.map(u => nodeChip(u)).join('')}</span></div>` : ''}</div>
        ${n.related.confusable.length ? `<div class="stack-s"><div class="kicker">容易和它混</div>${n.related.confusable.map(x => `<div class="confuse"><div class="row between">${nodeChip(x)}<a class="btn small" href="#/mix/pair/${encodeURIComponent(n.id + ',' + x.id)}">辨析练习</a></div><div class="tiny muted">${esc(x.how)}</div></div>`).join('')}</div>` : ''}
        ${n.related.together.length ? `<div class="stack-s"><div class="kicker">常和它一起出现</div><div class="chips">${n.related.together.map(x => nodeChip(x)).join('')}</div><span class="tiny muted">在同一篇材料里出现得最多的点，读到时可以留意它们怎么配合。</span></div>` : ''}</div>
      ${n.notes.length ? `<div class="stack-s section"><h2 class="h2">AI 在你写作里看到的</h2>${n.notes.map(x => `<div class="knote"><span class="small">${x.kind === 'flag' ? '需要留意：' : '用对了'}${esc((x.detail.split('|')[1] || ''))}</span><span class="tiny muted">${new Date(x.created * 1000).toLocaleDateString('zh-CN')}</span></div>`).join('')}</div>` : ''}
      ${n.examples.length ? `<div class="stack-s section"><h2 class="h2">在真实句子里看它</h2>${n.examples.map(x => `<a class="ex-quote" href="#/m/${encodeURIComponent(x.pack)}/read"><span>${esc(x.quote)}</span><div class="small muted">${esc(x.explanation)}</div></a>`).join('')}</div>` : ''}
      ${n.materials.length ? `<div class="section"><div class="section-head"><h2 class="h2">在文章里练它</h2></div><div class="grid-list">${n.materials.map(m => miniCard(m)).join('')}</div></div>` : ''}`;
    view.querySelectorAll('[data-say]').forEach(b => b.onclick = () => TTS.say(b.dataset.say));
    const jump = view.querySelector('#toPractice'); if (jump) jump.onclick = () => scrollToEl(view.querySelector('#practice'));
    const guided = pg ? pg.guided : null;
    let right = 0, answered = 0;
    view.querySelectorAll('.gq').forEach(box => box.querySelectorAll('.ans').forEach(b => b.onclick = async () => {
      if (box.dataset.done) return;
      const o = +b.dataset.o, fb = box.querySelector('.fb');
      let ok, answer, why;
      if (box.dataset.kind === 'guided') {  // learning support: checked here, never sent as evidence
        ok = o === guided.answer; answer = guided.answer; why = ok ? guided.explanation : '提示：' + guided.scaffold;
        if (!ok) { b.classList.add('wrong'); fb.textContent = why; return; }  // a hint and another go
      } else {
        const q = n.practice[+box.dataset.i];
        try { const r = await api('/api/next/node/answer', { question: q.id, choice: o }); ok = r.correct; answer = r.answer; why = r.explanation;
          if (r.label) { const st = view.querySelector('#nodeStatus'), was = st.className; st.className = 'node-chip st st-' + r.status; st.textContent = r.label;
            if (r.status === 'solid' && !/st-solid/.test(was)) { st.classList.add('lit-up'); toast('点亮了！「' + n.title + '」做题已验证'); } }
          if (r.review) view.querySelector('#nodeReview').textContent = ok ? reviewText(r.review) : '做错了：明天会再练一次这个点'; }
        catch (e) { toast(e.message); return; }
        answered++; if (ok) right++;
        const sc = view.querySelector('#pscore');
        if (answered === n.practice.length) {
          sc.textContent = `${n.practice.length} 题做对 ${right} 题。${right === n.practice.length ? (S.user ? '这个点可以算掌握了，到时间会提醒你再抽查一次。' : '这个点可以算掌握了。') : (S.user ? '错的题已经放进错题本，会按遗忘曲线再出现。' : '')}`;
          const again = view.querySelector('#again'); again.hidden = false; again.onclick = () => { const y = window.scrollY; route(true).then(() => window.scrollTo(0, y)); };
        }
      }
      box.dataset.done = '1';
      box.querySelectorAll('.ans').forEach(x => { x.disabled = true; if (+x.dataset.o === answer) x.classList.add('right'); });
      if (!ok) b.classList.add('wrong');
      fb.textContent = (ok ? '✓ ' : '✗ ') + (why || '') + (!ok && box.dataset.kind === 'check' && S.user ? ' 错题是最值钱的题：明天换一道题再考你。' : '');
      announce(ok ? '答对了' : '答错了');
    }));
  }

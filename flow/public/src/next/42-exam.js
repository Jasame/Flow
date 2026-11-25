  /* ---------- exam practice: a timed set at 中考 … 专八 / IELTS difficulty ---------- */
  const mmss = s => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
  async function examView(pick) {
    const o = await api('/api/next/exam');
    // 考试冲刺 (42-sprint.js): with an exam set, the page opens on it; another exam opens in the list as before.
    let cur = null;
    const pickList = list => list.length ? `<div class="exam-pick choice">${list.map(e => `<a class="opt" href="#/exam/${e.id}" aria-pressed="${cur && cur.id === e.id}"><span class="l">${esc(e.title)}</span>
        <span class="d">${esc(e.blurb)}</span><span class="tiny muted">约 ${e.minutes} 分钟${e.history.length ? ` · 上次 ${e.history[e.history.length - 1].pct}%` : ''}</span></a>`).join('')}</div>` : '';
    if (o.goal && (!pick || pick === o.goal.exam) && o.exams.some(e => e.id === o.goal.exam)) return sprintHub(o, pickList);
    cur = o.exams.find(e => e.id === pick) || null;
    // The chosen exam opens right under its own card (with eight exams, a block under the list was a scroll away): the
    // list is cut after it, so the details sit between the two halves and keep their own button styles.
    const at = cur ? o.exams.indexOf(cur) : o.exams.length - 1;
    const detail = cur ? `<div class="stack-s exam-cur" id="examCur"><h2 class="h2">${esc(cur.title)}</h2>
        <ul class="steps-list small"><li>词汇 10 题：${esc(cur.book_title)}里的词，选中文意思</li><li>语法 8 题：这个考试常考的语法点</li><li>阅读 2 篇短文，4 题</li></ul>
        ${cur.trend.length ? `<div class="stack-s"><span class="tiny muted">成绩走势</span>${trendHTML(cur.trend)}</div>` : ''}
        <button class="btn primary block" id="exStart">开始一套（约 ${cur.minutes} 分钟）</button>
        ${S.user ? (o.plan && o.plan.book === cur.book ? `<p class="tiny muted">你现在就在用「${esc(cur.book_title)}」背单词（${cur.words} 词）。</p>` :
          `<div class="row"><button class="btn small" id="exBook">改用「${esc(cur.book_title)}」背单词</button><span class="tiny muted">${cur.words} 词，按遗忘曲线每天背</span></div>`) :
          '<p class="tiny muted">登录后成绩会保存，语法错题进错题本，没认出的词可以一键加进单词本。</p>'}
        ${S.user ? `<button class="btn small" type="button" id="exGoal" data-tap="exam-goal">${o.goal ? '改成我的考试' : '设为我的考试'}</button>` : ''}
        ${typesHTML(cur.id, cur.types, o.types_note)}</div>` : '';
    // Signed in without an exam: one line says what setting it gives.
    const invite = S.user && !o.goal ? `<div class="card sunk stack-s sp-invite"><b>在准备哪个考试？</b><span class="small">设好考试和日期，这一页就是你的备考主页：倒计时、每天该背多少词、成绩走势和题型专练。</span>
        <div><button class="btn small primary" type="button" id="exInvite" data-tap="exam-goal">设定我的考试</button></div></div>` : '';
    view.innerHTML = `<div class="stack"><div><span class="kicker">考试练习</span><h1 class="h1">按考试难度练一套</h1>
        <p class="muted small">${esc(o.note)}</p></div>
      ${invite}${cur ? '' : '<p class="muted small">选一个考试开始。每套约 12–20 分钟，每周做一套就能看到变化。</p>'}
      ${pickList(o.exams.slice(0, at + 1))}${detail}${pickList(o.exams.slice(at + 1))}</div>`;
    drawTrends();
    const inv = document.getElementById('exInvite'); if (inv) inv.onclick = () => examGoalSheet(() => examView());
    if (!cur) return;
    requestAnimationFrame(() => { const d = document.getElementById('examCur'); if (d && d.getBoundingClientRect().bottom > innerHeight) d.scrollIntoView({ block: 'nearest', behavior: REDUCED ? 'auto' : 'smooth' }); });
    document.getElementById('exStart').onclick = () => examPaper(cur.id);
    const mine = document.getElementById('exGoal');
    if (mine) mine.onclick = async () => {
      try { await api('/api/next/exam/goal', { exam: cur.id, date: '' }); await refreshHome(); toast(`我的考试：${cur.short}。填上日期就能倒计时`); examView(cur.id); }
      catch (e) { toast(e.message); }
    };
    const book = document.getElementById('exBook');
    if (book) book.onclick = async () => {
      const p = o.plan || { daily_new: 10, retention: 0.9 };
      try { await api('/api/next/vocab/plan', { book: cur.book, daily_new: p.daily_new, retention: p.retention }); toast(`已改用「${cur.book_title}」，明天起每天背 ${p.daily_new} 个新词`); examView(pick); }
      catch (e) { toast(e.message); }
    };
  }
  async function examPaper(exam) {
    const p = await api('/api/next/exam/paper', { exam });
    const ans = { vocab: [], grammar: [], reading: [] };
    const started = Date.now();
    let n = 0;
    const q = (key, i, prompt, options, map, sub) => {
      const k = n++;
      return `<div class="q gq" data-key="${key}" data-i="${i}"><div class="prompt">${k + 1}. ${prompt}</div>${sub || ''}
        ${options.map((x, j) => `<button class="ans" data-o="${map ? map[j] : j}"><span class="k">${'ABCD'[j]}</span><span>${esc(x)}</span></button>`).join('')}</div>`;
    };
    const part = pt => {
      if (pt.key === 'vocab') return pt.items.map((x, i) => q('vocab', i, `<b class="en">${esc(x.word)}</b>`, x.options, null, x.phonetic ? `<div class="tiny muted">${esc(x.phonetic)}</div>` : '')).join('');
      if (pt.key === 'grammar') return pt.items.map((x, i) => q('grammar', i, esc(x.prompt), x.options, x.map)).join('');
      let i = 0;
      return pt.passages.map(ps => `<article class="stack-s"><h3 class="h3">${esc(ps.title)} ${aiTag()}</h3><div class="exam-passage">${esc(ps.body)}</div>
        ${ps.items.map(x => q('reading', i++, esc(x.prompt), x.options)).join('')}</article>`).join('');
    };
    const total = p.parts.reduce((s, pt) => s + (pt.items ? pt.items.length : pt.passages.reduce((a, ps) => a + ps.items.length, 0)), 0);
    view.innerHTML = `<div class="stack"><div class="exam-bar"><b>${esc(p.title)} · 练习</b><span class="clock" id="exClock" aria-live="off">0:00</span></div>
      ${p.parts.map(pt => `<section class="exam-part"><h2 class="h2">${esc(pt.title)}</h2><p class="tiny muted">${esc(pt.hint)}</p>${pt.key === 'grammar' ? aiMark('题目和解析由 AI 辅助编写') : ''}${part(pt)}</section>`).join('')}
      <button class="btn primary block" id="exDone">交卷</button><p class="tiny muted">建议 ${p.minutes} 分钟内完成；超时也可以交卷，只是会标出来。</p></div>`;
    const clock = document.getElementById('exClock');
    view.querySelector('.exam-bar').style.top = (bar.offsetHeight + 6) + 'px';  // just under the app's top bar, whatever its height
    const tick = setInterval(() => {
      if (!document.body.contains(clock)) { clearInterval(tick); return; }
      const s = Math.round((Date.now() - started) / 1000); clock.textContent = mmss(s); clock.classList.toggle('late', s > p.minutes * 60);
    }, 1000);
    view.querySelectorAll('.gq').forEach(box => box.querySelectorAll('.ans').forEach(b => b.onclick = () => {
      box.querySelectorAll('.ans').forEach(x => x.classList.toggle('chosen', x === b));
      ans[box.dataset.key][+box.dataset.i] = +b.dataset.o;
    }));
    let warned = false;
    document.getElementById('exDone').onclick = async () => {
      const done = ['vocab', 'grammar', 'reading'].reduce((s, k) => s + ans[k].filter(x => x !== undefined && x !== null).length, 0);
      const btn = document.getElementById('exDone');
      if (done < total && !warned) { warned = true; btn.textContent = `还有 ${total - done} 题没做，再点一次交卷`; return; }
      btn.disabled = true;
      const fill = (a, len) => Array.from({ length: len }, (_, i) => a[i] === undefined ? null : a[i]);
      const lens = { vocab: 0, grammar: 0, reading: 0 };
      p.parts.forEach(pt => { lens[pt.key] = pt.items ? pt.items.length : pt.passages.reduce((a, ps) => a + ps.items.length, 0); });
      try {
        const r = await api('/api/next/exam/submit', { paper: p.paper, seconds: Math.round((Date.now() - started) / 1000),
          answers: { vocab: fill(ans.vocab, lens.vocab), grammar: fill(ans.grammar, lens.grammar), reading: fill(ans.reading, lens.reading) } });
        clearInterval(tick); window.scrollTo(0, 0); examResult(p, r);
      } catch (e) { btn.disabled = false; toast(e.message); }
    };
  }
  function examResult(p, r) {
    const missed = r.vocab.filter(v => !v.correct), gmiss = r.grammar.filter(g => !g.correct);
    const nodes = [...new Map(gmiss.map(g => [g.node, g.node_title])).entries()];
    const late = r.seconds > r.minutes * 60;
    view.innerHTML = `<div class="stack"><div><span class="kicker">${esc(r.title)} · 练习结果</span><h1 class="h1">${r.total} 题做对 ${r.score} 题（${r.pct}%）</h1>
        <p class="muted small">用时 ${mmss(r.seconds)}${late ? `，比建议的 ${r.minutes} 分钟多了 ${mmss(r.seconds - r.minutes * 60)}` : `，在建议的 ${r.minutes} 分钟以内`}。</p></div>
      <div class="exam-score">${r.parts.map(x => `<div><span class="tiny muted">${esc(x.title)}</span><b>${x.right}/${x.of}</b></div>`).join('')}</div>
      ${r.history.length > 1 ? `<div class="stack-s"><span class="tiny muted">成绩走势</span>${trendHTML(r.history.map(x => ({ pct: x.pct, day: new Date(x.created * 1000).toISOString().slice(0, 10),
        parts: Object.fromEntries(x.parts.filter(t => t.of).map(t => [t.key, Math.round(100 * t.right / t.of)])) })))}</div>` : ''}
      ${missed.length ? `<div class="section stack-s"><h2 class="h2">没认出的 ${missed.length} 个词 ${aiVoice()}</h2><div class="plist">${missed.map(v => `<div class="crow"><button class="icon-btn" data-say="${esc(v.word)}" aria-label="朗读">${ICON.speak}</button><span><span class="en">${esc(v.word)}</span><span class="tiny muted">${esc(v.answer)}</span></span></div>`).join('')}</div>
        ${S.user ? '<button class="btn" id="exAdd">全部加进单词本</button>' : ''}</div>` : ''}
      ${nodes.length ? `<div class="section stack-s"><h2 class="h2">要补的语法点</h2><p class="small muted">${r.saved ? '错题已经放进错题本，这些点也排进了每天的计划。' : '登录后错题会进错题本。'}</p>
        <div class="plist">${nodes.map(([id, t]) => `<a class="nrow st st-watch" href="#/graph/${encodeURIComponent(id)}"><i class="dot" aria-hidden="true"></i><span class="t"><b>${esc(t)}</b></span><span></span><span class="go" aria-hidden="true">›</span></a>`).join('')}</div></div>` : ''}
      <details class="section"><summary class="small">看语法和阅读的解析</summary><div class="stack-s">${aiMark('题目和解析由 AI 辅助编写')}
        ${r.grammar.map((g, i) => { const it = p.parts.find(x => x.key === 'grammar').items[i]; const right = it.options[it.map.indexOf(g.answer)];
          return `<div class="pit"><div class="small">${esc(it.prompt)}</div><div class="${g.correct ? 'good' : 'bad'} small">${g.correct ? '✓ 答对' : '✗ 答案'}：${esc(right)}</div><div class="tiny muted">${esc(g.explanation)}</div></div>`; }).join('')}
        ${(() => { const rp = p.parts.find(x => x.key === 'reading'); if (!rp) return ''; const items = rp.passages.flatMap(ps => ps.items);
          return r.reading.map((x, i) => `<div class="pit"><div class="small">${esc(items[i].prompt)}</div><div class="${x.correct ? 'good' : 'bad'} small">${x.correct ? '✓ 答对' : '✗ 答案'}：${esc(items[i].options[x.answer])}</div>${x.evidence ? `<div class="tiny muted">原文依据：${esc(x.evidence)}</div>` : ''}</div>`).join(''); })()}
      </div></details>
      <div class="row"><button class="btn primary" id="exAgain">再来一套</button><a class="btn ghost" href="#/exam/${esc(r.exam)}">回到考试练习</a></div></div>`;
    drawTrends();
    announce(`练习结果：${r.total} 题做对 ${r.score} 题`);
    // a word's own recording, as in the word books; the voice only for a word without one
    view.querySelectorAll('[data-say]').forEach(b => b.onclick = () => {
      const v = missed.find(x => x.word === b.dataset.say);
      if (v && v.audio && (v.audio.us || v.audio.uk)) CLIP.word({ text: v.word, audio: v.audio }); else TTS.say(b.dataset.say);
    });
    const add = document.getElementById('exAdd');
    if (add) add.onclick = async () => {
      add.disabled = true;
      try { const x = await api('/api/next/vocab/add', { items: missed.map(v => ({ word: v.word })) }); add.textContent = x.added ? `已加入 ${x.added} 个词` : '这些词都已经在单词本里了'; }
      catch (e) { add.disabled = false; toast(e.message); }
    };
    document.getElementById('exAgain').onclick = () => examPaper(r.exam);
  }

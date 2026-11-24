  /* ---------- 考试冲刺 (r27): my exam and its date, the countdown word plan, the score trend, question-type practice ---------- */
  // The data comes from exam_sprint.py. With an exam set, 考试练习 opens on it (sprintHub): the countdown and whether the
  // word plan keeps up, the trend of the full sets, the question types, the full set; the other exams fold away below.
  const mdDay = iso => { const [, m, d] = String(iso).split('-').map(Number); return `${m}月${d}日`; };
  const num = n => Number(n || 0).toLocaleString();
  const PART_TITLE = { vocab: '词汇', grammar: '语法', reading: '阅读' };
  function examLabel(p) {
    if (!p || !p.exam) return '未设置';
    const short = { zk: '中考', gk: '高考', cet4: '四级', cet6: '六级', ky: '考研', tem4: '专四', tem8: '专八', ielts: '雅思' }[p.exam] || p.exam;
    return `${short} · ${p.exam_date ? mdDay(p.exam_date) : '没填日期'}`;
  }
  // 今日: one line under the plan's title, never a card (the top of 今日 belongs to 看得见的进步).
  function sprintLine(h) {
    const s = h && h.sprint;
    if (!s || s.status === 'past') return '';
    const when = s.days == null ? '填上考试日期 ›' : s.days === 0 ? '今天考试，加油' : `还有 ${s.days} 天`;
    // (no plan yet: the plan's first step already says 选一本词书, so this line does not say it again)
    const pace = s.days ? { on_time: '背词跟得上', behind: '背词跟不上', other_book: '还没背这本考试词书', done: '词书背完了' }[s.status] : '';
    return `<a class="sprint-line small${s.status === 'behind' ? ' behind' : ''}" href="#/exam/${esc(s.exam)}" data-tap="home-sprint"><b>${esc(s.short)}</b><span>${when}</span>${pace ? `<span class="pace">${pace}</span>` : ''}</a>`;
  }

  // ---- the countdown word plan, said plainly ----
  function paceHTML(cd) {
    if (!cd) return '';
    const book = `《${esc(cd.book_title)}》`, btn = (n, label) => `<button class="btn primary small" type="button" data-daily="${n}" data-tap="exam-pace">${label}</button>`;
    const slow = cd.daily && cd.plan_days >= 7 && cd.week_avg < cd.daily * 0.7 ? `<p class="small">最近 7 天平均每天只学了 ${cd.week_avg} 个新词，比计划的 ${cd.daily} 个少：计划的数要每天学完才算数。</p>` : '';
    let head = '', body = '', act = '';
    if (cd.status === 'past') { head = '考试日期已经过了'; body = `<p class="small">${mdDay(cd.date)} 已经过了。下一个考试是什么？改一下考试和日期，倒计时就会重新算。</p>`; act = '<button class="btn small" type="button" data-goal-edit>改考试或日期</button>'; }
    else if (cd.status === 'today') { head = '今天就考试了，加油'; body = '<p class="small">今天不背新词了。看看错题本里最近的错题，放松一点，按平时的节奏去考。</p>'; act = '<a class="btn small" href="#/cards/mistake">看错题本</a>'; }
    else if (cd.status === 'done') { head = '背词节奏：词书背完了 ✓'; body = `<p class="small">${book}的 ${num(cd.size)} 个词都学过了。考前每天把到期的复习做完，记得更牢。</p>`; }
    else if (cd.status === 'no_date') {
      head = '还没填考试日期';
      body = `<p class="small">${book}还有 ${num(cd.left)} 个词没学${cd.daily && cd.finish ? `；按每天 ${cd.daily} 个，${mdDay(cd.finish)} 能学完` : ''}。填上考试日期，就能算出每天该背多少、跟不跟得上。</p>`;
      act = '<button class="btn primary small" type="button" data-goal-edit>填考试日期</button>';
    } else if (cd.status === 'no_plan' || cd.status === 'other_book') {
      head = cd.status === 'no_plan' ? '还没有背词计划' : `还没在背${book}`;
      body = `<p class="small">${cd.status === 'other_book' ? `你现在背的是《${esc(cd.plan_book_title)}》。` : ''}倒计时按${book}算：还有 ${num(cd.left)} 个词没学，要在 ${mdDay(cd.last_new)} 前（考前留 ${cd.review_days} 天复习）学完，每天要 ${cd.need} 个。</p>
        ${cd.too_many ? `<p class="small">每天 ${cd.need} 个太多了，记不住。建议每天 ${cd.suggest} 个，先背最常用的前 ${num(cd.suggest_reach)} 个（词书越靠前的词越常用）。</p>` : ''}`;
      act = btn(cd.suggest, `用${book}背，每天 ${cd.suggest} 个`);
    } else if (cd.status === 'on_time') {
      head = '背词节奏：跟得上 ✓';
      body = `<p class="small">${book}还有 ${num(cd.left)} 个词没学。每天 ${cd.daily} 个，${mdDay(cd.last_new)} 前能学完，考前留 ${cd.review_days} 天只复习。</p>${slow}`;
    } else {
      head = '背词节奏：跟不上';
      body = `<p class="small">${book}还有 ${num(cd.left)} 个词没学。现在每天 ${cd.daily} 个，到 ${mdDay(cd.last_new)}（考前留 ${cd.review_days} 天复习）只能学 ${num(cd.reach)} 个。</p>
        ${cd.too_many ? `<p class="small">全部学完每天要 ${cd.need} 个，太多了：一个月后每天要复习好几百个，记不住。建议每天 ${cd.suggest} 个，先背最常用的前 ${num(cd.suggest_reach)} 个（词书越靠前的词越常用）。</p>`
          : `<p class="small">要按时学完，每天需要 ${cd.need} 个。</p>`}${slow}`;
      act = btn(cd.suggest, `改成每天 ${cd.suggest} 个`);
    }
    return `<section class="card flat sp-pace st-${cd.status}" aria-labelledby="spPaceH"><h2 class="h3" id="spPaceH">${head}</h2>${body}${act ? `<div class="row">${act}</div>` : ''}</section>`;
  }
  function bindPace(cd, redraw) {
    view.querySelectorAll('[data-goal-edit]').forEach(b => b.onclick = () => examGoalSheet(redraw));
    view.querySelectorAll('[data-daily]').forEach(b => b.onclick = async () => {
      const n = Number(b.dataset.daily); b.disabled = true;
      try {
        await api('/api/next/vocab/plan', { book: cd.book, daily_new: n, retention: cd.retention || 0.9 });
        await refreshHome(); toast(`已改成《${cd.book_title}》每天 ${n} 个新词`); redraw();
      } catch (e) { b.disabled = false; toast(e.message); }
    });
  }

  // ---- 成绩走势: the total as one line, then 词汇 / 语法 / 阅读 as three small lines side by side ----
  function trendHTML(tr) {
    if (!tr || !tr.length) return '<p class="small muted">还没做过完整的一套。做完第一套，这里会出现分数；做满两套就能看出走势。</p>';
    const parts = ['vocab', 'grammar', 'reading'].filter(k => tr.some(t => t.parts && t.parts[k] != null));
    const first = tr[0], last = tr[tr.length - 1];
    if (tr.length === 1) return `<p class="small">第一套：总分 ${first.pct}%（${parts.map(k => `${PART_TITLE[k]} ${first.parts[k]}%`).join(' · ')}）。再做一套就能看出走势。</p>`;
    const line = (vals, kind, label) => `<div class="trend-chart ${kind}" data-v="${vals.join(',')}" role="img" aria-label="${esc(label)}"></div>`;
    const ofPart = k => tr.map(t => t.parts[k]).filter(v => v != null);
    return `<div class="trend"><div class="trend-head"><span class="small">总分</span><b>${first.pct}% → ${last.pct}%</b></div>
      ${line(tr.map(t => t.pct), 'big', `总分：第一套 ${first.pct}%，最近一套 ${last.pct}%，共 ${tr.length} 套`)}
      <div class="trend-parts">${parts.map(k => { const v = ofPart(k);
        return `<div class="tp"><span class="tiny muted">${PART_TITLE[k]}</span><b class="small">${v[0]} → ${v[v.length - 1]}</b>${line(v, 'small', `${PART_TITLE[k]}：从 ${v[0]}% 到 ${v[v.length - 1]}%`)}</div>`; }).join('')}</div>
      <p class="tiny muted">${tr.length} 套，从 ${mdDay(first.day)} 到 ${mdDay(last.day)}。分数只用来看自己的变化，不能换算成考试分数。</p></div>`;
  }
  // Drawn at the width the box really has (the page is laid out first), so dots stay round and lines stay thin.
  function drawTrends(root) {
    (root || view).querySelectorAll('.trend-chart').forEach(box => {
      const v = box.dataset.v.split(',').map(Number), big = box.classList.contains('big');
      const W = Math.max(60, Math.round(box.clientWidth)), H = big ? 112 : 40, L = big ? 34 : 4, R = 8, T = 8, B = big ? 10 : 6;
      const x = i => L + (v.length > 1 ? i * (W - L - R) / (v.length - 1) : (W - L - R) / 2), y = p => T + (1 - p / 100) * (H - T - B);
      const grid = big ? [0, 50, 100].map(p => `<line class="g" x1="${L}" x2="${W - R}" y1="${y(p)}" y2="${y(p)}"/><text x="${L - 6}" y="${y(p) + 4}" text-anchor="end">${p}%</text>`).join('') : '';
      const pts = v.map((p, i) => `${x(i).toFixed(1)},${y(p).toFixed(1)}`).join(' ');
      const dots = v.map((p, i) => `<circle class="${i === v.length - 1 ? 'last' : ''}" cx="${x(i).toFixed(1)}" cy="${y(p).toFixed(1)}" r="${big ? (i === v.length - 1 ? 5 : 3.5) : (i === v.length - 1 ? 3.5 : 2.2)}"/>`).join('');
      box.innerHTML = `<svg viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" aria-hidden="true" focusable="false">${grid}<polyline points="${pts}"/>${dots}</svg>`;
    });
  }
  let trendTimer = 0;
  addEventListener('resize', () => { clearTimeout(trendTimer); trendTimer = setTimeout(() => { if (view.querySelector('.trend-chart')) drawTrends(); }, 150); });

  // ---- 题型专练: the list on an exam ----
  function typesHTML(exam, types, note) {
    if (!types || !types.length) return '';
    return `<section class="section stack-s" aria-labelledby="spTypesH"><h2 class="h2" id="spTypesH">题型专练</h2><p class="tiny muted">${esc(note)}</p>
      <div class="mlist">${types.map(t => `<a class="mrow" href="#/exam/${esc(exam)}/${esc(t.id)}" data-tap="exam-type"><span class="t"><b>${esc(t.title)}</b>
        <span class="tiny muted">${t.items} 题，分 ${t.sets} 组${t.last ? ` · 上次 ${t.last.right}/${t.last.of}` : ' · 还没做'}</span></span><span class="go" aria-hidden="true">›</span></a>`).join('')}
        <a class="mrow" href="#/exam/${esc(exam)}/reading" data-tap="exam-reading"><span class="t"><b>阅读一篇</b><span class="tiny muted">这个考试难度的一篇原创短文，4 题；今日计划里的「考试小练」也会排到它</span></span><span class="go" aria-hidden="true">›</span></a></div></section>`;
  }

  // ---- the hub: 考试练习 when an exam is set ----
  function sprintHub(o, pickList) {
    const g = o.goal, cd = o.countdown, cur = o.exams.find(e => e.id === g.exam);
    const others = o.exams.filter(e => e.id !== g.exam);
    const when = !g.date ? '还没填考试日期' : cd && cd.days > 0 ? `${mdDay(g.date)} · 还有 ${cd.days} 天` : cd && cd.days === 0 ? `${mdDay(g.date)} · 就是今天` : `${mdDay(g.date)} · 已经过了`;
    view.innerHTML = `<div class="stack sprint"><div><span class="kicker">考试练习 · 我的考试</span><h1 class="h1">${esc(cur.title)}</h1>
        <p class="sp-when"><span class="small">${when}</span><button class="link small" type="button" data-goal-edit data-tap="exam-goal">改考试或日期</button></p></div>
      ${paceHTML(cd)}
      <section class="section stack-s" aria-labelledby="spTrendH"><h2 class="h2" id="spTrendH">成绩走势${cur.trend.length > 1 ? `<span class="tiny muted">（最近 ${cur.trend.length} 套）</span>` : ''}</h2>${trendHTML(cur.trend)}</section>
      ${typesHTML(cur.id, cur.types, o.types_note)}
      <section class="section stack-s" aria-labelledby="spFullH"><h2 class="h2" id="spFullH">完整一套</h2>
        <p class="small muted">词汇 10 题（${esc(cur.book_title)}）· 语法 8 题 · 阅读 2 篇 4 题，计时做完再看解析。${cd && cd.sprint ? '考前这几周，今日的计划里每周排一套。' : ''}</p>
        <button class="btn primary block" id="exStart">开始一套（约 ${cur.minutes} 分钟）</button><p class="tiny muted">${esc(o.note)}</p></section>
      ${others.length ? `<details class="section sp-others"><summary class="small">其他考试（${others.length} 个）</summary>${pickList(others)}</details>` : ''}</div>`;
    drawTrends();
    bindPace(cd, () => examView(g.exam));
    document.getElementById('exStart').onclick = () => examPaper(cur.id);
  }

  // ---- 我的考试: which exam and when (我的, 考试练习; 背词计划 sets it with its chips) ----
  async function examGoalSheet(onSaved) {
    const o = await api('/api/next/exam/goal');
    let exam = o.goal ? o.goal.exam : '';
    const today = new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 10);
    openSheet(`<div class="stack"><h2 class="h2" id="sheetTitle">我的考试</h2>
      <p class="muted small">设好考试和日期，「考试练习」会变成你的备考主页：倒计时、每天该背多少词、成绩走势和题型专练；考前最后四周，今日的计划会加上每周一套和这个考试的语法点。</p>
      <div class="chips" role="radiogroup" aria-label="在准备哪个考试">${[{ id: '', short: '不考试' }, ...o.exams].map(e => `<button class="chip" type="button" role="radio" data-exam="${e.id}" aria-checked="${e.id === exam}">${esc(e.short)}</button>`).join('')}</div>
      <div class="stack-s" id="egDate"><label class="small" for="egIn">考试日期（选填，不确定可以先空着）</label>
        <input type="date" id="egIn" min="${today}" value="${esc(o.goal && o.goal.date || '')}"></div>
      <p class="err" id="egErr" role="alert"></p>
      <div class="row"><button class="btn primary" type="button" id="egSave">保存</button><button class="btn ghost" type="button" data-close>取消</button></div></div>`, card => {
      const date = card.querySelector('#egDate'), sync = () => { date.hidden = !exam; };
      card.querySelectorAll('[data-exam]').forEach(b => b.onclick = () => { exam = b.dataset.exam; card.querySelectorAll('[data-exam]').forEach(x => x.setAttribute('aria-checked', String(x === b))); sync(); });
      sync();
      card.querySelector('#egSave').onclick = async e => {
        e.currentTarget.disabled = true;
        try {
          const r = await api('/api/next/exam/goal', { exam, date: exam ? card.querySelector('#egIn').value : '' });
          closeSheet(); await refreshHome();
          toast(r.goal ? `我的考试：${r.goal.short}${r.goal.date ? ' · ' + mdDay(r.goal.date) : ''}` : '已改成不考试');
          if (onSaved) onSaved();
        } catch (x) { e.currentTarget.disabled = false; card.querySelector('#egErr').textContent = x.message; }
      };
    });
  }

  // ---- 背词计划: the date under the exam chips, and how many words a day the date asks for ----
  function planExamRow(p) {
    const today = new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 10);
    return `<div class="stack-s plan-exam" id="pxRow" hidden><label class="small" for="pxDate">考试日期（选填）</label>
      <input type="date" id="pxDate" min="${today}" value="${esc(p && p.exam_date || '')}"><span class="tiny muted" id="pxHint" aria-live="polite"></span></div>`;
  }
  function planExamHint(exam, date, b, chosen, daily, done) {
    if (!exam) return '';
    if (!date) return '填上日期，就能算出每天要背多少个新词才来得及。';
    const days = Math.round((new Date(date + 'T00:00:00') - new Date(new Date().toDateString())) / 864e5);
    if (days <= 0) return days === 0 ? '今天就考试了。' : '这个日期已经过了。';
    if (chosen !== exam) return `离考试还有 ${days} 天。倒计时按这个考试的词书算，你现在选的是另一本。`;
    const left = Math.max(0, (b.size || 0) - (b.skippable || 0) - done), study = Math.max(1, days - Math.min(7, Math.floor(days / 3))), need = Math.ceil(left / study);
    if (!left) return `离考试还有 ${days} 天，这本词书都学过了。`;
    return `离考试还有 ${days} 天，最后 ${days - study} 天留着复习，前 ${study} 天要学完剩下的 ${num(left)} 个词：每天需要 ${need} 个新词` +
      (daily >= need ? '，现在选的够了。' : need > 40 ? `。太多了，记不住：建议每天 40 个，先背最常用的前 ${num(40 * study)} 个。` : `；现在选的每天 ${daily} 个跟不上。`);
  }

  // ---- one question type: a set of original items, handed in once, then every answer with its reason ----
  const LETTERS = 'ABCDEFGHIJKLMNO', ROMAN = ['i', 'ii', 'iii', 'iv', 'v', 'vi', 'vii', 'viii', 'ix', 'x', 'xi', 'xii'], TFNG = ['TRUE', 'FALSE', 'NOT GIVEN'];
  const tapWords = line => line.split(/\s+/).filter(Boolean);
  async function examTypeView(exam, tid, setId) {
    const r = await api(`/api/next/exam/type?exam=${encodeURIComponent(exam)}&type=${encodeURIComponent(tid)}${setId ? '&set=' + encodeURIComponent(setId) : ''}`);
    const s = r.set, k = s.kind, n = s.items.length, ans = Array(n).fill(null);
    const label = (i, a) => a == null ? '' : k === 'bank' ? `${LETTERS[a]}. ${s.bank[a]}` : k === 'headings' ? `${ROMAN[a]}. ${s.bank[a]}` : k === 'match' ? `${LETTERS[a]} 段`
      : k === 'tfng' ? TFNG[a] : k === 'proof' ? a : s.items[i].options[a];
    const gapText = t => esc(t).replace(/\{(\d+)\}/g, (_, d) => k === 'bank' ? `<button class="gap" type="button" data-gap="${d - 1}" aria-label="第 ${d} 空，点这里选">(${d}) <span class="gv">＿＿＿</span></button>`
      : `<span class="gap ro" data-gap="${d - 1}">(${d}) <span class="gv">＿＿＿</span></span>`);
    const opts = (i, list, fmt) => `<div class="xt-opts">${list.map((x, j) => `<button class="ans" type="button" data-i="${i}" data-o="${j}"><span class="k">${fmt ? fmt(j) : LETTERS[j]}</span><span>${esc(x)}</span></button>`).join('')}</div>`;
    let body = '';
    if (k === 'cloze') body = `<div class="exam-passage xt-text">${gapText(s.text)}</div><div class="stack-s">${s.items.map((it, i) => `<div class="q gq xt-q" data-q="${i}"><div class="prompt">第 ${i + 1} 空</div>${opts(i, it.options)}</div>`).join('')}</div>`;
    if (k === 'bank') body = `<div class="xt-bank card sunk"><b class="small">选项（每个只用一次）</b><ol class="xt-banklist${s.bank.every(x => x.length <= 16) ? ' words' : ''}">${s.bank.map((x, j) => `<li data-b="${j}"><span class="k">${LETTERS[j]}</span><span>${esc(x)}</span></li>`).join('')}</ol></div>
      <div class="exam-passage xt-text${s.bank.some(x => x.length > 30) ? ' long' : ''}">${gapText(s.text)}</div>`;
    if (k === 'headings') body = `<div class="xt-bank card sunk"><b class="small">标题（每个只用一次，有几个用不上）</b><ol class="xt-banklist">${s.bank.map((x, j) => `<li data-b="${j}"><span class="k">${ROMAN[j]}</span><span>${esc(x)}</span></li>`).join('')}</ol></div>
      ${s.paras.map((p, i) => `<div class="xt-para"><div class="row"><b>${LETTERS[i]}</b><button class="gap" type="button" data-gap="${i}" aria-label="${LETTERS[i]} 段的标题，点这里选"><span class="gv">选标题</span></button></div><p class="exam-passage">${esc(p)}</p></div>`).join('')}`;
    if (k === 'match') body = `${s.paras.map((p, i) => `<p class="exam-passage xt-para"><b>${LETTERS[i]}</b> ${esc(p)}</p>`).join('')}
      <div class="stack-s">${s.items.map((it, i) => `<div class="q gq xt-q" data-q="${i}"><div class="prompt">${i + 1}. ${esc(it.prompt)}</div><div class="xt-letters">${s.paras.map((_, j) => `<button class="ans" type="button" data-i="${i}" data-o="${j}" aria-label="${LETTERS[j]} 段">${LETTERS[j]}</button>`).join('')}</div></div>`).join('')}</div>`;
    if (k === 'tfng') body = `<div class="exam-passage xt-text">${esc(s.text)}</div><div class="stack-s">${s.items.map((it, i) => `<div class="q gq xt-q" data-q="${i}"><div class="prompt">${i + 1}. ${esc(it.prompt)}</div><div class="xt-tf">${TFNG.map((x, j) => `<button class="ans" type="button" data-i="${i}" data-o="${j}">${x}</button>`).join('')}</div></div>`).join('')}</div>`;
    if (k === 'choice') body = `<div class="stack-s">${s.items.map((it, i) => `<div class="q gq xt-q" data-q="${i}"><div class="prompt">${i + 1}. ${esc(it.prompt)}</div>${opts(i, it.options)}</div>`).join('')}</div>`;
    // 阅读一篇 (考试小练, r28): a passage at the exam's level, then its questions
    if (k === 'reading') body = `<div class="exam-passage xt-text" lang="en">${esc(s.text)}</div><div class="stack-s">${s.items.map((it, i) => `<div class="q gq xt-q" data-q="${i}"><div class="prompt" lang="en">${i + 1}. ${esc(it.prompt)}</div>${opts(i, it.options)}</div>`).join('')}</div>`;
    if (k === 'proof') body = `<div class="stack-s">${s.lines.map((line, i) => `<div class="q gq xt-q xt-line" data-q="${i}"><div class="tiny muted">第 ${i + 1} 行</div><div class="xt-words">${tapWords(line).map((w, j) => `<button class="xw" type="button" data-i="${i}" data-w="${j}" aria-pressed="false">${esc(w)}</button>`).join('')}</div></div>`).join('')}</div>`;
    view.innerHTML = `<div class="stack xt"><div><span class="kicker">${esc(r.exam_title)} · ${k === 'reading' ? '考试小练' : '题型专练'}</span><h1 class="h1">${esc(r.title)}</h1>
        <p class="small">${esc(r.how)}</p><p class="tiny muted">${esc(r.note)}</p></div>
      <div class="row between"><span class="tiny muted">${[r.of > 1 ? `第 ${r.index} 组，共 ${r.of} 组` : '', s.title ? `<span lang="en">${esc(s.title)}</span>` : ''].filter(Boolean).join(' · ')}</span><span class="tiny muted" id="xtLeft">还有 ${n} 题</span></div>
      ${body}
      <button class="btn primary block" id="xtDone" type="button">交卷</button>
      <a class="link small" href="#/exam/${esc(exam)}">回到考试练习</a></div>`;
    const left = () => { const m = ans.filter(a => a == null).length; document.getElementById('xtLeft').textContent = m ? `还有 ${m} 题` : '都做完了'; };
    const fillGap = i => { const g = view.querySelector(`[data-gap="${i}"] .gv`); if (g) g.textContent = ans[i] == null ? (k === 'headings' ? '选标题' : '＿＿＿') : label(i, ans[i]); };
    view.querySelectorAll('.ans').forEach(b => b.onclick = () => {
      const i = +b.dataset.i; ans[i] = +b.dataset.o;
      view.querySelectorAll(`.ans[data-i="${i}"]`).forEach(x => x.classList.toggle('chosen', x === b));
      if (k === 'cloze') fillGap(i);
      left();
    });
    view.querySelectorAll('.xw').forEach(b => b.onclick = () => {
      const i = +b.dataset.i, on = !b.classList.contains('chosen');
      view.querySelectorAll(`.xw[data-i="${i}"]`).forEach(x => { x.classList.toggle('chosen', on && x === b); x.setAttribute('aria-pressed', String(on && x === b)); });
      ans[i] = on ? b.textContent : null; left();
    });
    // 选词填空、七选五、段落标题: tap a gap, pick from the options in a sheet (one already used shows where)
    const used = () => { view.querySelectorAll('.xt-banklist li').forEach(li => li.classList.toggle('used', ans.includes(+li.dataset.b))); };
    view.querySelectorAll('button.gap').forEach(g => g.onclick = () => {
      const i = +g.dataset.gap, fmt = j => k === 'headings' ? ROMAN[j] : LETTERS[j];
      openSheet(`<div class="stack"><h2 class="h2" id="sheetTitle">${k === 'headings' ? `${LETTERS[i]} 段的标题` : `第 ${i + 1} 空`}</h2>
        <div class="stack-s xt-pick">${s.bank.map((x, j) => { const at = ans.indexOf(j);
          return `<button class="ans${ans[i] === j ? ' chosen' : ''}" type="button" data-pick="${j}"><span class="k">${fmt(j)}</span><span>${esc(x)}${at >= 0 && at !== i ? `<span class="tiny muted">（已用在${k === 'headings' ? ` ${LETTERS[at]} 段` : `第 ${at + 1} 空`}）</span>` : ''}</span></button>`; }).join('')}</div>
        <div class="row">${ans[i] != null ? '<button class="btn ghost" type="button" id="xtClear">清空这一空</button>' : ''}<button class="btn ghost" type="button" data-close>取消</button></div></div>`, card => {
        card.querySelectorAll('[data-pick]').forEach(b => b.onclick = () => {
          const j = +b.dataset.pick, was = ans.indexOf(j);
          if (was >= 0 && was !== i) { ans[was] = null; fillGap(was); }  // one option, one gap: it moves here
          ans[i] = j; fillGap(i); used(); left(); closeSheet();
          const nextGap = view.querySelector(`button.gap[data-gap="${i + 1}"]`); if (nextGap && ans[i + 1] == null) nextGap.focus({ preventScroll: true });
        });
        const cl = card.querySelector('#xtClear'); if (cl) cl.onclick = () => { ans[i] = null; fillGap(i); used(); left(); closeSheet(); };
      });
    });
    let warned = false;
    document.getElementById('xtDone').onclick = async e => {
      const btn = e.currentTarget, m = ans.filter(a => a == null).length;
      if (m && !warned) { warned = true; btn.textContent = `还有 ${m} 题没做，再点一次交卷`; return; }
      btn.disabled = true;
      let out;
      try { out = await api('/api/next/exam/type', { exam, type: tid, set: s.id, answers: ans }); }
      catch (x) { btn.disabled = false; toast(x.message); return; }
      window.scrollTo(0, 0); typeResult(r, ans, out, label);
    };
  }
  function typeResult(r, ans, out, label) {
    const s = r.set, k = s.kind;
    const what = i => k === 'cloze' || k === 'bank' ? `第 ${i + 1} 空` : k === 'headings' ? `${LETTERS[i]} 段` : k === 'proof' ? `第 ${i + 1} 行` : `${i + 1}. ${s.items[i].prompt}`;
    const right = (it, i) => k === 'proof' ? `${it.wrong} → ${it.fix || '删去'}` : label(i, it.answer);
    const text = k === 'match' || k === 'headings' ? s.paras.map((p, i) => `${LETTERS[i]}  ${p}`).join('\n\n') : k === 'proof' ? s.lines.join('\n')
      : s.text ? s.text.replace(/\{(\d+)\}/g, (_, d) => `(${d}) ${label(d - 1, out.items[d - 1].answer)}`) : '';  // 单选题 have no passage
    view.innerHTML = `<div class="stack xt"><div><span class="kicker">${esc(r.exam_title)} · ${esc(r.title)}</span><h1 class="h1">${out.of} 题做对 ${out.right} 题</h1>
        <p class="small muted">${out.saved ? '结果已记下，题型列表会显示上次的成绩。' : '登录后会记下每次的成绩。'}每题都写了答案在原文里的依据。</p></div>
      <div class="stack-s">${out.items.map((it, i) => `<div class="pit"><div class="small">${esc(what(i))}</div>
        <div class="${it.correct ? 'ok' : 'no'} small">${it.correct ? '✓ 答对' : '✗ 答错了，答案是'}：${esc(right(it, i))}${!it.correct && ans[i] != null ? `<span class="tiny muted">（你选的：${esc(k === 'proof' ? ans[i] : label(i, ans[i]))}）</span>` : ''}</div>
        <div class="tiny muted">${esc(it.why)}</div></div>`).join('')}</div>
      ${text ? `<details class="section"><summary class="small">看原文${k === 'cloze' || k === 'bank' ? '（空里填的是答案）' : ''}</summary><div class="exam-passage xt-text">${esc(text)}</div></details>` : ''}
      <div class="row"><button class="btn primary" id="xtNext" type="button">${k === 'reading' ? '再读一篇' : '再做一组'}</button><a class="btn ghost" href="#/exam/${esc(r.exam)}">回到考试练习</a></div></div>`;
    announce(`${out.of} 题做对 ${out.right} 题`);
    document.getElementById('xtNext').onclick = () => { window.scrollTo(0, 0); examTypeView(r.exam, r.type, out.next); };
  }

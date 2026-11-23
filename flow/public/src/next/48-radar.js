  /* ---------- ability radar: six skills against the learner's own goals, and what moved ---------- */
  const DIM_TEST = { vocab: '#/vocab/test', grammar: '#/placement', reading: '#/radar/test/reading', listening: '#/radar/test/listening', speaking: '#/radar/test/speaking', writing: '#/radar/test/writing' };
  const CONF = { high: '测评', medium: '估计', low: '粗略估计' };
  function radarSVG(dims, prev) {
    const W = 320, C = 160, R = 112, n = dims.length;
    const pt = (k, v) => { const a = -Math.PI / 2 + k * 2 * Math.PI / n, r = R * Math.max(0, Math.min(100, v)) / 100; return [C + r * Math.cos(a), C + r * Math.sin(a)]; };
    const poly = vals => vals.map((v, k) => pt(k, v).map(x => x.toFixed(1)).join(',')).join(' ');
    const rings = [25, 50, 75].map(v => `<polygon class="rg" points="${poly(dims.map(() => v))}"/>`).join('');
    const axes = dims.map((d, k) => { const [x, y] = pt(k, 100); return `<line class="ax" x1="${C}" y1="${C}" x2="${x.toFixed(1)}" y2="${y.toFixed(1)}"/>`; }).join('');
    const labels = dims.map((d, k) => { const [x, y] = pt(k, 128); const anchor = Math.abs(x - C) < 8 ? 'middle' : x > C ? 'start' : 'end';
      return `<text class="lb" x="${x.toFixed(1)}" y="${(y + 4).toFixed(1)}" text-anchor="${anchor}">${esc(d.label)}<tspan class="sc" dx="4">${d.score == null ? '?' : d.score}</tspan></text>`; }).join('');
    const cur = dims.map(d => d.score == null ? 0 : d.score);
    const dots = dims.map((d, k) => { const [x, y] = pt(k, cur[k]); return `<circle class="dt${d.score == null ? ' none' : ''}" cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="${d.score == null ? 3 : 4.5}"/>`; }).join('');
    return `<svg class="radar" viewBox="-40 0 400 ${W}" role="img" aria-label="能力雷达：${dims.map(d => d.label + (d.score == null ? '暂无数据' : ' ' + d.score + ' 分')).join('，')}">
      ${rings}${axes}<polygon class="goal" points="${poly(dims.map(() => 100))}"/>
      ${prev ? `<polygon class="prev" points="${poly(dims.map(d => prev[d.id] == null ? 0 : prev[d.id]))}"/>` : ''}
      <g class="cur"><polygon class="area" points="${poly(cur)}"/>${dots}</g>${labels}</svg>`;
  }
  function spark(vals) {
    const xs = vals.filter(v => v != null); if (xs.length < 2) return '';
    const pts = vals.map((v, k) => v == null ? null : `${(k / (vals.length - 1) * 60).toFixed(1)},${(18 - v / 100 * 16).toFixed(1)}`).filter(Boolean).join(' ');
    return `<svg class="spark" viewBox="0 0 60 20" aria-hidden="true"><polyline points="${pts}"/></svg>`;
  }
  async function radarView() {
    if (!S.user) return needLogin('登录后可以设定目标、做能力测评，看到自己每一项离目标还差多少。');
    const r = await api('/api/next/radar');
    const prev = r.before ? (r.history.find(h => h.created === r.before) || {}).scores : null;
    const known = r.dims.filter(d => d.score != null);
    view.innerHTML = `<div class="stack"><div><span class="kicker">能力雷达</span><h1 class="h1">离目标还差多少</h1><p class="muted small">${esc(r.note)}</p></div>
      ${r.goals_chosen ? '' : `<a class="card flat place-cta" href="#/radar/goals"><b>先定一个目标</b><span class="small muted">每一项想到什么水平？现在先按比你的水平高一级来算，可以随时改。</span></a>`}
      <div class="radar-box">${radarSVG(r.dims, prev)}
        <div class="radar-legend tiny"><span class="lg goal">目标（100 分）</span>${prev ? '<span class="lg prev">上次</span>' : ''}<span class="lg cur">现在</span></div></div>
      ${known.length < r.dims.length ? `<p class="small">${r.dims.length - known.length} 项还没有足够的数据。做一次测评，雷达图就完整了。</p>` : ''}
      <div class="row"><a class="btn primary" href="#/radar/test">${r.due.length ? `做测评（${r.due.length} 项该测了）` : '再测一次'}</a><a class="btn" href="#/radar/goals">调整目标</a></div>
      <section class="stack-s section">${r.dims.map((d, k) => { const delta = d.score != null && d.prev_score != null ? d.score - d.prev_score : null;
        return `<div class="rdim pop-in" data-k="${k}"><div class="row between"><b>${esc(d.label)}</b><span class="tiny muted">目标 ${esc(d.goal)}</span></div>
          ${d.score == null ? `<div class="small muted">还没有数据 · <a class="link" href="${DIM_TEST[d.id]}">测一测</a></div>` : `
          <div class="rbar"><span class="vbar"><i data-w="${d.score}"></i></span><b class="num">${d.score}</b>${delta ? `<span class="${delta > 0 ? 'up' : 'down'}">${delta > 0 ? '+' : ''}${delta}</span>` : ''}${spark(r.history.map(h => h.scores[d.id]))}</div>
          <div class="tiny muted">现在约 ${esc(d.level)} · ${CONF[d.confidence] || ''}${d.assessed ? '（' + new Date(d.assessed * 1000).toLocaleDateString('zh-CN') + ' 测评）' : '（来自平时练习）'}
            · <a class="link" href="${DIM_TEST[d.id]}">${d.due ? '该测了' : '重测'}</a>${r.gap === d.id ? ` · <a class="link" href="${d.href}">差距最大：${esc(d.tip)}</a>` : ''}</div>`}</div>`; }).join('')}</section>
      ${r.gap ? `<p class="small cheer">${esc(r.dims.find(d => d.id === r.gap).label)}离目标最远，每天的计划会多安排这方面的练习。</p>` : ''}
      <details class="card flat fold" id="abFold"><summary><b>按平时练习估计</b><span class="tiny muted">近 45 天 · 8 项，含翻译和发音</span></summary><div id="abSlot"><p class="muted small"><span class="spin"></span></p></div></details></div>`;
    view.querySelectorAll('.pop-in').forEach(el => el.style.setProperty('--d', Number(el.dataset.k) * 60 + 'ms'));
    // What used to be the 能力画像 card on 我的: loaded when it is opened.
    const fold = document.getElementById('abFold');
    fold.addEventListener('toggle', () => {
      if (!fold.open || fold.dataset.done) return;
      fold.dataset.done = '1';
      api('/api/next/ability').then(ab => {
        const slot = document.getElementById('abSlot'); if (!slot) return;
        slot.innerHTML = abilityHTML(ab);
        requestAnimationFrame(() => requestAnimationFrame(() => slot.querySelectorAll('.vbar i').forEach(i => { i.style.width = i.dataset.w + '%'; })));
      }).catch(e => { const slot = document.getElementById('abSlot'); if (slot) slot.innerHTML = `<p class="muted small">${esc(e.message)}</p>`; delete fold.dataset.done; });
    });
    requestAnimationFrame(() => requestAnimationFrame(() => { view.querySelectorAll('.vbar i').forEach(i => { i.style.width = i.dataset.w + '%'; }); const g = view.querySelector('.radar .cur'); if (g) g.classList.add('on'); }));
  }
  async function radarGoals() {
    if (!S.user) return needLogin('登录后可以设定目标。');
    const r = await api('/api/next/radar'), g = { ...r.goals }, LV = { A2: '入门', B1: '中级', B2: '中高级', C1: '高级' };
    const draw = () => {
      view.innerHTML = `<div class="stack"><div><a class="link small" href="#/radar">← 能力雷达</a></div><div><span class="kicker">设定目标</span><h1 class="h1">每一项想到什么水平？</h1>
          <p class="muted small">目标就是雷达图上的 100 分。可以每项不一样，比如“口语到 B1，阅读到 B2”。</p></div>
        <div class="row"><span class="small muted">全部设为</span>${r.goal_levels.map(l => `<button class="chip" data-all="${l}">${l}</button>`).join('')}</div>
        ${r.dims.map(d => `<div class="stack-s goal-row"><b>${esc(d.label)}</b><div class="chips">${r.goal_levels.map(l => `<button class="chip" data-d="${d.id}" data-l="${l}" aria-pressed="${g[d.id] === l}">${l} ${LV[l]}</button>`).join('')}</div></div>`).join('')}
        <button class="btn primary block" id="gSave">保存目标</button></div>`;
      view.querySelectorAll('[data-d]').forEach(b => b.onclick = () => { g[b.dataset.d] = b.dataset.l; draw(); });
      view.querySelectorAll('[data-all]').forEach(b => b.onclick = () => { r.dims.forEach(d => { g[d.id] = b.dataset.all; }); draw(); });
      document.getElementById('gSave').onclick = async e => { e.currentTarget.disabled = true; try { await api('/api/next/radar/goals', { goals: g }); toast('目标已保存'); location.hash = '#/radar'; } catch (x) { toast(x.message); e.currentTarget.disabled = false; } };
    };
    draw();
  }
  async function radarTests() {
    if (!S.user) return needLogin('登录后可以做能力测评。');
    const r = await api('/api/next/radar');
    const MIN = { vocab: 3, grammar: 5, reading: 6, listening: 8, speaking: 3, writing: 10 };
    view.innerHTML = `<div class="stack"><div><a class="link small" href="#/radar">← 能力雷达</a></div><div><span class="kicker">能力测评</span><h1 class="h1">选一项，测 3–10 分钟</h1>
        <p class="muted small">不用一次测完。建议每 4 周测一轮，雷达图会把两次的变化画出来。</p></div>
      <div class="plist">${r.dims.map(d => `<a class="nrow ${d.due ? 'st st-untouched' : 'st st-solid'}" href="${DIM_TEST[d.id]}"><i class="dot" aria-hidden="true"></i>
        <span class="t"><b>${esc(d.label)}</b><span class="tiny muted">约 ${MIN[d.id]} 分钟 · ${d.assessed ? '上次 ' + new Date(d.assessed * 1000).toLocaleDateString('zh-CN') : '还没测过'}${d.due ? ' · 该测了' : ''}</span></span><span></span><span class="go" aria-hidden="true">›</span></a>`).join('')}</div>
      <p class="tiny muted">词汇用词汇量测试，语法用起点小测；阅读和听力各有 2–3 段短文；口语录一段回答、写作写一小段，由 AI 按 CEFR 描述评分。</p></div>`;
  }
  async function assessComprehension(kind) {
    if (!S.user) return needLogin('登录后可以做能力测评。');
    const t = await api('/api/next/assess/test?kind=' + kind), answers = [];
    let k = 0, plays = 0;
    const name = kind === 'reading' ? '阅读' : '听力';
    const show = () => {
      const p = t.passages[k]; plays = 0;
      view.innerHTML = `<div class="stack"><div class="row between"><span class="kicker">${name}测评 · 第 ${k + 1} / ${t.passages.length} 段</span><span class="pill">${esc(p.level)}</span></div>
        ${kind === 'reading' ? `<h2 class="h2">${esc(p.title)}</h2><div class="exam-passage">${esc(p.body)}</div>` :
          `<p class="small muted">听一段录音，然后回答两道题。最多听两遍，听的时候看不到原文。</p><button class="btn primary block" id="aPlay">▶ 播放录音</button><p class="tiny muted" id="aPlays"></p>`}
        <div id="aQs" ${kind === 'listening' ? 'hidden' : ''}>${p.questions.map(q => `<div class="q gq" data-i="${q.i}"><div class="prompt">${esc(q.prompt)}</div>
          ${q.options.map((o, j) => `<button class="ans" data-o="${j}"><span class="k">${'ABCD'[j]}</span><span>${esc(o)}</span></button>`).join('')}</div>`).join('')}
          <button class="btn primary block" id="aNext" disabled>${k + 1 < t.passages.length ? '下一段' : '交卷，看结果'}</button></div></div>`;
      const chosen = {};
      view.querySelectorAll('.gq').forEach(box => box.querySelectorAll('.ans').forEach(b => b.onclick = () => {
        box.querySelectorAll('.ans').forEach(x => x.classList.toggle('chosen', x === b)); chosen[box.dataset.i] = Number(b.dataset.o);
        document.getElementById('aNext').disabled = Object.keys(chosen).length < p.questions.length;
      }));
      const play = document.getElementById('aPlay');
      if (play) play.onclick = async () => {
        if (plays >= 2) return; plays++; play.disabled = true; play.textContent = '正在播放…';
        const done = () => { play.disabled = plays >= 2; play.textContent = plays >= 2 ? '已经听了两遍' : '▶ 再听一遍'; document.getElementById('aQs').hidden = false; document.getElementById('aPlays').textContent = `已听 ${plays} / 2 遍`; };
        const voices = p.audio.voices || [];
        if (voices.length && await NAR.load(p.pack, voices.includes(S.voice) ? S.voice : voices[0], p.audio.version)) NAR.play(0, null, null, done);
        else TTS.say(p.body.replace(/^[A-Z][a-z]+(?: [A-Z][a-z]+)?:\s+/gm, ''), done);
      };
      document.getElementById('aNext').onclick = async () => {
        NAR.stop(); TTS.stop();
        p.questions.forEach(q => answers.push({ pack: p.pack, i: q.i, choice: chosen[q.i] }));
        if (++k < t.passages.length) { window.scrollTo(0, 0); show(); return; }
        let r; try { r = await api('/api/next/assess/comprehension', { kind, answers }); } catch (e) { toast(e.message); return; }
        assessResult(name, r.recorded, `<div class="stack-s">${Object.entries(r.levels).map(([lv, x]) => `<div class="row between small"><span>${lv} 难度</span><span>${x.right} / ${x.of}</span></div>`).join('')}</div>`);
      };
    };
    if (!t.passages.length) { view.innerHTML = '<div class="empty"><p>暂时没有合适的测评材料。</p><a class="btn" href="#/radar/test">返回</a></div>'; return; }
    show();
  }
  async function assessJudged(kind) {
    if (!S.user) return needLogin('登录后可以做能力测评。');
    const t = await api('/api/next/assess/task?kind=' + kind), name = kind === 'speaking' ? '口语' : '写作';
    view.innerHTML = `<div class="stack"><div><a class="link small" href="#/radar/test">← 能力测评</a></div>
      <div><span class="kicker">${name}测评 · ${esc(t.level)}</span><h1 class="h1">${esc(t.question)}</h1><p class="small">${esc(t.task)}</p><p class="tiny muted">${esc(t.limit)}。AI 按 CEFR 描述从四个方面评分，不看话题难易${kind === 'speaking' ? '，口音不扣分' : ''}。</p></div>
      ${kind === 'speaking' ? `<div class="row center">${recBtn('aMic', '开始回答')}<span class="small" id="aState">点 ● 开始说，说完再点一下结束</span></div>` :
        `<textarea id="aText" rows="9" lang="en" placeholder="用英文写……" autocapitalize="sentences" spellcheck="false"></textarea><div class="row between"><span class="tiny muted" id="aCount">0 词</span><button class="btn primary" id="aGo">提交</button></div>`}
      <div id="aOut"></div></div>`;
    const send = async body => {
      const out = document.getElementById('aOut'); out.innerHTML = '<p class="loading"><span class="spin"></span> AI 正在评估…</p>';
      try {
        const x = (await api('/api/next/assess/' + kind, { question: t.question, request_id: rid('as'), ...body })).result;
        const DIMN = kind === 'speaking' ? { fluency: '流利度', accuracy: '准确度', range: '词汇句式', pronunciation: '发音清晰度' } : { content: '内容切题', organization: '结构衔接', accuracy: '语言准确', range: '词汇句式' };
        assessResult(name, x.recorded, `${x.transcript ? `<div class="small"><span class="muted">AI 听到的：</span>${esc(x.transcript)}</div>` : ''}
          <div class="ab-list">${Object.entries(x.scores).map(([k2, v]) => `<div class="ab"><span class="nm">${DIMN[k2] || k2}</span><span class="vbar"><i data-w="${v * 20}"></i></span><span class="lv">${v} / 5</span></div>`).join('')}</div>
          ${x.strength ? `<div class="small"><span class="ok">做得好：</span>${esc(x.strength)}</div>` : ''}${(x.next || []).map(s => `<div class="small">· ${esc(s)}</div>`).join('')}`);
      } catch (e) { out.innerHTML = ''; toast(e.message); }
    };
    if (kind === 'speaking') {
      const mic = document.getElementById('aMic'), st = document.getElementById('aState');
      mic.onclick = () => { st.textContent = MIC.busy() ? '' : '正在录音，说完再点一下'; MIC.toggle(mic, 75, async blob => { st.textContent = ''; send({ audio: await MIC.payload(blob) }); }); };
    } else {
      const ta = document.getElementById('aText'), cnt = document.getElementById('aCount');
      ta.oninput = () => { cnt.textContent = (ta.value.match(/[A-Za-z]+(?:'[A-Za-z]+)?/g) || []).length + ' 词'; };
      document.getElementById('aGo').onclick = () => send({ text: ta.value });
    }
  }
  function assessResult(name, rec, detail) {
    view.innerHTML = `<div class="stack"><div class="done-burst" aria-hidden="true">${doneRing}</div>
      <div class="tc"><span class="kicker">${esc(name)}测评结果</span><h1 class="h1">${rec ? `约 ${esc(rec.level)} · ${rec.score} 分` : '已完成'}</h1>
        ${rec ? `<p class="small muted">目标 ${esc(rec.goal)} = 100 分。这是一次测评的估计，和平时练习结合起来看更准。</p>` : ''}</div>
      ${detail}<div class="row center"><a class="btn" href="#/radar/test">测别的项目</a><a class="btn primary" href="#/radar">看雷达图</a></div></div>`;
    requestAnimationFrame(() => requestAnimationFrame(() => view.querySelectorAll('.vbar i').forEach(i => { i.style.width = i.dataset.w + '%'; })));
    if (S.user) refreshHome().catch(() => {});
  }

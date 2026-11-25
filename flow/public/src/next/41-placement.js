  /* ---------- grammar starting check: places the learner and lights the points they already know ---------- */
  async function placementView() {
    if (!S.meta) S.meta = await api('/api/next/meta');
    const t = await api('/api/next/placement');
    const items = t.items, per = t.per_band, answers = [];
    let i = 0;
    view.innerHTML = `<div class="place stack"><div><span class="kicker">语法起点小测</span><h1 class="h1">16 道题，找到你的起点</h1>
        <p class="muted">从简单到难，每 4 题一档。会就选，不会就点「不会」，不用猜。题目明显变难、开始吃力时会自动结束，一般 3–6 分钟。</p></div>
      <ul class="steps-list small"><li>做完给你一个起点等级，可以直接用它开始学</li><li>做对的语法点会点亮${S.user ? '' : '（登录后保存）'}，几天后再抽查一次</li><li>该补的点会排进今天的计划</li></ul>
      <p class="tiny muted">${esc(t.note)}</p>${aiMark('题目由 AI 辅助编写')}
      <button class="btn primary block" id="pStart">开始</button></div>`;
    document.getElementById('pStart').onclick = () => ask();
    function ask() {
      const q = items[i];
      view.innerHTML = `<div class="place stack"><div class="progress-line"><i id="pp"></i></div>
        <div class="row between"><span class="tiny muted">第 ${i + 1} 题 · 共最多 ${items.length} 题</span><span class="pill">${esc(q.band)}</span></div>
        <div class="q gq"><div class="prompt">${esc(q.prompt)}</div>
          ${q.options.map((o, j) => `<button class="ans" data-o="${q.map[j]}"><span class="k">${'ABCD'[j]}</span><span>${esc(o)}</span></button>`).join('')}</div>
        <button class="btn ghost" id="pSkip">不会</button></div>`;
      const pp = document.getElementById('pp'); pp.style.width = (i / items.length * 100) + '%';
      requestAnimationFrame(() => requestAnimationFrame(() => { pp.style.width = ((i + 1) / items.length * 100) + '%'; }));
      enter(view.querySelector('.q'));
      const pick = (choice, btn) => {
        view.querySelectorAll('.ans, #pSkip').forEach(b => b.disabled = true);
        if (btn) btn.classList.add('chosen');
        answers.push({ question: q.id, choice });
        setTimeout(step, REDUCED ? 0 : 220);
      };
      view.querySelectorAll('.ans').forEach(b => b.onclick = () => pick(+b.dataset.o, b));
      document.getElementById('pSkip').onclick = () => pick(null, null);
      announce(`第 ${i + 1} 题`);
    }
    async function step() {
      i++;
      if (i % per === 0 || i === items.length) {  // a band is done: ask whether the check is decided
        let r;
        try { r = await api('/api/next/placement', { answers, final: i === items.length }); }
        catch (e) { toast(e.message); i--; answers.pop(); ask(); return; }
        if (r.done) return result(r);
      }
      ask();
    }
    function result(r) {
      const byId = Object.fromEntries(items.map(q => [q.id, q])), lv = (S.meta && S.meta.levels || []).find(l => l.id === r.level);
      const cur = (S.home && S.home.profile) || S.guest || null;
      view.innerHTML = `<div class="place stack"><div><span class="kicker">小测结果</span><h1 class="h1">建议从 ${esc(r.level)} 开始</h1>
          ${lv ? `<p class="muted">${esc(lv.label)}：${esc(lv.desc)}</p>` : ''}</div>
        <div class="pl-bands">${r.scores.map(s => `<div class="pl-band${s.right <= per / 2 ? ' low' : ''}"><b>${esc(s.band)}</b><span>${s.right} / ${s.of}</span></div>`).join('')}</div>
        <button class="btn primary block" id="pUse">${cur && cur.level === r.level ? `保持 ${esc(r.level)}，去学习` : `用 ${esc(r.level)} 开始学`}</button>
        ${r.gaps.length ? `<div class="section stack-s"><h2 class="h2">先补这 ${r.gaps.length} 个点</h2><p class="small muted">在你的起点以内做错了。${r.saved ? '已经标为“要留意”，每天的计划会先排一个来补。' : '登录后再测，它们会排进每天的计划。'}</p>
          <div class="plist">${r.gaps.map(g => `<a class="nrow st st-watch" href="#/graph/${encodeURIComponent(g.id)}"><i class="dot" aria-hidden="true"></i><span class="t"><b>${esc(g.title)}</b></span><span class="lv">${esc(g.band)}</span><span class="go" aria-hidden="true">›</span></a>`).join('')}</div></div>` : ''}
        ${r.known.length ? `<p class="small section">${r.known.length} 个语法点做对了${r.saved ? '，已经在图谱里点亮，几天后会再抽查一次' : '；登录后再测一次，就会点亮在你的图谱里'}。</p>` : ''}
        <details class="section"><summary class="small">看每题的解析</summary><div class="stack-s">${r.results.map(x => { const q = byId[x.id]; if (!q) return '';
          const right = q.options[q.map.indexOf(x.answer)];
          return `<div class="pit"><div class="small">${esc(q.prompt)}</div><div class="${x.correct ? 'good' : 'bad'} small">${x.correct ? '✓ 答对' : '✗ 答案'}：${esc(right)}</div><div class="tiny muted">${esc(x.explanation)}</div></div>`; }).join('')}</div></details>
        <div class="row"><a class="link small" href="#/graph">看我的语法地图 →</a>${r.saved ? '<a class="link small" href="#/radar">语法这一项已记进能力雷达 →</a>' : ''}</div></div>`;
      enter(view.firstElementChild);
      announce('小测结束，建议从 ' + r.level + ' 开始');
      document.getElementById('pUse').onclick = async () => {
        if (!cur) { S.placed = r.level; location.hash = '#/welcome'; return; }  // first visit: the other questions still to come
        const prof = { ...cur, level: r.level, level_source: 'placed' };
        S.guest = prof; save('flow-next-guest', prof);
        if (S.user) { try { await api('/api/next/profile', prof); } catch (e) { toast(e.message); return; } }
        await refreshHome(); S.homeFresh = true; location.hash = '#/';
      };
    }
  }

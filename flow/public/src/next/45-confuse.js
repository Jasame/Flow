  /* ---------- words Chinese speakers mix up: how to tell them apart, and interleaved practice ---------- */
  async function confuseView() {
    const d = await api('/api/next/words/confuse');
    const LV = ['A2', 'B1', 'B2', 'C1'];
    view.innerHTML = `<div class="stack"><div><h1 class="h1">词汇辨析</h1>
        <p class="muted small">中文里是一个词，英语里是几个：借 = borrow / lend，看 = look / see / watch。选几组混着练，错的会进复习。</p></div>
      <button class="btn primary block" id="cfMix" disabled>混合练习选中的组</button>
      ${LV.map(lv => { const gs = d.groups.filter(g => g.level === lv); return gs.length ? `<section class="stack-s section"><h2 class="h2">${lv}</h2>
        <div class="cf-list">${gs.map(g => `<label class="cf-row${g.tries ? ' tried' : ''}"><input type="checkbox" value="${esc(g.id)}"><span class="t"><b class="en">${esc(g.words.join(' / '))}</b>
          <span class="tiny muted">${esc(g.how)}</span></span><span class="tiny muted">${g.tries ? `${g.right}/${g.tries}` : ''}</span><a class="btn small" href="#/words/confuse/${encodeURIComponent(g.id)}">练</a></label>`).join('')}</div></section>` : ''; }).join('')}</div>`;
    const boxes = [...view.querySelectorAll('.cf-row input')], go = document.getElementById('cfMix');
    const upd = () => { const n = boxes.filter(b => b.checked).length; go.disabled = n < 2; go.textContent = n < 2 ? '选两组以上，混合练习' : `混合练习选中的 ${n} 组`; };
    boxes.forEach(b => b.onchange = () => { if (boxes.filter(x => x.checked).length > 6) { b.checked = false; toast('一次最多混 6 组'); } upd(); });
    go.onclick = () => { location.hash = '#/words/confuse/' + boxes.filter(b => b.checked).map(b => b.value).join(','); };
    upd();
  }
  async function confuseRound(groups) {
    const d = await api('/api/next/words/confuse/round?groups=' + encodeURIComponent(groups));
    const items = d.items; let i = 0, right = 0;
    // On a phone the round is one screen, like 复习: no tabs below, the question at the bottom where the thumb is, and
    // 怎么区分 open for the first question only, then one line to tap open again (语流 B8's audit: 119-213 px past the
    // screen on an iPhone SE, the last answer under the tabs)
    document.body.classList.add('reviewing');
    view.innerHTML = `<div class="stack mix confuse"><div><a class="link small" href="#/words/confuse">← 词汇辨析</a></div>
      <div><span class="kicker">词汇辨析</span><h1 class="h1">${esc(d.groups.map(g => g.words.join(' / ')).join(' · '))}</h1></div>
      <details class="cf-how" id="cfHow" open><summary data-tap="confuse-how"><b>怎么区分</b></summary><div class="stack-s">
      ${d.groups.map(g => `<div class="howto"><b class="en">${esc(g.words.join(' / '))}</b><span class="small">${esc(g.how)}</span></div>`).join('')}</div></details>
      <div class="cf-q"><div class="mix-dots" aria-hidden="true">${items.map(() => '<i></i>').join('')}</div><div id="mixQ"></div></div></div>`;
    const dots = [...view.querySelectorAll('.mix-dots i')];
    const ask = () => {
      const it = items[i], box = document.getElementById('mixQ');
      if (i === 1) document.getElementById('cfHow').open = false;  // read once; a tap brings it back
      dots.forEach((x, k) => x.classList.toggle('now', k === i));
      box.innerHTML = `<div class="q gq enter"><div class="tiny muted">第 ${i + 1} / ${items.length} 题</div><div class="prompt">${esc(it.prompt)}</div>
        ${it.options.map((o, j) => `<button class="ans" data-o="${j}"><span class="k">${'ABCD'[j]}</span><span>${esc(o)}</span></button>`).join('')}<div class="fb" aria-live="polite"></div></div>`;
      box.querySelectorAll('.ans').forEach(b => b.onclick = () => {
        const ok = Number(b.dataset.o) === it.answer;
        box.querySelectorAll('.ans').forEach((x, j) => { x.disabled = true; if (j === it.answer) x.classList.add('right'); });
        if (!ok) b.classList.add('wrong'); else right++;
        dots[i].classList.add(ok ? 'ok' : 'no');
        api('/api/next/words/confuse/answer', { item: it.id, correct: ok }).catch(() => {});
        box.querySelector('.fb').innerHTML = `<div class="${ok ? 'ok' : 'bad'}">${ok ? '✓ 对了' : '✗ 选错了'}</div><div class="small">${esc(it.explanation)}</div>
          <button class="btn primary block" id="mixNext">${i + 1 < items.length ? '下一题' : '看结果'}</button>`;
        const nx = document.getElementById('mixNext'); nx.scrollIntoView({ block: 'nearest', behavior: REDUCED ? 'auto' : 'smooth' });
        nx.onclick = () => { i++; if (i < items.length) ask(); else done(); };
        announce(ok ? '答对了' : '答错了');
      });
    };
    const done = () => {
      document.body.classList.remove('reviewing');
      view.innerHTML = `<div class="stack mix-done">${right * 2 >= items.length ? `<div class="done-burst${right === items.length ? ' all' : ''}" aria-hidden="true">${doneRing}</div>` : ''}
        <div class="tc"><span class="kicker">词汇辨析</span><h1 class="h1">${items.length} 题做对 ${right} 题</h1>
        <p class="small">${right === items.length ? '全对！这几组你已经分得很清楚了。' : S.user ? `错的 ${items.length - right} 组已经放进复习，下次会换一道题考你。` : '登录后，错的会进复习，下次换一道题考你。'}</p></div>
        <div class="row center"><a class="btn" href="#/words/confuse">选别的组</a><button class="btn primary" id="cfAgain">再来一轮</button></div></div>`;
      document.getElementById('cfAgain').onclick = () => confuseRound(groups);
      announce(`${items.length} 题做对 ${right} 题`);
    };
    ask();
  }

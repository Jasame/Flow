  /* ---------- 发音入门: minimal pairs, tell them apart, then say them ---------- */
  async function soundsView(setId) {
    if (!S.sounds) S.sounds = (await api('/api/next/sounds')).sets;
    const sets = S.sounds;
    if (!setId) {
      view.innerHTML = `<h1 class="h1">发音入门</h1><span class="muted small">中国学习者最容易混的 ${sets.length} 组音。先听辨，再跟读；读不准的会进错题本。</span>
        <div class="grid-list section">${sets.map(s => `<a class="card flat mini" href="#/sounds/${esc(s.id)}"><span class="t">${esc(s.title)}</span><span class="pill">${s.pairs.length} 对</span>
          <span class="p">${esc(s.pairs.slice(0, 3).map(p => p[0].word + ' / ' + p[1].word).join('　'))}</span></a>`).join('')}</div>`;
      return;
    }
    const s = sets.find(x => x.id === setId); if (!s) { location.hash = '#/sounds'; return; }
    view.innerHTML = `<a class="link small" href="#/sounds">← 全部</a><h1 class="h1">${esc(s.title)}</h1><div class="card sunk small stack-s"><span>${esc(s.tip)}</span>${s.listen ? `<span class="muted">${esc(s.listen)}</span>` : ''}</div>
      <div class="section row between"><h2 class="h2">先听，再跟读</h2><button class="btn small primary" id="quiz">听辨练习</button></div>
      <p class="muted tiny">点 ▶ 听，点 ● 读这个词（再点一次停止）；${S.user ? 'AI 会告诉你目标音发得对不对。' : '登录后 AI 会告诉你目标音发得对不对。'}</p>
      <div class="stack-s pairs">${s.pairs.map((p, i) => `<div class="card flat pair">${p.map((w, j) => `<div class="pw"><span class="wd"><b>${esc(w.word)}</b>${w.phonetic ? `<span class="ph">${esc(w.phonetic)}</span>` : ''}</span>
        <button class="icon-btn" data-play="${i}-${j}" aria-label="听 ${esc(w.word)}">${ICON.speak}</button>${recBtn(`r${i}-${j}`, '跟读 ' + w.word)}<span class="tiny res" id="o${i}-${j}"></span></div>`).join('')}</div>`).join('')}</div>`;
    const word = (i, j) => s.pairs[i][j];
    view.querySelectorAll('[data-play]').forEach(b => b.onclick = () => { const [i, j] = b.dataset.play.split('-').map(Number); CLIP.word({ text: word(i, j).word, audio: word(i, j).audio }); });
    s.pairs.forEach((p, i) => p.forEach((w, j) => {
      const btn = document.getElementById(`r${i}-${j}`), out = document.getElementById(`o${i}-${j}`);
      btn.onclick = () => MIC.toggle(btn, 4, async blob => {
        if (!S.user) { needLogin('登录后 AI 会听你的发音。'); return; }
        out.innerHTML = '<span class="spin"></span>';
        try {
          const x = (await api('/api/next/say', { text: w.word, audio: await MIC.payload(blob), request_id: rid('sy') })).result;
          out.innerHTML = (x.ok ? `<span class="ok-mark">✓ 读对了</span>` : `<span class="bad-mark">听着像 ${esc(x.heard || '?')}</span>`)
            + (x.tentative ? '<div class="tiny muted">这次的判断可能不准，可以再读一次</div>' : '');  // a reference verdict (Qwen-Omni): not filed as a mistake
          if (!x.ok) toast(x.confirmed ? '两次都没读准，已放进错题本：' + (x.tip || x.note) : `AI 听成了「${x.heard || '?'}」，再读一遍确认一下`);
        } catch (e) { out.textContent = ''; toast(e.message); }
      }, { wav: true });
    }));
    document.getElementById('quiz').onclick = () => soundQuiz(s);
  }
  function soundQuiz(s) {
    // Each pair in turn (shuffled), never the same pair twice in a row.
    const deck = []; while (deck.length < 10) { const sh = s.pairs.slice().sort(() => Math.random() - 0.5); if (deck.length && sh[0] === deck[deck.length - 1]) sh.push(sh.shift()); deck.push(...sh); }
    const rounds = deck.slice(0, 10).map(p => ({ p, k: Math.random() < 0.5 ? 0 : 1 }));
    let i = 0, right = 0; const missed = [];
    const play = () => { const r = rounds[i]; CLIP.word({ text: r.p[r.k].word, audio: r.p[r.k].audio }); };
    function show() {
      if (i >= rounds.length) {
        if (S.user) api('/api/next/skill', { kind: 'discriminate', score: right / rounds.length }).catch(() => {});
        view.innerHTML = `<div class="card done-card enter">${doneRing}<h2 class="h2">听对了 ${right} / ${rounds.length}</h2><p class="muted small">${right >= 8 ? '耳朵已经分得清了，去跟读几遍吧。' : '再多听几遍对比。' + esc(s.listen || '')}</p>
          ${missed.length ? `<div class="small">听错的：${missed.map(x => `<b>${esc(x)}</b>`).join('、')}</div>` : ''}
          <div class="row center"><a class="btn" href="#/sounds/${esc(s.id)}">回到这组</a><button class="btn primary" id="again">再练一轮</button></div></div>`;
        document.getElementById('again').onclick = () => soundQuiz(s); return;
      }
      const r = rounds[i];
      view.innerHTML = `<div class="rtop"><a class="link small" href="#/sounds/${esc(s.id)}">结束</a><div class="bar-progress"><i id="rp"></i></div></div><div class="review enter"><p class="muted small">听到的是哪一个？${TOUCH ? '' : '（← → 选，空格再听）'}</p>
        <div><button class="icon-btn big" id="pl" aria-label="再听一次">${ICON.speak}</button></div>
        <div class="choice two">${r.p.map((w, k) => `<button data-k="${k}">${esc(w.word)}</button>`).join('')}</div><p class="muted tiny tc">${i + 1} / ${rounds.length}</p></div>`;
      document.getElementById('rp').style.width = (i / rounds.length * 100) + '%';
      document.getElementById('pl').onclick = play; play();
      document.onkeydown = e => { if (e.key === ' ') { e.preventDefault(); play(); } else if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') { e.preventDefault(); const b = view.querySelector(`[data-k="${e.key === 'ArrowLeft' ? 0 : 1}"]`); if (b && !b.disabled) b.click(); } };
      view.querySelectorAll('[data-k]').forEach(b => b.onclick = () => {
        const ok = Number(b.dataset.k) === r.k; if (ok) right++; else missed.push(r.p[r.k].word);
        b.classList.add(ok ? 'good' : 'again'); if (!ok) view.querySelector(`[data-k="${r.k}"]`).classList.add('good');
        view.querySelectorAll('[data-k]').forEach(x => x.disabled = true);
        setTimeout(() => { i++; show(); }, ok ? 500 : 1100);
      });
    }
    show();
  }


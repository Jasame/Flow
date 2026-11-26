    /* check: one question a screen; answer, then the evidence sentence is swept in under the two options that stay */
    function check() {
      if (!m.questions.length) {
        pane.innerHTML = `<div class="empty"><p>这篇还没有理解题。</p>${m.imported ? '<button class="btn primary" id="mkQ">✦ 让 AI 出几道理解题</button><p class="muted tiny">同时挑出值得学的表达，写一段中文导读（用 1 次 AI）。</p>' : ''}</div><div class="row between"><span></span><button class="btn" id="toOut">去用出来 →</button></div>`;
        pane.querySelector('#toOut').onclick = () => { markStep('check'); go('output'); };
        const mk = pane.querySelector('#mkQ');
        if (mk) mk.onclick = async () => {
          if (!S.user) return needLogin('登录后可以让 AI 出题。');
          mk.disabled = true; mk.innerHTML = '<span class="spin"></span> 正在出题…';
          try { await api('/api/next/import/enrich', { id, request_id: rid('ie') }); delete MAT[id]; toast('题目出好了'); route(true); }
          catch (e) { toast(e.message); mk.disabled = false; mk.textContent = '✦ 让 AI 出几道理解题'; }
        };
        return;
      }
      // One question a screen (B9, 2026-11-26; the user on the mock-ups: 完全做，按照现在的效果图). A tap answers: the other
      // options fold away, the learner's pick and the right one stay, and the block under them says which was right,
      // shows the sentence in the text, and holds the one button (下一题, 看结果 after the last). The result page lists
      // the questions (a tap opens one again, as it was answered) and leads on to 用出来.
      const n = m.questions.length, got = {};   // got[i] = { pick, answer, correct, evidence }
      const all = () => Object.keys(got).length === n;
      const note = m.imported ? aiMark('这些题目由 AI 根据这篇文章出，仅供练习') : '';
      const result = k => { const g = got[k];
        return `<p class="chk-h"><b>${g.correct ? '答对了' : '正确答案是 ' + 'ABCD'[g.answer]}</b>${g.evidence ? '<span class="tiny muted">答案在原文这里</span>' : ''}</p>${g.evidence ? `<div class="evidence">${esc(g.evidence)}</div>` : ''}
          <button class="btn primary block chk-go" id="chkGo" type="button">${all() ? '看结果' : '下一题'}</button>`; };
      // The question goes to the top of the screen (the material's title scrolls away), so that on a short phone the two
      // options that stay and the block under them are all on screen; the first question is left where the step opened.
      // Under the step bar when that stays at the top of the screen (its own height and where it sticks), else at the top.
      const toQ = () => { const q = pane.querySelector('.q'), st = document.querySelector('.steps'); if (!q) return;
        const cs = st ? getComputedStyle(st) : null, under = cs && cs.position === 'sticky' ? st.getBoundingClientRect().height + (parseFloat(cs.top) || 0) : 0;
        window.scrollTo({ top: Math.max(0, window.scrollY + q.getBoundingClientRect().top - under - 8), behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' }); };
      const onward = () => { const b = pane.querySelector('#chkGo'); if (!b) return;
        b.onclick = () => { const next = m.questions.findIndex((q, i) => !got[i]); if (next < 0) { end(); window.scrollTo(0, 0); } else { show(next); toQ(); } }; };
      const show = k => {
        const q = m.questions[k], g = got[k];
        pane.innerHTML = `<div class="stack-s chk1">${note}<div class="q" data-q="${k}"><div class="chk-top"><span class="tiny muted">第 ${k + 1} / ${n} 题${q.type ? ` · ${esc(q.type)}` : ''}</span>
          <span class="chk-dots" aria-hidden="true">${m.questions.map((x, i) => `<i${i <= k || got[i] ? ' class="on"' : ''}></i>`).join('')}</span></div>
          <div class="prompt">${esc(q.prompt)}</div>
          ${q.options.map((o, j) => `<div class="chk-o${g && j !== g.answer && j !== g.pick ? ' gone' : ''}"><button class="ans${g ? (j === g.answer ? ' right' : j === g.pick ? ' wrong' : '') : ''}" data-q="${k}" data-o="${j}"${g ? ' disabled' : ''}><span class="k">${'ABCD'[j]}</span><span class="t">${esc(o)}</span>${g && j === g.pick && !g.correct ? '<span class="me">你选的</span>' : ''}</button></div>`).join('')}
          <div class="fb card flat chk-res" aria-live="polite">${g ? result(k) : ''}</div></div></div>`;
        onward();
        const box = pane.querySelector('.q');
        box.querySelectorAll('.ans').forEach(b => b.onclick = async () => {
          if (got[k] || box.dataset.busy) return;
          const j = Number(b.dataset.o);
          box.dataset.busy = '1'; box.querySelectorAll('.ans').forEach(x => x.disabled = true);
          try {
            let r;
            try { r = await api('/api/next/check', { pack: id, index: k, choice: j }); }
            catch (e) {
              // Without a connection, a material kept on the phone is graded there with its own answers; the answer is
              // sent when the phone is back online (mistake book, progress).
              const a = e.network && m.answers && m.answers[k]; if (!a) throw e;
              r = { correct: j === a.answer, answer: a.answer, evidence: a.evidence };
              if (S.user) OUTBOX.push({ path: '/api/next/check', body: { pack: id, index: k, choice: j } });
            }
            got[k] = { pick: j, answer: r.answer, correct: r.correct, evidence: r.evidence };
            if (all()) markStep('check');
            if (!box.isConnected) return;   // the learner went to another step while it was being checked
            box.querySelectorAll('.ans').forEach(x => { const o = Number(x.dataset.o);
              if (o === r.answer) x.classList.add('right');
              else if (o === j) { x.classList.add('wrong'); x.insertAdjacentHTML('beforeend', '<span class="me">你选的</span>'); }
              else x.parentNode.classList.add('gone'); });
            box.querySelector('.fb').innerHTML = result(k);
            onward(); toQ();
            const go2 = box.querySelector('#chkGo'); if (go2 && !matchMedia('(pointer:coarse)').matches) go2.focus({ preventScroll: true });
          } catch (e) { toast(e.message); delete box.dataset.busy; box.querySelectorAll('.ans').forEach(x => x.disabled = false); }
        });
      };
      const end = () => {
        const right = Object.values(got).filter(g => g.correct).length;
        pane.innerHTML = `<div class="stack chk1 chk-end"><div class="card flat chk-sum"><p class="tiny muted">理解</p><h2 class="chk-score"><b>${right} / ${n}</b> 题答对</h2>
          <div class="chk-list">${m.questions.map((q, i) => `<button class="chk-it" type="button" data-k="${i}"><span class="k${got[i].correct ? ' ok' : ''}" aria-hidden="true">${got[i].correct ? '✓' : '✕'}</span><span class="t">${esc(q.prompt)}</span><span class="sr-only">${got[i].correct ? '答对了' : '答错了'}，点一下再看这一题</span><span class="go" aria-hidden="true">›</span></button>`).join('')}</div></div>
          <div id="score"><button class="btn primary block chk-go" id="toOut" type="button">去用出来</button>
            ${(m.expressions || []).length ? '<div class="row"><button class="link small" id="shareX" type="button" data-tap="share-material">把学会的一句做成卡片，分享或保存</button></div>' : ''}</div></div>`;
        pane.querySelectorAll('.chk-it').forEach(b => b.onclick = () => { show(Number(b.dataset.k)); toQ(); });
        const sx = pane.querySelector('#shareX'); if (sx) sx.onclick = () => shareFromMaterial(m);
        pane.querySelector('#toOut').onclick = () => go('output');
        // After a first article tried without any questions: offer the level questions (and an account) next.
        if (!S.user && !hasProfile()) pane.querySelector('#score').insertAdjacentHTML('beforeend', `<div class="card stack-s enter try-next"><b>觉得有用？按你的目标每天推荐一篇</b>
          <span class="small muted">选学习目标和想达到的水平，大约 20 秒；注册以后，进度和收藏会保存下来。</span>
          <div class="row"><a class="btn primary" href="#/welcome" data-tap="trial-level">选学习目标</a><button class="btn" id="trialReg" type="button">注册 / 登录</button></div></div>`);
        const tr = pane.querySelector('#trialReg'); if (tr) tr.onclick = () => openLogin();
      };
      show(0);
    }


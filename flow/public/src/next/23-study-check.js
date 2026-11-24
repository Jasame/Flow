    /* check: answer, then the evidence sentence is swept in and flashed in the text */
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
      const answered = {};
      pane.innerHTML = `<div class="stack">${m.questions.map((q, i) => `<div class="card flat q" data-q="${i}"><div class="tiny muted">第 ${i + 1} / ${m.questions.length} 题${q.type ? ` · ${esc(q.type)}` : ''}</div><div class="prompt">${esc(q.prompt)}</div>
        ${q.options.map((o, j) => `<button class="ans" data-q="${i}" data-o="${j}"><span class="k">${'ABCD'[j]}</span><span>${esc(o)}</span></button>`).join('')}<div class="fb" aria-live="polite"></div></div>`).join('')}
        <div id="score"></div></div>`;
      pane.querySelectorAll('.ans').forEach(b => b.onclick = async () => {
        const i = Number(b.dataset.q), j = Number(b.dataset.o);
        if (answered[i] != null) return;
        answered[i] = j;
        const box = pane.querySelector(`.q[data-q="${i}"]`);
        box.querySelectorAll('.ans').forEach(x => x.disabled = true);
        try {
          let r;
          try { r = await api('/api/next/check', { pack: id, index: i, choice: j }); }
          catch (e) {
            // Without a connection, a material kept on the phone is graded there with its own answers; the answer is
            // sent when the phone is back online (mistake book, progress).
            const a = e.network && m.answers && m.answers[i]; if (!a) throw e;
            r = { correct: j === a.answer, answer: a.answer, evidence: a.evidence };
            if (S.user) OUTBOX.push({ path: '/api/next/check', body: { pack: id, index: i, choice: j } });
          }
          answered[i] = r.correct;
          box.querySelector(`[data-o="${r.answer}"]`).classList.add('right');
          if (!r.correct) b.classList.add('wrong');
          box.querySelector('.fb').innerHTML = `<p class="small"><b>${r.correct ? '答对了。' : '答案在原文这里：'}</b></p>${r.evidence ? `<div class="evidence">${esc(r.evidence)}</div>` : ''}`;
          if (Object.keys(answered).length === m.questions.length) {
            const right = Object.values(answered).filter(Boolean).length;
            markStep('check');
            pane.querySelector('#score').innerHTML = `<div class="card sunk row between enter"><span><b>${right} / ${m.questions.length}</b> 题答对</span><button class="btn primary" id="toOut">去用出来 →</button></div>
              ${(m.expressions || []).length ? '<div class="row"><button class="link small" id="shareX" type="button" data-tap="share-material">把学会的一句做成卡片，分享或保存</button></div>' : ''}`;
            const sx = pane.querySelector('#shareX'); if (sx) sx.onclick = () => shareFromMaterial(m);
            pane.querySelector('#toOut').onclick = () => go('output');
            // After a first article tried without any questions: offer the level questions (and an account) next.
            if (!S.user && !hasProfile()) pane.querySelector('#score').insertAdjacentHTML('beforeend', `<div class="card stack-s enter try-next"><b>觉得有用？按你的目标每天推荐一篇</b>
              <span class="small muted">选学习目标和想达到的水平，大约 20 秒；注册以后，进度和收藏会保存下来。</span>
              <div class="row"><a class="btn primary" href="#/welcome" data-tap="trial-level">选学习目标</a><button class="btn" id="trialReg" type="button">注册 / 登录</button></div></div>`);
            const tr = pane.querySelector('#trialReg'); if (tr) tr.onclick = () => openLogin();
          }
        } catch (e) { toast(e.message); delete answered[i]; box.querySelectorAll('.ans').forEach(x => x.disabled = false); }
      });
    }


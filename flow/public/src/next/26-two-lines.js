  /* ---------- 听两句、答一句 (r29, the user's pick 2026-11-26): 5 分钟的表达日 ---------- */
  // Two neighbouring sentences of today's text, heard first (the recording when this text as shown has one, else the
  // server voice), then a question the AI writes on them (two_lines.ask, marked AI 生成), one sentence back by voice or
  // typing, and one line of AI feedback (two_lines.check). 给我一点提示 shows a way to begin and marks the answer as
  // helped (assisted). The phrase to learn goes into 单词本 at once, with 撤销.
  function twoPair(m) {
    // the first pair that holds one of the text's marked expressions, else the first two sentences
    const ss = m.sentences || [], ex = (m.expressions || []).map(e => (e.text || '').toLowerCase()).filter(Boolean);
    for (let i = 0; i + 1 < ss.length; i++) {
      const pair = (ss[i] + ' ' + ss[i + 1]).toLowerCase();
      if (ex.some(e => pair.indexOf(e) >= 0)) return i;
    }
    return 0;
  }
  async function twoView(pid) {
    const m = MAT[pid] || await api(materialPath(pid));
    MAT[pid] = m;
    const i = twoPair(m), lines = [(m.sentences || [])[i] || '', (m.sentences || [])[i + 1] || ''];
    const voice = !m.variant && m.audio && (m.audio.voices || []).indexOf(S.voice) >= 0 ? m.audio.version : 0;
    let q = null, hinted = false, blob = null;
    view.innerHTML = `<div class="one-task stack">
      <div><span class="kicker">今天的计划 · 约 3 分钟</span><h1 class="h1">听两句，用一句话回答</h1></div>
      <div class="two-listen"><button class="btn block" id="twPlay" type="button" data-tap="two-play">${ICON.speak}听这两句</button>
        <span class="small muted">出自《${esc(m.title)}》 · <button class="link small" id="twShow" type="button">看原文</button></span>
        <p class="two-lines" id="twLines" lang="en" hidden>${lines.map(esc).join('<br>')}</p>${aiVoiceNote('朗读由 AI 合成')}</div>
      <div class="two-q" id="twQ"><span class="tiny muted">问题 ${aiTag()}</span><b lang="en" id="twQen"><span class="spin"></span></b><span class="small muted" id="twQzh"></span>
        <span class="small two-hint" id="twHint" hidden></span></div>
      <div class="two-answer" id="twAns">
        <button class="btn primary block two-say" id="twMic" type="button">说出来</button>
        <textarea id="twText" rows="2" maxlength="300" lang="en" placeholder="用英文写一句" hidden></textarea>
        <div class="two-alts"><button class="link small hit44" id="twType" type="button">改成打字</button><button class="link small hit44" id="twHelp" type="button" data-tap="two-hint">给我一点提示</button></div>
        <button class="btn primary block" id="twSend" type="button" hidden>交上去</button></div>
      <div id="twOut"></div></div>`;
    const $ = s => view.querySelector(s);
    $('#twPlay').onclick = () => CLIP.sentence({ pack: pid, i, text: lines[0], audio: voice }, () => CLIP.sentence({ pack: pid, i: i + 1, text: lines[1], audio: voice }));
    $('#twShow').onclick = e => { $('#twLines').hidden = !$('#twLines').hidden; e.currentTarget.textContent = $('#twLines').hidden ? '看原文' : '收起原文'; };
    try {
      q = (await api('/api/next/two/ask', { pack: pid, i, lines, request_id: rid('ta') })).result;
      if (!$('#twQen')) return;
      $('#twQen').textContent = q.question; $('#twQzh').textContent = q.zh || '';
    } catch (e) { if ($('#twQen')) $('#twQen').textContent = e.message; return; }
    $('#twHelp').onclick = () => { hinted = true; $('#twHint').hidden = false; $('#twHint').textContent = '可以这样开头：' + (q.hint || ''); $('#twHelp').hidden = true; };
    $('#twType').onclick = () => { $('#twText').hidden = false; $('#twSend').hidden = false; $('#twMic').hidden = true; $('#twType').hidden = true; $('#twText').focus(); };
    const send = async body => {
      $('#twOut').innerHTML = '<p class="small muted"><span class="spin"></span> 正在看…</p>';
      try {
        const x = (await api('/api/next/two/check', Object.assign({ pack: pid, i, lines, question: q.question, assisted: hinted, request_id: rid('tc') }, body))).result;
        if (!$('#twOut')) return;
        if (x.heard_nothing) { $('#twOut').innerHTML = `<p class="small">${esc(x.note || '没听清，再说一次吧')}</p>`; return; }  // no answer: say it again
        twoFeedback(pid, m, x, body.text || '', hinted);
      } catch (e) { if ($('#twOut')) $('#twOut').innerHTML = `<p class="small">${esc(e.message)}</p>`; }
    };
    $('#twMic').onclick = () => MIC.toggle($('#twMic'), 30, async b => { blob = b; send({ audio: await MIC.payload(blob) }); });
    $('#twSend').onclick = () => {
      const text = $('#twText').value.trim();
      if ((text.match(/[A-Za-z]+/g) || []).length < 3) { toast('请用英文写至少 3 个词'); return; }
      send({ text });
    };
  }
  // The feedback, said plainly: met or not yet, what was said, a better way; the phrase to learn is kept, with 撤销.
  async function twoFeedback(pid, m, x, said, hinted) {
    const met = x.met === 'met', better = esc(x.better || '').replace(/\[\[(.+?)\]\]/g, '<b>$1</b>');
    ['#twAns', '#twQ'].forEach(s => { const e = view.querySelector(s); if (e) e.hidden = true; });
    const ls = view.querySelector('.two-listen'); if (ls) ls.hidden = true;  // the answer's page: what was said and a better way, nothing else
    view.querySelector('h1').textContent = met ? '说到了' : '意思还没到';
    scrollTo(0, 0);
    const out = view.querySelector('#twOut');
    out.innerHTML = `<div class="two-fb stack-s"><span class="tiny muted">✦ AI 点评</span><span class="${met ? 'two-ok' : ''}">${esc(x.note || '')}</span>
        ${said ? `<div class="stack-s"><span class="tiny muted">你说的</span><span class="two-en" lang="en">${esc(said)}</span></div>` : ''}
        ${better ? `<div class="stack-s"><span class="tiny muted">${met ? '还可以这样说' : '可以这样开头'}</span><span class="two-en" lang="en">${better}</span></div>` : ''}
        <span class="tiny muted" id="twSaved">${hinted ? '看了提示' : '没看提示，自己说的'}</span></div>
      ${met ? `<div class="two-row"><button class="btn block" id="twAgain" type="button">再说一次</button><a class="btn primary block" href="#/" data-tap="two-next">下一步</a></div>`
        : `<button class="btn primary block" id="twAgain" type="button">再说一次</button><a class="link small hit44 two-skip" href="#/">先跳过，明天再练</a>`}`;
    out.querySelector('#twAgain').onclick = () => twoView(pid);
    if (met && x.save && S.user) {
      try {
        const r = await api('/api/next/cards', { text: x.save, meaning: '', context: (x.better || '').replace(/\[\[|\]\]/g, ''), pack: pid });
        const line = out.querySelector('#twSaved');
        if (!r.existing && line) {
          line.innerHTML = `${hinted ? '看了提示' : '没看提示，自己说的'} · 「${esc(x.save)}」已存进单词本，明天复习 · <button class="link tiny" id="twUndo" type="button">撤销</button>`;
          line.querySelector('#twUndo').onclick = async () => {
            try { await api('/api/next/cards/delete', { id: r.card.id }); line.textContent = hinted ? '看了提示' : '没看提示，自己说的'; } catch (e) { toast(e.message); }
          };
        }
      } catch (e) { /* kept for later: the feedback stands */ }
    }
  }

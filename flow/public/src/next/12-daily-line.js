  /* ---------- 今日好句 (r27): a row under 还有时间的话 that opens in place (列表), or a card of its own (卡片) ---------- */
  // 好句 (daily_line.py, in the home data): a public-domain line one day, a sentence from a 语流 text the next, with its
  // meaning and where it comes from. 听一遍 (the text's own narration when it has one, else the browser voice),
  // 跟读 (record, play back after the original; signed in, the AI says what to fix) and 收藏 (into review).
  // The sentence (the expression to learn in bold), what it means, where it is from, and 听一遍 · 跟读 · 收藏: opened in
  // place from its row under 还有时间的话 (列表), or the whole of its card (卡片, 13-today-views.js).
  function lineEnHTML(l) {
    let en = esc(l.en).split(' / ').join('<br>');
    if (l.expression) { const k = l.en.toLowerCase().indexOf(l.expression.toLowerCase()); if (k >= 0) en = esc(l.en.slice(0, k)) + '<b>' + esc(l.en.slice(k, k + l.expression.length)) + '</b>' + esc(l.en.slice(k + l.expression.length)); }
    return en;
  }
  function lineBodyHTML(l) {
    return `<p class="lc-en${l.say.length > 100 ? ' long' : ''}" lang="en">${lineEnHTML(l)}</p>
      <p class="lc-zh">${esc(l.zh)}</p>${l.note ? `<p class="tiny muted lc-note">${esc(l.note)}</p>` : ''}
      <p class="lc-src tiny">${l.kind === 'quote' ? '— ' : ''}${esc(l.source)}${l.label ? ' · ' + esc(l.label) : ''}${l.href ? ` · <a class="link" href="${esc(l.href)}" data-tap="line-read">读原文</a>` : ''}</p>
      <div class="lc-acts"><button class="btn small" id="lcSay" type="button" data-tap="line-say">${ICON.speak}听一遍</button>
        <button class="btn small" id="lcShadow" type="button" data-tap="line-shadow" aria-expanded="false" aria-controls="lcPanel">跟读</button>
        <button class="btn small" id="lcKeep" type="button" data-tap="line-keep">${ICON.star}收藏</button>${aiVoiceNote('AI 合成', 'span')}</div>
      <div id="lcPanel" hidden></div>`;
  }
  function lineDay(l) { return new Date().toDateString() + ' ' + l.id; }
  function sayLine(l, done) {
    if (l.kind === 'text' && l.audio) CLIP.sentence({ pack: l.pack, i: l.i, text: l.say, audio: l.audio }, done);
    else TTS.say(l.say, done);
  }
  function bindLine(h) {
    const l = h && h.line, box = document.getElementById('lineCard'); if (!l || !box) return;
    // 列表: a row that opens the sentence in place (open for the rest of the day); 卡片: always open, no row
    const fold = box.querySelector('#lcFold');
    if (fold) {
      const show = open => { box.classList.toggle('open', open); fold.setAttribute('aria-expanded', String(open)); };
      show(load('flow-line-open') === lineDay(l));
      fold.onclick = () => {
        const open = !box.classList.contains('open');
        show(open); save('flow-line-open', open ? lineDay(l) : null);
        if (!open) { MIC.stop(); const p = box.querySelector('#lcPanel'); if (p && !p.hidden) box.querySelector('#lcShadow').click(); }
      };
    }
    box.querySelector('#lcSay').onclick = () => sayLine(l);
    box.querySelector('#lcKeep').onclick = e => saveCard(l.kind === 'text'
      ? { text: l.expression, meaning: l.meaning, context: l.en, pack: l.pack }
      : { text: l.say, meaning: l.zh, context: l.source }, e.currentTarget);
    const tog = box.querySelector('#lcShadow'), panel = box.querySelector('#lcPanel');
    if (!tog || !panel) return;  // 卡片: 听一遍 and 收藏 only
    let blob = null, url = '';
    tog.onclick = () => {
      const open = panel.hidden; panel.hidden = !open; tog.setAttribute('aria-expanded', String(open));
      if (!open) { MIC.stop(); return; }
      panel.innerHTML = `<div class="lc-sh stack-s"><p class="small">先听一遍，再点红点读出来（最长 15 秒），读完和原句对比着听。</p>
        <div class="row"><button class="btn small" id="lsOrig" type="button">${ICON.speak}原句</button>${recBtn('lsRec', '录音')}
          <button class="btn small" id="lsBack" type="button" disabled>对比回放</button><button class="btn small" id="lsAI" type="button" disabled>✦ AI 点评</button></div>
        <div class="lc-out" aria-live="polite"></div></div>`;
      const rec = panel.querySelector('#lsRec'), back = panel.querySelector('#lsBack'), ai = panel.querySelector('#lsAI');
      panel.querySelector('#lsOrig').onclick = () => sayLine(l);
      rec.onclick = () => MIC.toggle(rec, 15, b => { blob = b; if (url) URL.revokeObjectURL(url); url = URL.createObjectURL(b); back.disabled = false; ai.disabled = false; toast('录好了，可以对比回放'); });
      back.onclick = () => sayLine(l, () => CLIP.mine(url));  // the original, then the learner's own recording
      ai.onclick = async () => {
        if (!S.user) return needLogin('登录后，AI 会听你的跟读，指出漏读、读错和需要连读的地方。');
        if (!blob) return;
        ai.disabled = true; ai.innerHTML = '<span class="spin"></span>';
        try {
          const body = { audio: await MIC.payload(blob), request_id: rid('ls'), ...(l.kind === 'text' ? { pack: l.pack, i: l.i } : { quote: l.id.slice(2) }) };
          const x = (await api('/api/next/shadow', body)).result;
          const flu = { smooth: '流畅', ok: '基本流畅', choppy: '有点断断续续' }[x.fluency] || '';
          const sc = x.score;  // 发音分 (r27 C, the same as 听 → 跟读): accuracy, fluency and how much of the line was said
          panel.querySelector('.lc-out').innerHTML = `<div class="card flat stack-s enter">${aiMark('发音分和点评由 AI 估计，仅供参考')}${sc ? `<div class="small"><b class="lc-score">${sc.total}</b> 发音分 · 准确 ${sc.accuracy} · 流利 ${sc.fluency} · 完整 ${x.matched}/${x.words.length}<span class="tiny muted">（AI 估计，仅供参考）</span></div>` : ''}
            <div class="small">${x.words.map(w => `<span class="${w.ok ? '' : 'miss'}" lang="en">${esc(w.w)}</span>`).join(' ')}</div>
            <div class="tiny muted">AI 听到：<span lang="en">${esc(x.transcript || '（没听清）')}</span> · 读到 ${x.matched}/${x.words.length} 个词${flu && !sc ? ' · ' + flu : ''}</div>
            ${(x.sounds || []).map(sd => `<div class="small"><b lang="en">${esc(sd.sound)} ${esc(sd.word)}</b>：${esc(sd.note)}${sd.set ? ` <a class="link" href="#/sounds/${encodeURIComponent(sd.set)}" data-tap="shadow-sound">去练 ${esc(sd.set_title)} →</a>` : ''}</div>`).join('')}
            ${x.issues.map(it => `<div class="small"><b lang="en">${esc(it.word)}</b>：${esc(it.note)}</div>`).join('')}${x.tip ? `<div class="small">建议：${esc(x.tip)}</div>` : ''}</div>`;
        } catch (e) { toast(e.message); }
        ai.disabled = false; ai.textContent = '✦ AI 点评';
      };
    };
  }


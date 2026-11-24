  /* ---------- 今日好句 and 今日热点 (r27): the top of 今日 ---------- */
  // 好句 (daily_line.py, in the home data): a public-domain line one day, a sentence from a 语流 text the next, with its
  // meaning and where it comes from. 听一遍 (the text's own narration when it has one, else the browser voice),
  // 跟读 (record, play back after the original; signed in, the AI says what to fix) and 收藏 (into review).
  function lineCardHTML(h) {
    const l = h && h.line; if (!l) return '';
    let en = esc(l.en).split(' / ').join('<br>');
    if (l.expression) { const k = l.en.toLowerCase().indexOf(l.expression.toLowerCase()); if (k >= 0) en = esc(l.en.slice(0, k)) + '<b>' + esc(l.en.slice(k, k + l.expression.length)) + '</b>' + esc(l.en.slice(k + l.expression.length)); }
    return `<section class="card line-card" id="lineCard" aria-labelledby="lineTitle">
      <div class="lc-head"><h2 class="lc-title" id="lineTitle">今日好句</h2><span class="pill${l.kind === 'text' ? ' green' : ''}">${esc(l.label)}</span></div>
      <p class="lc-en${l.say.length > 100 ? ' long' : ''}" lang="en">${en}</p>
      <p class="lc-zh">${esc(l.zh)}</p>${l.note ? `<p class="tiny muted lc-note">${esc(l.note)}</p>` : ''}
      <p class="lc-src tiny">${l.kind === 'quote' ? '— ' : ''}${esc(l.source)}${l.href ? ` · <a class="link" href="${esc(l.href)}" data-tap="line-read">读原文</a>` : ''}</p>
      <div class="lc-acts"><button class="btn small" id="lcSay" type="button" data-tap="line-say">${ICON.speak}听一遍</button>
        <button class="btn small" id="lcShadow" type="button" data-tap="line-shadow" aria-expanded="false" aria-controls="lcPanel">跟读</button>
        <button class="btn small" id="lcKeep" type="button" data-tap="line-keep">${ICON.star}收藏</button></div>
      <div id="lcPanel" hidden></div></section>`;
  }
  function sayLine(l, done) {
    if (l.kind === 'text' && l.audio) CLIP.sentence({ pack: l.pack, i: l.i, text: l.say, audio: l.audio });
    else TTS.say(l.say, done);
  }
  function bindLine(h) {
    const l = h && h.line, box = document.getElementById('lineCard'); if (!l || !box) return;
    box.querySelector('#lcSay').onclick = () => sayLine(l);
    box.querySelector('#lcKeep').onclick = e => saveCard(l.kind === 'text'
      ? { text: l.expression, meaning: l.meaning, context: l.en, pack: l.pack }
      : { text: l.say, meaning: l.zh, context: l.source }, e.currentTarget);
    const tog = box.querySelector('#lcShadow'), panel = box.querySelector('#lcPanel');
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
      back.onclick = () => { const mine = () => { const a = new Audio(url); a.play().catch(() => {}); }; if (l.kind === 'text' && l.audio) { sayLine(l); setTimeout(mine, 600 + l.say.length * 70); } else sayLine(l, mine); };
      ai.onclick = async () => {
        if (!S.user) return needLogin('登录后，AI 会听你的跟读，指出漏读、读错和需要连读的地方。');
        if (!blob) return;
        ai.disabled = true; ai.innerHTML = '<span class="spin"></span>';
        try {
          const body = { audio: await MIC.payload(blob), request_id: rid('ls'), ...(l.kind === 'text' ? { pack: l.pack, i: l.i } : { quote: l.id.slice(2) }) };
          const x = (await api('/api/next/shadow', body)).result;
          const flu = { smooth: '流畅', ok: '基本流畅', choppy: '有点断断续续' }[x.fluency] || '';
          panel.querySelector('.lc-out').innerHTML = `<div class="card flat stack-s enter"><div class="small">${x.words.map(w => `<span class="${w.ok ? '' : 'miss'}" lang="en">${esc(w.w || w.word || '')}</span>`).join(' ')}</div>
            <div class="tiny muted">AI 听到：<span lang="en">${esc(x.transcript || '（没听清）')}</span> · 读到 ${x.matched}/${x.words.length} 个词${flu ? ' · ' + flu : ''}</div>
            ${x.issues.map(it => `<div class="small"><b lang="en">${esc(it.word)}</b>：${esc(it.note)}</div>`).join('')}${x.tip ? `<div class="small">建议：${esc(x.tip)}</div>` : ''}</div>`;
        } catch (e) { toast(e.message); }
        ai.disabled = false; ai.textContent = '✦ AI 点评';
      };
    };
  }
  // 今日热点: today's news text, rewritten by AI from what it found online and not checked by a person, said on it.
  function newsCardHTML(n) {
    if (!n) return '';
    return `<a class="card news-card" href="#/m/${encodeURIComponent(n.id)}" data-tap="home-news"><span class="lc-head"><span class="lc-title nc-title">今日热点</span><span class="pill amber">AI 改写 · 未经人工审核</span></span>
      <b class="nc-h">${esc(n.title)}</b>${n.preview ? `<span class="small muted nc-p">${esc(n.preview)}</span>` : ''}
      <span class="tiny muted">${n.level} · ${esc(n.theme_label || '')}${n.minutes ? ` · 约 ${n.minutes} 分钟` : ''}<span class="nc-go">读这篇 →</span></span></a>`;
  }

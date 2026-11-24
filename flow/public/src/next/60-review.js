  /* ---------- review: recognise -> recall -> spell as an item gets stronger ---------- */
  // Swiping a card (the review, the vocabulary test): right and left call what acts() returns at that moment
  // ({ right, left }, either may be missing). The whole screen takes the swipe, not only the card: on a wide screen (an
  // iPad sideways) the card is a column in the middle and the thumb rests beside it, or below it. Not from a link or a
  // field, and not while a sheet is open. A swipe is mostly sideways, without a strict
  // height limit (on a big screen it drifts). Leaving the page takes it off (swipeOff, in route()).
  function swipeOn(acts) {
    let sx = null;
    const cardEl = () => view.querySelector('.review');
    const settle = () => { const card = cardEl(); if (card) card.style.transform = ''; };
    document.ontouchstart = e => {
      // The card's own buttons count (on a phone the answer buttons are where the thumb rests; a finger that moves does
      // not press them); links, fields and buttons elsewhere (撤销) are left to themselves.
      const t = e.target, off = t.closest('a,input,select,textarea,label,.sheet') || (t.closest('button') && !t.closest('.review'));
      sx = e.touches.length === 1 && sheetEl.hidden && !isTyping(e) && !off ? [e.touches[0].clientX, e.touches[0].clientY] : null;
    };
    document.ontouchmove = e => {
      if (!sx || !acts()) return; const t = e.touches[0], dx = t.clientX - sx[0], card = cardEl();
      if (card && Math.abs(dx) > Math.abs(t.clientY - sx[1])) card.style.transform = `translateX(${dx * 0.35}px) rotate(${dx * 0.02}deg)`;
    };
    document.ontouchend = e => {
      settle(); const a = acts();
      if (!sx || !a) return; const t = e.changedTouches[0], dx = t.clientX - sx[0], dy = t.clientY - sx[1]; sx = null;
      if (Math.abs(dx) > 80 && Math.abs(dx) > Math.abs(dy) * 1.4) { const f = dx > 0 ? a.right : a.left; if (f) f(); }
    };
    document.ontouchcancel = () => { sx = null; settle(); };  // the browser took the gesture (a scroll, the system): the card goes back
  }
  function swipeOff() { document.ontouchstart = document.ontouchmove = document.ontouchend = document.ontouchcancel = null; }
  async function reviewView() {
    if (!S.user) return needLogin('登录后才能复习。');
    document.body.classList.add('reviewing');
    let first, offline = false;
    try { await OUTBOX.flush(); first = await api('/api/next/review'); save('flow-next-review-cache', { at: Date.now(), q: first }); }
    catch (e) {
      const cached = load('flow-next-review-cache');
      if (!e.network || !cached || Date.now() - cached.at > 2 * 86400000) throw e;
      const done = new Set(OUTBOX.list().map(x => x.body.id)); offline = true;
      first = { ...cached.q, items: cached.q.items.filter(x => !done.has(x.id)) };
    }
    if (offline) toast('现在没有网络：先用缓存的复习，联网后自动同步');
    prefetchAudio(first.items.flatMap(x => {
      const au = x.audio || {}, ac = au[CLIP.accent()] ? CLIP.accent() : au.us ? 'us' : null;
      return [ac ? `/audio/words/${ac}/${au[ac][0]}.mp4` : null, ...(x.examples || []).filter(e => e.audio).map(e => `/audio/${S.voice}/${encodeURIComponent(e.pack)}.json?v=${e.audio}`)];
    }));
    const lacking = first.items.filter(x => x.kind === 'word' && !(x.examples || []).length).map(x => x.text.toLowerCase()).slice(0, 8);
    if (lacking.length && !offline) api('/api/next/vocab/examples', { words: lacking, request_id: rid('ve') }).then(r => {
      Object.entries(r.examples || {}).forEach(([w, ex]) => items.forEach(x => { if (x.text.toLowerCase() === w && !(x.examples || []).length) x.examples = ex; }));
    }).catch(() => {});
    const items = first.items.slice(), seen = new Set(items.map(x => x.id));
    let i = 0, doneN = 0, left = first, farthest = 0; const tally = { again: 0, hard: 0, good: 0, easy: 0, known: 0 };
    const OUTCOME = { passed: '过关！这张错题卡完成了，不会再出现', reread: '这题先放下：回原文把那一段再读一遍更有用', later: '后天带着原文再做一次',
      tomorrow: '今天先到这儿，明天再见它', 'once-more': '答对了，下次再换一道题确认一次' };
    // Progress counts cards, not answers: a card shown again to consolidate it does not grow the total.
    const uniq = new Set(items.map(x => x.id)), doneIds = new Set();
    // How long the rest will take, from this session's own pace (about 9 seconds a card until there is one).
    const started = Date.now(); let spent = 0;
    const eta = () => { const rest = uniq.size - doneIds.size; if (rest < 3) return ''; const per = doneN ? spent / doneN : 9000; return ` · 约 ${Math.max(1, Math.round(rest * per / 60000))} 分钟`; };
    // A full batch of the most urgent 40 out of more: said as such (先做 40 个（还有 N 个）), with a place to stop after it.
    const batchN = first.batch || 40, beyond = Math.max(0, (first.due || 0) + (first.new || 0) - first.items.length);
    const pos = () => c.repeat ? '再巩固一次' : `${beyond ? `先做 ${uniq.size} 个（还有 ${beyond} 个） · ` : ''}${Math.min(uniq.size, doneIds.size + 1)} / ${uniq.size}${c.source === 'book' && c.state === 'new' ? ' · 新词' : ''}${eta()}`;
    const foot = () => `<p class="muted tiny tc rfoot">${pos()}</p>`;
    let undo = null;  // the latest rating, while it can be taken back (撤销)
    const top = () => `<div class="rtop"><a class="link small hit44" href="#/cards">结束</a><div class="bar-progress"><i id="rp"></i></div>${undo ? `<button class="link small undo" id="undo" type="button" aria-label="撤销上一张：${esc(undo.c.text)}">↶ 撤销</button>` : ''}</div>`;
    const badge = res => { const b = document.getElementById('dueBadge'); if (b && res && res.due != null) { const n = res.due + res.new; b.hidden = !n; b.textContent = n > 99 ? '99+' : n; } };
    // Touch: swipe the card right for "I know it" (or the main button), left for "I don't".
    let swipe = null;
    const onSwipe = (right, left2) => { swipe = { right, left: left2 }; };
    if (!items.length) {
      document.body.classList.remove('reviewing');
      view.innerHTML = `<div class="empty"><div class="big">✓</div><p>现在没有要复习的单词。</p><div class="row center"><a class="btn" href="#/cards">单词</a><a class="btn primary" href="#/">回到今日</a></div></div>`; return;
    }
    let c, t0, claim;
    const bar = () => {
      const rp = document.getElementById('rp'); if (rp) rp.style.width = (doneIds.size / Math.max(1, uniq.size) * 100) + '%';
      const u = document.getElementById('undo'); if (u) u.onclick = takeBack;
    };
    const keys = map => { document.onkeydown = e => { if (!sheetEl.hidden || e.metaKey || e.ctrlKey || e.altKey) return; if (e.target.matches && e.target.matches('input,textarea')) { if (e.key === 'Enter' && map.Enter && ['spellIn', 'fixIn'].includes(e.target.id)) { e.preventDefault(); map.Enter(); } return; } const f = map[e.key] || map[e.key.toLowerCase()]; if (f) { e.preventDefault(); f(); } }; };
    swipeOn(() => swipe);
    if (TOUCH && !load('flow-next-swipe-tip')) { save('flow-next-swipe-tip', 1); setTimeout(() => toast('小技巧：右滑「认识」，左滑「不认识」'), 600); }
    // A saved sentence pattern: the frame's fixed words become gaps in its example, so the front does not give it away.
    const frameCloze = (example, frame) => {
      const fixed = (frame.match(/[A-Za-z']+/g) || []).filter(w => !/^(A|B|C|sb|sth|do|doing|done|adj|n|v|X|Y)$/.test(w)).map(w => w.toLowerCase());
      let k = 0; const want = fixed.slice();
      return esc(example).replace(/[A-Za-z']+/g, w => (k < want.length && w.toLowerCase() === want[k]) ? (k++, `<span class="gap">${' '.repeat(Math.max(3, w.length))}</span>`) : w);
    };
    const sentenceOf = x => x.context && x.context.toLowerCase().includes(x.text.toLowerCase()) ? { text: x.context, form: x.text } : (x.examples && x.examples[0]) || null;
    const meaningHTML = x => x.meaning ? `<div class="mean-q">${esc(x.meaning).replace(/；|;/g, '<br>')}</div>` : '';

    // Mistakes come back on the forgetting curve too: answer the question again, fix the phrase, say the sound.
    function mistakeAsk() {
      const ex = c.extra || {}, src = { reading: '理解题', writing: '写作', speaking: '口语', translation: '翻译', pronunciation: '发音', vocabulary: '词汇辨析', grammar: '语法' }[c.skill] || '错题';
      const tag = `<span class="pill amber rtag">错题 · ${esc(src)}</span>`;
      let body = '';
      if (c.mode === 'question' && c.variant) {
        // A grammar mistake comes back as a different question on the same point: the rule is practised, not one answer.
        const v = c.variant;
        body = `${tag}<div class="tiny muted">${v.kind === 'word' ? '同一组易混词，换一道题：' + esc(c.text) : '同一个语法点，换一道题' + (c.node ? '：' + esc(c.node.title) : '')}</div><div class="prompt-q">${esc(v.prompt)}</div>
          <div class="qopts">${v.options.map((o, k) => `<button class="qopt" data-o="${v.map ? v.map[k] : k}">${esc(o)}</button>`).join('')}</div>`;
      } else if (c.mode === 'question') {
        // A reading question comes back with its part of the text: it is answered by reading, not by remembering.
        const opts = ex.options || [], ps = c.passage;
        body = `${tag}${ps ? `<div class="passage-q"><div class="tiny muted">原文片段${ps.title ? ' · ' + esc(ps.title) : ''}</div><p class="ptext" id="ptext">${ps.start ? '… ' : ''}${esc(ps.text)}${ps.end ? ' …' : ''}</p></div>` : ''}
          <div class="prompt-q">${esc(c.text)}</div><div class="qopts">${opts.map((o, k) => `<button class="qopt" data-o="${k}">${esc(o)}</button>`).join('')}</div>`;
      } else if (c.mode === 'fix') {
        // Just the sentence the mistake was in (older cards kept the whole paragraph), with the wrong part underlined.
        const sent = c.context && ex.from ? (splitSentences(c.context).find(x => x.toLowerCase().includes(ex.from.toLowerCase())) || '') : '';
        const ctx = sent ? highlight(sent, ex.from) : '';
        body = `${tag}<div class="muted small">上次这样写：</div><div class="cloze fixq">${ctx || `<mark>${esc(ex.from || '')}</mark>`}</div>
          ${c.node ? `<div>${nodeChip({ id: c.node.id, title: c.node.title, status: 'watch' })}</div>` : ''}
          <input id="fixIn" class="spell" lang="en" enterkeyhint="done" autocomplete="off" autocapitalize="off" autocorrect="off" spellcheck="false" placeholder="划线部分应该怎么写？">
          <div class="row center"><button class="btn primary" id="fixGo">确定</button><button class="btn ghost" id="fixNo">想不起来</button></div>`;
      } else {
        body = `${tag}<div class="wordbig">${esc(c.text)}</div><div><button class="icon-btn big" id="sayW" aria-label="听">${ICON.speak}</button></div>
          ${c.meaning ? `<div class="mean-q small">${esc(c.meaning)}</div>` : ''}
          <div class="row center">${recBtn('sndMic', '读一遍')}<span class="muted tiny" id="sndOut">${S.user ? '点 ● 读一遍，AI 听你读得准不准' : ''}</span></div>
          <div class="choice">${['读准了', '还不稳', '不会读'].map((t, k) => `<button class="${['good', '', 'again'][k]}" data-self="${['good', 'hard', 'again'][k]}">${t}</button>`).join('')}</div>`;
      }
      // A question or a sentence to fix has no word to put in the middle of the screen: it starts at the top.
      view.innerHTML = `${top()}<div class="review enter${c.mode === 'sound' ? '' : ' q'}">${body}${foot()}</div>`;
      bar(); swipe = null;
      const after = (r, html) => {
        const ms = Date.now() - t0;
        view.querySelector('.review').insertAdjacentHTML('beforeend', `<div class="stack-s enter">${html}<div class="row center"><button class="btn primary" id="go">下一个</button></div></div>`);
        document.getElementById('go').onclick = () => rate(r, ms); keys({ Enter: () => rate(r, ms), ' ': () => rate(r, ms) });
      };
      if (c.mode === 'question' && c.variant) {
        view.querySelectorAll('[data-o]').forEach(b => b.onclick = async () => {
          view.querySelectorAll('[data-o]').forEach(x => { x.disabled = true; });
          let r;
          if (c.variant.kind === 'word') {  // a word group: checked here, the answer recorded for the group's progress
            r = { correct: Number(b.dataset.o) === c.variant.answer, answer: c.variant.answer, explanation: c.variant.explanation };
            api('/api/next/words/confuse/answer', { item: c.variant.id, correct: r.correct, from: 'review' }).catch(() => {});
          } else {
            try { r = await api('/api/next/node/answer', { question: c.variant.id, choice: Number(b.dataset.o), from: 'review' }); }
            catch (e) { toast(e.message); view.querySelectorAll('[data-o]').forEach(x => { x.disabled = false; }); return; }
          }
          view.querySelectorAll('[data-o]').forEach(x => { if (Number(x.dataset.o) === r.answer) x.classList.add('right'); });
          if (!r.correct) b.classList.add('wrong');
          after(r.correct ? 'good' : 'again', `<div class="${r.correct ? 'ok' : 'bad'}">${r.correct ? '✓ 换了一道题也答对了' : '这题没答对'}</div><div class="small">${esc(r.explanation || '')}</div>
            ${!r.correct && c.variant.kind === 'word' ? `<div class="tiny muted">${esc(c.meaning || '')}</div>` : ''}
            ${!r.correct && c.node ? `<a class="link small" href="#/graph/${encodeURIComponent(c.node.id)}">回到「${esc(c.node.title)}」看一遍讲解 →</a>` : ''}`);
        });
        keys({ 1: () => view.querySelector('.qopt:nth-child(1)').click(), 2: () => view.querySelector('.qopt:nth-child(2)').click(), 3: () => view.querySelector('.qopt:nth-child(3)').click(), 4: () => view.querySelector('.qopt:nth-child(4)').click() });
      } else if (c.mode === 'question') {
        view.querySelectorAll('[data-o]').forEach(b => b.onclick = () => {
          const k = Number(b.dataset.o), ok = k === ex.answer, ps = c.passage;
          view.querySelectorAll('[data-o]').forEach(x => { x.disabled = true; if (Number(x.dataset.o) === ex.answer) x.classList.add('right'); });
          if (!ok) b.classList.add('wrong');
          const pt = document.getElementById('ptext'); if (pt && ps && ps.evidence) pt.innerHTML = (ps.start ? '… ' : '') + highlight(ps.text, ps.evidence) + (ps.end ? ' …' : '');
          after(ok ? 'good' : 'again', `<div class="${ok ? 'ok' : 'bad'}">${ok ? '✓ 这次答对了，这道题过关' : '还是没答对'}</div>${ex.evidence && !(pt && ps) ? `<div class="small"><span class="muted">原文依据：</span>${esc(ex.evidence)}</div>` : ''}
            ${!ok && c.pack ? `<a class="link small" href="#/m/${encodeURIComponent(c.pack)}/read">回原文把这一段再读一遍 →</a>` : ''}`);
        });
        keys({ 1: () => view.querySelector('[data-o="0"]').click(), 2: () => view.querySelector('[data-o="1"]').click(), 3: () => view.querySelector('[data-o="2"]').click(), 4: () => view.querySelector('[data-o="3"]').click() });
      } else if (c.mode === 'fix') {
        const inp = document.getElementById('fixIn'); setTimeout(() => inp.focus(), 50);
        const norm = s => s.toLowerCase().replace(/[^a-z' ]+/g, ' ').replace(/\s+/g, ' ').trim();
        const done = v => {
          view.querySelectorAll('#fixGo,#fixNo').forEach(b => b.remove()); inp.disabled = true;
          const ok = !!v && norm(v) === norm(c.text);
          if (ok || !v) return after(ok ? 'good' : 'again', `<div class="${ok ? 'ok' : 'bad'}">${ok ? '✓ 改对了' : '应该是'}：<b>${esc(c.text)}</b></div>${c.meaning ? `<div class="small">${esc(c.meaning)}</div>` : ''}`);
          // Not the same words: often a correct other wording. The learner compares and decides; no loop over one word.
          const ms = Date.now() - t0;
          view.querySelector('.review').insertAdjacentHTML('beforeend', `<div class="stack-s enter"><div class="small"><span class="muted">你写的：</span>${esc(v)}</div>
            <div class="small"><span class="muted">参考改法：</span><b>${esc(c.text)}</b></div>${c.meaning ? `<div class="small muted">${esc(c.meaning)}</div>` : ''}
            <div class="row center"><button class="btn" id="fixSame">我写的也对</button><button class="btn primary" id="fixMiss">没写对，记下了</button></div></div>`);
          document.getElementById('fixSame').onclick = () => rate('good', ms); document.getElementById('fixMiss').onclick = () => rate('again', ms);
        };
        document.getElementById('fixGo').onclick = () => done(inp.value.trim());
        document.getElementById('fixNo').onclick = () => done('');
        keys({ Enter: () => done(inp.value.trim()) });
      } else {
        document.getElementById('sayW').onclick = () => CLIP.word(c); CLIP.word(c);
        const mic = document.getElementById('sndMic'), out = document.getElementById('sndOut');
        mic.onclick = () => MIC.toggle(mic, 4, async blob => {
          out.innerHTML = '<span class="spin"></span>';
          try { const x = (await api('/api/next/say', { text: c.text, audio: await MIC.payload(blob), request_id: rid('sy') })).result; out.innerHTML = x.ok ? '<span class="ok-mark">✓ 这次读准了</span>' : `<span class="bad-mark">AI 听成了「${esc(x.heard || '?')}」</span><div class="tiny muted">${esc(x.tip || x.note || '')}</div>`; }
          catch (e) { out.textContent = e.message; }
        });
        view.querySelectorAll('[data-self]').forEach(b => b.onclick = () => rate(b.dataset.self, Date.now() - t0));
        onSwipe(() => rate('good', Date.now() - t0), () => rate('again', Date.now() - t0));
      }
    }
    function ask() {
      if (i >= items.length) return more();
      c = items[i]; claim = null; t0 = Date.now();
      if (['fix', 'question', 'sound'].includes(c.mode)) return mistakeAsk();
      const sent = sentenceOf(c), pattern = c.kind !== 'word' && /^句型｜例：/.test(c.meaning || '');
      // Nothing to recall from (an imported phrase with no meaning or sentence): show it and ask whether it is known.
      const m = (c.mode === 'recall' || c.mode === 'cloze') && !c.meaning && !sent ? 'recognize' : c.mode;
      let body = '', choices = '';
      if (m === 'recognize') {
        body = `<div class="wordbig${c.kind === 'word' ? '' : ' phrase'}">${esc(c.text)}</div><div class="ph">${esc(c.phonetic || '')} <button class="icon-btn" id="sayW" aria-label="朗读">${ICON.speak}</button></div>`;
        choices = ['认识', '模糊', '不认识'];
      } else if (m === 'spell') {
        body = `<div class="muted small">听发音，拼出这个词</div><div><button class="icon-btn big" id="sayW" aria-label="再听一次">${ICON.speak}</button></div>${meaningHTML(c)}
          ${sent ? `<div class="cloze">${gapped(sent.text, sent.form, false)}</div>` : ''}
          <input id="spellIn" class="spell" lang="en" enterkeyhint="done" autocomplete="off" autocapitalize="off" autocorrect="off" spellcheck="false" aria-label="拼写" placeholder="输入单词">`;
      } else if (pattern) {
        body = `<div class="hint">回忆这个句型</div><div class="cloze">${frameCloze(c.meaning.replace(/^句型｜例：/, ''), c.text)}</div>`;
        choices = ['想起来了', '有点模糊', '想不起来'];
      } else {
        body = `${meaningHTML(c) || '<div class="hint">回忆这个表达</div>'}${sent ? `<div class="cloze">${gapped(sent.text, sent.form, false)}</div>` : `<div class="cloze"><span class="gap">？</span></div>`}
          ${c.kind === 'word' ? `<div class="muted tiny">首字母 ${esc(c.text[0])} · ${c.text.length} 个字母</div>` : ''}`;
        choices = ['想起来了', '有点模糊', '想不起来'];
      }
      view.innerHTML = `${top()}<div class="review enter">${body}
        ${m === 'spell' ? '<div class="row center"><button class="btn primary" id="check">确定</button><button class="btn ghost" id="giveup">不会</button></div>'
          : `<div class="choice">${choices.map((t, k) => `<button class="${['good', '', 'again'][k]}" data-claim="${['know', 'fuzzy', 'forgot'][k]}">${t}${TOUCH ? '' : `<small>${k + 1}</small>`}</button>`).join('')}</div>`}
        ${foot()}</div>`;
      bar(); swipe = null;
      const say = document.getElementById('sayW'); if (say) say.onclick = () => CLIP.word(c);
      if (m === 'recognize' || m === 'spell') CLIP.word(c);
      if (m === 'spell') {
        const inp = document.getElementById('spellIn'); setTimeout(() => inp.focus(), 50);
        const check = () => { const v = inp.value.trim(); if (!v) return; spellResult(v); };
        document.getElementById('check').onclick = check; document.getElementById('giveup').onclick = () => spellResult('');
        keys({ Enter: check });
      } else {
        view.querySelectorAll('[data-claim]').forEach(b => b.onclick = () => reveal(b.dataset.claim));
        keys({ 1: () => reveal('know'), 2: () => reveal('fuzzy'), 3: () => reveal('forgot') });
        onSwipe(() => reveal('know'), () => reveal('forgot'));
      }
    }
    function answerHTML() {
      return `<div class="wordbig">${esc(c.text)}</div><div class="ph">${esc(c.phonetic || '')} <button class="icon-btn" id="sayW" aria-label="朗读">${ICON.speak}</button></div>
        ${c.meaning ? `<div class="mean-a">${esc(c.meaning).replace(/；|;/g, '<br>')}</div>` : ''}${rootsHTML(c)}${examplesHTML(c)}`;
    }
    function reveal(how) {
      claim = how; const ms = Date.now() - t0;
      const next = how === 'know' ? [['记错了', 'again', 'again x'], ['没错，下一个', 'good', 'good primary']] : [[how === 'fuzzy' ? '下一个' : '记住了，下一个', how === 'fuzzy' ? 'hard' : 'again', 'primary']];
      view.innerHTML = `${top()}<div class="review open-card">${answerHTML()}
        <div class="row center">${next.map(([t, r, cls]) => `<button class="btn ${cls.includes('primary') ? 'primary' : ''}" data-rate="${r}">${t}</button>`).join('')}</div>
        ${c.kind === 'word' && how === 'know' ? '<button class="btn ghost small" id="tooEasy">太简单了，以后不用再背</button>' : ''}${foot()}</div>`;
      bar(); bindExamples(view, c);
      document.getElementById('sayW').onclick = () => CLIP.word(c);
      if (c.mode !== 'recognize') CLIP.word(c);
      view.querySelectorAll('[data-rate]').forEach(b => b.onclick = () => rate(b.dataset.rate, ms));
      const te = document.getElementById('tooEasy'); if (te) te.onclick = () => known();
      const primary = next[next.length - 1][1];
      keys({ Enter: () => rate(primary, ms), ' ': () => rate(primary, ms), x: () => how === 'know' && rate('again', ms) });
      onSwipe(() => rate(primary, ms), how === 'know' ? () => rate('again', ms) : null);
    }
    function spellResult(v) {
      const ms = Date.now() - t0, want = c.text.toLowerCase(), got = v.toLowerCase();
      const dist = (a, b) => { const d = Array.from({ length: a.length + 1 }, (_, k) => [k]); for (let j = 1; j <= b.length; j++) d[0][j] = j;
        for (let k = 1; k <= a.length; k++) for (let j = 1; j <= b.length; j++) d[k][j] = Math.min(d[k - 1][j] + 1, d[k][j - 1] + 1, d[k - 1][j - 1] + (a[k - 1] === b[j - 1] ? 0 : 1)); return d[a.length][b.length]; };
      const r = !got ? 'again' : got === want ? 'good' : (want.length > 4 && dist(got, want) === 1) ? 'hard' : 'again';
      const msg = r === 'good' ? '<div class="ok">✓ 拼对了</div>' : r === 'hard' ? `<div class="warn">差一点：你写的是 <s>${esc(v)}</s></div>` : got ? `<div class="bad">你写的是 <s>${esc(v)}</s></div>` : '';
      view.innerHTML = `${top()}<div class="review open-card">${msg}${answerHTML()}<div class="row center"><button class="btn primary" id="go">下一个</button></div>${foot()}</div>`;
      bar(); bindExamples(view, c); document.getElementById('sayW').onclick = () => CLIP.word(c); CLIP.word(c);
      document.getElementById('go').onclick = () => rate(r, ms); keys({ Enter: () => rate(r, ms), ' ': () => rate(r, ms) });
      onSwipe(() => rate(r, ms), null);
    }
    let busy = false;
    async function rate(r, ms) {
      if (busy) return; busy = true; document.onkeydown = null;
      try {
        const body = { id: c.id, rating: r, mode: c.mode, ms: Math.min(ms, 3599999), at: Math.floor(Date.now() / 1000) };
        const before = { c, r, i, had: doneIds.has(c.id), left, inserted: -1, offline: false, body };
        let res;
        try { res = await api('/api/next/review', body); }
        catch (e) {
          if (!e.network) throw e;
          OUTBOX.push({ path: '/api/next/review', body }); before.offline = true;  // offline: keep going, sync later
          const learning = c.state !== 'review' || r === 'again';
          res = { card: { ...c, state: learning && r !== 'easy' ? (c.state === 'review' ? 'relearning' : 'learning') : 'review' }, due: left ? left.due : 0, new: left ? left.new : 0 };
          if (r === 'good' && c.state === 'learning' && (c.step || 0) >= 1) res.card.state = 'review';
          res.card.step = (c.step || 0) + 1;
        }
        tally[r]++; doneN++; left = res; i++; doneIds.add(c.id); badge(res); spent += Math.min(ms, 60000); undo = before;
        const n = res.card;
        if (res.outcome && OUTCOME[res.outcome]) toast(OUTCOME[res.outcome]);
        if ((r === 'good' || r === 'easy') && n.due) farthest = Math.max(farthest, Math.round((n.due * 1000 - Date.now()) / 86400000));
        // Only what is due again within minutes (a miss, or a fuzzy new card) comes back in this session, a few cards later;
        // a card answered right waits for its next step (10 minutes, then days) and is picked up by "继续" or the next session.
        const soon = n.due ? n.due * 1000 - Date.now() < 5 * 60000 : r === 'again';
        // At most one more try in this session; a card missed again waits for tomorrow (the server moves it there too).
        const parked = ['tomorrow', 'later', 'passed', 'reread'].includes(res.outcome) || (c.tries || 0) >= 1;
        if ((n.state === 'learning' || n.state === 'relearning') && soon && !parked) {
          const again = { ...c, ...n, mode: c.kind === 'word' ? 'recognize' : c.mode, repeat: true, tries: (c.tries || 0) + 1 };
          before.inserted = Math.min(items.length, i + 4); items.splice(before.inserted, 0, again);
        }
        const el = view.querySelector('.review'); if (el) el.classList.add('out');
        setTimeout(ask, REDUCED ? 0 : 180);
      } catch (e) { toast(e.message); keys({}); }
      finally { busy = false; }
    }
    // 撤销: the latest rating taken back (a slip of the finger); the same card comes up again to answer.
    async function takeBack() {
      const u = undo; if (!u || busy) return; busy = true;
      try {
        let res = u.left;
        if (u.offline) OUTBOX.unpush({ path: '/api/next/review', body: u.body });
        else res = await api('/api/next/review/undo', { id: u.c.id });
        tally[u.r]--; doneN--; if (!u.had) doneIds.delete(u.c.id);
        if (u.inserted >= 0) items.splice(u.inserted, 1);
        i = u.i; left = res; undo = null; badge(res);
        toast('已撤销，再答一次这一张'); ask();
      } catch (e) { undo = null; toast(e.message); const b = document.getElementById('undo'); if (b) b.remove(); }
      finally { busy = false; }
    }
    async function known() {
      try { const res = await api('/api/next/vocab/known', { id: c.id, known: true }); tally.known++; doneN++; i++; doneIds.add(c.id); left = res; toast('已标为熟知'); ask(); } catch (e) { toast(e.message); }
    }
    async function more() {
      document.onkeydown = null;
      try {
        const q = await api('/api/next/review');
        const fresh = q.items.filter(x => !seen.has(x.id) || (x.state !== 'new' && x.due * 1000 <= Date.now()));
        const extra = fresh.filter(x => !items.slice(i).some(y => y.id === x.id));
        // this batch's own cards due again (a miss, a learning step) are finished first; after a full batch, the next
        // one waits behind a place to stop
        const back = extra.filter(x => seen.has(x.id)), next = extra.filter(x => !seen.has(x.id));
        const go = back.length ? back : uniq.size >= batchN ? [] : next;
        if (go.length) { go.forEach(x => { seen.add(x.id); uniq.add(x.id); items.push(x); }); return ask(); }
        left = q;
      } catch (e) { /* show the summary anyway */ }
      refreshHome().catch(() => {});
      swipeOff(); document.body.classList.remove('reviewing');
      undo = null;
      const rated = tally.again + tally.hard + tally.good + tally.easy, mins = Math.max(1, Math.round((Date.now() - started) / 60000));
      view.innerHTML = `<div class="card done-card enter">${doneRing}<h2 class="h2">这一轮复习了 ${doneIds.size} 个</h2>
        <p class="small rsum">用时约 ${mins} 分钟${rated ? ` · 记住了 ${Math.round((tally.good + tally.easy) / rated * 100)}%` : ''}<span id="tmr"></span></p>${doneN > doneIds.size ? `<p class="muted tiny">共作答 ${doneN} 次，其中 ${doneN - doneIds.size} 次是再巩固</p>` : ''}
        <p class="muted small">记得 ${tally.good + tally.easy} · 模糊 ${tally.hard} · 忘了 ${tally.again}${tally.known ? ' · 熟知 ' + tally.known : ''}。</p>
        <p class="small cheer">${tally.good + tally.easy ? `记得的都往后推了${farthest > 1 ? `，最远的要 ${farthest} 天后才再见` : ''}。` : ''}${tally.again ? `忘了的 ${tally.again} 个明天再来：忘了再想起来，正是记牢的过程。` : tally.good + tally.easy ? '这一轮全都记得，很稳。' : ''}</p>
        ${left && (left.due + left.new) ? (uniq.size >= batchN
          ? `<p class="small stop-ok" id="stopOk"><b>今天做到这里也行。</b>最要紧的 ${uniq.size} 个已经复习过了，还有 ${left.due + left.new} 个，之后几天接着来，最容易忘的排在前面。</p>`
          : `<p class="small">还有 ${left.due + left.new} 个可以继续。</p>`) : ''}
        <div class="row center">${left && (left.due + left.new) && uniq.size >= batchN
          ? `<button class="btn" id="again">再做 ${Math.min(batchN, left.due + left.new)} 个</button><a class="btn primary" href="#/">今天就到这里</a>`
          : `<a class="btn" href="#/cards">单词</a>${left && (left.due + left.new) ? '<button class="btn primary" id="again">继续</button>' : '<a class="btn primary" href="#/">回到今日</a>'}`}</div>
        ${left && !(left.due + left.new) ? '<div class="row center"><button class="btn ghost small" id="moreNew">还想多背：再学 10 个新词</button></div>' : ''}</div>`;
      api('/api/next/vocab').then(o => { const t = document.getElementById('tmr'); if (t && o.forecast && o.forecast[1] != null) t.textContent = ` · 明天大约复习 ${o.forecast[1]} 个`; }).catch(() => {});
      const ag = document.getElementById('again'); if (ag) ag.onclick = () => reviewView();
      const mn = document.getElementById('moreNew');
      if (mn) mn.onclick = async () => { mn.disabled = true; try { const r = await api('/api/next/vocab/more', { n: 10 }); if (r.added) reviewView(); else { toast('词书里的词都学过了'); } } catch (e) { toast(e.message); mn.disabled = false; } };
    }
    ask();
  }


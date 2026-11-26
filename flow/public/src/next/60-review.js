  /* ---------- review: recognise -> recall -> spell as an item gets stronger ---------- */
  // Swiping a card (the review, the vocabulary test): right and left call what acts() returns at that moment
  // ({ right, left }, either may be missing). The whole screen takes the swipe, not only the card: on a wide screen (an
  // iPad sideways) the card is a column in the middle and the thumb rests beside it, or below it. Not from a link or a
  // field, and not while a sheet is open. A swipe is mostly sideways, without a strict
  // height limit (on a big screen it drifts). Leaving the page takes it off (swipeOff, in route()).
  let SWIPED = 0, SCROLLED = 0;  // when a swipe last answered; when the page last scrolled (the tap that stops a scroll answers nothing)
  addEventListener('scroll', () => { SCROLLED = Date.now(); }, { passive: true });  // when a swipe last answered: the click a browser may still send after it is not a tap on the card
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
      if (Math.abs(dx) > 80 && Math.abs(dx) > Math.abs(dy) * 1.4) { const f = dx > 0 ? a.right : a.left; if (f) { SWIPED = Date.now(); f(); } }
    };
    document.ontouchcancel = () => { sx = null; settle(); };  // the browser took the gesture (a scroll, the system): the card goes back
  }
  function swipeOff() { document.ontouchstart = document.ontouchmove = document.ontouchend = document.ontouchcancel = null; view.onclick = view.onpointerdown = null; activityEnd(); }
  // goOn: 继续复习 past today's share (r28: a day of words has a cap in minutes), or the extra new words of 再学 10 个
  // part 'other': 其他复习 (练习 → 复习; review-split-plan.md): mistakes, saved sentences and patterns, apart from the words
  async function reviewView(goOn, part) {
    if (!S.user) return needLogin('登录后才能复习。');
    document.body.classList.add('reviewing');
    const other = part === 'other', CACHE = other ? 'flow-next-review-other' : 'flow-next-review-cache';
    // this page's address: a learner who leaves while an answer is being saved gets nothing drawn over the next page
    const HERE = location.hash;
    const R = '/api/next/review' + (other ? '?part=other' : goOn ? '?more=1' : '');
    const NAME = other ? '复习错题和句型' : '复习单词';
    const seenOld = !!(load('flow-next-review-cache') || load('flow-next-swipe-tip'));  // this device reviewed before (the cache is saved just below)
    let first, offline = false;
    try { await OUTBOX.flush(); first = await api(R); save(CACHE, { at: Date.now(), q: first }); }
    catch (e) {
      const cached = load(CACHE);
      if (!e.network || !cached || Date.now() - cached.at > 2 * 86400000) throw e;
      const done = new Set(OUTBOX.list().map(x => x.body.id)); offline = true;
      first = { ...cached.q, items: cached.q.items.filter(x => !done.has(x.id)) };
    }
    if (offline) toast('现在没有网络：先用缓存的复习，联网后自动同步');
    // the file each word will play (CLIP.wordSrc: its own small clip on an iPhone or iPad, its sprite elsewhere)
    prefetchAudio(first.items.flatMap(x => [CLIP.wordSrc(x), ...(x.examples || []).filter(e => e.audio).map(e => `/audio/${S.voice}/${encodeURIComponent(e.pack)}.json?v=${e.audio}`)]));
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
    // The buttons at the bottom, in one place on both sides of the card (the user, 2026-11-25: 「把操作的按钮全都放在底部」;
    // AnkiDroid and AnkiMobile keep them there): what is above scrolls when the answer is long, they stay (80-flat.css).
    const actions = (html, over) => `<div class="ractions">${over || ''}${html}${foot()}</div>`;
    // the word itself plays too (like the speaker beside its phonetics); a tap on it answers nothing
    const sayBtn = (label, big) => `<button class="icon-btn ${big ? 'big' : 'say-btn'}" id="sayW" type="button" aria-label="${label}（AI 朗读）">${ICON.speak}</button>`;
    const wordHTML = (cls) => `<div class="wordbig tapsay${cls || ''}">${esc(c.text)}</div><div class="ph">${esc(c.phonetic || '')}${sayBtn('播放读音')}</div>`;
    let undo = null;  // the latest rating, while it can be taken back (撤销)
    // the answer shown and not yet rated: 撤销 turns the card back (a slip on the front, a tap or a button, sent nothing)
    let peek = null;
    // 太简单 (语流 B9, A0): a small button at the top right on both sides of a word card, out of the three parts' way;
    // the card leaves at once, 撤销 for six seconds at the bottom
    // voice: this side plays the word (or its examples) — 「读音由 AI 合成」, one grey line under the progress bar (aiVoiceNote)
    const top = voice => `<h1 class="sr-only">${NAME}</h1><div class="rtop"><a class="link small hit44" href="#/cards">结束</a><div class="bar-progress"><i id="rp"></i></div>${peek ? '<button class="link small undo" id="undo" type="button" aria-label="撤销：回到这一张的正面">↶ 撤销</button>' : undo ? `<button class="link small undo" id="undo" type="button" aria-label="撤销上一张：${esc(undo.c.text)}">↶ 撤销</button>` : '<button class="link small undo" id="undo" type="button" disabled aria-label="撤销（还没有可撤销的）">↶ 撤销</button>'}${viewBtn()}</div>${sub(voice)}`;
    // the line under the bar (B9, 2026-11-26: the top bar is 结束 · 进度条 · 撤销 · 简|详 only, so the bar keeps its width):
    // 「读音由 AI 合成」 on the left, a grey 「太简单」 on the right for a word to recall
    const sub = voice => { const easy = c && c.kind === 'word' && !['fix', 'question', 'sound'].includes(c.mode);
      return voice || easy ? `<div class="rsub">${voice ? aiVoiceNote('读音由 AI 合成', 'p', 'rvoice') : '<span></span>'}${easy ? '<button class="link small easy-btn" id="easyBtn" type="button" aria-label="太简单，以后不用再背">太简单</button>' : ''}</div>` : ''; };
    const badge = res => { if (!other && res && res.due != null) tabCount('dueBadge', res.due + res.new, '单词'); };  // 02-shell.js
    // Touch: swipe the card right for "I know it" (or the main button), left for "I don't".
    let swipe = null;
    const onSwipe = (right, left2) => { swipe = { right, left: left2 }; };
    if (!items.length) {
      document.body.classList.remove('reviewing');
      view.innerHTML = `<div class="empty"><div class="big">✓</div><p>${other ? '现在没有要复习的错题和句型。' : '现在没有要复习的单词。'}</p><div class="row center">${other ? '<a class="btn" href="#/practice">练习</a>' : '<a class="btn" href="#/cards">单词</a>'}<a class="btn primary" href="#/">回到今日</a></div></div>`; return;
    }
    let c, t0, claim;
    const bar = () => {
      const rp = document.getElementById('rp'); if (rp) rp.style.width = (doneIds.size / Math.max(1, uniq.size) * 100) + '%';
      const u = document.getElementById('undo'); if (u) u.onclick = takeBack;
      const eb = document.getElementById('easyBtn'); if (eb) eb.onclick = () => known();
      document.querySelectorAll('#vmode [data-v]').forEach(x => { x.onclick = () => { if ((x.dataset.v === 'detailed') !== detailed()) flipView(); }; });
    };
    const keys = map => { document.onkeydown = e => { if (!sheetEl.hidden || e.metaKey || e.ctrlKey || e.altKey) return; if (e.target.matches && e.target.matches('input,textarea')) { if (e.key === 'Enter' && map.Enter && ['spellIn', 'fixIn'].includes(e.target.id)) { e.preventDefault(); map.Enter(); } return; } const f = map[e.key] || map[e.key.toLowerCase()]; if (f) { e.preventDefault(); f(); } }; };
    swipeOn(() => swipe);
    // the swipe tip, once; where the zones' first-time guide comes it says this too
    // once per account (08-tips.js: put away on another device, or by seeing the 新手引导 through, it is not said again)
    if (TOUCH && tipSeen('swipe-tip', 'flow-next-swipe-tip') === false && !(KNOW.tap() && tipSeen('review-zones', 'flow-tap-guide') === false)) { TIPS.mark('swipe-tip'); setTimeout(() => toast(KNOW.side() === 'right' ? '小技巧：右滑「认识」，左滑「不认识」' : '小技巧：左滑「认识」，右滑「不认识」'), 600); }
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
        body = `${tag}<div class="wordbig">${esc(c.text)}</div><div class="row center">${sayBtn('听', true)}</div>
          ${c.meaning ? `<div class="mean-q small">${esc(c.meaning)}</div>` : ''}
          <div class="row center">${recBtn('sndMic', '读一遍')}<span class="muted tiny" id="sndOut">${S.user ? '点 ● 读一遍，AI 听你读得准不准' : ''}</span></div>
          ${actions(`<div class="choice">${KNOW.order([['读准了', 'good', 'good'], ['还不稳', '', 'hard'], ['不会读', 'again', 'again']]).map(([t, cls, r]) => `<button class="${cls}" data-self="${r}">${t}</button>`).join('')}</div>`)}`;
      }
      // A question or a sentence to fix has no word to put in the middle of the screen: it starts at the top.
      view.innerHTML = `${top(c.mode === 'sound')}<div class="review enter${c.mode === 'sound' ? '' : ' q'}">${body}${c.mode === 'sound' ? '' : foot()}</div>`;
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
          try { const x = (await api('/api/next/say', { text: c.text, audio: await MIC.payload(blob), request_id: rid('sy') })).result; out.innerHTML = aiTag() + ' ' + (x.ok ? '<span class="ok-mark">✓ 这次读准了</span>' : `<span class="bad-mark">AI 听成了「${esc(x.heard || '?')}」</span><div class="tiny muted">${esc(x.tip || x.note || '')}</div>`) + (x.tentative ? '<div class="tiny muted">AI 的判断只作参考，不会进错题本</div>' : ''); }
          catch (e) { out.textContent = e.message; }
        });
        view.querySelectorAll('[data-self]').forEach(b => b.onclick = () => rate(b.dataset.self, Date.now() - t0));
        onSwipe(...KNOW.swipe(() => rate('good', Date.now() - t0), () => rate('again', Date.now() - t0)));
      }
    }
    function ask(quiet) {
      if (location.hash !== HERE) return;
      if (i >= items.length) return more();
      c = items[i]; claim = null; t0 = Date.now(); view.onclick = view.onpointerdown = null;
      if (['fix', 'question', 'sound'].includes(c.mode)) return mistakeAsk();
      const sent = sentenceOf(c), pattern = c.kind !== 'word' && /^句型｜例：/.test(c.meaning || '');
      // Nothing to recall from (an imported phrase with no meaning or sentence): show it and ask whether it is known.
      const m = (c.mode === 'recall' || c.mode === 'cloze') && !c.meaning && !sent ? 'recognize' : c.mode;
      let body = '', choices = '';
      if (m === 'recognize') {
        body = wordHTML(c.kind === 'word' ? '' : ' phrase') + (detailed() ? `<div class="detail-line">${esc(metaLine())}</div>` : '');
        choices = ['认识', '模糊', '不认识'];
      } else if (m === 'spell') {
        body = `<div class="muted small">听发音，拼出这个词</div><div class="row center">${sayBtn('再听一次', true)}</div>${meaningHTML(c)}
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
      view.innerHTML = `${top(m === 'recognize' || m === 'spell')}<div class="review enter">${body}
        ${m === 'spell' ? `<div class="row center"><button class="btn primary" id="check">确定</button><button class="btn ghost" id="giveup">不会</button></div>${foot()}`
          : actions(`<div class="choice">${KNOW.order(choices.map((t, k) => [t, ['good', '', 'again'][k], ['know', 'fuzzy', 'forgot'][k]])).map(([t, cls, how], k) => `<button class="${cls}" data-claim="${how}">${t}${TOUCH ? '' : `<small>${['←', '↓', '→'][k]}</small>`}</button>`).join('')}</div>`)}</div>`;
      // 「认识」 moved to the right (2026-11-25): said once to those who reviewed before, so a habit does not answer wrong
      if (m !== 'spell' && first.veteran && seenOld && KNOW.side() === 'right' && tipSeen('know-side', 'flow-know-tip') === false) {
        view.querySelector('.review').insertAdjacentHTML('afterbegin', `<div class="know-tip" id="knowTip" role="note"><span class="small">「认识」换到右边了，想换回去：我的 → 设置</span><button class="btn small" type="button" id="knowTipOk">知道了</button></div>`);
        document.getElementById('knowTipOk').onclick = () => { TIPS.mark('know-side'); const t = document.getElementById('knowTip'); if (t) t.remove(); };
      }
      bar(); swipe = null;
      sayable();
      if (!quiet && (m === 'recognize' || m === 'spell')) CLIP.word(c);
      if (m === 'spell') {
        const inp = document.getElementById('spellIn'); setTimeout(() => inp.focus(), 50);
        const check = () => { const v = inp.value.trim(); if (!v) return; spellResult(v); };
        document.getElementById('check').onclick = check; document.getElementById('giveup').onclick = () => spellResult('');
        keys({ Enter: check });
      } else {
        view.querySelectorAll('[data-claim]').forEach(b => b.onclick = () => reveal(b.dataset.claim));
        const fronts = [...view.querySelectorAll('[data-claim]')].map(b => () => reveal(b.dataset.claim));
        keys({ ...KNOW.keys(fronts), ArrowDown: fronts[1], ' ': fronts[1], e: () => c.kind === 'word' && known() });  // ← 不会 · ↓ or space 模糊 · → 会 (by place) · E 太简单
        if (KNOW.tap()) tapZones([...view.querySelectorAll('.ractions [data-claim]')]);
        onSwipe(...KNOW.swipe(() => reveal('know'), () => reveal('forgot')));
      }
    }
    // One rule on every side of the card (the owner, 2026-11-26: 「一以贯之的用户操作习惯，不要反直觉」): the page is the
    // buttons below it, part for part — three on the front (不会 · 模糊 · 会), two on the back (记错了 · 没错), and when the
    // back has one button the whole page is it (下一个). 「认识」's side (KNOW) sets which end is which, for taps, swipes and
    // keys alike. What can be tapped (the word, a speaker, 再看, 撤销, links, the top line) does its own thing first; a
    // finger that moved, a swipe just done, or a tap in the first moment after the card turned (a double tap) answers nothing.
    // the part tapped lights up for a moment with the word it stands for (不认识, 模糊, 认识 …): an answer is seen to be taken
    function flash(r, n, k, btn) {
      const f = document.createElement('div'), tone = btn.classList.contains('good') ? 'good' : btn.classList.contains('again') ? 'again' : 'mid';
      f.className = 'zone-flash ' + tone; f.textContent = btn.firstChild.textContent.replace(/，.*$/, '');
      Object.assign(f.style, { left: (r.left + r.width * k / n) + 'px', width: (r.width / n) + 'px', top: Math.max(0, r.top) + 'px', height: Math.min(innerHeight, r.bottom) - Math.max(0, r.top) + 'px' });
      document.body.appendChild(f); setTimeout(() => f.remove(), REDUCED ? 250 : 520);
    }
    let turned = 0;
    function tapZones(btns, back) {
      if (!btns.length) return;
      const card = view.querySelector('.review'); if (!card) return;
      card.classList.add('zoned'); turned = Date.now();  // a new card or a turned one: the next 600 ms are not an answer
      const skip = '.tapsay,#sayW,[data-exp],a,button,input,summary,details,.ractions,.know-tip,.rtop,.rsub,.rvoice,.sheet';
      let down = null;
      view.onpointerdown = e => { down = [e.clientX, e.clientY]; };
      view.onclick = e => {
        const d = down; down = null;
        if (!card.isConnected) { view.onclick = view.onpointerdown = null; return; }  // the card is gone (rated, the round over)
        if (Date.now() - turned < 600 || Date.now() - SCROLLED < 300) return;  // a double tap, or the tap that ends a scroll
        const g = card.querySelector('.zone-guide'); if (g) { g.remove(); return; }  // the first tap puts the guide away, answers nothing
        if (e.target.closest(skip) || !d || Math.hypot(e.clientX - d[0], e.clientY - d[1]) > 10 || Date.now() - SWIPED < 350) return;
        const r = card.getBoundingClientRect(), n = btns.length;
        const k = Math.min(n - 1, Math.max(0, Math.floor((e.clientX - r.left) / (r.width / n))));
        flash(r, n, k, btns[k]); btns[k].click();
      };
      // the first time on each side: its parts drawn over the card, a tap puts it away (and answers nothing); once per
      // account (08-tips.js), so another phone does not draw it again
      const tip = back ? 'review-zones-back' : 'review-zones', local = back ? 'flow-tap-guide-back' : 'flow-tap-guide';
      const draw = () => {
        if (!card.isConnected || card.querySelector('.know-tip, #zoneGuide')) return;
        const swipe = KNOW.side() === 'right' ? ['右滑', '左滑'] : ['左滑', '右滑'];
        const say = !back ? `点左、中、右也能作答，和下面的按钮一样；也可以${swipe[0]}「认识」，${swipe[1]}「不认识」。点单词只是播放。点一下收起`
          : `翻面也是这三块：${swipe[0]}或点${KNOW.side() === 'right' ? '右' : '左'}边是没错，另一边是记错了，中间是模糊。翻面前选的那个加了框，回车或空格就是它。点一下收起`;
        card.insertAdjacentHTML('beforeend', `<div class="zone-guide n${btns.length}" id="zoneGuide" aria-hidden="true">${btns.map(b => `<span>${esc(b.firstChild.textContent)}</span>`).join('')}<p>${say}</p></div>`);
        const gd = document.getElementById('zoneGuide'), ra = card.querySelector('.ractions');
        if (ra) gd.style.bottom = (card.getBoundingClientRect().bottom - ra.getBoundingClientRect().top) + 'px';  // the buttons stay in view below it
        // shown once: seen now. It lets taps through (pointer-events: none), so the word still plays and the buttons answer;
        // a tap on the page itself only puts it away (above)
        TIPS.mark(tip); TIPS.mark('swipe-tip');
      };
      // not known on this phone yet (a new device): drawn over the card, it can come when the answer does without moving
      // anything; known: now or never
      const seen = tipSeen(tip, local);
      if (seen === false) draw(); else if (seen === null) TIPS.load().then(() => { if (tipSeen(tip, local) === false) draw(); });
    }
    // the speaker and the word play it; the examples' speakers are bound by bindExamples
    function sayable() {
      view.querySelectorAll('#sayW, .review .tapsay').forEach(b => { b.onclick = () => CLIP.word(c); });
    }
    function answerHTML() {
      if (!detailed()) return `${wordHTML()}
        ${c.meaning ? `<div class="mean-a">${esc(c.meaning).replace(/；|;/g, '<br>')}</div>` : ''}${rootsHTML(c)}${examplesHTML({ ...c, examples: (c.examples || []).slice(0, 2) })}`;
      // 详细 (B9's sheet, words-modes/): the meaning by part of speech, the roots, the examples as many as 简洁 shows (two)
      // and the rest one tap away, the confusable group (词汇辨析) with how to tell them apart, a grey line of how well it is held
      const pos = (c.meaning || '').split(/；|;/).map(x => x.trim()).filter(Boolean).map(x => { const m = x.match(/^([a-z]+\.)\s*(.*)$/);
        return m ? `<b>${esc(m[1])}</b><span>${esc(m[2])}</span>` : `<span class="all">${esc(x)}</span>`; }).join('');  // a grid: the 词性 column as wide as its widest (B9, r36 audit)
      const g = (c.confuse || [])[0], n = (c.context ? 1 : 0) + (c.examples || []).length, open = 2;
      return `${wordHTML()}${pos ? `<div class="mean-a mean-pos">${pos}</div>` : ''}${rootsHTML(c)}
        <div class="ex-wrap${n > open ? ' fold' : ''}">${examplesHTML(c)}${n > open ? `<button class="ex-more" type="button" id="exMore">再看 ${n - open} 句 ⌄</button>` : ''}</div>
        ${g ? `<details class="conf-wrap"><summary class="conf-line"><span>易混：${g.words.map(w => `<b>${esc(w)}</b>`).join(' / ')}</span><span class="how">怎么区分 ›</span></summary><p class="small">${esc(g.how)}</p></details>` : ''}
        <div class="mem-line">${esc(memLine())}</div>`;
    }
    // 简洁 / 详细 for this card (KNOW.view): words only, new words and reviews apart; the switch at the top changes it for
    // that kind and keeps it; the card is drawn again in place (not an answer, the clock runs on)
    function detailed() { return !!c && c.kind === 'word' && KNOW.view(c.state === 'new' ? 'new' : 'review') === 'detailed'; }
    function viewBtn() {
      if (!c || c.kind !== 'word' || ['fix', 'question', 'sound'].includes(c.mode)) return '';
      const d = detailed();
      return `<div class="vt" id="vmode" role="radiogroup" aria-label="复习卡">${[['simple', '简', '简洁'], ['detailed', '详', '详细']].map(([v, t, l]) => `<button type="button" role="radio" data-v="${v}" aria-label="${l}" aria-checked="${(v === 'detailed') === d}"${(v === 'detailed') === d ? ' class="on"' : ''}>${t}</button>`).join('')}</div>`;
    }
    function flipView() {
      KNOW.setView(c.state === 'new' ? 'new' : 'review', detailed() ? 'simple' : 'detailed');
      if (view.querySelector('.open-card') && claim) reveal(claim, true);
      else { const t = t0; ask(true); t0 = t; }
    }
    const TAGS = { zk: '中考', gk: '高考', cet4: '四级', cet6: '六级', ky: '考研', tem4: '专四', tem8: '专八', ielts: '雅思', toefl: '托福', gre: 'GRE' };
    const ago = s => { const d = Math.floor((Date.now() / 1000 - s) / 86400); return d <= 0 ? '今天' : d === 1 ? '昨天' : d + ' 天前'; };
    // 详细's grey line on the front: which exams list it, how common it is, how many times seen — nothing of its meaning
    function metaLine() {
      const r = c.rank || 0, freq = !r ? '' : r <= 2000 ? '最常用' : r <= 5000 ? '常用' : r <= 10000 ? '较常用' : '';
      const seen = c.state === 'new' || !c.reps ? '新词' : `第 ${c.reps + 1} 次见${c.last ? ' · 上次 ' + ago(c.last) : ''}`;
      return [...(c.tags || []).map(t => TAGS[t]).filter(Boolean).slice(0, 3), freq, seen].filter(Boolean).join(' · ');
    }
    function memLine() {
      if (c.state === 'new' || !c.reps) return '新词 · 第一次见';
      const r = c.recall == null ? null : c.recall;
      return `记得的把握：${r == null ? '—' : r >= 0.9 ? '高' : r >= 0.7 ? '中' : '低'} · 复习过 ${c.reps} 次${c.lapses ? `，忘过 ${c.lapses} 次` : ''}`;
    }
    function reveal(how, quiet) {
      claim = how; const ms = Date.now() - t0; peek = { t0 };
      if (!quiet) haptic('select');
      // The back has the front's three parts too, the same width, place and colour (the owner: 「只做了一个界面的三分点」):
      // left 记错了 (again), middle 模糊 (hard), right 没错 (good). The one the front chose is framed: ↵ and space take it, and
      // the back can still change it (认识 thought, the answer seen, it was wrong: the left). After 不认识 the right says
      // 其实认识 — a slip on the front, mended — never 记住了: what is rated is what was recalled before the answer.
      const right = how === 'forgot' ? '其实认识' : '没错';
      const want = { know: 'good', fuzzy: 'hard', forgot: 'again' }[how];
      const next = KNOW.order([[right, 'good', 'good'], ['模糊', 'hard', ''], [how === 'forgot' ? '不认识' : '记错了', 'again', 'again']]);
      view.innerHTML = `${top(true)}<div class="review open-card">${answerHTML()}
        ${actions(`<div class="choice">${next.map(([t, r, cls], k) => `<button class="${cls}${r === want ? ' def' : ''}" data-rate="${r}"${r === want ? ' aria-describedby="defNote"' : ''}>${t}${TOUCH ? '' : `<small>${['←', '↓', '→'][k]}</small>`}</button>`).join('')}</div><span class="sr-only" id="defNote">翻面前选的就是这一个，回车或空格就是它</span>`)}</div>`;
      bar(); bindExamples(view, c); sayable();
      const em = document.getElementById('exMore'); if (em) em.onclick = () => { em.closest('.ex-wrap').classList.remove('fold'); em.remove(); };
      if (!quiet && c.mode !== 'recognize') CLIP.word(c);
      view.querySelectorAll('[data-rate]').forEach(b => b.onclick = () => rate(b.dataset.rate, ms));
      const acts = next.map(([, r]) => () => rate(r, ms));
      keys({ ...KNOW.keys(acts), ArrowDown: acts[1], Enter: () => rate(want, ms), ' ': () => rate(want, ms), x: () => rate('again', ms), e: () => known() });
      onSwipe(...KNOW.swipe(() => rate('good', ms), () => rate('again', ms)));  // the same way as on the front
      if (KNOW.tap()) tapZones([...view.querySelectorAll('.ractions [data-rate]')], true);
    }
    function spellResult(v) {
      const ms = Date.now() - t0, want = c.text.toLowerCase(), got = v.toLowerCase();
      const dist = (a, b) => { const d = Array.from({ length: a.length + 1 }, (_, k) => [k]); for (let j = 1; j <= b.length; j++) d[0][j] = j;
        for (let k = 1; k <= a.length; k++) for (let j = 1; j <= b.length; j++) d[k][j] = Math.min(d[k - 1][j] + 1, d[k][j - 1] + 1, d[k - 1][j - 1] + (a[k - 1] === b[j - 1] ? 0 : 1)); return d[a.length][b.length]; };
      const r = !got ? 'again' : got === want ? 'good' : (want.length > 4 && dist(got, want) === 1) ? 'hard' : 'again';
      const msg = r === 'good' ? '<div class="ok">✓ 拼对了</div>' : r === 'hard' ? `<div class="warn">差一点：你写的是 <s>${esc(v)}</s></div>` : got ? `<div class="bad">你写的是 <s>${esc(v)}</s></div>` : '';
      view.innerHTML = `${top(true)}<div class="review open-card">${msg}${answerHTML()}${actions('<div class="choice one"><button class="primary" id="go">下一个</button></div>')}</div>`;
      bar(); bindExamples(view, c); sayable(); CLIP.word(c);
      const em = document.getElementById('exMore'); if (em) em.onclick = () => { em.closest('.ex-wrap').classList.remove('fold'); em.remove(); };
      document.getElementById('go').onclick = () => rate(r, ms); keys({ Enter: () => rate(r, ms), ' ': () => rate(r, ms) });
      onSwipe(...KNOW.swipe(() => rate(r, ms), null));
    }
    let busy = false;
    async function rate(r, ms) {
      if (busy) return; busy = true; document.onkeydown = null; peek = null; view.onclick = view.onpointerdown = null;  // one answer per card
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
        haptic(r === 'again' ? 'warning' : r === 'hard' ? 'tap' : 'success');
        if (!other) activity('review', doneIds.size, uniq.size);
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
      if (peek && !busy) { const t = peek.t0; peek = null; ask(true); t0 = t; haptic('tap'); return; }  // the front again; the time runs on
      const u = undo; if (!u || busy) return; busy = true;
      try {
        let res = u.left;
        if (u.offline) OUTBOX.unpush({ path: '/api/next/review', body: u.body });
        else res = await api('/api/next/review/undo', { id: u.c.id });
        tally[u.r]--; doneN--; if (!u.had) doneIds.delete(u.c.id);
        if (u.inserted >= 0) items.splice(u.inserted, 1);
        i = u.i; left = res; undo = null; badge(res);
        toast('已撤销，再答一次这一张'); haptic('tap'); ask();
      } catch (e) { undo = null; toast(e.message); const b = document.getElementById('undo'); if (b) b.remove(); }
      finally { busy = false; }
    }
    async function known() {
      if (busy) return; busy = true; peek = null; view.onclick = view.onpointerdown = null;
      const was = { c, i };
      try { const res = await api('/api/next/vocab/known', { id: c.id, known: true }); tally.known++; doneN++; i++; doneIds.add(c.id); left = res; haptic('tap'); easyBar(was); ask(); }
      catch (e) { toast(e.message); } finally { busy = false; }
    }
    // 「已标为太简单，不再复习 · 撤销」 at the bottom for six seconds; 撤销 brings the card back to be answered
    function easyBar(was) {
      document.querySelectorAll('.easy-bar').forEach(x => x.remove());
      const b = document.createElement('div'); b.className = 'easy-bar'; b.setAttribute('role', 'status');
      b.innerHTML = `<span>已标为太简单，「${esc(was.c.text)}」不再复习</span><button class="link small" type="button">撤销</button>`;
      document.body.appendChild(b);
      const gone = setTimeout(() => b.remove(), 6000);
      b.querySelector('button').onclick = async () => {
        clearTimeout(gone); b.remove();
        try { left = (await api('/api/next/vocab/known', { id: was.c.id, known: false })); tally.known--; doneN--; doneIds.delete(was.c.id); items.splice(i, 0, was.c); haptic('tap'); toast('已撤销，再答一次这一张'); ask(); }
        catch (e) { toast(e.message); }
      };
    }
    async function more() {
      document.onkeydown = null;
      try {
        const q = await api(R);
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
      if (location.hash !== HERE) return;
      swipeOff(); document.body.classList.remove('reviewing');
      undo = null;
      const rated = tally.again + tally.hard + tally.good + tally.easy, mins = Math.max(1, Math.round((Date.now() - started) / 60000));
      view.innerHTML = `<h1 class="sr-only">${NAME}</h1><div class="card done-card enter">${doneRing}<h2 class="h2">这一轮复习了 ${doneIds.size} 个</h2>
        <p class="small rsum">用时约 ${mins} 分钟${rated ? ` · 记住了 ${Math.round((tally.good + tally.easy) / rated * 100)}%` : ''}<span id="tmr"></span></p>${doneN > doneIds.size ? `<p class="muted tiny">共作答 ${doneN} 次，其中 ${doneN - doneIds.size} 次是再巩固</p>` : ''}
        <p class="muted small">记得 ${tally.good + tally.easy} · 模糊 ${tally.hard} · 忘了 ${tally.again}${tally.known ? ' · 熟知 ' + tally.known : ''}。</p>
        <p class="small cheer">${tally.good + tally.easy ? `记得的都往后推了${farthest > 1 ? `，最远的要 ${farthest} 天后才再见` : ''}。` : ''}${tally.again ? `忘了的 ${tally.again} 个明天再来：忘了再想起来，正是记牢的过程。` : tally.good + tally.easy ? '这一轮全都记得，很稳。' : ''}</p>
        ${left && !(left.due + left.new) && left.later ? `<p class="small stop-ok" id="capDone"><b>今天的单词做完了。</b>还有 ${left.later} 个复习留到之后几天，最容易忘的排在前面。想多背可以继续。</p>` : ''}
        ${left && (left.due + left.new) ? (uniq.size >= batchN
          ? `<p class="small stop-ok" id="stopOk"><b>今天做到这里也行。</b>最要紧的 ${uniq.size} 个已经复习过了，还有 ${left.due + left.new} 个，之后几天接着来，最容易忘的排在前面。</p>`
          : `<p class="small">还有 ${left.due + left.new} 个可以继续。</p>`) : ''}
        <div class="row center">${left && (left.due + left.new) && uniq.size >= batchN
          ? `<button class="btn" id="again">再做 ${Math.min(batchN, left.due + left.new)} 个</button><a class="btn primary" href="#/">今天就到这里</a>`
          : `${left && !(left.due + left.new) && left.later ? '<button class="btn" id="againMore">继续复习</button>' : (other ? '<a class="btn" href="#/practice">练习</a>' : '<a class="btn" href="#/cards">单词</a>')}${left && (left.due + left.new) ? '<button class="btn primary" id="again">继续</button>' : '<a class="btn primary" href="#/">回到今日</a>'}`}</div>
        ${left && !(left.due + left.new) && !left.later ? '<div class="row center"><button class="btn ghost small" id="moreNew">还想多背：再学 10 个新词</button></div>' : ''}
        ${left && !(left.due + left.new) ? '<div class="row center"><button class="link small hit44" type="button" id="onceAsk">今天或明天什么时候有空复习？</button></div>' : ''}</div>`;
      api('/api/next/vocab').then(o => { const t = document.getElementById('tmr'); if (t && o.forecast && o.forecast[1] != null) t.textContent = ` · 明天大约复习 ${o.forecast[1]} 个`; }).catch(() => {});
      const ag = document.getElementById('again'); if (ag) ag.onclick = () => reviewView(goOn);
      const am = document.getElementById('againMore'); if (am) am.onclick = () => reviewView(true);
      const oa = document.getElementById('onceAsk'); if (oa) oa.onclick = () => remindOnce();
      const mn = document.getElementById('moreNew');
      if (mn) mn.onclick = async () => { mn.disabled = true; try { const r = await api('/api/next/vocab/more', { n: 10 }); if (r.added) reviewView(true); else { toast('词书里的词都学过了'); } } catch (e) { toast(e.message); mn.disabled = false; } };
    }
    ask();
  }


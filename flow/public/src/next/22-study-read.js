    /* after reading: the words looked up here (and the pre-reading list) can go into review in one tap */
    function newWordItems() {
      const looked = [...((m._looked && m._looked.values()) || [])];
      const mine = new Set((m.mine || []).map(x => x.form));
      const items = looked.filter(x => !mine.has(x.word)).map(x => ({ ...x, on: true }));
      (m.preread || []).forEach(w => { if (!items.some(x => x.word === w.word) && !mine.has(w.form)) items.push({ word: w.word, meaning: w.meaning, sentence: findContext(w.form, lines()), on: false }); });
      return items.slice(0, 14);
    }
    function newWordsHTML() {
      const items = newWordItems();
      if (!items.length) return '<p class="muted small">读的时候点过的词会出现在这里，勾选后按遗忘曲线复习。</p>';
      return `<div class="stack-s" id="newWords"><div class="row between"><b class="small">这篇的生词</b><span class="muted tiny">勾选的会按遗忘曲线复习</span></div>
        <div class="nw-list">${items.map((x, k) => `<label class="nw"><input type="checkbox" data-nw="${k}" ${x.on ? 'checked' : ''}><b>${esc(x.word)}</b><span class="muted tiny">${esc(x.meaning || '')}</span></label>`).join('')}</div>
        <div><button class="btn small primary" id="nwAdd">加入复习</button></div></div>`;
    }
    function bindNewWords() {
      const box = pane.querySelector('#newWords'); if (!box) return;
      const items = newWordItems();
      box.querySelector('#nwAdd').onclick = async e => {
        if (!S.user) return needLogin('登录后可以把这些词加入复习。');
        const pick = [...box.querySelectorAll('[data-nw]:checked')].map(c => items[Number(c.dataset.nw)]).filter(Boolean);
        if (!pick.length) { toast('先勾选要复习的词'); return; }
        const btn = e.currentTarget; btn.disabled = true;
        try {
          const r = await api('/api/next/vocab/add', { pack: id, items: pick.map(x => ({ word: x.word, sentence: x.sentence || '' })) });
          toast(r.added ? `已加入 ${r.added} 个词` : '这些词已经在复习里了'); refreshHome().catch(() => {});
          m.mine = (m.mine || []).concat(pick.map(x => ({ form: x.word.toLowerCase(), id: 0 }))); m._looked = new Map();
          if (m._onLook) m._onLook();
        } catch (x) { toast(x.message); btn.disabled = false; }
      };
    }
    // What this text leaves you with, in one folded card under the text: expressions, words (the ones looked up
    // too, to put into review) and grammar points, one tab at a time. Open or closed and the tab are remembered.
    function gainsTabs() {
      const vocab = m.vocabulary.length + (m.variant ? m.variant.notes.length : 0), fresh = newWordItems().filter(x => x.on).length;
      return [
        m.expressions.length && ['expr', '表达', m.expressions.length, () => `<p class="muted tiny">能直接搬进你自己话里的搭配。</p><div class="stack-s">${m.expressions.map((x, i) => `<div class="expr"><span class="e">${esc(x.text)}</span><span class="row"><button class="icon-btn" data-sayx="${i}" aria-label="朗读">${ICON.speak}</button><button class="icon-btn" data-sx="${i}" aria-label="收藏 ${esc(x.text)}">${ICON.star}</button></span><span class="m">${esc(x.meaning)}</span><span class="n">${esc(x.note || '')}</span></div>`).join('')}</div>`],
        ['words', '词汇', vocab + fresh, () => `${m.vocabulary.length ? `<div class="vocab-list">${m.vocabulary.map((v, i) => `<div class="vrow"><span class="term">${esc(v.term)}</span><button class="icon-btn" data-sv="${i}" aria-label="收藏 ${esc(v.term)}">${ICON.star}</button><span class="muted small">${esc(v.meaning)}</span><span class="vex">${esc(v.example || '')}</span></div>`).join('')}</div>` : ''}
          ${(m.variant && m.variant.notes.length) ? `<b class="small">改写版新出现的表达</b><div class="vocab-list">${m.variant.notes.map((v, i) => `<div class="vrow"><span class="term">${esc(v.text)}</span><button class="icon-btn" data-sn="${i}" aria-label="收藏">${ICON.star}</button><span class="muted small">${esc(v.meaning)}</span></div>`).join('')}</div>` : ''}
          <div id="nwSlot">${newWordsHTML()}</div>`],
        m.notes.length && ['notes', '知识点', m.notes.length, () => `<div class="stack-s">${m.notes.map(n => `<div class="knote"><div class="row between">${nodeChip({ id: n.node, title: n.title, status: n.status })}<span class="tiny muted">${esc(n.label)}</span></div><q>${esc(n.quote)}</q><div class="small muted">${esc(n.explanation)}</div></div>`).join('')}
          <a class="link small" href="#/graph">在知识图谱里看 →</a></div>`]].filter(Boolean);
    }
    function gainsSummary() {
      const vocab = m.vocabulary.length + (m.variant ? m.variant.notes.length : 0), fresh = newWordItems().filter(x => x.on).length;
      return [m.expressions.length && `${m.expressions.length} 个表达`, vocab && `${vocab} 个词`, m.notes.length && `${m.notes.length} 个知识点`, fresh && `查过 ${fresh} 个词，可以加入复习`].filter(Boolean).join(' · ') || '查过的词会收在这里';
    }
    function gainsHTML() {
      const tabs = gainsTabs();
      let open = false, cur = tabs[0][0];
      try { open = localStorage.getItem('flow-gains-open') === '1'; const t = localStorage.getItem('flow-gains-tab'); if (tabs.some(x => x[0] === t)) cur = t; } catch (e) { /* private mode */ }
      return `<details class="card flat fold gains section" id="gains"${open ? ' open' : ''}><summary data-tap="read-gains"><b>这篇的收获</b><span class="tiny muted" id="gainsSum">${gainsSummary()}</span></summary>
        <div class="seg gtabs" role="tablist" aria-label="这篇的收获">${tabs.map(([k, l, n]) => `<button role="tab" type="button" data-gt="${k}" aria-selected="${k === cur}">${l} ${n}</button>`).join('')}</div>
        ${tabs.map(([k, , , html]) => `<div class="gpane stack-s" data-gp="${k}" role="tabpanel"${k === cur ? '' : ' hidden'}>${html()}</div>`).join('')}</details>`;
    }
    function bindGains() {
      const g = pane.querySelector('#gains'); if (!g) return;
      g.addEventListener('toggle', () => { try { localStorage.setItem('flow-gains-open', g.open ? '1' : ''); } catch (e) { /* private mode */ } });
      g.querySelectorAll('[data-gt]').forEach(b => b.onclick = () => {
        g.querySelectorAll('[data-gt]').forEach(x => x.setAttribute('aria-selected', String(x === b)));
        g.querySelectorAll('[data-gp]').forEach(p => { p.hidden = p.dataset.gp !== b.dataset.gt; });
        try { localStorage.setItem('flow-gains-tab', b.dataset.gt); } catch (e) { /* private mode */ }
      });
    }

    /* read: tap a word, ✦ explains a sentence, select to save, read-along, expressions, knowledge points */
    function wordClass(part) {
      const key = part.toLowerCase();
      const isVocab = m.vocabulary.some(v => v.term.toLowerCase() === key);
      const mine = (m.mine || []).some(x => x.form === key) ? ' mine' : '';
      return (isVocab ? 'w vocab' : (m.hard[key] ? 'w hard' : 'w')) + mine;
    }
    // The ✦ is glued to the sentence's last word, so it can never wrap to the start of the next line.
    // A line that begins with a speaker ("Staff: …") starts a new turn on its own line.
    function sentenceHTML(s, i) {
      let html = wordSpans(s, wordClass, ` data-s="${i}"`);
      const at = html.lastIndexOf('<span class="');
      const btn = `<button class="link tiny" data-ex="${i}" aria-label="AI 讲解第 ${i + 1} 句">✦</button>`;
      html = at < 0 ? html + btn : html.slice(0, at) + '<span class="nobr">' + html.slice(at) + btn + '</span>';
      const turn = i > 0 && /^[A-Z][a-z]+(?: [A-Z][a-z]+)?:\s/.test(s) ? ' turn' : '';
      return `<span class="sent${turn}" data-si="${i}">${html}</span> `;
    }
    function read() {
      const ls = lines();
      // One row of tools (中文导读, 改写成我的难度, 伴读) and one line of colour key and hints, so the text starts on the
      // first screen of a phone; the summary opens under the row.
      const variantBar = m.variant ? `<div class="seg" role="tablist"><button data-ver="v" aria-selected="${!st.showOriginal}">适合我的版本（${m.variant.level} · AI 改写）</button><button data-ver="o" aria-selected="${st.showOriginal}">原文（${m.original_level}）</button><span></span></div>` : '';
      pane.innerHTML = `<div class="read-tools">${m.summary_zh ? '<button class="chip small" id="zhGuide" type="button" aria-expanded="false" aria-controls="zhText">中文导读</button>' : ''}
          ${m.can_variant ? `<button class="chip small" id="mkVar" type="button" title="这篇原文是 ${m.original_level}，你选的是 ${m.user_level}">改写成 ${m.user_level} 难度</button>` : ''}
          <button class="btn small" id="readAlong" title="边听边看文字，读到哪句亮哪句">${playIcon(false, 14)}<span>伴读</span></button>
          <button class="link tiny" id="alongRestart" type="button" hidden>从头开始</button></div>
        <p class="tiny muted sv-prep" id="svPrep" role="status" hidden></p>
        ${m.summary_zh ? `<p class="guide-zh small" id="zhText" hidden>${esc(m.summary_zh)}</p>` : ''}${variantBar}
        <div class="read-hint tiny muted"><div class="legend"><span>本篇词汇</span><span class="h">可能超出你的水平</span>${(m.mine || []).length ? '<span class="m">你在背的词</span>' : ''}</div>
          <span>点词查词，点句尾 ✦ 讲解整句，${TOUCH ? '长按拖选' : '选中'}可收藏${TOUCH ? '' : '；键盘：Tab 进入正文后 ← → 逐词，↵ 查词，E 讲解'}</span></div>
        <div class="text" id="reader" tabindex="0" aria-label="正文：左右方向键逐词移动，回车查词">${ls.map((s, i) => sentenceHTML(s, i)).join('')}</div>
        <div class="section row between"><span></span><button class="btn primary" id="toCheck">读完了，做理解题 →</button></div>
        ${gainsHTML()}`;
      const reader = pane.querySelector('#reader');
      // The narration's timings are fetched now, so a tap on 伴读 can start the sound inside the tap (in-app browsers
      // such as WeChat's refuse sound that starts after a download).
      let nmNow = null; narration(ls).then(x => { nmNow = x; }).catch(() => {});
      pane.querySelectorAll('[data-ver]').forEach(b => b.onclick = () => { st.showOriginal = b.dataset.ver === 'o'; m._showOriginal = st.showOriginal; read(); });
      const zg = pane.querySelector('#zhGuide');
      if (zg) zg.onclick = () => { const t = pane.querySelector('#zhText'), open = t.hidden; t.hidden = !open; zg.setAttribute('aria-expanded', String(open)); };
      const mk = pane.querySelector('#mkVar');
      if (mk) mk.onclick = async () => {
        if (!S.user) return needLogin('登录后可以让 AI 把这篇改写成适合你的难度（每天的 AI 次数有上限）。');
        mk.disabled = true; mk.innerHTML = '<span class="spin"></span> 正在改写…';
        try { const r = await api('/api/next/variant', { pack: id, level: m.user_level, request_id: rid('nv') }); m.variant = { level: r.level, body: r.body, notes: r.notes }; m.original = m.sentences; m.sentences = splitSentences(r.body); m.can_variant = false; read(); toast(r.cached ? '已打开改写版' : '改写好了'); }
        catch (e) { toast(e.message); mk.disabled = false; mk.textContent = `改写成 ${m.user_level} 难度`; }
      };
      reader.onclick = e => {
        const ex = e.target.closest('[data-ex]'); if (ex) return explainSheet(ls[Number(ex.dataset.ex)], id);
        const w = e.target.closest('.w'); if (w && !String(getSelection()).trim()) lookupSheet(w.dataset.w, ls[Number(w.dataset.s)], id, w.classList.contains('mine'));
      };
      // Read-along (LONG, 01-audio-offline.js): sentence by sentence; the current sentence stays bright, the rest dims, the
      // current word lights up when a recording (or the browser voice) says which. A text without a recording (an imported
      // article, a 热点 before its recording) is read by the server voice (owner, 2026-11-25): each sentence made once and
      // kept (an import's for its owner only), the next two asked for while one plays, a line while one is being made; the
      // browser voice only for a sentence the server cannot give, with the reason. 暂停 / 继续, and where it was left is
      // kept on this phone (「从第 N 句继续」) until the end is reached.
      const ra = pane.querySelector('#readAlong'), restart = pane.querySelector('#alongRestart'), prep = pane.querySelector('#svPrep');
      const RKEY = 'read:' + id, sentEl = i => reader.querySelector(`.sent[data-si="${i}"]`);
      let alongShown = -1;
      const setRa = () => {
        const r = LONG.of(RKEY), at = r ? r.i : PROG.at(RKEY, ls.length);
        ra.innerHTML = r && r.state !== 'paused' ? `${pauseIcon(14)}<span>暂停</span>` : `${playIcon(false, 14)}<span>${r ? '继续' : at ? `从第 ${at + 1} 句继续` : '伴读'}</span>`;
        restart.hidden = !at; reader.classList.toggle('reading', !!r);
      };
      const stopAlong = () => LONG.stop();
      const readAlong = from => LONG.start({
        key: RKEY, texts: ls, nm: nmNow, pack: id, title: m.title, label: i => `伴读 · 第 ${i + 1} / ${ls.length} 句`,
        onState: (state, i, note) => {
          setRa(); prep.textContent = note || ''; prep.hidden = !note;
          if (state === 'idle') { alongShown = -1; reader.querySelectorAll('.now,.cur').forEach(x => x.classList.remove('now', 'cur')); return; }
          const s = sentEl(i);
          if (i !== alongShown && s) { alongShown = i; reader.querySelectorAll('.sent.now').forEach(x => x.classList.remove('now')); s.classList.add('now'); if (state !== 'paused') s.scrollIntoView({ block: 'center', behavior: REDUCED ? 'auto' : 'smooth' }); }
        },
        onWord: (i, c) => { const s = sentEl(i); if (!s) return; if (c == null) s.querySelectorAll('.cur').forEach(x => x.classList.remove('cur')); else lightWord(s, c); },
        onDone: () => markStep('read'),
      }, from);
      ra.onclick = async () => {
        if (LONG.of(RKEY)) { LONG.toggle(); return; }
        if (!nmNow) { ra.disabled = true; nmNow = await narration(ls); ra.disabled = false; }  // fetched when the page opened, as a rule
        readAlong(PROG.at(RKEY, ls.length));
      };
      restart.onclick = async () => { LONG.stop(); PROG.clear(RKEY); if (!nmNow) nmNow = await narration(ls); readAlong(0); };
      setRa();
      // An expression is read by the server voice (the browser voice where it is off); with neither (WeChat on Android,
      // the server voice off), its sentence from the narration.
      pane.querySelectorAll('[data-sayx]').forEach(b => b.onclick = () => {
        const x = m.expressions[Number(b.dataset.sayx)], k = ls.findIndex(s => s.toLowerCase().includes(x.text.toLowerCase()));
        if (!TTS.can() && nmNow && k >= 0) NAR.play(nmNow.sentences[k].s, nmNow.sentences[k].e, null, null); else TTS.say(x.text, null, null, { pack: id });
      });
      pane.querySelectorAll('[data-sx]').forEach(b => b.onclick = () => { const x = m.expressions[Number(b.dataset.sx)]; saveCard({ text: x.text, meaning: x.meaning + (x.note ? '｜' + x.note : ''), context: findContext(x.text, ls), pack: id }, b); });
      pane.querySelectorAll('[data-sv]').forEach(b => b.onclick = () => { const v = m.vocabulary[Number(b.dataset.sv)]; saveCard({ text: v.term, meaning: v.meaning, context: findContext(v.term, ls) || v.example, pack: id }, b); });
      pane.querySelectorAll('[data-sn]').forEach(b => b.onclick = () => { const v = m.variant.notes[Number(b.dataset.sn)]; saveCard({ text: v.text, meaning: v.meaning, context: findContext(v.text, ls), pack: id }, b); });
      pane.querySelector('#toCheck').onclick = () => { stopAlong(); markStep('read'); go('check'); };
      // Reading to the end of the text counts as having read it (after a short while on the page, not a quick scroll).
      const t0r = Date.now();
      if ('IntersectionObserver' in window) {
        const io = new IntersectionObserver(es => { if (es.some(x => x.isIntersecting) && Date.now() - t0r > 20000) { markStep('read'); io.disconnect(); } });
        io.observe(pane.querySelector('#toCheck'));
      }
      // Keyboard reading: ← → walk the words, ↵ looks one up, E explains its sentence.
      const words = () => [...reader.querySelectorAll('.w')];
      let kw = -1;
      const kmove = k => { const ws = words(); if (!ws.length) return; reader.querySelectorAll('.kfocus').forEach(x => x.classList.remove('kfocus')); kw = Math.max(0, Math.min(ws.length - 1, k)); ws[kw].classList.add('kfocus'); ws[kw].scrollIntoView({ block: 'nearest' }); };
      reader.addEventListener('keydown', e => {
        if (e.metaKey || e.ctrlKey || e.altKey) return;
        const ws = words();
        if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') { e.preventDefault(); kmove(kw < 0 ? 0 : kw + (e.key === 'ArrowRight' ? 1 : -1)); }
        else if (e.key === 'Enter' && kw >= 0) { e.preventDefault(); const w = ws[kw]; lookupSheet(w.dataset.w, ls[Number(w.dataset.s)], id, w.classList.contains('mine')); }
        else if ((e.key === 'e' || e.key === 'E') && kw >= 0) { e.preventDefault(); explainSheet(ls[Number(ws[kw].dataset.s)], id); }
      });
      reader.addEventListener('blur', () => reader.querySelectorAll('.kfocus').forEach(x => x.classList.remove('kfocus')));
      bindGains(); bindNewWords();
      m._onLook = () => {
        const slot = pane.querySelector('#nwSlot'); if (!slot) return;
        slot.innerHTML = newWordsHTML(); bindNewWords();
        const sum = pane.querySelector('#gainsSum'); if (sum) sum.textContent = gainsSummary();
        const n = (gainsTabs().find(x => x[0] === 'words') || [])[2], t = pane.querySelector('[data-gt="words"]'); if (t) t.textContent = '词汇 ' + n;
      };
      const onSel = () => {
        const sel = getSelection(); const t = String(sel).replace(/\s+/g, ' ').trim();
        if (!t || t.length > 160 || !/[A-Za-z]/.test(t) || !reader.contains(sel.anchorNode)) { hideSelbar(); return; }
        const sentEl = sel.anchorNode.parentElement && sel.anchorNode.parentElement.closest('.sent');
        const ctx = sentEl ? ls[Number(sentEl.dataset.si)] : '';
        if (!selbar) { selbar = document.createElement('div'); selbar.className = 'selbar'; document.body.appendChild(selbar); }
        selbar.innerHTML = `<span>${esc(t)}</span><button type="button">收藏</button>`;
        selbar.querySelector('button').onclick = () => { const from = selbar; saveCard({ text: t, context: ctx, pack: id }, null, from); sel.removeAllRanges(); setTimeout(hideSelbar, 50); };
      };
      document.onselectionchange = () => { clearTimeout(onSel.t); onSel.t = setTimeout(onSel, 250); };
    }


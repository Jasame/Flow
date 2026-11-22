    /* after reading: the words looked up here (and the pre-reading list) can go into review in one tap */
    function newWordsHTML() {
      const looked = [...((m._looked && m._looked.values()) || [])];
      const mine = new Set((m.mine || []).map(x => x.form));
      const items = looked.filter(x => !mine.has(x.word)).map(x => ({ ...x, on: true }));
      (m.preread || []).forEach(w => { if (!items.some(x => x.word === w.word) && !mine.has(w.form)) items.push({ word: w.word, meaning: w.meaning, sentence: findContext(w.form, lines()), on: false }); });
      if (!items.length) return '';
      return `<div class="card flat stack-s" id="newWords"><div class="row between"><b>这篇的生词</b><span class="muted tiny">勾选的会按遗忘曲线复习</span></div>
        <div class="nw-list">${items.slice(0, 14).map((x, k) => `<label class="nw"><input type="checkbox" data-nw="${k}" ${x.on ? 'checked' : ''}><b>${esc(x.word)}</b><span class="muted tiny">${esc(x.meaning || '')}</span></label>`).join('')}</div>
        <div><button class="btn small primary" id="nwAdd">加入复习</button></div></div>`;
    }
    function bindNewWords() {
      const box = pane.querySelector('#newWords'); if (!box) return;
      const looked = [...((m._looked && m._looked.values()) || [])];
      const items = looked.map(x => ({ ...x })); (m.preread || []).forEach(w => { if (!items.some(x => x.word === w.word)) items.push({ word: w.word, sentence: findContext(w.form, lines()) }); });
      box.querySelector('#nwAdd').onclick = async e => {
        if (!S.user) return needLogin('登录后可以把这些词加入复习。');
        const pick = [...box.querySelectorAll('[data-nw]:checked')].map(c => items[Number(c.dataset.nw)]).filter(Boolean);
        if (!pick.length) { toast('先勾选要复习的词'); return; }
        const btn = e.currentTarget; btn.disabled = true;
        try { const r = await api('/api/next/vocab/add', { pack: id, items: pick.map(x => ({ word: x.word, sentence: x.sentence || '' })) }); toast(r.added ? `已加入 ${r.added} 个词` : '这些词已经在复习里了'); refreshHome().catch(() => {}); box.remove(); }
        catch (x) { toast(x.message); btn.disabled = false; }
      };
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
      const variantBar = m.variant ? `<div class="seg" role="tablist"><button data-ver="v" aria-selected="${!st.showOriginal}">适合我的版本（${m.variant.level}）</button><button data-ver="o" aria-selected="${st.showOriginal}">原文（${m.original_level}）</button><span></span></div>`
        : m.can_variant ? `<div class="card sunk row between"><span class="small">这篇原文是 ${m.original_level}，你选的是 ${m.user_level}。</span><button class="btn small" id="mkVar">改写成 ${m.user_level} 难度</button></div>` : '';
      pane.innerHTML = `${m.summary_zh ? `<details class="guide"><summary>中文导读</summary><p>${esc(m.summary_zh)}</p></details>` : ''}${variantBar}
        <div class="row between"><div class="legend"><span>本篇词汇</span><span class="h">可能超出你的水平</span>${(m.mine || []).length ? '<span class="m">你在背的词</span>' : ''}</div>
          <button class="btn small" id="readAlong" title="边听录音边看文字，读到哪句亮哪句">${playIcon(false, 14)}<span>伴读</span></button></div>
        <p class="muted tiny">点单词查词；点句尾的 ✦ 让 AI 讲解整句；${TOUCH ? '长按拖选' : '选中'}一段文字可以收藏。${TOUCH ? '' : '键盘：Tab 进入正文后用 ← → 逐词移动，↵ 查词，E 讲解这句。'}</p>
        <div class="text" id="reader" tabindex="0" aria-label="正文：左右方向键逐词移动，回车查词">${ls.map((s, i) => sentenceHTML(s, i)).join('')}</div>
        ${m.expressions.length ? `<div class="section"><div class="section-head"><h2 class="h2">地道表达</h2><span class="muted tiny">能直接搬进你自己话里的搭配</span></div><div class="stack-s">${m.expressions.map((x, i) => `<div class="expr"><span class="e">${esc(x.text)}</span><span class="row"><button class="icon-btn" data-sayx="${i}" aria-label="朗读">${ICON.speak}</button><button class="icon-btn" data-sx="${i}" aria-label="收藏 ${esc(x.text)}">${ICON.star}</button></span><span class="m">${esc(x.meaning)}</span><span class="n">${esc(x.note || '')}</span></div>`).join('')}</div></div>` : ''}
        ${m.vocabulary.length ? `<div class="section"><h2 class="h2">本篇词汇</h2><div class="vocab-list section">${m.vocabulary.map((v, i) => `<div class="vrow"><span class="term">${esc(v.term)}</span><button class="icon-btn" data-sv="${i}" aria-label="收藏 ${esc(v.term)}">${ICON.star}</button><span class="muted small">${esc(v.meaning)}</span><span class="vex">${esc(v.example || '')}</span></div>`).join('')}</div></div>` : ''}
        ${(m.variant && m.variant.notes.length) ? `<div class="section"><h2 class="h2">改写版新出现的表达</h2><div class="vocab-list section">${m.variant.notes.map((v, i) => `<div class="vrow"><span class="term">${esc(v.text)}</span><button class="icon-btn" data-sn="${i}" aria-label="收藏">${ICON.star}</button><span class="muted small">${esc(v.meaning)}</span></div>`).join('')}</div></div>` : ''}
        ${m.notes.length ? `<div class="section stack-s"><div class="section-head"><h2 class="h2">这篇练到的知识点</h2><a class="link small" href="#/graph">知识图谱 →</a></div>${m.notes.map(n => `<div class="knote"><div class="row between">${nodeChip({ id: n.node, title: n.title, status: n.status })}<span class="tiny muted">${esc(n.label)}</span></div><q>${esc(n.quote)}</q><div class="small muted">${esc(n.explanation)}</div></div>`).join('')}</div>` : ''}
        <div class="section" id="nwSlot">${newWordsHTML()}</div>
        <div class="section row between"><span></span><button class="btn" id="toCheck">读完了，做理解题 →</button></div>`;
      const reader = pane.querySelector('#reader');
      pane.querySelectorAll('[data-ver]').forEach(b => b.onclick = () => { st.showOriginal = b.dataset.ver === 'o'; m._showOriginal = st.showOriginal; read(); });
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
      // Read-along: sentence by sentence; the current sentence stays bright, the rest dims, the current word lights up.
      let along = false, alongShown = -1;
      const ra = pane.querySelector('#readAlong');
      const stopAlong = () => { along = false; TTS.stop(); NAR.stop(); MINI.hide(); reader.classList.remove('reading'); reader.querySelectorAll('.now,.cur').forEach(x => x.classList.remove('now', 'cur')); ra.innerHTML = playIcon(false, 14) + '<span>伴读</span>'; };
      const alongAudio = nm => {
        alongShown = -1;
        NAR.play(nm.sentences[0].s, null, t => {
          const [si, wc] = NAR.locate(t);
          const s = reader.querySelector(`.sent[data-si="${si}"]`);
          if (si !== alongShown && s) { alongShown = si; MINI.update(`伴读 · 第 ${si + 1} / ${ls.length} 句`); reader.querySelectorAll('.sent.now').forEach(x => x.classList.remove('now')); s.classList.add('now'); s.scrollIntoView({ block: 'center', behavior: REDUCED ? 'auto' : 'smooth' }); }
          if (s) lightAt(s, wc);
        }, () => { stopAlong(); markStep('read'); });
      };
      const alongFrom = i => {
        if (!along) return;
        if (i >= ls.length) { stopAlong(); markStep('read'); return; }
        reader.querySelectorAll('.sent.now').forEach(x => x.classList.remove('now'));
        const s = reader.querySelector(`.sent[data-si="${i}"]`); s.classList.add('now'); s.scrollIntoView({ block: 'center', behavior: REDUCED ? 'auto' : 'smooth' });
        TTS.say(ls[i], () => alongFrom(i + 1), c => lightWord(s, c));
      };
      ra.onclick = async () => {
        if (along) return stopAlong();
        along = true; reader.classList.add('reading'); ra.innerHTML = playIcon(true, 14) + '<span>停止</span>'; MINI.show('伴读中', stopAlong);
        const nm = await narration(ls);
        if (along) { if (nm) alongAudio(nm); else alongFrom(0); }
      };
      pane.querySelectorAll('[data-sayx]').forEach(b => b.onclick = () => TTS.say(m.expressions[Number(b.dataset.sayx)].text));
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
      bindNewWords();
      m._onLook = () => { const slot = pane.querySelector('#nwSlot'); if (!slot) return; slot.innerHTML = newWordsHTML(); bindNewWords(); };
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


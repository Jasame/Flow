    /* output: write, get the AI rewrite comparison, tied back to the knowledge graph */
    /* output modes: 仿写 (above) · 复述 · 情景对话 · 翻译 · 写作 — all built on this material */
    const OUT_MODES = { model: '仿写', retell: '复述', dialog: '对话', translate: '翻译', essay: '写作' };
    function outTabs(cur) {
      return `<div class="seg outmodes" role="tablist" aria-label="输出练习">${Object.entries(OUT_MODES).map(([k, l]) => `<a role="tab" href="#/m/${encodeURIComponent(id)}/output${k === 'model' ? '' : '/' + k}" aria-selected="${cur === k}">${l}</a>`).join('')}</div>`;
    }
    const needAI = reason => { if (!S.user) { needLogin(reason); return true; } return false; };

    function retellMode() {
      pane.innerHTML = `${outTabs('retell')}<div class="card flat task stack-s"><div class="kicker">复述</div><b>不看原文，用自己的话把这篇讲一遍</b>
          <span class="muted small">可以打字，也可以点 ● 直接说（最长 2 分钟）。AI 会提炼原文要点，看你讲到了哪些，并改出最影响理解的错误。</span></div>
        <textarea id="rtText" rows="6" maxlength="2500" lang="en" data-submit="#rtGo" placeholder="In this article, ..."></textarea>
        <div class="row between"><span class="row">${recBtn('rtMic', '说出来')}<span class="muted tiny" id="rtState">打字或录音都行</span></span><button class="btn primary" id="rtGo">AI 看看我的复述</button></div>
        <div id="rtOut"></div>`;
      let blob = null;
      const mic = pane.querySelector('#rtMic'), state = pane.querySelector('#rtState');
      mic.onclick = () => MIC.toggle(mic, 120, b => { blob = b; state.textContent = '已录好一段，可以提交了（会先转写）'; });
      pane.querySelector('#rtGo').onclick = async e => {
        if (needAI('登录后 AI 会看你的复述讲到了哪些要点。')) return;
        const text = pane.querySelector('#rtText').value.trim();
        if (!blob && (text.match(/[A-Za-z]+/g) || []).length < 8) { toast('先说一段或写几句英文'); return; }
        const btn = e.currentTarget; btn.disabled = true; btn.innerHTML = '<span class="spin"></span> 正在看…';
        try {
          const body = { pack: id, request_id: rid('rt') };
          if (blob) body.audio = await MIC.payload(blob); else body.text = text;
          const x = (await api('/api/next/retell', body)).result;
          pane.querySelector('#rtOut').innerHTML = `<div class="result enter stack">
            ${blob ? `<div class="card sunk small"><span class="muted">AI 听到：</span>${esc(x.transcript)}</div>` : ''}
            <div class="card verdict"><span class="dot"></span><div>${esc(x.comment)}<div class="tiny muted">讲到 ${x.points.filter(p => p.covered).length} / ${x.points.length} 个要点</div></div></div>
            <div class="card flat stack-s"><b>原文要点</b>${x.points.map(p => `<div class="small"><span class="${p.covered ? 'ok-mark' : 'bad-mark'}">${p.covered ? '✓' : '✗'}</span> ${esc(p.point)}</div>`).join('')}</div>
            ${x.used.length ? `<div class="small">用上了原文的表达：${x.used.map(u => `<span class="pill green">${esc(u)}</span>`).join(' ')}</div>` : ''}
            ${fixesHTML(x.fixes)}
            ${x.model ? `<div class="card flat stack-s"><div class="row between"><b>示范复述</b><button class="icon-btn" id="rtSay" aria-label="朗读">${ICON.speak}</button></div><div class="text small">${esc(x.model)}</div></div>` : ''}</div>`;
          const say = pane.querySelector('#rtSay'); if (say) say.onclick = () => TTS.say(x.model);
          bringIntoView(pane.querySelector('#rtOut'));
          markStep('output'); blob = null; state.textContent = '打字或录音都行';
        } catch (x) { toast(x.message); }
        btn.disabled = false; btn.textContent = 'AI 看看我的复述';
      };
    }

    function dialogMode() {
      const hist = [];
      pane.innerHTML = `${outTabs('dialog')}<div class="card flat task stack-s"><div class="kicker">情景对话</div><b>${esc(m.speaking_task || '围绕这篇的话题和 AI 聊几句')}</b>
          <span class="muted small">AI 扮演情景里的另一方。可以打字或说，每说一句它会顺手纠正；聊 4–6 轮后点「结束并总结」。</span></div>
        <div class="chat" id="chat"></div>
        <div id="dlgIn" class="stack-s" hidden><div class="tiny muted" id="dlgHint"></div>
          <div class="chat-in"><textarea id="dlgText" rows="2" maxlength="480" lang="en" enterkeyhint="send" placeholder="用英文回答…"></textarea>${recBtn('dlgMic', '说出来')}<button class="btn primary" id="dlgSend">发送</button></div>
          <div><button class="btn small ghost" id="dlgEnd">结束并总结</button></div></div>
        <div><button class="btn primary" id="dlgStart">开始对话</button></div><div id="dlgOut"></div>`;
      const chat = pane.querySelector('#chat');
      const bubble = (role, text, extra) => { chat.insertAdjacentHTML('beforeend', `<div class="msg ${role}"><div class="b">${esc(text)}</div>${extra || ''}</div>`); chat.lastElementChild.scrollIntoView({ block: 'nearest', behavior: REDUCED ? 'auto' : 'smooth' }); };
      const busy = on => { ['#dlgSend', '#dlgEnd', '#dlgMic'].forEach(s => { const b = pane.querySelector(s); if (b) b.disabled = on; }); };
      // After each reply: the newest message and the answer box are on screen together, above the keyboard and the tabs.
      const showInput = () => { const box = pane.querySelector('#dlgIn'); if (box && !box.hidden) box.scrollIntoView({ block: 'end', behavior: REDUCED ? 'auto' : 'smooth' }); };
      async function turn(body) {
        busy(true);
        try { return (await api('/api/next/dialog', { pack: id, history: hist, request_id: rid('dg'), ...body })).result; }
        catch (e) { toast(e.message); return null; } finally { busy(false); }
      }
      pane.querySelector('#dlgStart').onclick = async e => {
        if (needAI('登录后可以和 AI 做情景对话。')) return;
        const btn = e.currentTarget; btn.disabled = true; btn.innerHTML = '<span class="spin"></span>';
        const x = await turn({}); if (!x) { btn.disabled = false; btn.textContent = '开始对话'; return; }
        btn.parentNode.remove();
        chat.insertAdjacentHTML('beforeend', `<div class="scene small">${esc(x.scene)}${x.role ? `（AI 扮演：${esc(x.role)}）` : ''}</div>`);
        bubble('ai', x.reply); TTS.say(x.reply); hist.push({ role: 'ai', text: x.reply });
        pane.querySelector('#dlgIn').hidden = false; showInput(); if (!TOUCH) pane.querySelector('#dlgText').focus({ preventScroll: true });
      };
      async function send(text, blob) {
        const body = blob ? { audio: await MIC.payload(blob) } : { text };
        const x = await turn(body); if (!x) return;
        const me = x.heard || text;
        bubble('me', me, x.correction ? `<div class="fix tiny"><del>${esc(x.correction.original)}</del> → <b>${esc(x.correction.better)}</b> <span class="muted">${esc(x.correction.why)}</span></div>` : '');
        hist.push({ role: 'me', text: me });
        bubble('ai', x.reply); TTS.say(x.reply); hist.push({ role: 'ai', text: x.reply });
        pane.querySelector('#dlgHint').textContent = x.hint ? '提示：' + x.hint : '';
        showInput();
        if (hist.length >= 14) toast('聊得差不多了，可以结束并看总结');
      }
      pane.querySelector('#dlgSend').onclick = () => { const t = pane.querySelector('#dlgText'); const v = t.value.trim(); if (!v) return; t.value = ''; send(v); };
      pane.querySelector('#dlgText').addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); pane.querySelector('#dlgSend').click(); } });
      const mic = pane.querySelector('#dlgMic'); mic.onclick = () => MIC.toggle(mic, 30, b => send('', b));
      pane.querySelector('#dlgEnd').onclick = async e => {
        if (hist.filter(h => h.role === 'me').length < 1) { toast('先说一两句再总结'); return; }
        const btn = e.currentTarget; btn.innerHTML = '<span class="spin"></span>';
        const x = await turn({ end: true }); if (!x) { btn.textContent = '结束并总结'; return; }
        pane.querySelector('#dlgIn').hidden = true; TTS.stop(); markStep('output');
        pane.querySelector('#dlgOut').innerHTML = `<div class="result enter stack"><div class="card verdict"><span class="dot"></span><div>${esc(x.summary)}</div></div>
          ${x.good.length ? `<div class="card flat stack-s"><b>说得好的句子</b>${x.good.map(g => `<div class="small text">${esc(g)}</div>`).join('')}</div>` : ''}
          ${fixesHTML(x.fixes)}
          ${x.expressions.length ? `<div class="card flat stack-s"><b>可以学的表达</b>${x.expressions.map((ex, k) => `<div class="row between small"><span><b>${esc(ex.text)}</b> <span class="muted">${esc(ex.meaning)}</span></span><button class="btn small" data-kx="${k}">收藏</button></div>`).join('')}</div>` : ''}
          <div class="row"><button class="btn primary" id="dlgAgain">再练一轮</button><a class="btn" href="#/m/${encodeURIComponent(id)}/output/translate">换个练法：翻译</a></div></div>`;
        pane.querySelectorAll('[data-kx]').forEach(b => b.onclick = () => { const ex = x.expressions[Number(b.dataset.kx)]; saveCard({ text: ex.text, meaning: ex.meaning, context: '', pack: id }, b); });
        pane.querySelector('#dlgAgain').onclick = () => { scrollTo({ top: 0 }); dialogMode(); };
        bringIntoView(pane.querySelector('#dlgOut'));
      };
    }

    function translateMode() {
      const ls = lines().map(s => s.replace(/^[A-Z][a-z]+(?: [A-Z][a-z]+)?:\s+/, ''));
      const good = ls.map((s, i) => [s, i]).filter(([s]) => (s.match(/[A-Za-z]+/g) || []).length >= 8);
      let k = Math.max(0, good.findIndex(([, i]) => i === m.dictation_index)), dir = load('flow-next-trans-dir') || 'zh2en';
      async function render() {
        const [en, i] = good[k] || [ls[0], 0];
        pane.innerHTML = `${outTabs('translate')}<div class="seg two" role="tablist"><button data-dir="zh2en" aria-selected="${dir === 'zh2en'}">汉译英</button><button data-dir="en2zh" aria-selected="${dir === 'en2zh'}">英译汉</button></div>
          <div class="card flat stack-s"><div class="row between"><span class="kicker">第 ${k + 1} / ${good.length} 句</span><button class="link small" id="trNext">换一句</button></div>
            <div class="text" id="trSrc">${dir === 'en2zh' ? esc(en) : '<span class="spin"></span>'}</div></div>
          <textarea id="trIn" rows="3" maxlength="800" lang="${dir === 'zh2en' ? 'en' : 'zh'}" data-submit="#trGo" placeholder="${dir === 'zh2en' ? '译成英文…' : '译成中文…'}"></textarea>
          <div class="row between"><span class="muted tiny">${dir === 'zh2en' ? '译完对照原文，看哪里不一样。' : '意思准确、读起来像中文就是好译文。'}</span><button class="btn primary" id="trGo">提交</button></div><div id="trOut"></div>`;
        pane.querySelectorAll('[data-dir]').forEach(b => b.onclick = () => { dir = b.dataset.dir; save('flow-next-trans-dir', dir); render(); });
        pane.querySelector('#trNext').onclick = () => { k = (k + 1) % good.length; render(); };
        if (dir === 'zh2en') {
          if (!S.user) { pane.querySelector('#trSrc').innerHTML = '<span class="muted small">登录后可以做汉译英（中文原句由 AI 翻出，全站共享）。</span>'; }
          else try { pane.querySelector('#trSrc').textContent = (await api('/api/next/translate/source', { pack: id, i, request_id: rid('ts') })).zh; }
          catch (e) { pane.querySelector('#trSrc').textContent = e.message; }
        }
        pane.querySelector('#trGo').onclick = async e => {
          if (needAI('登录后 AI 会批改你的译文。')) return;
          const text = pane.querySelector('#trIn').value.trim(); if (text.length < 2) { toast('先写下你的译文'); return; }
          const btn = e.currentTarget; btn.disabled = true; btn.innerHTML = '<span class="spin"></span>';
          try {
            const x = (await api('/api/next/translate', { pack: id, i, direction: dir, text, request_id: rid('tr') })).result;
            pane.querySelector('#trOut').innerHTML = `<div class="result enter stack"><div class="card verdict"><span class="dot"></span><div>得分 ${Math.round(x.score * 100)}<div class="small">${esc(x.accuracy)}</div><div class="small muted">${esc(x.fluency)}</div></div></div>
              ${fixesHTML(x.fixes)}<div class="card flat stack-s"><b>${dir === 'zh2en' ? '原文' : '参考译文'}</b><div class="text small">${esc(dir === 'zh2en' ? x.original : x.reference)}</div>
              ${dir === 'zh2en' && x.reference && x.reference !== x.original ? `<div class="tiny muted">另一种自然说法：${esc(x.reference)}</div>` : ''}</div></div>`;
            markStep('output'); bringIntoView(pane.querySelector('#trOut'));
          } catch (x) { toast(x.message); }
          btn.disabled = false; btn.textContent = '提交';
        };
      }
      render();
    }

    function essayMode() {
      const key = 'flow-next-essay-' + id, lv = m.user_level || level();
      // The task's own word count wins ("写 200–250 词"); otherwise a range that fits the level.
      const asked = /(\d{2,3})\s*[–~\-—至到]\s*(\d{2,3})\s*(?:个)?(?:英文)?词/.exec(m.writing_task || '');
      const range = asked ? [Number(asked[1]), Number(asked[2])] : { A2: [60, 120], B1: [80, 160], B2: [120, 250], C1: [180, 350] }[lv] || [80, 200];
      pane.innerHTML = `${outTabs('essay')}<div class="card flat task stack-s"><div class="kicker">写作 · 建议 ${range[0]}–${range[1]} 词</div><b>${esc(m.writing_task || '围绕这篇的话题，写一段你自己的看法或经历。')}</b>
          <span class="muted small">按内容、结构、准确、丰富四个维度批改，给段落点评和示范段落；改出来的错误进错题本。</span></div>
        <textarea id="esIn" rows="10" maxlength="3000" lang="en" data-submit="#esGo" placeholder="Write here…">${esc(load(key) || '')}</textarea>
        <div class="row between"><span class="counter" id="esN"></span><button class="btn primary" id="esGo">AI 批改</button></div><div id="esOut"></div>`;
      const ta = pane.querySelector('#esIn'), n = pane.querySelector('#esN');
      const count = () => { const w = (ta.value.match(/[A-Za-z]+(?:'[A-Za-z]+)?/g) || []).length; n.textContent = `${w} 词`; n.classList.toggle('warn', w && (w < range[0] || w > range[1])); return w; };
      ta.oninput = () => { save(key, ta.value); count(); }; count();
      pane.querySelector('#esGo').onclick = async e => {
        if (needAI('登录后 AI 会按评分维度批改你的短文。')) return;
        if (count() < 40) { toast('至少写 40 个词'); return; }
        const btn = e.currentTarget; btn.disabled = true; btn.innerHTML = '<span class="spin"></span> 正在批改…';
        try {
          const x = (await api('/api/next/essay', { pack: id, text: ta.value, request_id: rid('es') })).result;
          const dims = { content: '内容切题', organization: '结构衔接', accuracy: '语言准确', range: '词汇句式' };
          pane.querySelector('#esOut').innerHTML = `<div class="result enter stack"><div class="card verdict"><span class="dot"></span><div>${esc(x.comment)}${x.level ? `<div class="tiny muted">这篇体现的水平约 ${esc(x.level)}</div>` : ''}</div></div>
            <div class="card flat ab-list">${Object.entries(dims).map(([k, l]) => `<div class="ab"><span class="nm">${l}</span><span class="vbar"><i data-w="${x.scores[k] * 20}"></i></span><span class="lv">${x.scores[k]} / 5</span></div>`).join('')}</div>
            ${x.paragraphs.length ? `<div class="card flat stack-s"><b>段落点评</b>${x.paragraphs.map(pg => `<div class="small"><b>第 ${pg.para} 段</b>：${esc(pg.note)}</div>`).join('')}</div>` : ''}
            ${fixesHTML(x.fixes)}
            ${x.better.length ? `<div class="card flat stack-s"><b>可以写得更好</b>${x.better.map(b => `<div class="small"><del>${esc(b.from)}</del><br><ins>${esc(b.to)}</ins><div class="tiny muted">${esc(b.why)}</div></div>`).join('')}</div>` : ''}
            ${x.model ? `<div class="card flat stack-s"><b>示范段落</b><div class="text small">${esc(x.model)}</div></div>` : ''}</div>`;
          requestAnimationFrame(() => requestAnimationFrame(() => pane.querySelectorAll('#esOut .vbar i').forEach(i => { i.style.width = i.dataset.w + '%'; })));
          const wn = count();
          if (wn < range[0] || wn > range[1]) pane.querySelector('#esOut .result').insertAdjacentHTML('afterbegin', `<div class="card sunk small">这篇 ${wn} 词，任务建议 ${range[0]}–${range[1]} 词：${wn < range[0] ? '内容展开得还不够，考试里会影响「内容」分。' : '超出了建议长度，考试里要注意时间和篇幅。'}</div>`);
          markStep('output'); bringIntoView(pane.querySelector('#esOut'));
        } catch (x) { toast(x.message); }
        btn.disabled = false; btn.textContent = '再批改一次';
      };
    }

    function output() {
      const om = parts()[3];
      if (om === 'retell') return retellMode();
      if (om === 'dialog') return dialogMode();
      if (om === 'translate') return translateMode();
      if (om === 'essay') return essayMode();
      const key = 'flow-next-draft-' + id;
      const draft = load(key) || '';
      pane.innerHTML = `${outTabs('model')}<div class="stack"><div class="card flat task"><div class="kicker">用出来</div><b>${esc(m.task.prompt)}</b>
          ${m.task.model ? `<div class="model">${esc(m.task.model)} <button class="icon-btn" id="sayModel" aria-label="朗读参考句">${ICON.speak}</button></div>` : ''}
          ${m.task.hint ? `<div class="muted small">${esc(m.task.hint)}</div>` : ''}
          ${(m.mine || []).length ? `<div class="muted small">可以试着用上你在背的词：${[...new Set(m.mine.map(x => x.form))].slice(0, 5).map(w => `<b>${esc(w)}</b>`).join('、')}（用对了算一次成功复习）</div>` : ''}</div>
        <label class="field">你的英文<textarea id="ans" maxlength="600" lang="en" data-submit="#go" placeholder="写一两句就好，写错没关系。">${esc(draft)}</textarea></label>
        <div class="row between"><span class="counter" id="cnt">${draft.length} / 600</span><button class="btn primary" id="go">让 AI 帮我改</button></div>
        <p class="err" id="outErr" role="alert"></p><div id="result"></div></div>`;
      const ta = pane.querySelector('#ans');
      ta.oninput = () => { save(key, ta.value); pane.querySelector('#cnt').textContent = ta.value.length + ' / 600'; };
      const sm = pane.querySelector('#sayModel'); if (sm) sm.onclick = () => TTS.say(m.task.model);
      pane.querySelector('#go').onclick = async () => {
        const text = ta.value.trim(), err = pane.querySelector('#outErr'); err.textContent = '';
        if (!/[A-Za-z]{2,}.*\s+.*[A-Za-z]/.test(text)) { err.textContent = '先用英文写一个短句。'; return; }
        if (!S.user) return needLogin('登录后 AI 会帮你改写，并给出三种更好的说法。');
        const btn = pane.querySelector('#go'); btn.disabled = true; btn.innerHTML = '<span class="spin"></span> 正在看你写的…';
        try { const r = await api('/api/next/rewrite', { pack: id, text, request_id: rid('nr') }); markStep('output'); renderResult(r.result, text, r.remaining); }
        catch (e) { err.textContent = e.message; }
        btn.disabled = false; btn.textContent = '再改一次';
      };
    }
    function renderResult(r, yours, remaining) {
      const box = pane.querySelector('#result');
      const same = r.corrected.trim() === yours.trim();
      box.innerHTML = `<div class="result enter">
        <div class="card verdict ${esc(r.verdict)}"><span class="dot"></span><div>${esc(r.summary)}</div></div>
        <div class="card compare"><div class="kicker">${same ? '你写的已经是对的' : '改对之后'}</div>
          ${same ? '' : `<div class="yours">${esc(yours)}</div>`}<div class="fixed">${esc(r.corrected)} <button class="icon-btn" data-say-text="${esc(r.corrected)}" aria-label="朗读">${ICON.speak}</button></div>
          ${r.changes.length ? `<div>${r.changes.map(c => `<div class="change"><span class="ft"><del>${esc(c.from)}</del> → <ins>${esc(c.to)}</ins></span><span class="why">${esc(c.why)}</span>${c.node ? `<span>${nodeChip({ id: c.node, title: c.node_title || c.node, status: 'watch' })}</span>` : ''}</div>`).join('')}</div>` : ''}
          ${r.used_well && r.used_well.length ? `<div class="used-well small"><span class="muted">用对了：</span>${r.used_well.map(n => nodeChip({ id: n.id, title: n.title, status: 'used' })).join('')}</div>` : ''}</div>
        <div class="stack-s"><h2 class="h2">还可以这样说</h2>${r.versions.map((v, i) => `<div class="version"><div class="row between"><span class="pill green">${esc(v.label)}</span><span class="row"><button class="icon-btn" data-say-text="${esc(v.text)}" aria-label="朗读">${ICON.speak}</button><button class="icon-btn" data-keep-v="${i}" aria-label="收藏这句">${ICON.star}</button></span></div><div class="v">${esc(v.text)}</div><div class="small muted">${esc(v.why)}</div></div>`).join('')}</div>
        ${r.word_use && r.word_use.length ? `<div class="card sunk stack-s"><div class="kicker">你用到了正在背的词</div>${r.word_use.map(u => `<div class="small"><span class="${u.ok ? 'ok-mark' : 'bad-mark'}">${u.ok ? '✓' : '✗'}</span> <b>${esc(u.word)}</b>：${esc(u.note)}</div>`).join('')}
          <div class="tiny muted">用对的算一次成功复习；用错的会提前安排复习。</div></div>` : ''}
        ${r.keep ? `<div class="card sunk row between"><div><div class="kicker">值得收藏</div><b class="text">${esc(r.keep.text)}</b> <span class="muted small">${esc(r.keep.meaning)}</span></div><button class="btn small primary" id="keep">收藏</button></div>` : ''}
        <div class="card done-card">${doneRing}<h2 class="h2">这篇完成了</h2>${(m.expressions || []).length ? '<button class="link small" id="shareDone" type="button" data-tap="share-material">把学会的一句做成卡片</button>' : ''}<p class="muted small">${remaining != null ? '今天还可以用 AI ' + remaining + ' 次。' : ''}收藏的表达会在合适的时候出现在复习里，知识图谱也已更新。</p>
          <div class="row center">${m.series && m.series.next ? `<a class="btn" href="#/">回到今日</a><a class="btn primary" href="#/m/${encodeURIComponent(m.series.next)}">下一集：第 ${m.series.part + 1} 集</a>` : '<a class="btn" href="#/graph">看知识图谱</a><a class="btn primary" href="#/">回到今日</a>'}</div></div></div>`;
      box.querySelectorAll('[data-say-text]').forEach(b => b.onclick = () => TTS.say(b.dataset.sayText));
      const sd = box.querySelector('#shareDone'); if (sd) sd.onclick = () => shareFromMaterial(m);
      box.querySelectorAll('[data-keep-v]').forEach(b => b.onclick = () => { const v = r.versions[Number(b.dataset.keepV)]; saveCard({ text: v.text, meaning: v.label + '：' + v.why, context: '', pack: id }, b); });
      const k = box.querySelector('#keep'); if (k) k.onclick = () => saveCard({ text: r.keep.text, meaning: r.keep.meaning, context: r.corrected, pack: id }, k);
      box.scrollIntoView({ behavior: REDUCED ? 'auto' : 'smooth', block: 'start' });
    }
    ({ listen, read, check, output })[st.step]();
  }

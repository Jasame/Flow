  /* ---------- the speaking route: role-play scenes from ordering a coffee to answering a sceptical boss ---------- */
  async function speakView() {
    const d = await api('/api/next/speak' + guestQuery(true));
    const LV = { A2: '入门', B1: '中级', B2: '中高级', C1: '高级' };
    view.innerHTML = `<div class="stack"><div><span class="kicker">口语路线</span><h1 class="h1">开口说，从真实情景开始</h1>
        ${aiMark('对话里的角色由 AI 扮演')}<p class="muted small">AI 扮演情景里的另一方：店员、房东、面试官……你用英文完成任务，可以说也可以打字。每说一句它会顺手纠正一处，并按你的回答放慢或加深一点；结束时告诉你哪里说得好、哪里要改。练过的情景过两周会回来：第 2 轮多一条要求，第 3 轮换角色。</p></div>
      ${d.next ? (n => `<a class="btn primary block" href="#/speak/${encodeURIComponent(d.next)}">下一个：${esc(n.title)}${n.rounds ? ` · 第 ${n.round} 轮` : ''}<span aria-hidden="true">→</span></a>`)(d.items.find(x => x.id === d.next)) : ''}
      <p class="small muted">${d.round_two ? `${d.total} 个情景都练过了，现在是复练：练过的情景会多一条要求，或者换角色再演一次。` : `已完成 ${d.done} / ${d.total} 个情景`}</p>
      <a class="card flat ielts-entry" href="#/speak/ielts" data-tap="speak-ielts"><span class="stack-xs"><b>雅思口语 · Part 1 和 Part 2</b>
        <span class="tiny muted">考官提问、话题卡计时，按四项标准给 AI 估计分（练习用，不是官方成绩）</span></span><span class="go" aria-hidden="true">›</span></a>
      ${['A2', 'B1', 'B2', 'C1'].map(lv => { const xs = d.items.filter(x => x.level === lv); return xs.length ? `<section class="stack-s section"><h2 class="h2">${lv} · ${LV[lv]}</h2>
        <div class="plist">${xs.map(x => `<a class="nrow ${x.done ? 'st st-solid' : 'st st-untouched'}" href="#/speak/${encodeURIComponent(x.id)}"><i class="dot" aria-hidden="true"></i>
          <span class="t"><b>${esc(x.title)}</b><span class="tiny muted">你：${esc(x.me)} · AI：${esc(x.ai)}${x.rounds ? ` · 练过 ${x.rounds} 轮` : ''}</span></span><span></span><span class="go" aria-hidden="true">›</span></a>`).join('')}</div></section>` : ''; }).join('')}</div>`;
  }
  async function speakScene(sid) {
    const d = await api('/api/next/speak' + guestQuery(true)), x = d.items.find(s => s.id === sid);
    if (!x) { view.innerHTML = '<div class="empty"><p>没有这个情景。</p><a class="btn" href="#/speak">口语路线</a></div>'; return; }
    const hist = [], paced = { easier: 0, harder: 0 };
    // round 2, 3…: one more requirement (even rounds) or the roles swapped (odd rounds from 3); scenarios.mode_of
    const swap = x.mode === 'swap', again = x.rounds > 0;
    const goals = swap ? x.swap_goals : x.goals;
    view.innerHTML = `<div><a class="link small" href="#/speak">← 口语路线</a></div>
      <div class="stack"><div><span class="kicker">情景对话 · ${esc(x.level)}${again ? ` · 第 ${x.round} 轮` : ''}</span><h1 class="h1">${esc(x.title)}</h1><div class="title-en">${esc(x.title_en)}</div>
        ${aiMark('对话里的角色由 AI 扮演，每句的纠正也由 AI 给出')}<p class="small">${swap ? `这一轮换过来：你扮演${esc(x.ai)}，AI 扮演${esc(x.me)}。情景还是：${esc(x.brief)}` : esc(x.brief)}</p></div>
      <div class="scene-goals"><div class="kicker">你的任务${swap ? `（你是${esc(x.ai)}）` : ''}</div><ol class="steps-list small">${goals.map(g => `<li>${esc(g)}</li>`).join('')}</ol>
        ${x.mode === 'challenge' ? `<div class="round-extra small"><b>这一轮多一条：</b>${esc(x.challenge)}</div>` : ''}</div>
      ${swap ? '' : `<details class="useful"><summary class="small">用得上的说法（${x.useful.length}）</summary><div class="plist">${x.useful.map(u => `<div class="crow"><button class="icon-btn" data-say="${esc(u.text)}" aria-label="朗读">${ICON.speak}</button><span><span class="en">${esc(u.text)}</span><span class="tiny muted">${esc(u.meaning)}</span></span></div>`).join('')}</div></details>`}
      <div class="chat" id="chat"></div>
      <div id="dlgIn" class="stack-s" hidden><div class="tiny muted" id="dlgHint"></div>
        <div class="chat-in"><textarea id="dlgText" rows="2" maxlength="480" lang="en" enterkeyhint="send" placeholder="用英文回答，或者点 ● 说出来"></textarea>${recBtn('dlgMic', '说出来')}<button class="btn primary" id="dlgSend" data-own-wait>发送</button></div>
        <div class="row between"><span class="tiny muted" id="dlgCount"></span><button class="btn small ghost" id="dlgEnd">结束并看反馈</button></div></div>
      <div><button class="btn primary block" id="dlgStart">开始对话</button></div><div id="dlgOut"></div></div>`;
    view.querySelectorAll('[data-say]').forEach(b => b.onclick = () => TTS.say(b.dataset.say));
    const chat = view.querySelector('#chat');
    const bubble = (role, text, extra) => { chat.insertAdjacentHTML('beforeend', `<div class="msg ${role}"><div class="b">${esc(text)}</div>${extra || ''}</div>`); chat.lastElementChild.scrollIntoView({ block: 'nearest', behavior: REDUCED ? 'auto' : 'smooth' }); };
    const busy = on => { ['#dlgSend', '#dlgEnd', '#dlgMic'].forEach(s => { const b = view.querySelector(s); if (b) b.disabled = on; }); };
    const showInput = () => { const box = view.querySelector('#dlgIn'); if (box && !box.hidden) box.scrollIntoView({ block: 'end', behavior: REDUCED ? 'auto' : 'smooth' }); };
    const mine = () => hist.filter(h => h.role === 'me').length;
    async function turn(body) {
      busy(true);
      try { return (await api('/api/next/dialog', { scenario: sid, history: hist, request_id: rid('sp'), ...body })).result; }
      catch (e) { toast(e.message); return null; } finally { busy(false); }
    }
    view.querySelector('#dlgStart').onclick = async e => {
      if (!S.user) { needLogin('登录后可以和 AI 做情景对话。'); return; }
      const btn = e.currentTarget; btn.disabled = true; btn.innerHTML = '<span class="spin"></span>';
      const r = await turn({}); if (!r) { btn.disabled = false; btn.textContent = '开始对话'; return; }
      btn.parentNode.remove();
      chat.insertAdjacentHTML('beforeend', `<div class="scene small">${esc(r.scene)}${r.role ? `（AI 扮演：${esc(r.role)}）` : ''}</div>`);
      bubble('ai', r.reply); speakReply(r.reply, r.voice); hist.push({ role: 'ai', text: r.reply });
      view.querySelector('#dlgIn').hidden = false; showInput(); if (!TOUCH) view.querySelector('#dlgText').focus({ preventScroll: true });
    };
    // The AI's line in its role's voice (r.voice, scenarios.voice_for), which the server began making along with the reply
    // (声音接力), so it is usually there at once. SV.say waits for it with 「正在准备朗读…」 rather than switch to the browser
    // voice for being a few seconds late (the owner hears that as a robot); the browser voice only when the server cannot
    // give it, and one line says why. Played as SV plays (#78): Web Audio where it can, so an iPhone keeps the first word.
    function speakReply(text, voice) {
      if (!voice || !SV.on()) { TTS.say(text); return; }
      SV.say(text, null, { voice, title: '语流 · 口语情景' });
    }
    // 说完就显示进度: from the moment an answer is sent, a line at the end of the chat says what is happening and for how
    // long (the seconds are not read aloud); a recording that did not get through stays to be sent again, not said twice.
    function waiting(spoken) {
      const el = document.createElement('div'), t0 = Date.now();
      el.className = 'dlg-wait small muted'; el.setAttribute('role', 'status');
      el.innerHTML = `<span class="spin" aria-hidden="true"></span><span>${spoken ? '正在听你说的…' : '对方正在回…'}</span> <span class="secs" aria-hidden="true">0 秒</span>`;
      const secs = el.querySelector('.secs'), timer = setInterval(() => { secs.textContent = Math.floor((Date.now() - t0) / 1000) + ' 秒'; }, 1000);
      chat.append(el); el.scrollIntoView({ block: 'nearest', behavior: REDUCED ? 'auto' : 'smooth' });
      return {
        done() { clearInterval(timer); el.remove(); },
        failed(again) {
          clearInterval(timer);
          el.innerHTML = '<span>这段录音没有发出去。</span> <button class="btn small" type="button" data-own-wait>重发这段录音</button>';
          el.querySelector('button').onclick = () => { el.remove(); again(); };
        },
      };
    }
    async function send(text, blob) {
      const w = waiting(!!blob);
      let body;
      try { body = blob ? { audio: await MIC.payload(blob) } : { text }; } catch (e) { w.done(); toast(e.message); return; }
      const r = await turn(body);
      if (!r) {
        if (blob) { w.failed(() => send('', blob)); return; }
        w.done(); const box = view.querySelector('#dlgText'); if (box && !box.value) box.value = text;  // typed: back in the box
        return;
      }
      w.done();
      const me = r.heard || text;
      // 按回答调难度 (scenarios.pace): the AI's next line follows this answer's length and mistakes; say so in one line
      const pace = r.pace === 'easier' ? '放慢了一点' : r.pace === 'harder' ? '加深了一点' : '';
      if (pace) paced[r.pace] += 1;
      bubble('me', me, (r.correction ? `<div class="fix tiny"><del>${esc(r.correction.original)}</del> → <b>${esc(r.correction.better)}</b> <span class="muted">${esc(r.correction.why)}</span></div>` : '')
        + (pace ? `<div class="pace tiny muted" data-pace="${r.pace}">↳ AI 按你的回答${pace}</div>` : ''));
      hist.push({ role: 'me', text: me });
      bubble('ai', r.reply); speakReply(r.reply, r.voice); hist.push({ role: 'ai', text: r.reply });
      const hint = view.querySelector('#dlgHint');
      hint.innerHTML = (r.hint ? esc('提示：' + r.hint) : '') + (r.say ? `<span class="say-line">${r.hint ? '' : '提示：'}可以说 <b lang="en">${esc(r.say)}</b><button class="icon-btn" type="button" id="dlgSay" aria-label="朗读这句">${ICON.speak}</button></span>` : '');
      const sb = hint.querySelector('#dlgSay'); if (sb) sb.onclick = () => TTS.say(r.say);
      const n = mine(); view.querySelector('#dlgCount').textContent = n < 4 ? `已经说了 ${n} 句，说到 4 句左右就可以看反馈` : `已经说了 ${n} 句，可以看反馈了`;
      showInput();
    }
    view.querySelector('#dlgSend').onclick = () => { const t = view.querySelector('#dlgText'); const v = t.value.trim(); if (!v) return; t.value = ''; send(v); };
    view.querySelector('#dlgText').addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); view.querySelector('#dlgSend').click(); } });
    const mic = view.querySelector('#dlgMic'); mic.dataset.ownWait = ''; mic.onclick = () => MIC.toggle(mic, 30, b => send('', b));
    view.querySelector('#dlgEnd').onclick = async e => {
      if (mine() < 1) { toast('先说一两句再看反馈'); return; }
      const btn = e.currentTarget; btn.innerHTML = '<span class="spin"></span>';
      const r = await turn({ end: true }); if (!r) { btn.textContent = '结束并看反馈'; return; }
      view.querySelector('#dlgIn').hidden = true; TTS.stop();
      view.querySelector('#dlgOut').innerHTML = `<div class="result enter stack">${aiMark('总结和建议由 AI 生成，仅供参考')}<div class="card verdict"><span class="dot"></span><div>${esc(r.summary)}</div></div>
        ${r.good.length ? `<div class="stack-s"><b>说得好的句子</b>${r.good.map(g => `<div class="small text">${esc(g)}</div>`).join('')}</div>` : ''}
        ${r.fixes.length ? `<div class="stack-s"><b>要改的地方</b>${fixesHTML(r.fixes)}</div>` : ''}
        ${r.challenge ? `<div class="round-extra small"><b>这一轮的要求：</b>${esc(r.challenge)}${typeof r.challenge_met === 'boolean' ? (r.challenge_met ? ' <span class="ok-mark">✓ 做到了</span>' : ' <span class="muted">· 这次还没做到，下一轮再试</span>') : ''}</div>` : ''}
        ${paced.easier || paced.harder ? `<p class="tiny muted">这一轮 AI 按你的回答${paced.easier ? `放慢了 ${paced.easier} 次` : ''}${paced.easier && paced.harder ? '、' : ''}${paced.harder ? `加深了 ${paced.harder} 次` : ''}。</p>` : ''}
        ${r.expressions.length ? `<div class="stack-s"><b>可以学的表达</b>${r.expressions.map((ex, k) => `<div class="row between small"><span><b>${esc(ex.text)}</b> <span class="muted">${esc(ex.meaning)}</span></span><button class="btn small" data-kx="${k}">收藏</button></div>`).join('')}</div>` : ''}
        <p class="small cheer">${mine() >= 4 ? '完整完成了一个情景。' : ''}敢开口就是进步：说错的地方，正是下次能说对的地方。</p>
        <div class="row"><button class="btn" id="dlgAgain">再练一次</button><a class="btn primary" href="#/speak">下一个情景</a></div></div>`;
      view.querySelectorAll('[data-kx]').forEach(b => b.onclick = () => { const ex = r.expressions[Number(b.dataset.kx)]; saveCard({ text: ex.text, meaning: ex.meaning, context: '', pack: null }, b); });
      view.querySelector('#dlgAgain').onclick = () => { scrollTo({ top: 0 }); speakScene(sid); };
      bringIntoView(view.querySelector('#dlgOut'));
      if (S.user) refreshHome().catch(() => {});
    };
  }

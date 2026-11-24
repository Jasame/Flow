  /* ---------- the speaking route: role-play scenes from ordering a coffee to answering a sceptical boss ---------- */
  async function speakView() {
    const d = await api('/api/next/speak' + guestQuery(true));
    const LV = { A2: '入门', B1: '中级', B2: '中高级', C1: '高级' };
    view.innerHTML = `<div class="stack"><div><span class="kicker">口语路线</span><h1 class="h1">开口说，从真实情景开始</h1>
        <p class="muted small">AI 扮演情景里的另一方：店员、房东、面试官……你用英文完成任务，可以说也可以打字。每说一句它会顺手纠正一处，结束时告诉你哪里说得好、哪里要改。</p></div>
      ${d.next ? `<a class="btn primary block" href="#/speak/${encodeURIComponent(d.next)}">下一个：${esc(d.items.find(x => x.id === d.next).title)}<span aria-hidden="true">→</span></a>` : ''}
      <p class="small muted">已完成 ${d.done} / ${d.total} 个情景</p>
      <a class="card flat ielts-entry" href="#/speak/ielts" data-tap="speak-ielts"><span class="stack-xs"><b>雅思口语 · Part 1 和 Part 2</b>
        <span class="tiny muted">考官提问、话题卡计时，按四项标准给 AI 估计分（练习用，不是官方成绩）</span></span><span class="go" aria-hidden="true">›</span></a>
      ${['A2', 'B1', 'B2', 'C1'].map(lv => { const xs = d.items.filter(x => x.level === lv); return xs.length ? `<section class="stack-s section"><h2 class="h2">${lv} · ${LV[lv]}</h2>
        <div class="plist">${xs.map(x => `<a class="nrow ${x.done ? 'st st-solid' : 'st st-untouched'}" href="#/speak/${encodeURIComponent(x.id)}"><i class="dot" aria-hidden="true"></i>
          <span class="t"><b>${esc(x.title)}</b><span class="tiny muted">你：${esc(x.me)} · AI：${esc(x.ai)}${x.done ? ' · 完成过' : ''}</span></span><span></span><span class="go" aria-hidden="true">›</span></a>`).join('')}</div></section>` : ''; }).join('')}</div>`;
  }
  async function speakScene(sid) {
    const d = await api('/api/next/speak' + guestQuery(true)), x = d.items.find(s => s.id === sid);
    if (!x) { view.innerHTML = '<div class="empty"><p>没有这个情景。</p><a class="btn" href="#/speak">口语路线</a></div>'; return; }
    const hist = [];
    view.innerHTML = `<div><a class="link small" href="#/speak">← 口语路线</a></div>
      <div class="stack"><div><span class="kicker">情景对话 · ${esc(x.level)}</span><h1 class="h1">${esc(x.title)}</h1><div class="title-en">${esc(x.title_en)}</div>
        <p class="small">${esc(x.brief)}</p></div>
      <div class="scene-goals"><div class="kicker">你的任务</div><ol class="steps-list small">${x.goals.map(g => `<li>${esc(g)}</li>`).join('')}</ol></div>
      <details class="useful"><summary class="small">用得上的说法（${x.useful.length}）</summary><div class="plist">${x.useful.map(u => `<div class="crow"><button class="icon-btn" data-say="${esc(u.text)}" aria-label="朗读">${ICON.speak}</button><span><span class="en">${esc(u.text)}</span><span class="tiny muted">${esc(u.meaning)}</span></span></div>`).join('')}</div></details>
      <div class="chat" id="chat"></div>
      <div id="dlgIn" class="stack-s" hidden><div class="tiny muted" id="dlgHint"></div>
        <div class="chat-in"><textarea id="dlgText" rows="2" maxlength="480" lang="en" enterkeyhint="send" placeholder="用英文回答，或者点 ● 说出来"></textarea>${recBtn('dlgMic', '说出来')}<button class="btn primary" id="dlgSend">发送</button></div>
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
      bubble('ai', r.reply); TTS.say(r.reply); hist.push({ role: 'ai', text: r.reply });
      view.querySelector('#dlgIn').hidden = false; showInput(); if (!TOUCH) view.querySelector('#dlgText').focus({ preventScroll: true });
    };
    async function send(text, blob) {
      const body = blob ? { audio: await MIC.payload(blob) } : { text };
      const r = await turn(body); if (!r) return;
      const me = r.heard || text;
      bubble('me', me, r.correction ? `<div class="fix tiny"><del>${esc(r.correction.original)}</del> → <b>${esc(r.correction.better)}</b> <span class="muted">${esc(r.correction.why)}</span></div>` : '');
      hist.push({ role: 'me', text: me });
      bubble('ai', r.reply); TTS.say(r.reply); hist.push({ role: 'ai', text: r.reply });
      view.querySelector('#dlgHint').textContent = r.hint ? '提示：' + r.hint : '';
      const n = mine(); view.querySelector('#dlgCount').textContent = n < 4 ? `已经说了 ${n} 句，说到 4 句左右就可以看反馈` : `已经说了 ${n} 句，可以看反馈了`;
      showInput();
    }
    view.querySelector('#dlgSend').onclick = () => { const t = view.querySelector('#dlgText'); const v = t.value.trim(); if (!v) return; t.value = ''; send(v); };
    view.querySelector('#dlgText').addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); view.querySelector('#dlgSend').click(); } });
    const mic = view.querySelector('#dlgMic'); mic.onclick = () => MIC.toggle(mic, 30, b => send('', b));
    view.querySelector('#dlgEnd').onclick = async e => {
      if (mine() < 1) { toast('先说一两句再看反馈'); return; }
      const btn = e.currentTarget; btn.innerHTML = '<span class="spin"></span>';
      const r = await turn({ end: true }); if (!r) { btn.textContent = '结束并看反馈'; return; }
      view.querySelector('#dlgIn').hidden = true; TTS.stop();
      view.querySelector('#dlgOut').innerHTML = `<div class="result enter stack"><div class="card verdict"><span class="dot"></span><div>${esc(r.summary)}</div></div>
        ${r.good.length ? `<div class="stack-s"><b>说得好的句子</b>${r.good.map(g => `<div class="small text">${esc(g)}</div>`).join('')}</div>` : ''}
        ${r.fixes.length ? `<div class="stack-s"><b>要改的地方</b><span class="tiny muted">已经放进错题本，会按遗忘曲线回来。</span>${fixesHTML(r.fixes)}</div>` : ''}
        ${r.expressions.length ? `<div class="stack-s"><b>可以学的表达</b>${r.expressions.map((ex, k) => `<div class="row between small"><span><b>${esc(ex.text)}</b> <span class="muted">${esc(ex.meaning)}</span></span><button class="btn small" data-kx="${k}">收藏</button></div>`).join('')}</div>` : ''}
        <p class="small cheer">${mine() >= 4 ? '完整完成了一个情景。' : ''}敢开口就是进步：说错的地方，正是下次能说对的地方。</p>
        <div class="row"><button class="btn" id="dlgAgain">再练一次</button><a class="btn primary" href="#/speak">下一个情景</a></div></div>`;
      view.querySelectorAll('[data-kx]').forEach(b => b.onclick = () => { const ex = r.expressions[Number(b.dataset.kx)]; saveCard({ text: ex.text, meaning: ex.meaning, context: '', pack: null }, b); });
      view.querySelector('#dlgAgain').onclick = () => { scrollTo({ top: 0 }); speakScene(sid); };
      bringIntoView(view.querySelector('#dlgOut'));
      if (S.user) refreshHome().catch(() => {});
    };
  }

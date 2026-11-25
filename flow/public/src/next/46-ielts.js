  /* ---------- 雅思口语练习 (ielts_speaking): Part 1 questions and Part 2 cue cards, on the four criteria ---------- */
  // Every band shown is the AI's estimate for practice, and each page with one says so (d.notice).
  const IELTS_BACK = '<div><a class="link small" href="#/speak/ielts">← 雅思口语</a></div>';
  const bandTxt = b => (b == null ? '—' : b.toFixed(1));
  async function ieltsView() {
    const d = await api('/api/next/ielts');
    const row = (href, title, sub, last) => `<a class="nrow ${last != null ? 'st st-solid' : 'st st-untouched'}" href="${href}"><i class="dot" aria-hidden="true"></i>
        <span class="t"><b>${esc(title)}</b><span class="tiny muted">${esc(sub)}${last != null ? ` · 上次约 ${bandTxt(last)}` : ''}</span></span><span></span><span class="go" aria-hidden="true">›</span></a>`;
    view.innerHTML = `<div><a class="link small" href="#/speak">← 口语路线</a></div>
      <div class="stack"><div><h1 class="h1">雅思口语</h1>
        <p class="muted small">像考场一样开口说：Part 1 日常问答；Part 2 话题卡，准备 1 分钟，说 1–2 分钟。</p>
        <details class="basis"><summary>怎么评分</summary><p class="small">说完按雅思口语的四项标准（流利与连贯、词汇、语法、发音）给出估计分和改法。</p></details>
        <p class="tiny ielts-note">${esc(d.notice)}</p></div>
      <section class="stack-s"><h2 class="h2">Part 1 · 日常问答</h2><p class="tiny muted">每个话题 4 个问题，大约 3 分钟。考官不打断你，每句下面可以看「这句可以更好」。</p>
        <div class="plist">${d.part1.map(x => row(`#/speak/ielts/p1-${x.id}`, x.title, x.title_en, x.last)).join('')}</div></section>
      <section class="stack-s"><h2 class="h2">Part 2 · 话题卡</h2><p class="tiny muted">准备 1 分钟（可以记关键词），时间到自动开始录音，最多说 2 分钟。</p>
        <div class="plist">${d.part2.map(x => row(`#/speak/ielts/p2-${x.id}`, x.title, x.task, x.last)).join('')}</div></section></div>`;
  }
  async function ieltsPractice(key) {
    const d = await api('/api/next/ielts');
    const m = /^p([12])-([a-z-]+)$/.exec(key || ''), list = m && (m[1] === '1' ? d.part1 : d.part2), x = list && list.find(t => t.id === m[2]);
    if (!x) { view.innerHTML = '<div class="empty"><p>没有这个练习。</p><a class="btn" href="#/speak/ielts">雅思口语</a></div>'; return; }
    return m[1] === '1' ? ieltsPart1(d, x) : ieltsPart2(d, x);
  }
  // The feedback of either part: overall estimate, the four criteria (a bar each, what went well, what to do next),
  // what was said, a model answer to listen to, and the corrections (already in the mistake book).
  function ieltsFeedbackHTML(r, said) {
    return `<div class="result enter stack ielts-fb">${aiMark('估计分、点评和示范回答由 AI 生成，不是官方成绩')}
        <div class="card ielts-top"><div class="ielts-overall"><b>${r.overall == null ? '—' : '约 ' + bandTxt(r.overall)}</b><span class="small">总体估计</span></div>
          <p class="tiny ielts-note">${esc(r.notice)}</p>${r.summary ? `<p class="small">${esc(r.summary)}</p>` : ''}</div>
        <div class="stack-s ielts-crit">${r.criteria.map(c => `<div class="crit">
            <div class="ab"><span class="nm">${esc(c.title)}</span><span class="vbar"><i data-w="${c.band == null ? 0 : Math.round(c.band / 9 * 100)}"></i></span><span class="lv">${bandTxt(c.band)}</span></div>
            ${c.band == null && c.id === 'p' ? '<div class="tiny muted">这次是打字作答，不评发音。</div>' : ''}
            ${c.good ? `<div class="tiny"><span class="ok-mark" aria-hidden="true">✓</span> ${esc(c.good)}</div>` : ''}${c.next ? `<div class="tiny"><span class="up" aria-hidden="true">↑</span> ${esc(c.next)}</div>` : ''}</div>`).join('')}</div>
        ${said}
        ${r.model ? `<details class="card flat fold" open><summary><b class="small">示范回答${r.model_q ? '：' + esc(r.model_q) : ''}</b></summary><div class="stack-s">
          <div class="row"><button class="btn small" id="ieModel" type="button">${ICON.speak.replace('<svg', '<svg width="16" height="16"')}<span>朗读</span></button><span class="tiny muted">AI 写的示范，学说法，不用背</span></div>
          <p class="text ielts-model">${esc(r.model)}</p></div></details>` : ''}
        ${r.fixes.length ? `<div class="stack-s"><b>要改的地方</b>${fixesHTML(r.fixes)}</div>` : ''}
        <div class="row"><button class="btn" id="ieAgain" type="button">再练一次</button><a class="btn primary" href="#/speak/ielts">换一个</a></div></div>`;
  }
  function bindIeltsFeedback(out, r, again) {
    requestAnimationFrame(() => requestAnimationFrame(() => out.querySelectorAll('.vbar i').forEach(i => { i.style.width = i.dataset.w + '%'; })));
    const md = out.querySelector('#ieModel'); if (md) md.onclick = () => TTS.say(r.model);
    out.querySelector('#ieAgain').onclick = () => { TTS.stop(); scrollTo({ top: 0 }); again(); };
    bringIntoView(out);
    if (S.user) refreshHome().catch(() => {});
  }
  const ieltsSay = t => { if (TTS.can()) TTS.say(t); };  // WeChat has no browser voice; the server voice (when on) works there

  /* Part 1: the examiner's four questions in order. Each answer: what the AI heard and, folded, a better way to say it. */
  function ieltsPart1(d, x) {
    const answers = [];
    let q = 0;
    view.innerHTML = `${IELTS_BACK}<div class="stack"><div><span class="kicker">雅思口语 Part 1 · 练习</span><h1 class="h1">${esc(x.title)}</h1><div class="title-en">${esc(x.title_en)}</div>
        <div class="ai-line">${aiVoice()}<span>考官的声音由 AI 合成</span></div><p class="small">考官一题一题问，不会打断你。每题说 2–4 句：先直接回答，再加一个理由或例子。可以说，也可以打字（打字不评发音）。</p></div>
      <div class="chat" id="chat"></div>
      <div id="ieIn" class="stack-s" hidden><div class="tiny muted" id="ieQn"></div>
        <div class="chat-in"><textarea id="ieText" rows="2" maxlength="600" lang="en" enterkeyhint="send" placeholder="用英文回答，或者点 ● 说出来"></textarea>${recBtn('ieMic', '说出来')}<button class="btn primary" id="ieSend">发送</button></div>
        <div class="row between"><span class="tiny muted">说完再点一次 ● 停止，最长 45 秒</span><button class="btn small ghost" id="ieEnd">结束并看反馈</button></div></div>
      <div><button class="btn primary block" id="ieStart">开始</button></div><div id="ieOut"></div></div>`;
    const chat = view.querySelector('#chat'), box = view.querySelector('#ieIn');
    const bubble = (role, text, extra) => { chat.insertAdjacentHTML('beforeend', `<div class="msg ${role}"><div class="b">${esc(text)}</div>${extra || ''}</div>`); chat.lastElementChild.scrollIntoView({ block: 'nearest', behavior: REDUCED ? 'auto' : 'smooth' }); };
    const busy = on => ['#ieSend', '#ieEnd', '#ieMic'].forEach(s => { const b = view.querySelector(s); if (b) b.disabled = on; });
    const ask = () => {
      const t = x.questions[q]; bubble('ai', t, `<span class="tiny muted who">考官 · 第 ${q + 1} / ${x.questions.length} 题</span>`); ieltsSay(t);
      view.querySelector('#ieQn').textContent = `第 ${q + 1} / ${x.questions.length} 题`;
    };
    view.querySelector('#ieStart').onclick = e => {
      if (!S.user) { needLogin('登录后可以练雅思口语，AI 会听你的回答并给估计分。'); return; }
      e.currentTarget.parentNode.remove(); box.hidden = false; ask();
      if (!TOUCH) view.querySelector('#ieText').focus({ preventScroll: true });
    };
    async function feedback() {
      MIC.stop(); box.hidden = true; TTS.stop();
      const out = view.querySelector('#ieOut'); out.innerHTML = '<div class="card sunk small row"><span class="spin"></span><span>考官在看你的回答，给四项估计分（约 10–20 秒）</span></div>';
      try {
        const r = (await api('/api/next/ielts', { step: 'part1', topic: x.id, answers, request_id: rid('ie') })).result;
        const said = `<details class="card flat fold"><summary><b class="small">你的回答（${r.answered} 题）</b></summary><div class="stack-s">${answers.map(a => `<div class="small"><div class="muted">${esc(x.questions[a.q])}</div><div class="text">${esc(a.text)}</div></div>`).join('')}</div></details>`;
        out.innerHTML = ieltsFeedbackHTML(r, said);
        bindIeltsFeedback(out, r, () => ieltsPart1(d, x));
      } catch (e) {
        out.innerHTML = `<div class="card sunk stack-s"><span class="small">${esc(e.message)}</span><button class="btn small" id="ieRetry">再试一次</button></div>`;
        out.querySelector('#ieRetry').onclick = feedback;
      }
    }
    async function send(text, blob) {
      busy(true);
      let r;
      try { r = (await api('/api/next/ielts', { step: 'answer', topic: x.id, q, request_id: rid('ie'), ...(blob ? { audio: await MIC.payload(blob) } : { text }) })).result; }
      catch (e) { toast(e.message); busy(false); if (text) view.querySelector('#ieText').value = text; return; }
      busy(false);
      const said = (r.heard || text || '').trim() || '[听不清]';
      bubble('me', said, r.better ? `<details class="better"><summary class="tiny">这句可以更好 ${aiTag()}</summary><div class="small text">${esc(r.better.text)}</div>${r.better.why ? `<div class="tiny muted">${esc(r.better.why)}</div>` : ''}</details>` : '');
      answers.push({ q, text: said.slice(0, 1200), note: r.note || '', spoken: !!blob });
      q += 1;
      if (q >= x.questions.length) { bubble('ai', 'Thank you. That\'s the end of Part 1.'); feedback(); return; }
      ask();
    }
    view.querySelector('#ieSend').onclick = () => { const t = view.querySelector('#ieText'), v = t.value.trim(); if (!v) return; t.value = ''; send(v); };
    view.querySelector('#ieText').addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); view.querySelector('#ieSend').click(); } });
    const mic = view.querySelector('#ieMic'); mic.onclick = () => MIC.toggle(mic, 45, b => send('', b));
    view.querySelector('#ieEnd').onclick = () => { if (!answers.length) { toast('先回答一题再看反馈'); return; } feedback(); };
  }

  /* Part 2: the cue card. 开始准备 asks for the microphone inside the tap (WeChat and iPhones allow it only there), one
     minute to prepare with a box for notes, then the recording starts by itself and stops at two minutes. The microphone
     stays open from 开始准备 to the end of the talk (nothing plays meanwhile) and is let go the moment the talk ends, so
     the feedback and the model answer are heard on the loudspeaker (micOpen / micClose, 70-learner.js). */
  const LONGREC = {
    stream: null, mr: null, chunks: [], t0: 0,
    async open() {
      try { this.stream = await micOpen(); } catch (e) { throw new Error(e.message + '；也可以打字作答'); }
    },
    start(onStop) {
      const type = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4'].find(t => MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported(t)) || '';
      // a low bitrate keeps two minutes of speech under the 1.4 MB a recording may be
      const opts = Object.assign(type ? { mimeType: type } : {}, { audioBitsPerSecond: 32000 });
      let mr; try { mr = new MediaRecorder(this.stream, opts); } catch (e) { mr = new MediaRecorder(this.stream); }
      this.mr = mr; this.chunks = []; this.t0 = Date.now();
      mr.ondataavailable = e => { if (e.data && e.data.size) this.chunks.push(e.data); };
      mr.onstop = () => { const secs = Math.round((Date.now() - this.t0) / 1000), blob = new Blob(this.chunks, { type: mr.mimeType || type || 'audio/webm' }); this.close(); onStop(blob, secs); };
      mr.start(1000);
    },
    stop() { if (this.mr && this.mr.state === 'recording') this.mr.stop(); else this.close(); },
    close() { if (this.stream) micClose(this.stream); this.stream = null; },
  };
  function ieltsPart2(d, x) {
    let timer = 0;
    const alive = () => document.body.contains(card);  // left the page: let go of the microphone
    view.innerHTML = `${IELTS_BACK}<div class="stack"><div><span class="kicker">雅思口语 Part 2 · 练习</span><h1 class="h1">${esc(x.title)}</h1></div>
      <div class="cue" id="cue" lang="en"><b>${esc(x.task)}</b><div class="small">You should say:</div><ul>${x.points.map(p => `<li>${esc(p)}</li>`).join('')}</ul><div class="small">${esc(x.last_point)}</div></div>
      <div id="p2" class="stack-s"><p class="small">点「开始准备」：1 分钟准备，可以在下面记几个关键词；时间到自动开始录音，最多说 2 分钟，到时间自动停。也可以提前开始、提前结束。尽量说满 1 分钟以上。</p>
        <button class="btn primary block" id="p2Start">开始准备</button><button class="btn small ghost" id="p2Type" type="button">不方便说话？打字作答（不评发音）</button></div>
      <div id="ieOut"></div></div>`;
    const card = view.querySelector('#cue'), stage = view.querySelector('#p2'), out = view.querySelector('#ieOut');
    const meter = (label, s, total, cls) => `<div class="p2-clock ${cls}" role="timer" aria-live="off"><span class="lbl">${label}</span><b id="p2T">${mmss(Math.max(0, s))}</b><span class="vbar"><i id="p2Bar" style="width:${Math.round((total - s) / total * 100)}%"></i></span></div>`;
    const tick = (s, total) => { const t = view.querySelector('#p2T'), b = view.querySelector('#p2Bar'); if (t) t.textContent = mmss(Math.max(0, s)); if (b) b.style.width = Math.round((total - s) / total * 100) + '%'; };
    async function submit(body) {
      stage.innerHTML = '<div class="card sunk small row"><span class="spin"></span><span>AI 在听你的回答，按四项标准估计分数（约 20–40 秒）</span></div>';
      try {
        const r = (await api('/api/next/ielts', { step: 'part2', card: x.id, request_id: rid('ie'), ...body })).result;
        stage.innerHTML = ''; if (body.text) draftDone('ielts-p2-' + x.id);
        const cov = r.covered ? `<div class="tiny muted">话题卡的 4 个要点：${r.covered.map((c, k) => `<span class="${c ? 'ok-mark' : 'bad-mark'}">${c ? '✓' : '✗'}</span> ${esc(k < 3 ? x.points[k] : 'explain…')}`).join('　')}</div>` : '';
        const said = `<details class="card flat fold"><summary><b class="small">你说的${r.spoken ? '（AI 转写' + (r.seconds ? ' · ' + mmss(r.seconds) : '') + '）' : ''}</b></summary><div class="stack-s"><p class="text">${esc(r.transcript || '（没听清）')}</p>${cov}</div></details>`;
        out.innerHTML = ieltsFeedbackHTML(r, said);
        bindIeltsFeedback(out, r, () => ieltsPart2(d, x));
      } catch (e) {
        stage.innerHTML = `<div class="card sunk stack-s"><span class="small">${esc(e.message)}</span><button class="btn small" id="p2Retry">再试一次</button></div>`;
        stage.querySelector('#p2Retry').onclick = () => submit(body);
      }
    }
    function talk() {
      clearInterval(timer);
      let left = d.talk;
      const notes = view.querySelector('#p2Notes'), kept = notes ? notes.value : '';
      stage.innerHTML = `${meter('<span class="dot rec-dot" aria-hidden="true"></span>正在录音', left, d.talk, 'talk')}
        ${kept ? `<div class="card sunk tiny p2-kept">你的笔记：${esc(kept)}</div>` : ''}<button class="btn primary block" id="p2Done">说完了</button>`;
      LONGREC.start(async (blob, secs) => {
        clearInterval(timer);
        if (!alive()) return;
        if (secs < 5 || blob.size < 2000) { stage.innerHTML = '<p class="small">录音太短了。</p><button class="btn primary" id="p2Re">重新开始</button>'; stage.querySelector('#p2Re').onclick = () => ieltsPart2(d, x); return; }
        let audio; try { audio = await MIC.payload(blob); } catch (e) { stage.innerHTML = `<p class="small">${esc(e.message)}</p>`; return; }
        submit({ audio, seconds: secs });
      });
      timer = setInterval(() => { if (!alive()) { clearInterval(timer); LONGREC.stop(); return; } left -= 1; tick(left, d.talk); if (left <= 0) LONGREC.stop(); }, 1000);
      stage.querySelector('#p2Done').onclick = () => LONGREC.stop();
      card.scrollIntoView({ block: 'start', behavior: REDUCED ? 'auto' : 'smooth' });  // the card in view while speaking
    }
    stage.querySelector('#p2Start').onclick = async e => {
      if (!S.user) { needLogin('登录后可以练雅思口语，AI 会听你的回答并给估计分。'); return; }
      const b = e.currentTarget;
      if (!micReady(() => b.click())) return;
      b.disabled = true;
      try { await LONGREC.open(); } catch (err) { b.disabled = false; toast(err.message); return; }
      let left = d.prep;
      stage.innerHTML = `${meter('准备', left, d.prep, 'prep')}
        <textarea id="p2Notes" rows="3" maxlength="300" lang="en" placeholder="记几个关键词，例如：cooking · grandma · 3 months · saves money" autocapitalize="off" spellcheck="false"></textarea>
        <button class="btn block" id="p2Go">提前开始说</button>`;
      stage.querySelector('#p2Go').onclick = talk;
      timer = setInterval(() => { if (!alive()) { clearInterval(timer); LONGREC.close(); return; } left -= 1; tick(left, d.prep); if (left <= 0) talk(); }, 1000);
    };
    stage.querySelector('#p2Type').onclick = () => {
      if (!S.user) { needLogin('登录后可以练雅思口语，AI 会看你的回答并给估计分。'); return; }
      stage.innerHTML = `<textarea id="p2Txt" data-draft="ielts-p2-${esc(x.id)}" rows="8" maxlength="3000" lang="en" placeholder="像说话一样写下你的回答（至少 20 个英文词）"></textarea>
        <div class="row between"><span class="tiny muted">打字作答不评发音，其他三项照常估计</span><button class="btn primary" id="p2Send">提交</button></div>`;
      stage.querySelector('#p2Send').onclick = () => { const v = stage.querySelector('#p2Txt').value.trim(); if ((v.match(/[A-Za-z]+/g) || []).length < 20) { toast('至少写 20 个英文词'); return; } submit({ text: v }); };
    };
  }

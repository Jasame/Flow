    /* listen: sentence list, word-by-word highlight while it plays */
    // Narration is usable when this material has the chosen voice and the shown text is the original.
    async function narration(ls) {
      const voices = (m.audio && m.audio.voices) || [];
      if (!voices.length || (m.variant && !st.showOriginal)) return null;
      if (!voices.includes(S.voice)) S.voice = voices[0];
      const ok = await NAR.load(id, S.voice, m.audio.version);
      return ok && NAR.meta && NAR.meta.sentences.length === ls.length ? NAR.meta : null;
    }
    const LOOP = Object.assign({ rep: 1, gap: 0 }, load('flow-next-loop') || {});  // 复读, kept on the phone
    // 复听 (relisten_service), from 今日: the text hidden at first; after a listen, how much was understood, then the text.
    const RELISTEN = [[3, '几乎都懂'], [2, '大部分'], [1, '一半左右'], [0, '很少']];
    function relistenHTML() {
      return st.relistened ? `<div class="card sunk stack-s relisten" id="relisten" aria-live="polite"><b>${esc(st.relistened)}</b><span class="small muted">原文出来了：没听懂的句子，点句子前面的喇叭单独再听几遍。</span></div>`
        : `<div class="card sunk stack-s relisten" id="relisten"><b>复听：先不看原文，从头听一遍</b>
          <span class="small">点「播放全文」。听完选一下听懂了多少，原文就会出来，再看没听懂的句子。</span>
          <div class="chips" role="group" aria-label="听懂了多少">${RELISTEN.map(([k, l]) => `<button class="chip" type="button" data-und="${k}">${l}</button>`).join('')}</div></div>`;
    }
    function bindRelisten() {
      const showText = () => {
        st.blind = false; pane.querySelectorAll('.line .txt').forEach(t => t.classList.remove('blind'));
        const bl = pane.querySelector('#blind'); if (bl) { bl.classList.remove('on'); bl.setAttribute('aria-pressed', 'false'); }
        const box = pane.querySelector('#relisten'); if (box) box.outerHTML = relistenHTML();
      };
      pane.querySelectorAll('[data-und]').forEach(b => b.onclick = async () => {
        const body = { pack: id, understood: Number(b.dataset.und) }, label = b.textContent;
        pane.querySelectorAll('[data-und]').forEach(x => { x.disabled = true; });
        try {
          const r = await api('/api/next/relisten', body);
          st.relistened = `记下了：听懂了${r.label}。` + (r.known ? '这篇已经听熟了，以后不再安排复听。' : `${r.next_days} 天后再听一次。`);
        } catch (e) {
          if (!e.network) { toast(e.message); pane.querySelectorAll('[data-und]').forEach(x => { x.disabled = false; }); return; }
          OUTBOX.push({ path: '/api/next/relisten', body });  // without a connection: sent when the phone is back online
          st.relistened = `记下了：听懂了${label}，联网后同步。`;
        }
        showText();
      });
    }
    async function listen() {
      const again = parts()[3] === 'again' && !!S.user;
      if (again && !st.againSet) { st.againSet = true; st.mode = 'listen'; st.blind = true; }
      if (st.mode === 'shadow') return shadowMode();
      if (st.mode === 'dictate') return dictateMode();
      const ls = lines();
      const nm = await narration(ls);
      const voices = (m.audio && m.audio.voices) || [];
      pane.innerHTML = `${again ? relistenHTML() : ''}${modeTabs()}<div class="player">
          <button class="btn primary" id="playAll">${ICON.play.replace('<svg', '<svg width="18" height="18" fill="currentColor"')}<span>播放全文</span></button>
          <div class="speed" role="group" aria-label="语速">${[0.75, 1, 1.25].map(r => `<button data-rate="${r}" aria-pressed="${TTS.rate === r}">${r}×</button>`).join('')}</div>
          <button class="icon-btn ${st.blind ? 'on' : ''}" id="blind" aria-pressed="${st.blind}" title="盲听：先只听不看" aria-label="盲听">${ICON.eye}</button>
        </div>
        <div class="loopbar"><div class="lg" role="group" aria-label="复读：每句几遍"><span class="tiny muted">每句</span>${[[1, '1 遍'], [3, '3 遍'], [5, '5 遍'], [0, '循环']].map(([n, l]) => `<button class="chip small" data-rep="${n}" aria-pressed="${LOOP.rep === n}">${l}</button>`).join('')}</div>
          <div class="lg" role="group" aria-label="复读：句后停顿"><span class="tiny muted">句后</span>${[[0, '不停'], [2, '停 2 秒'], [-1, '留时间跟说']].map(([n, l]) => `<button class="chip small" data-gap="${n}" aria-pressed="${LOOP.gap === n}">${l}</button>`).join('')}</div></div>
        ${voices.length ? voiceChips(voices) : ''}${prereadHTML()}
        ${nm ? '' : (TTS.ok ? '<p class="muted tiny">这篇暂时没有真人声录音，先用浏览器朗读。</p>' : '<p class="err">这个浏览器不支持朗读，可以直接去「读」。</p>')}
        <p class="muted small">想练耳朵，可以先点 👁 只听不看；听不懂的句子单独点开反复听。播放时正在读的词会亮起来${TOUCH ? '' : '（空格键播放 / 停止）'}。</p>
        <div class="lines">${ls.map((s, i) => `<div class="line" data-i="${i}"><button class="icon-btn" data-say="${i}" aria-label="播放第 ${i + 1} 句">${ICON.speak}</button><div class="txt ${st.blind ? 'blind' : ''}">${wordSpans(s, () => 'kw')}</div></div>`).join('')}</div>
        <div class="section row between"><span class="muted small">共 ${ls.length} 句${nm ? ' · ' + Math.round(nm.duration / 60 * 10) / 10 + ' 分钟' : ''}</span><button class="btn" id="toRead">听完了，去读 →</button></div>`;
      let playing = -1, shown = -1;
      const lineEl = i => pane.querySelector(`.line[data-i="${i}"]`);
      const setNow = i => pane.querySelectorAll('.line').forEach(el => { const on = Number(el.dataset.i) === i; el.classList.toggle('now', on); if (!on) el.querySelectorAll('.cur').forEach(x => x.classList.remove('cur')); });
      const setBtn = on => { const b = pane.querySelector('#playAll'); if (b) { b.innerHTML = playIcon(on) + `<span>${on ? '停止' : '播放全文'}</span>`; b.setAttribute('aria-pressed', String(on)); } };
      const follow = t => {
        const [si, wc] = NAR.locate(t);
        if (si !== shown) { shown = si; setNow(si); MINI.update(`第 ${si + 1} / ${ls.length} 句`); const el = lineEl(si); if (el && playing >= 0) el.scrollIntoView({ block: 'center', behavior: REDUCED ? 'auto' : 'smooth' }); }
        if (si >= 0) lightAt(lineEl(si), wc);
      };
      const stopAll = () => { loopTok++; clearTimeout(loopTimer); TTS.stop(); NAR.stop(); playing = -1; shown = -1; setNow(-1); setBtn(false); MINI.hide(); };
      // 复读: a sentence said LOOP.rep times (0: until stopped), with a pause after it: none, 2 s, or as long as the
      // sentence itself and a little more, to say it back.
      let loopTok = 0, loopTimer = 0;
      const gapMs = i => (LOOP.gap === -1 ? Math.max(1500, nm ? (nm.sentences[i].e - nm.sentences[i].s) * 1300 : ls[i].split(' ').length * 450) : LOOP.gap * 1000);
      const sayRepeated = (i, then, n = 0) => {
        const tok = loopTok;
        sayLine(i, () => {
          if (tok !== loopTok) return;
          const more = LOOP.rep === 0 || n + 1 < LOOP.rep, next = () => { if (tok === loopTok) { if (more) sayRepeated(i, then, n + 1); else if (then) then(); } };
          const g = more || then ? gapMs(i) : 0;
          if (g) loopTimer = setTimeout(next, g); else next();
        });
      };
      const looping = () => LOOP.rep !== 1 || LOOP.gap !== 0;
      const sayLine = (i, then) => {
        if (nm) { shown = -1; NAR.play(nm.sentences[i].s, nm.sentences[i].e, follow, then); return; }
        const el = lineEl(i); TTS.say(ls[i], then, c => lightWord(el, c));
      };
      const playFrom = i => {
        if (i >= ls.length) { stopAll(); markStep('listen'); return; }
        playing = i; setNow(i); MINI.update(`第 ${i + 1} / ${ls.length} 句`);
        const el = lineEl(i); if (el) el.scrollIntoView({ block: 'center', behavior: REDUCED ? 'auto' : 'smooth' });
        sayRepeated(i, () => playFrom(i + 1));
      };
      pane.querySelector('#playAll').onclick = () => {
        if (playing >= 0) return stopAll();
        setBtn(true); MINI.show('正在播放全文', stopAll);
        // one sentence after another (each said again, and pauses, when 复读 is set); otherwise the narration straight through
        if (nm && !looping()) { playing = 0; shown = -1; NAR.play(nm.sentences[0].s, null, follow, () => { stopAll(); markStep('listen'); }); }
        else playFrom(0);
      };
      pane.querySelectorAll('[data-say]').forEach(b => b.onclick = () => {
        const i = Number(b.dataset.say); stopAll(); setNow(i);
        if (looping()) MINI.show(`复读第 ${i + 1} 句`, stopAll);  // a stop button on screen while it repeats
        sayRepeated(i, () => { setNow(-1); MINI.hide(); });
      });
      pane.querySelectorAll('[data-rep], [data-gap]').forEach(b => b.onclick = () => {
        const k = 'rep' in b.dataset ? 'rep' : 'gap'; LOOP[k] = Number(b.dataset[k]); save('flow-next-loop', LOOP);
        pane.querySelectorAll(`[data-${k}]`).forEach(x => x.setAttribute('aria-pressed', String(x === b)));
      });
      pane.querySelectorAll('.line .txt').forEach((t, i) => t.onclick = e => { if (e.target.dataset.w && !st.blind) lookupSheet(e.target.dataset.w, ls[i], id); });
      pane.querySelectorAll('[data-rate]').forEach(b => b.onclick = () => { TTS.rate = Number(b.dataset.rate); save('flow-next-rate', TTS.rate); NAR.audio.playbackRate = TTS.rate; pane.querySelectorAll('[data-rate]').forEach(x => x.setAttribute('aria-pressed', String(x === b))); });
      pane.querySelectorAll('[data-voice]').forEach(b => b.onclick = async () => { if (b.disabled) return; stopAll(); await setVoice(b.dataset.voice); listen(); toast('已切换为' + VOICE_LABELS[b.dataset.voice]); });
      pane.querySelector('#blind').onclick = e => { st.blind = !st.blind; toast(st.blind ? '盲听：只听不看，再点一次显示原文' : '已显示原文'); e.currentTarget.classList.toggle('on', st.blind); e.currentTarget.setAttribute('aria-pressed', String(st.blind)); pane.querySelectorAll('.txt').forEach(t => t.classList.toggle('blind', st.blind)); };
      pane.querySelector('#toRead').onclick = () => { stopAll(); markStep('listen'); go('read'); };
      if (again) bindRelisten();
      bindListenHead(stopAll);
      document.onkeydown = e => {
        if (isTyping(e) || !sheetEl.hidden || e.metaKey || e.ctrlKey || e.altKey) return;
        const b = pane.querySelector('#playAll'); if (b && (e.key === ' ' || e.key === 'k')) { e.preventDefault(); b.click(); }
      };
    }

    /* listen modes: 精听 (sentence list) · 跟读 (record, compare, AI feedback) · 听写 (type what you hear) */
    const MODES = { listen: '精听', shadow: '跟读', dictate: '听写' };
    if (!st.mode) st.mode = MODES[load('flow-next-listen-mode')] ? load('flow-next-listen-mode') : 'listen';
    const stripLabel = s => s.replace(/^[A-Z][a-z]+(?: [A-Z][a-z]+)?:\s+/, '');
    // The words worth knowing before listening, folded into one line (open it for the meaning, the sound, review).
    function prereadHTML() {
      const pr = m._prHidden ? [] : (m.preread || []);
      return pr.length ? `<details class="card sunk fold preread"><summary data-tap="listen-preread"><b class="small">读前先认识这 ${pr.length} 个词</b><span class="tiny muted">${pr.map(w => esc(w.word)).join(' · ')}</span></summary>
          <div class="stack-s"><div class="pr-list">${pr.map((w, k) => `<div class="pr"><button class="icon-btn" data-prsay="${k}" aria-label="朗读 ${esc(w.word)}">${ICON.speak}</button>
            <div><b>${esc(w.word)}</b> <span class="ph">${esc(w.phonetic)}</span><div class="tiny muted">${esc(w.meaning)}</div></div></div>`).join('')}</div>
          <div class="row"><button class="btn small primary" id="prAdd">全部加入复习</button><span class="muted tiny">加入后会在文章里标出来</span></div></div></details>` : '';
    }
    function modeTabs() {
      return `<div class="seg modes" role="tablist" aria-label="听的方式">${Object.entries(MODES).map(([k, l]) => `<button role="tab" data-mode="${k}" aria-selected="${st.mode === k}">${l}</button>`).join('')}</div>`;
    }
    function listenHead() { return modeTabs() + prereadHTML(); }
    function bindListenHead(stop) {
      pane.querySelectorAll('[data-mode]').forEach(b => b.onclick = () => { stop(); st.mode = b.dataset.mode; save('flow-next-listen-mode', st.mode); listen(); });
      const pr = m.preread || [];
      pane.querySelectorAll('[data-prsay]').forEach(b => b.onclick = () => { stop(); const w = pr[Number(b.dataset.prsay)]; CLIP.word({ text: w.word, audio: w.audio }); });
      const add = pane.querySelector('#prAdd');
      if (add) add.onclick = async () => {
        if (!S.user) return needLogin('登录后可以把这些词加入复习，按遗忘曲线安排。');
        add.disabled = true;
        try {
          const r = await api('/api/next/vocab/add', { pack: id, items: pr.map(w => ({ word: w.word, sentence: findContext(w.form, lines()) })) });
          toast(r.added ? `已加入 ${r.added} 个词，读的时候会标出来` : '这些词已经在复习里了');
          m.mine = (m.mine || []).concat(pr.map(w => ({ form: w.form, id: 0 })));
          m._prHidden = true; pane.querySelector('.preread').remove(); refreshHome().catch(() => {});
        } catch (e) { toast(e.message); add.disabled = false; }
      };
    }
    function wordDiff(target, typed) {  // same alignment as the server's compare_words
      const t = (target.toLowerCase().match(/[a-z]+(?:'[a-z]+)?/g) || []), h = (typed.toLowerCase().match(/[a-z]+(?:'[a-z]+)?/g) || []);
      const L = Array.from({ length: t.length + 1 }, () => new Array(h.length + 1).fill(0));
      for (let i = t.length - 1; i >= 0; i--) for (let j = h.length - 1; j >= 0; j--) L[i][j] = t[i] === h[j] ? L[i + 1][j + 1] + 1 : Math.max(L[i + 1][j], L[i][j + 1]);
      const out = []; let i = 0, j = 0;
      while (i < t.length) {
        if (j < h.length && t[i] === h[j]) { out.push({ w: t[i], ok: true }); i++; j++; }
        else if (j < h.length && L[i][j + 1] >= L[i + 1][j]) j++;
        else { out.push({ w: t[i], ok: false }); i++; }
      }
      return out;
    }
    const wordsHTML = ws => `<div class="wdiff">${ws.map(w => `<span class="${w.ok ? 'ok' : 'miss'}">${esc(w.w)}</span>`).join(' ')}</div>`;

    async function shadowMode() {
      const ls = lines(), nm = await narration(ls);
      pane.innerHTML = `${listenHead()}<p class="muted small">先点 ▶ 听原声，再点 ● 跟着读一遍（再点一次停止）。「对比」先放原声再放你的录音；${S.user ? '「AI 点评」会写出它听到的内容，并指出要改的地方。' : '登录后可以让 AI 点评。'}</p>
        <div class="lines">${ls.map((s, i) => `<div class="line sh" data-i="${i}"><div class="txt">${esc(s)}</div>
          <div class="sh-ctl"><button class="icon-btn" data-o="${i}" aria-label="听原声">${ICON.play.replace('<svg', '<svg fill="currentColor"')}</button>
            <button class="icon-btn rec" data-r="${i}" aria-label="录音"><span class="dot"></span></button>
            <button class="btn small" data-c="${i}" disabled>对比</button><button class="btn small" data-ai="${i}" disabled>✦ AI 点评</button></div>
          <div class="sh-out"></div></div>`).join('')}</div>
        <div class="section row between"><span></span><button class="btn" id="toRead">去读 →</button></div>`;
      const REC = { mr: null, blobs: {}, timer: 0, url: {} };
      const row = i => pane.querySelector(`.line[data-i="${i}"]`);
      const stop = () => { TTS.stop(); NAR.stop(); CLIP.stop(); if (REC.mr && REC.mr.state === 'recording') REC.mr.stop(); };
      const orig = (i, then) => { if (nm) NAR.play(nm.sentences[i].s, nm.sentences[i].e, null, then); else TTS.say(stripLabel(ls[i]), then); };
      async function record(i, btn) {
        if (REC.mr && REC.mr.state === 'recording') { REC.mr.stop(); return; }
        stop();
        if (!navigator.mediaDevices || !window.MediaRecorder) { toast('这个浏览器不支持录音，换 Safari 或 Chrome 试试'); return; }
        let stream;
        try { stream = await navigator.mediaDevices.getUserMedia({ audio: true }); } catch (e) { toast('没有拿到麦克风权限，可以在浏览器设置里打开'); return; }
        const type = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4'].find(t => MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported(t)) || '';
        const mr = new MediaRecorder(stream, type ? { mimeType: type } : undefined), chunks = [];
        REC.mr = mr;
        mr.ondataavailable = e => { if (e.data && e.data.size) chunks.push(e.data); };
        mr.onstop = () => {
          stream.getTracks().forEach(t => t.stop()); clearTimeout(REC.timer); btn.classList.remove('on'); btn.setAttribute('aria-label', '录音');
          if (!chunks.length) return;
          REC.blobs[i] = new Blob(chunks, { type: mr.mimeType || type || 'audio/webm' });
          if (REC.url[i]) URL.revokeObjectURL(REC.url[i]);
          REC.url[i] = URL.createObjectURL(REC.blobs[i]);
          row(i).querySelector('[data-c]').disabled = false; row(i).querySelector('[data-ai]').disabled = false;
        };
        mr.start(); btn.classList.add('on'); btn.setAttribute('aria-label', '停止录音');
        const secs = nm ? (nm.sentences[i].e - nm.sentences[i].s) * 2.2 + 2 : 12;
        REC.timer = setTimeout(() => { if (mr.state === 'recording') mr.stop(); }, Math.min(25, secs) * 1000);
      }
      function compare(i) { stop(); orig(i, () => { const a = new Audio(REC.url[i]); a.play().catch(() => {}); }); }
      async function aiCheck(i, btn) {
        if (!S.user) return needLogin('登录后，AI 会听你的跟读，指出漏读、读错和需要连读的地方。');
        const blob = REC.blobs[i]; if (!blob) return;
        if (blob.size > 1400000) { toast('录音太长了，读这一句就好'); return; }
        btn.disabled = true; btn.innerHTML = '<span class="spin"></span>';
        try {
          const data = await new Promise((ok, no) => { const r = new FileReader(); r.onload = () => ok(String(r.result).split(',')[1]); r.onerror = no; r.readAsDataURL(blob); });
          const mime = /mp4|m4a|aac/.test(blob.type) ? 'audio/mp4' : /ogg/.test(blob.type) ? 'audio/ogg' : 'audio/webm';
          const x = (await api('/api/next/shadow', { pack: id, i, audio: { mime_type: mime, data }, request_id: rid('sh') })).result;
          const flu = { smooth: '流畅', ok: '基本流畅', choppy: '有点断断续续' }[x.fluency];
          row(i).querySelector('.sh-out').innerHTML = `<div class="card flat sh-res stack-s enter">${wordsHTML(x.words)}
            <div class="tiny muted">AI 听到：${esc(x.transcript || '（没听清）')} · 读到 ${x.matched}/${x.words.length} 个词 · ${flu}</div>
            ${x.issues.map(it => `<div class="small"><b>${esc(it.word)}</b>：${esc(it.note)}</div>`).join('')}${x.tip ? `<div class="small tip">建议：${esc(x.tip)}</div>` : ''}</div>`;
        } catch (e) { toast(e.message); }
        btn.disabled = false; btn.textContent = '✦ AI 点评';
      }
      pane.querySelectorAll('[data-o]').forEach(b => b.onclick = () => { stop(); orig(Number(b.dataset.o)); });
      pane.querySelectorAll('[data-r]').forEach(b => b.onclick = () => record(Number(b.dataset.r), b));
      pane.querySelectorAll('[data-c]').forEach(b => b.onclick = () => compare(Number(b.dataset.c)));
      pane.querySelectorAll('[data-ai]').forEach(b => b.onclick = () => aiCheck(Number(b.dataset.ai), b));
      pane.querySelector('#toRead').onclick = () => { stop(); markStep('listen'); go('read'); };
      bindListenHead(stop);
    }

    async function dictateMode() {
      const ls = lines(), nm = await narration(ls);
      const score = m._dictScore || (m._dictScore = { got: 0, total: 0 });
      let i = Math.min(m._dictI || 0, ls.length - 1);
      const stop = () => { TTS.stop(); NAR.stop(); CLIP.stop(); };
      const play = slow => {
        stop(); const keep = TTS.rate; TTS.rate = slow ? 0.75 : keep;
        if (nm) NAR.play(nm.sentences[i].s, nm.sentences[i].e, null, null); else TTS.say(stripLabel(ls[i]));
        TTS.rate = keep;
      };
      function render() {
        pane.innerHTML = `${listenHead()}<div class="card flat dict stack"><div class="row between"><span class="kicker">听写 · 第 ${i + 1} / ${ls.length} 句</span>
            <span class="muted tiny">${score.total ? '这篇正确率 ' + Math.round(score.got / score.total * 100) + '%' : '可以反复播放'}</span></div>
          <div class="row"><button class="btn primary" id="dPlay">${ICON.play.replace('<svg', '<svg width="16" height="16" fill="currentColor"')}<span>播放这一句</span></button><button class="btn small" id="dSlow">慢速</button></div>
          <textarea id="dIn" rows="3" lang="en" enterkeyhint="done" placeholder="听到什么写什么，拼不出的词先空着" autocapitalize="off" autocomplete="off" autocorrect="off" spellcheck="false"></textarea>
          <div class="row"><button class="btn" id="dCheck">检查</button><button class="btn ghost" id="dSkip">跳过这句</button></div><div id="dOut"></div></div>
          <div class="section row between"><span class="muted small">听错的词可以直接加入复习。</span><button class="btn" id="toRead">去读 →</button></div>`;
        const inp = pane.querySelector('#dIn');
        pane.querySelector('#dPlay').onclick = () => { play(false); inp.focus({ preventScroll: true }); };
        pane.querySelector('#dSlow').onclick = () => play(true);
        const next = () => { i += 1; m._dictI = i; if (i >= ls.length) { m._dictI = 0; markStep('listen'); toast('这篇听写完了'); i = 0; } render(); play(false); };
        pane.querySelector('#dSkip').onclick = next;
        pane.querySelector('#dCheck').onclick = () => {
          const target = stripLabel(ls[i]), ws = wordDiff(target, inp.value), got = ws.filter(w => w.ok).length;
          score.got += got; score.total += ws.length;
          m._dictChecked = (m._dictChecked || 0) + 1; if (m._dictChecked >= 3) markStep('listen');
          if (S.user && ws.length) api('/api/next/skill', { kind: 'dictation', score: got / ws.length, pack: id }).catch(() => {});
          const missed = [...new Set(ws.filter(w => !w.ok).map(w => w.w))].filter(w => w.length > 3);
          pane.querySelector('#dOut').innerHTML = `<div class="stack-s enter">${wordsHTML(ws)}<div class="muted tiny">写对 ${got} / ${ws.length} 个词</div>
            <div class="row">${missed.length ? `<button class="btn small" id="dAdd">把听错的 ${missed.length} 个词加入复习</button>` : ''}<button class="btn small primary" id="dNext">${i + 1 < ls.length ? '下一句' : '完成'}</button></div></div>`;
          pane.querySelector('#dNext').onclick = next;
          const add = pane.querySelector('#dAdd');
          if (add) add.onclick = async () => {
            if (!S.user) return needLogin('登录后可以把听错的词加入复习。');
            add.disabled = true;
            try {
              const r = await api('/api/next/vocab/add', { pack: id, min_rank: 1500, items: missed.map(w => ({ word: w, sentence: target })) });
              const rest = missed.length - (r.added || 0);
              toast(r.added ? `已加入 ${r.added} 个词${rest ? `；另外 ${rest} 个是常用词或已在复习里` : ''}` : '这几个都是常用词（不用专门背），或已经在复习里了');
              add.textContent = r.added ? `已加入 ${r.added} 个` : '不用加';
            }
            catch (e) { toast(e.message); add.disabled = false; }
          };
        };
        inp.addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); pane.querySelector('#dCheck').click(); } });
        pane.querySelector('#toRead').onclick = () => { stop(); go('read'); };
        bindListenHead(stop);
      }
      render();
    }


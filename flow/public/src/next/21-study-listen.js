    /* listen: sentence list, word-by-word highlight while it plays */
    // Narration is usable when this material has the chosen voice and the shown text is the original.
    async function narration(ls) {
      const voices = (m.audio && m.audio.voices) || [];
      if (!voices.length || (m.variant && !st.showOriginal)) return null;
      // not recorded in the learner's voice: another of its recordings, for this text only (S.voice, the setting, stays)
      const ok = await NAR.load(id, voices.includes(S.voice) ? S.voice : voices[0], m.audio.version);
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
        document.querySelectorAll('#blind, #psBlind').forEach(bl => { bl.classList.remove('on'); bl.setAttribute('aria-pressed', 'false'); });  // 👁 is in the bar
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
      MINI.undock();  // 精听 docks it again below; 跟读 and 听写 have their own buttons
      const again = parts()[3] === 'again' && !!S.user;
      if (again && !st.againSet) { st.againSet = true; st.mode = 'listen'; st.blind = true; }
      if (st.mode === 'shadow') return shadowMode();
      if (st.mode === 'dictate') return dictateMode();
      const ls = lines();
      const nm = await narration(ls);
      const voices = (m.audio && m.audio.voices) || [];
      // The user's pick (语流 B9's design, 2026-11-25): 播放全文, 「AI 合成」, the speed and 👁 sit in the bar above the tabs
      // (MINI, docked), where the thumb is, and the text starts high on the first screen (B9's r36 audit F1: no row of tools
      // above the sentences); 播放设置 opens from 「1×」 as a sheet, with 「从头开始」 and 只听不看 at its top, playing or not;
      // the how-to is a first-use tip (08-tips.js).
      const rateL = r => `${r}×`;
      // 「AI 合成」 is said once, in the bar by the play button (the user, 2026-11-25: no second line); the browser's own
      // voice is not AI, and only this line says so
      // a recording this device cannot play (no AAC decoder): said here too, as the reason the text is read sentence by sentence
      const lead = voices.length && !NAR.aac ? (SV.on() ? '这台设备放不了录音的格式，改用 AI 朗读一句一句读。' : '这台设备放不了录音的格式，先用浏览器朗读。')
        : nm || SV.on() ? '' : '这篇还没有录音，先用浏览器朗读。';
      const hint = `点 👁 只听不看，点喇叭单句反复听${TOUCH ? '' : '；空格键播放 / 暂停'}。`;  // one line on SE (F1)
      pane.innerHTML = `${again ? relistenHTML() : ''}${modeTabs()}${prereadHTML()}
        <p class="tiny muted sv-prep" id="lsPrep" role="status" hidden></p>
        ${!nm && !TTS.can() ? '<p class="err">这个浏览器不支持朗读，可以直接去「读」。</p>' : ''}
        <p class="muted tiny listen-tip">${lead}</p>
        ${tipSlot('listen', hint)}
        <div class="lines">${ls.map((s, i) => `<div class="line" data-i="${i}"><button class="icon-btn" data-say="${i}" aria-label="播放第 ${i + 1} 句">${ICON.speak}</button><div class="txt ${st.blind ? 'blind' : ''}">${wordSpans(s, () => 'kw')}</div></div>`).join('')}</div>
        <div class="section row between"><span class="muted small">共 ${ls.length} 句${nm ? ' · ' + Math.round(nm.duration / 60 * 10) / 10 + ' 分钟' : ''}</span><button class="btn" id="toRead">听完了，去读 →</button></div>`;
      let shown = -1;
      const lineEl = i => pane.querySelector(`.line[data-i="${i}"]`);
      const setNow = i => pane.querySelectorAll('.line').forEach(el => { const on = Number(el.dataset.i) === i; el.classList.toggle('now', on); if (!on) el.querySelectorAll('.cur').forEach(x => x.classList.remove('cur')); });
      const light = (el, c) => { if (!el) return; if (c == null) el.querySelectorAll('.cur').forEach(x => x.classList.remove('cur')); else lightWord(el, c); };
      // 播放全文 (LONG, 01-audio-offline.js): 暂停 / 继续, and where it was left kept on this phone: 「从第 N 句继续」.
      // #playAll is the bar's button: its start label is painted here, its 暂停 / 继续 by the player (MINI.paint).
      const PKEY = 'listen:' + id;
      const setBtn = () => {
        const b = document.getElementById('playAll'), rs = document.getElementById('playRestart'), rb = MINI.el && MINI.el.querySelector('.speed-set');
        const r = LONG.of(PKEY), at = r ? r.i : PROG.at(PKEY, ls.length);
        if (rs) rs.hidden = !at;
        if (rb) rb.textContent = rateL(TTS.rate);
        if (!b || MINI.h) return;
        b.innerHTML = `${playIcon(false, 15)}<span>${at ? `从第 ${at + 1} 句继续` : '播放全文'}</span>`;
        b.setAttribute('aria-pressed', 'false');
      };
      const prepLine = note => { const p = pane.querySelector('#lsPrep'); if (p) { p.textContent = note || ''; p.hidden = !note; } };
      const stopAll = () => { loopTok++; clearTimeout(loopTimer); LONG.stop(); TTS.stop(); NAR.stop(); shown = -1; setNow(-1); MINI.hide(); setBtn(); };
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
      // one sentence: its part of the recording, else the server voice (the browser voice only when that cannot)
      const sayLine = (i, then) => {
        if (nm) { NAR.play(nm.sentences[i].s, nm.sentences[i].e, t => { const [si, wc] = NAR.locate(t); if (si === i) lightAt(lineEl(i), wc); }, then); return; }
        const el = lineEl(i); TTS.say(ls[i], then, c => lightWord(el, c), { pack: id, title: '语流 · ' + m.title });
      };
      // 语速 and 复读 set from outside (the iOS app's lock screen, NATIVE.takeKnobs): kept; the bar's 1× and an open 播放设置 follow
      const knobsShown = () => {
        setBtn();
        document.querySelectorAll('#sheet [data-rate]').forEach(x => x.setAttribute('aria-pressed', String(Number(x.dataset.rate) === TTS.rate)));
        document.querySelectorAll('#sheet [data-rep]').forEach(x => x.setAttribute('aria-pressed', String(Number(x.dataset.rep) === LOOP.rep)));
      };
      const readAll = (from, auto) => LONG.start({
        key: PKEY, texts: ls, nm, pack: id, title: m.title, loop: looping(), rep: () => LOOP.rep, gap: gapMs, label: i => `第 ${i + 1} / ${ls.length} 句`, auto: !!auto,
        setRep: n => { LOOP.rep = n; save('flow-next-loop', LOOP); }, onKnobs: knobsShown,
        onState: (state, i, note) => {
          setBtn(); prepLine(note);
          if (state === 'idle') { shown = -1; setNow(-1); return; }
          if (i !== shown) { shown = i; setNow(i); const el = lineEl(i); if (el && state !== 'paused') el.scrollIntoView({ block: 'center', behavior: REDUCED ? 'auto' : 'smooth' }); }
        },
        onWord: (i, c) => light(lineEl(i), c),
        onDone: () => markStep('listen'),
      }, from);
      const playAll = () => {
        if (LONG.of(PKEY)) { LONG.toggle(); return; }
        loopTok++; clearTimeout(loopTimer);  // a sentence repeating
        readAll(PROG.at(PKEY, ls.length));
      };
      // 播放设置 from 「1×」: 语速, 复读 (times, the pause after), 声音; it takes effect at once, also on what is playing
      // 盲听 (只听不看): the bar's 👁, the switch in 播放设置, and the sentences, kept in step
      const setBlind = on => {
        st.blind = on; pane.querySelectorAll('.txt').forEach(t => t.classList.toggle('blind', on));
        document.querySelectorAll('#blind, #psBlind').forEach(b => { b.classList.toggle('on', on); b.setAttribute('aria-pressed', String(on)); });
        toast(on ? '盲听：只听不看，再点一次显示原文' : '已显示原文');
      };
      const playsetHTML = () => `<div class="stack"><h2 class="h2" id="sheetTitle">播放设置</h2>
        <div class="row between ps-top"><button class="chip small${st.blind ? ' on' : ''}" type="button" id="psBlind" aria-pressed="${st.blind}">${ICON.eye}<span>只听不看</span></button>
          <button class="btn small" type="button" id="playRestart"${PROG.at(PKEY, ls.length) || LONG.of(PKEY) ? '' : ' hidden'}>从头开始</button></div>
        <div class="loopbar">
          <div class="lg" role="group" aria-label="语速"><span class="tiny muted">语速</span>${[0.75, 1, 1.25].map(r => `<button class="chip small" type="button" data-rate="${r}" aria-pressed="${TTS.rate === r}">${r}×</button>`).join('')}</div>
          <div class="lg" role="group" aria-label="复读：每句几遍"><span class="tiny muted">每句</span>${[[1, '1 遍'], [3, '3 遍'], [5, '5 遍'], [0, '循环']].map(([n, l]) => `<button class="chip small" type="button" data-rep="${n}" aria-pressed="${LOOP.rep === n}">${l}</button>`).join('')}</div>
          <div class="lg" role="group" aria-label="复读：句后停顿"><span class="tiny muted">句后</span>${[[0, '不停'], [2, '停 2 秒'], [-1, '留时间跟说']].map(([n, l]) => `<button class="chip small" type="button" data-gap="${n}" aria-pressed="${LOOP.gap === n}">${l}</button>`).join('')}</div>
          ${voices.length ? `<div class="lg"><span class="tiny muted">声音</span>${voiceChips(voices)}</div>` : ''}</div>
        <button class="btn block" type="button" id="psDone" data-close>好</button></div>`;
      const openPlayset = () => openSheet(playsetHTML(), card => {
        card.querySelector('#psBlind').onclick = () => setBlind(!st.blind);
        card.querySelector('#playRestart').onclick = () => { closeSheet(); LONG.stop(); PROG.clear(PKEY); readAll(0); };
        card.querySelectorAll('[data-rep], [data-gap]').forEach(b => b.onclick = () => {
          const k = 'rep' in b.dataset ? 'rep' : 'gap'; LOOP[k] = Number(b.dataset[k]); save('flow-next-loop', LOOP);
          NATIVE.retune();  // the app playing it gets the new 复读 at once
          card.querySelectorAll(`[data-${k}]`).forEach(x => x.setAttribute('aria-pressed', String(x === b)));
        });
        card.querySelectorAll('[data-rate]').forEach(b => b.onclick = () => {
          TTS.rate = Number(b.dataset.rate); save('flow-next-rate', TTS.rate); NAR.audio.playbackRate = TTS.rate; NATIVE.retune();
          card.querySelectorAll('[data-rate]').forEach(x => x.setAttribute('aria-pressed', String(x === b))); setBtn();
        });
        card.querySelectorAll('[data-voice]').forEach(b => b.onclick = async () => { if (b.disabled) return; closeSheet(); stopAll(); await setVoice(b.dataset.voice); listen(); toast('已切换为' + VOICE_LABELS[b.dataset.voice]); });
      });
      // attach: the app plays this text (语流's iOS app, loaded again): the bar becomes its player (NATIVE.adopt)
      MINI.dock({ key: PKEY, ai: () => !!nm || SV.on(), paint: setBtn, play: playAll, rate: openPlayset, attach: () => readAll(PROG.at(PKEY, ls.length), true),
        blind: { on: () => st.blind, toggle: () => setBlind(!st.blind) } });
      setBtn();
      NATIVE.follow(PKEY, setBtn);  // in the app: the button says where the app got to (it may have played on, or still plays)
      pane.querySelectorAll('[data-say]').forEach(b => b.onclick = () => {
        const i = Number(b.dataset.say); stopAll(); setNow(i);
        if (looping()) MINI.show(`复读第 ${i + 1} 句`, { stop: stopAll, ai: !!nm || SV.on() });  // a stop button on screen while it repeats
        sayRepeated(i, () => { setNow(-1); MINI.hide(); });
      });
      pane.querySelectorAll('.line .txt').forEach((t, i) => t.onclick = e => { if (e.target.dataset.w && !st.blind) lookupSheet(e.target.dataset.w, ls[i], id); });
      pane.querySelector('#toRead').onclick = () => { stopAll(); markStep('listen'); go('read'); };
      if (again) bindRelisten();
      bindListenHead(stopAll);
      document.onkeydown = e => {
        if (isTyping(e) || !sheetEl.hidden || e.metaKey || e.ctrlKey || e.altKey) return;
        const b = document.getElementById('playAll'); if (b && (e.key === ' ' || e.key === 'k')) { e.preventDefault(); b.click(); }
      };
    }

    /* listen modes: 精听 (sentence list) · 跟读 (record, compare, AI feedback) · 听写 (type what you hear) */
    const MODES = { listen: '精听', shadow: '跟读', dictate: '听写' };
    if (!st.mode) st.mode = MODES[load('flow-next-listen-mode')] ? load('flow-next-listen-mode') : 'listen';
    const stripLabel = s => s.replace(/^[A-Z][a-z]+(?: [A-Z][a-z]+)?:\s+/, '');
    // The words worth knowing before listening, folded into one line (open it for the meaning, the sound, review).
    function prereadHTML() {
      const pr = m._prHidden ? [] : (m.preread || []);
      return pr.length ? `<details class="fold preread"><summary data-tap="listen-preread"><b class="small">读前先认识这 ${pr.length} 个词</b><span class="tiny muted">${pr.map(w => esc(w.word)).join(' · ')}</span></summary>
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

    // 发音分 of 跟读: accuracy and fluency are the AI's estimate from the recording, completeness is counted from what it
    // heard (next_service.pron_score). Each sentence's latest score stays on its row while the material is open.
    const shScores = m._shScores || (m._shScores = {});
    function shAvgHTML() {
      const v = Object.values(shScores);
      return `<p class="tiny muted" id="shAvg"${v.length ? '' : ' hidden'}>${v.length ? `这篇已经点评 ${v.length} 句，发音分平均 ${Math.round(v.reduce((a, b) => a + b, 0) / v.length)}（AI 估计）` : ''}</p>`;
    }
    function pronHTML(x) {
      const sc = x.score;
      if (!sc) return x.matched ? '' : '<div class="small err">AI 没听清这一句。离麦克风近一点，完整读一遍再点评。</div>';
      const bar = (l, v, txt) => `<div class="ab"><span class="nm">${l}</span><span class="vbar"><i data-w="${v}"></i></span><span class="lv">${txt == null ? v : txt}</span></div>`;
      return `<div class="pron"><div class="pron-top"><b class="pron-n">${sc.total}</b><span class="stack-xs"><b>发音分</b></span></div>
          <div class="ab-list">${bar('准确', sc.accuracy)}${bar('流利', sc.fluency)}${bar('完整', sc.complete, `${x.matched}/${x.words.length}`)}</div></div>`;
    }
    function soundsHTML(ss) {
      return ss && ss.length ? `<div class="stack-s"><b class="small">要练的音</b>${ss.map(s => `<div class="snd small"><b class="ph">${esc(s.sound)}</b>
          <span><b>${esc(s.word)}</b>：${esc(s.note)}${s.set ? ` <a class="link" href="#/sounds/${encodeURIComponent(s.set)}" data-tap="shadow-sound">去练 ${esc(s.set_title)} →</a>` : ''}</span></div>`).join('')}</div>` : '';
    }
    async function shadowMode() {
      const ls = lines(), nm = await narration(ls);
      // Every sentence keeps its ▶; the recording tools (●, 对比, AI 点评) show under the sentence being practised only,
      // so eleven rows of four buttons do not bury the text. A tap anywhere on a sentence makes it the one.
      pane.innerHTML = `${listenHead()}<p class="muted small">${nm || SV.on() ? aiVoiceNote('朗读由 AI 合成。', 'span', 'in') : ''}点一句开始练：先点 ▶ 听原声，再点 ● 跟着读一遍（再点一次停止）。「对比」先放原声再放你的录音；${S.user ? '「AI 点评」给一个发音分（AI 估计），写出它听到的内容和要练的音。' : '登录后可以让 AI 点评、给发音分。'}</p>
        ${shAvgHTML()}
        <div class="lines">${ls.map((s, i) => `<div class="line sh${i === 0 ? ' cur' : ''}" data-i="${i}"><div class="txt">${esc(s)}</div>
          <div class="sh-ctl"><button class="icon-btn" data-o="${i}" aria-label="听原声">${ICON.play.replace('<svg', '<svg fill="currentColor"')}</button>
            <button class="icon-btn rec" data-r="${i}" aria-label="录音"><span class="dot"></span></button>
            <button class="btn small" data-c="${i}" disabled>对比</button><button class="btn small" data-ai="${i}" disabled>✦ AI 点评</button>${shScores[i] != null ? `<span class="pron-chip" data-sc="${i}" title="这一句的发音分（AI 估计）">${shScores[i]}</span>` : `<span class="pron-chip" data-sc="${i}" hidden></span>`}</div>
          <div class="sh-out"></div></div>`).join('')}</div>
        <div class="section row between"><span></span><button class="btn" id="toRead">去读 →</button></div>`;
      const REC = { mr: null, blobs: {}, timer: 0, url: {} };
      const row = i => pane.querySelector(`.line[data-i="${i}"]`);
      pane.querySelectorAll('.line.sh').forEach(l => l.addEventListener('click', () => {
        if (l.classList.contains('cur')) return;
        pane.querySelectorAll('.line.sh.cur').forEach(x => x.classList.remove('cur')); l.classList.add('cur');
      }, true));  // capture: a tap on ▶ of another sentence plays it and makes it the one
      const stop = () => { TTS.stop(); NAR.stop(); CLIP.stop(); if (REC.mr && REC.mr.state === 'recording') REC.mr.stop(); };
      const orig = (i, then) => { if (nm) NAR.play(nm.sentences[i].s, nm.sentences[i].e, null, then); else TTS.say(stripLabel(ls[i]), then, null, { pack: id }); };
      async function record(i, btn) {
        if (REC.mr && REC.mr.state === 'recording') { REC.mr.stop(); return; }
        if (!micReady(() => record(i, btn))) return;
        stop();
        let stream;
        try { stream = await micOpen(); } catch (e) { toast(e.message); return; }  // 70-learner.js: open only while recording
        const type = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4'].find(t => MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported(t)) || '';
        const mr = recorderFor(stream, type ? { mimeType: type } : undefined, 25), chunks = [];  // the app's cap; the timer below stops it sooner
        REC.mr = mr;
        mr.ondataavailable = e => { if (e.data && e.data.size) chunks.push(e.data); };
        mr.onstop = () => {
          micClose(stream); clearTimeout(REC.timer); btn.classList.remove('on'); btn.setAttribute('aria-label', '录音');
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
      function compare(i) { stop(); orig(i, () => CLIP.mine(REC.url[i])); }
      async function aiCheck(i, btn) {
        if (!S.user) return needLogin('登录后，AI 会听你的跟读，指出漏读、读错和需要连读的地方。');
        const blob = REC.blobs[i]; if (!blob) return;
        if (blob.size > 1400000) { toast('录音太长了，读这一句就好'); return; }
        btn.disabled = true; btn.innerHTML = '<span class="spin"></span>';
        try {
          const data = await new Promise((ok, no) => { const r = new FileReader(); r.onload = () => ok(String(r.result).split(',')[1]); r.onerror = no; r.readAsDataURL(blob); });
          const mime = /wav/.test(blob.type) ? 'audio/wav' : /mp4|m4a|aac/.test(blob.type) ? 'audio/mp4' : /ogg/.test(blob.type) ? 'audio/ogg' : 'audio/webm';  // wav: 语流's iOS app
          const x = (await api('/api/next/shadow', { pack: id, i, audio: { mime_type: mime, data }, request_id: rid('sh') })).result;
          const flu = { smooth: '流畅', ok: '基本流畅', choppy: '有点断断续续' }[x.fluency];
          const out = row(i).querySelector('.sh-out');
          out.innerHTML = `<div class="card flat sh-res stack-s enter">${aiMark('发音分和点评由 AI 估计，仅供参考')}${pronHTML(x)}${soundsHTML(x.sounds)}
            ${x.issues.length ? `<div class="stack-s"><b class="small">${x.sounds && x.sounds.length ? '其他要注意的' : '要注意的'}</b>${x.issues.map(it => `<div class="small"><b>${esc(it.word)}</b>：${esc(it.note)}</div>`).join('')}</div>` : ''}
            ${x.tip ? `<div class="small tip">建议：${esc(x.tip)}</div>` : ''}
            <div class="stack-xs">${wordsHTML(x.words)}<div class="tiny muted">AI 听到：${esc(x.transcript || '（没听清）')} · 读到 ${x.matched}/${x.words.length} 个词${x.score ? '' : ' · ' + flu}</div></div></div>`;
          requestAnimationFrame(() => requestAnimationFrame(() => out.querySelectorAll('.vbar i').forEach(b => { b.style.width = b.dataset.w + '%'; })));
          if (x.score) {
            shScores[i] = x.score.total;
            const chip = row(i).querySelector('[data-sc]'); chip.textContent = x.score.total; chip.hidden = false;
            const avg = pane.querySelector('#shAvg'); if (avg) avg.outerHTML = shAvgHTML();
          }
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
        if (nm) NAR.play(nm.sentences[i].s, nm.sentences[i].e, null, null); else TTS.say(stripLabel(ls[i]), null, null, { pack: id });
        TTS.rate = keep;
      };
      function render() {
        pane.innerHTML = `${listenHead()}<div class="card flat dict stack"><div class="row between"><span class="kicker">听写 · 第 ${i + 1} / ${ls.length} 句</span>
            <span class="muted tiny">${score.total ? '这篇正确率 ' + Math.round(score.got / score.total * 100) + '%' : '可以反复播放'}</span></div>
          <div class="row"><button class="btn primary" id="dPlay">${ICON.play.replace('<svg', '<svg width="16" height="16" fill="currentColor"')}<span>播放这一句</span></button><button class="btn small" id="dSlow">慢速</button>${nm || SV.on() ? aiVoiceNote('AI 合成', 'span') : ''}</div>
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


  /* ---------- learner model: ability profile, daily path, level suggestion ---------- */
  const LV_W = { A2: 25, B1: 50, B2: 75, C1: 100 };
  // Practice evidence of the last 45 days, skill by skill: shown folded at the foot of the ability radar.
  function abilityHTML(ab) {
    const ev = s => s.id === 'vocab' ? (s.size ? `词汇量约 ${s.size.toLocaleString()}` : (s.count ? `已掌握 ${s.count} 词` : '做一次词汇量测试'))
      : s.id === 'grammar' ? (s.count ? `${s.count} 个知识点用对或做对${s.watch ? ` · ${s.watch} 个要留意` : ''}` : '读和写的时候会点亮')
      : s.count ? `${s.count} 次练习 · 平均 ${Math.round((s.avg || 0) * 100)}%` : '还没练过';
    return `<div class="ab-list" id="ability">${ab.skills.map(s => `<div class="ab ${s.level ? '' : 'none'}"><span class="nm">${esc(s.label)}</span><span class="vbar"><i data-w="${s.level ? LV_W[s.level] : 3}"></i></span>
        <span class="lv">${s.level || '—'}</span><span class="tiny muted ev">${esc(ev(s))}</span></div>`).join('')}</div>
      <p class="muted small">不用专门测：做理解题、听写、跟读和写作时自动记下。做一次测评会更准。</p>`;
  }
  function suggestHTML(sg) {
    return sg ? `<div class="card sunk section suggest row between"><div class="small">${esc(sg.reason)}</div>
      <div class="row"><button class="btn small primary" id="sgYes" data-tap="notice-level">换到 ${esc(sg.to)}</button><button class="btn small ghost" id="sgNo">先不用</button></div></div>` : '';
  }
  function bindSuggest(h, after) {
    const y = document.getElementById('sgYes'), n = document.getElementById('sgNo');
    if (y) y.onclick = async () => { try { await api('/api/next/profile', { ...h.profile, level: h.suggest.to }); toast('已换到 ' + h.suggest.to + '，推荐会跟着变'); await refreshHome(); S.homeFresh = true; route(); } catch (e) { toast(e.message); } };
    if (n) n.onclick = () => { save('flow-next-suggest-skip', Date.now()); if (after) after(); else n.closest('.suggest').remove(); };
  }

  /* ---------- the microphone is open only while a recording runs ----------
     While it is open an iPhone sends every sound to the earpiece, quietly (the audio session turns to play-and-record),
     so each recorder takes it with micOpen() at the tap and lets go with micClose() the moment the recording ends: the
     examiner and the AI then speak through the loudspeaker again. The first time on a device a short sheet says why the
     microphone is asked for; a home-screen app on an iPhone asks again after every launch (an iOS rule, not ours). */
  const MIC_SEEN = 'flow-mic-explained', MIC_HOW = '打开方法见操作指南「常见问题」里的「录音、跟读用不了？」';
  function micSession(type) {  // tells iOS (16.4+) what the page does, so sound leaves the earpiece once recording ends
    try {
      if (typeof AUDIO !== 'undefined' && AUDIO && typeof AUDIO.session === 'function') AUDIO.session(type);  // 语流 11's helper (01-audio-offline.js), once it is in
      else if (navigator.audioSession && 'type' in navigator.audioSession) navigator.audioSession.type = type;
    } catch (e) { /* older iOS, other browsers: nothing to switch */ }
  }
  function micReady(go) {  // true: record now; false: the sheet is up, and its button calls go() (a fresh tap, which iPhones and WeChat need)
    let seen = true;
    try { seen = localStorage.getItem(MIC_SEEN) === '1'; } catch (e) { /* storage blocked: do not ask every time */ }
    if (seen) return true;
    openSheet(`<div class="stack"><h2 class="h2" id="sheetTitle">要用一下麦克风</h2>
      <p class="small">说出来的回答要录音。麦克风只在你点 ● 以后、说话的这几秒打开，说完马上关；录音只在批改时发给 AI，服务器上不留。</p>
      <p class="small muted">接下来手机会问能不能用麦克风，请选「允许」。放在 iPhone 主屏上的语流，每次重新打开后第一次录音，系统都会再问一次，这是 iOS 的规定。</p>
      <div class="row"><button class="btn primary" id="micGo" type="button">好，开始录音</button><button class="btn ghost" type="button" data-close>先不用</button></div></div>`, card => {
      card.querySelector('#micGo').onclick = () => { try { localStorage.setItem(MIC_SEEN, '1'); } catch (e) { /* asked again next time */ } closeSheet(); go(); };
    });
    return false;
  }
  async function micOpen() {  // the stream; throws an Error whose message is for the learner
    if (!navigator.mediaDevices || !window.MediaRecorder) throw new Error('这个浏览器不支持录音，换 Safari 或 Chrome 试试');
    micSession('play-and-record');
    try { return await navigator.mediaDevices.getUserMedia({ audio: true }); }
    catch (e) { micSession('playback'); throw new Error('没有拿到麦克风权限，' + MIC_HOW); }
  }
  function micClose(stream) {
    if (stream) stream.getTracks().forEach(t => t.stop());
    micSession('playback');
  }

  /* ---------- 16 kHz WAV for the 发音 check: prepared, off until the server says say_wav ----------
     A pronunciation scorer (Aliyun's, which 语流 12 is trying) takes 16000 Hz, mono, 16-bit PCM in a WAV file, not the
     browser's own opus or AAC. Web Audio gives the microphone at the device rate (44100 or 48000 Hz); each 1/16000 s here
     is the average of the samples it covers (a plain low-pass, enough for speech), and the file header is written here.
     ScriptProcessor rather than an AudioWorklet: a worklet needs a script file of its own under this page's rules, and
     every browser we serve still runs ScriptProcessor. Anything missing (no Web Audio, the context refuses the stream)
     falls back to MediaRecorder as before. On when /api/session says say_wav (FLOW_SAY_WAV=1 on the server), or in one
     browser with localStorage flow-say-wav=1, for a test. */
  const WAV16 = {
    RATE: 16000,
    on() {
      try { if (localStorage.getItem('flow-say-wav') === '1') return true; } catch (e) { /* storage blocked: the server decides */ }
      return !!(S.home && S.home.session && S.home.session.say_wav);
    },
    context() {  // made at the tap (before the microphone is asked for), so an iPhone lets it run
      const AC = window.AudioContext || window.webkitAudioContext;
      try { return AC ? new AC() : null; } catch (e) { return null; }
    },
    encode(chunks, rate) {  // Float32 chunks at `rate` → a WAV blob at 16000 Hz, or null when nothing was heard
      chunks = chunks.filter(c => c && c.length);
      const n = chunks.reduce((a, c) => a + c.length, 0), step = rate / this.RATE, out = Math.floor(n / step);
      if (!out) return null;
      const v = new DataView(new ArrayBuffer(44 + out * 2)), tag = (o, s) => { for (let i = 0; i < 4; i++) v.setUint8(o + i, s.charCodeAt(i)); };
      tag(0, 'RIFF'); v.setUint32(4, 36 + out * 2, true); tag(8, 'WAVE'); tag(12, 'fmt '); v.setUint32(16, 16, true);
      v.setUint16(20, 1, true); v.setUint16(22, 1, true); v.setUint32(24, this.RATE, true); v.setUint32(28, this.RATE * 2, true);
      v.setUint16(32, 2, true); v.setUint16(34, 16, true); tag(36, 'data'); v.setUint32(40, out * 2, true);
      let ci = 0, cj = 0, pos = 0, last = 0;
      for (let k = 0; k < out; k++) {
        const end = Math.min(n, Math.round((k + 1) * step));
        let sum = 0, cnt = 0;
        while (pos < end) { sum += chunks[ci][cj]; cnt++; pos++; if (++cj >= chunks[ci].length) { ci++; cj = 0; } }
        const s = Math.max(-1, Math.min(1, cnt ? sum / cnt : last));  // a device slower than 16 kHz: the sample repeats
        last = s;
        v.setInt16(44 + k * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
      }
      return new Blob([v.buffer], { type: 'audio/wav' });
    },
    recorder(stream, ctx) {  // a MediaRecorder stand-in: start(), stop(), state; ondataavailable gets the WAV, then onstop
      const src = ctx.createMediaStreamSource(stream), proc = ctx.createScriptProcessor(4096, 1, 1), chunks = [];
      const r = {
        state: 'inactive', mimeType: 'audio/wav', ondataavailable: null, onstop: null,
        start() {
          proc.onaudioprocess = e => chunks.push(new Float32Array(e.inputBuffer.getChannelData(0)));
          src.connect(proc); proc.connect(ctx.destination);  // the output stays silent; Chrome only runs a connected node
          r.state = 'recording';
          if (ctx.state === 'suspended' && ctx.resume) ctx.resume().catch(() => { /* stays silent: nothing heard, nothing sent */ });
        },
        stop() {
          if (r.state !== 'recording') return;
          r.state = 'inactive'; proc.onaudioprocess = null;
          try { src.disconnect(); proc.disconnect(); } catch (e) { /* already apart */ }
          const blob = WAV16.encode(chunks, ctx.sampleRate);
          WAV16.close(ctx);
          if (blob && r.ondataavailable) r.ondataavailable({ data: blob });
          if (r.onstop) r.onstop();
        },
      };
      return r;
    },
    close(ctx) { try { const p = ctx && ctx.close && ctx.close(); if (p && p.catch) p.catch(() => {}); } catch (e) { /* closed */ } },
  };

  /* ---------- microphone: one spoken answer, sent to the AI as {mime_type, data} ----------
     opts.wav: this recording is for the 发音 check, so it is made as a 16 kHz WAV when WAV16 is on. */
  const MIC = {
    mr: null, timer: 0,
    busy() { return !!(this.mr && this.mr.state === 'recording'); },
    stop() { if (this.busy()) this.mr.stop(); },
    async toggle(btn, maxSecs, onDone, opts) {
      if (this.busy()) { this.mr.stop(); return; }
      if (!micReady(() => this.toggle(btn, maxSecs, onDone, opts))) return;
      TTS.stop(); NAR.stop(); CLIP.stop();
      const ctx = opts && opts.wav && WAV16.on() ? WAV16.context() : null;
      let stream;
      try { stream = await micOpen(); } catch (e) { WAV16.close(ctx); toast(e.message); return; }
      const type = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4'].find(t => MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported(t)) || '';
      let mr = null;
      if (ctx) try { mr = WAV16.recorder(stream, ctx); } catch (e) { WAV16.close(ctx); }
      if (!mr) mr = new MediaRecorder(stream, type ? { mimeType: type } : undefined);
      const chunks = [];
      this.mr = mr;
      mr.ondataavailable = e => { if (e.data && e.data.size) chunks.push(e.data); };
      mr.onstop = () => {
        micClose(stream); clearTimeout(this.timer); btn.classList.remove('on');
        if (chunks.length) onDone(new Blob(chunks, { type: mr.mimeType || type || 'audio/webm' }));
      };
      mr.start(); btn.classList.add('on');
      this.timer = setTimeout(() => this.stop(), maxSecs * 1000);
    },
    async payload(blob) {
      if (blob.size > 1400000) throw new Error('录音太长了，缩短一点再试');
      const data = await new Promise((ok, no) => { const r = new FileReader(); r.onload = () => ok(String(r.result).split(',')[1]); r.onerror = no; r.readAsDataURL(blob); });
      return { mime_type: /wav/.test(blob.type) ? 'audio/wav' : /mp4|m4a|aac/.test(blob.type) ? 'audio/mp4' : /ogg/.test(blob.type) ? 'audio/ogg' : 'audio/webm', data };
    },
  };
  const recBtn = (id, label) => `<button class="icon-btn rec" id="${id}" type="button" aria-label="${label || '录音'}"><span class="dot"></span></button>`;
  const fixesHTML = fs => fs && fs.length ? `<div class="stack-s">${fs.map(f => `<div class="change"><span class="ft"><del>${esc(f.from)}</del> → <ins>${esc(f.to)}</ins></span><span class="why">${esc(f.why)}</span></div>`).join('')}
    <div class="tiny muted">这些已经放进错题本，会按遗忘曲线回来让你再改一次。</div></div>` : '';


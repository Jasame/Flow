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
      <p class="small muted">接下来手机会问能不能用麦克风，请选「允许」。${APP_REC() ? '在语流 App 里只问这一次。' : '放在 iPhone 主屏上的语流，每次重新打开后第一次录音，系统都会再问一次，这是 iOS 的规定。'}</p>
      <div class="row"><button class="btn primary" id="micGo" type="button">好，开始录音</button><button class="btn ghost" type="button" data-close>先不用</button></div></div>`, card => {
      card.querySelector('#micGo').onclick = () => { try { localStorage.setItem(MIC_SEEN, '1'); } catch (e) { /* asked again next time */ } closeSheet(); go(); };
    });
    return false;
  }
  // In 语流's iOS app the app records (16 kHz mono; WAV, or AAC past 40 s so it stays under 1.4 MB): micOpen() gives a stand-in stream after iOS's
  // own question, and recorderFor() a stand-in MediaRecorder the three recorders use as before (ios/README.md).
  const APP_REC = () => !!(window.FlowApp && FlowApp.has && FlowApp.has('rec'));
  // where the microphone is turned on, by platform (docs/native-bridge.md, section 1)
  const APP_MIC = { ios: ' iPhone 的「设置 → 语流 → 麦克风」', android: '手机的「设置 → 应用 → 语流 → 权限 → 麦克风」',
    windows: ' Windows 的「设置 → 隐私和安全性 → 麦克风」', macos: ' Mac 的「系统设置 → 隐私与安全性 → 麦克风」' };
  class AppRecorder {
    constructor(max) { this.max = max || 120; this.state = 'inactive'; this.mimeType = ''; this.ondataavailable = null; this.onstop = null; this.off = null; }
    start() {
      this.state = 'recording';
      FlowApp.rec.start({ max: this.max }).then(x => {
        if (x && x.ok) { this.mimeType = x.format === 'm4a' ? 'audio/mp4' : 'audio/wav'; return; }
        toast((x && x.message) || '录音没能开始'); this.done(null);
      }, () => this.done(null));
      this.off = FlowApp.on('rec', d => { if (d.state === 'done' || d.state === 'cut') this.stop(); });  // max reached, or a call
    }
    stop() {
      if (this.state !== 'recording') return;
      this.state = 'stopping';
      FlowApp.rec.stop().then(x => this.done(x && x.ok ? x : null), () => this.done(null));
    }
    done(x) {
      if (this.off) { this.off(); this.off = null; }
      this.state = 'inactive';
      if (x) {
        this.mimeType = x.mime_type;
        const bin = atob(x.data), bytes = new Uint8Array(bin.length);
        for (let k = 0; k < bin.length; k++) bytes[k] = bin.charCodeAt(k);
        if (this.ondataavailable) this.ondataavailable({ data: new Blob([bytes], { type: x.mime_type }) });
      }
      if (this.onstop) this.onstop();
    }
  }
  function recorderFor(stream, opts, maxSecs) { return stream && stream.app ? new AppRecorder(maxSecs) : new MediaRecorder(stream, opts); }
  async function micOpen() {  // the stream; throws an Error whose message is for the learner
    if (APP_REC()) {  // asked inside the tap, as with getUserMedia
      if (!(await FlowApp.rec.ask())) throw new Error('没有拿到麦克风权限，到' + (APP_MIC[FlowApp.platform] || APP_MIC.ios) + '打开');
      LONG.other();
      return { app: true, getTracks: () => [] };
    }
    if (!navigator.mediaDevices || !window.MediaRecorder) throw new Error('这个浏览器不支持录音，换 Safari 或 Chrome 试试');
    micSession('play-and-record');
    try { return await navigator.mediaDevices.getUserMedia({ audio: true }); }
    catch (e) { micSession('playback'); throw new Error('没有拿到麦克风权限，' + MIC_HOW); }
  }
  function micClose(stream) {
    if (stream) stream.getTracks().forEach(t => t.stop());
    micSession('playback');
  }

  /* ---------- microphone: one spoken answer, sent to the AI as {mime_type, data} ---------- */
  const MIC = {
    mr: null, timer: 0,
    busy() { return !!(this.mr && this.mr.state === 'recording'); },
    stop() { if (this.busy()) this.mr.stop(); },
    async toggle(btn, maxSecs, onDone) {
      if (this.busy()) { this.mr.stop(); return; }
      if (!micReady(() => this.toggle(btn, maxSecs, onDone))) return;
      LONG.other(); TTS.stop(); NAR.stop(); CLIP.stop();  // a whole text being read waits, paused where it was
      let stream;
      try { stream = await micOpen(); } catch (e) { toast(e.message); return; }
      const type = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4'].find(t => MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported(t)) || '';
      const mr = recorderFor(stream, type ? { mimeType: type } : undefined, maxSecs), chunks = [];
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


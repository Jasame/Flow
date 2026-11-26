  /* ---------- learner model: ability profile, daily path, level suggestion ---------- */
  const LV_W = { A2: 25, B1: 50, B2: 75, C1: 100 };
  // Practice evidence of the last 45 days, skill by skill: shown folded at the foot of the ability radar.
  function abilityHTML(ab) {
    const ev = s => s.id === 'vocab' ? (s.size ? `词汇量约 ${s.size.toLocaleString()}` : (s.count ? `已掌握 ${s.count} 词` : '测一次词汇量'))
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
      <p class="small">说出来的回答要录音。麦克风只在你点录音键以后、说话的这几秒打开，说完马上关；录音只在批改时发给 AI，服务器上不留。</p>
      <p class="small muted">接下来系统会问能不能用麦克风，请选「允许」。${APP_REC() ? '在语流 App 里只问这一次。' : '放在 iPhone 主屏上的语流，每次重新打开后第一次录音，系统都会再问一次，这是 iOS 的规定。'}</p>
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
    harmony: '手机的「设置 → 应用和元服务 → 语流 → 麦克风」',  // HarmonyOS 5 (语流 C4, checked on its 5.0.1 emulator)
    windows: ' Windows 的「设置 → 隐私和安全性 → 麦克风」', macos: ' Mac 的「系统设置 → 隐私与安全性 → 麦克风」' };
  const APP_MIC_ANY = '系统设置里找到语流，把麦克风';  // a platform not listed: no other system's path
  class AppRecorder {
    constructor(max) { this.max = max || 120; this.state = 'inactive'; this.mimeType = ''; this.ondataavailable = null; this.onstop = null; this.off = null; }
    start() {
      this.state = 'recording';
      FlowApp.rec.start({ max: this.max }).then(x => {
        if (x && x.ok) { this.mimeType = x.format === 'm4a' ? 'audio/mp4' : 'audio/wav'; return; }
        toast((x && x.message) || '录音没能开始'); this.done(null);
      }, () => this.done(null));
      this.off = FlowApp.on('rec', d => {  // max reached, or cut short (a call, the app left): what was said is kept
        if (d.state === 'cut') toast('录音被打断了，已经说的这段先用上');
        if (d.state === 'done' || d.state === 'cut') this.stop();
      });
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
      if (!(await FlowApp.rec.ask())) throw new Error('没有拿到麦克风权限，到' + (APP_MIC[FlowApp.platform] || APP_MIC_ANY) + '打开');
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
    if (!(stream && stream.app)) micSession('playback');  // in the app its own audio session is the app's (B3's review of #152, 8)
  }

  /* ---------- microphone: one spoken answer, sent to the AI as {mime_type, data} ---------- */
  const MIC = {
    mr: null, timer: 0,
    MAX: 1400000, FULL: 1340000,  // bytes a recording may be (base64 1.87 MB, under the server's 2.2 MB: app.py AUDIO_PATHS); a long one stops at FULL
    busy() { return !!(this.mr && this.mr.state === 'recording'); },
    stop() { if (this.busy()) this.mr.stop(); },
    async toggle(btn, maxSecs, onDone) {
      if (this.busy()) { this.mr.stop(); return; }
      if (!micReady(() => this.toggle(btn, maxSecs, onDone))) return;
      LONG.other(); TTS.stop(); NAR.stop(); CLIP.stop();  // a whole text being read waits, paused where it was
      let stream;
      try { stream = await micOpen(); } catch (e) { toast(e.message); return; }
      const type = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4'].find(t => MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported(t)) || '';
      // A long answer (the ability test's 75 s, a retell's 2 minutes) at a speech bitrate: by default an iPhone records
      // AAC at about 185 kb/s (1.7 MB in 75 s) and Chrome Opus at 128 kb/s (1.9 MB in 2 minutes), over the 1.4 MB a
      // recording may be; at 48 kb/s two minutes are about 0.7 MB. If a browser keeps its own rate, the recording stops
      // by itself just under the limit and what was said is sent, never lost. Short ones (words, a sentence) keep the default.
      const long = maxSecs > 30, opts = Object.assign(type ? { mimeType: type } : {}, long ? { audioBitsPerSecond: 48000 } : {});
      // In 语流's iOS app the app records (WAV, AAC past 40 s: always under the limit; recorderFor), the rest as before.
      let mr; try { mr = recorderFor(stream, opts, maxSecs); } catch (e) { mr = new MediaRecorder(stream, type ? { mimeType: type } : undefined); }
      const chunks = []; let size = 0, full = false;
      this.mr = mr;
      mr.ondataavailable = e => {
        if (!e.data || !e.data.size) return;
        chunks.push(e.data); size += e.data.size;
        if (long && size > this.FULL && mr.state === 'recording') { full = true; mr.stop(); }
      };
      mr.onstop = () => {
        micClose(stream); clearTimeout(this.timer); btn.classList.remove('on'); btn.setAttribute('aria-pressed', 'false');
        if (full) toast('录音到了长度上限，已经停下，先交这一段');
        if (chunks.length) onDone(new Blob(chunks, { type: mr.mimeType || type || 'audio/webm' }));
      };
      if (long) mr.start(1000); else mr.start();
      btn.classList.add('on'); btn.setAttribute('aria-pressed', 'true');
      this.timer = setTimeout(() => this.stop(), maxSecs * 1000);
    },
    async payload(blob) {
      if (blob.size > this.MAX) throw new Error('录音太长了，请在 1 分钟内说完再交');
      const data = await new Promise((ok, no) => { const r = new FileReader(); r.onload = () => ok(String(r.result).split(',')[1]); r.onerror = no; r.readAsDataURL(blob); });
      return { mime_type: /wav/.test(blob.type) ? 'audio/wav' : /mp4|m4a|aac/.test(blob.type) ? 'audio/mp4' : /ogg/.test(blob.type) ? 'audio/ogg' : 'audio/webm', data };
    },
  };
  // The record key is 语流's own mark: the rounded square with four sound waves (B9, 2026-11-26; the user: 我们这个语流
  // 的logo是很像一个录音键的……点的时候……波动动画，而不是这种默认的这种录音按钮). Small beside a field or a sentence (a soft patch
  // of the theme colour), large where speaking is the whole task (the mark itself); while it records (.on, set by
  // MIC.toggle) the four waves move and two rings stand round it (97-rec-key.css).
  const REC_MARK = '<svg class="rec-mark" viewBox="0 0 32 32" aria-hidden="true"><rect x="5.5" y="13" width="3" height="6" rx="1.5"/><rect x="11.5" y="8" width="3" height="16" rx="1.5"/><rect x="17.5" y="10.5" width="3" height="11" rx="1.5"/><rect x="23.5" y="14" width="3" height="4" rx="1.5"/></svg>';
  const recBtn = (id, label, big) => `<button class="icon-btn rec${big ? ' big' : ''}" id="${id}" type="button" aria-label="${label || '录音'}" aria-pressed="false">${REC_MARK}</button>`;
  const fixesHTML = fs => fs && fs.length ? `<div class="stack-s">${fs.map(f => `<div class="change"><span class="ft"><del>${esc(f.from)}</del> → <ins>${esc(f.to)}</ins></span><span class="why" data-ex>${esc(f.why)}</span></div>`).join('')}
    <div class="tiny muted">这些已经放进错题本，会按遗忘曲线回来让你再改一次。</div></div>` : '';


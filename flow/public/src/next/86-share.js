  /* ---------- 分享卡片: a picture of what was learned, to keep or to send ---------- */
  // A learned expression (with the sentence it came in) or the week, drawn on a canvas as a 1080 px picture with a QR code
  // back to the site. In WeChat a long press saves or sends it; other phones get the system's share sheet; computers a
  // download. Nothing leaves the phone until the learner sends it.
  const SHARE_URL = 'https://flowlang.cn/?f=card';
  const shareFont = (s, w, serif) => `${w || 500} ${s}px ${serif ? "'Flow Serif', Georgia, 'Songti SC', serif" : "-apple-system, 'PingFang SC', 'Microsoft YaHei', sans-serif"}`;
  // Lines no wider than max: English breaks between words, Chinese between characters.
  function wrapLines(g, text, max) {
    const parts = String(text || '').match(/[　-〿㐀-鿿＀-￯]|[^\s　-〿㐀-鿿＀-￯]+\s*|\s+/g) || [];
    const lines = []; let line = '';
    parts.forEach(p => { if (line && g.measureText(line + p).width > max) { lines.push(line.trimEnd()); line = p.trimStart(); } else line += p; });
    if (line.trim()) lines.push(line.trimEnd());
    return lines;
  }
  function brandFoot(g, W, H, note) {
    const green = '#1f9d55';
    g.fillStyle = green; g.beginPath(); g.roundRect ? g.roundRect(80, H - 260, 84, 84, 22) : g.rect(80, H - 260, 84, 84); g.fill();
    g.strokeStyle = '#fff'; g.lineWidth = 8; g.lineCap = 'round';
    [[101, 37, 79], [117, 21, 95], [133, 29, 87], [149, 37, 71]].forEach(([x, a, b]) => { g.beginPath(); g.moveTo(x, H - 260 + a); g.lineTo(x, H - 260 + b); g.stroke(); });
    g.fillStyle = '#1b1d1a'; g.font = shareFont(40, 700); g.fillText('语流 Flow', 184, H - 222);
    g.fillStyle = '#6f7369'; g.font = shareFont(28, 400); g.fillText('每天一篇，学了就能用', 184, H - 180);
    if (note) { g.fillStyle = green; g.font = shareFont(28, 600); g.fillText(note, 80, H - 110); }
    QR.draw(g, SHARE_URL, W - 300, H - 300, 220, '#13261b', '#ffffff');
    g.fillStyle = '#6f7369'; g.font = shareFont(24, 400); g.textAlign = 'center'; g.fillText('扫码一起学', W - 190, H - 52); g.textAlign = 'left';
  }
  // The week, said only when there is something to say: a streak of weeks, or the days of this one. Shared right after
  // studying (studiedNow), today counts even before 今日 is fetched again. The week's card has its days already
  // (streakOnly; its seven days are not the calendar week either).
  function habitNote(studiedNow, streakOnly) {
    const hb = S.user && S.home && S.home.stats && S.home.stats.habit;
    if (!hb) return '';
    const t = (hb.days || []).find(d => d.today), done = hb.done + (studiedNow && t && !t.active ? 1 : 0);
    const streak = hb.streak + (done >= hb.goal && !hb.met ? 1 : 0);
    return streak > 1 ? `已经连续 ${streak} 周达成学习目标` : done > 0 && !streakOnly ? `这周学了 ${done} 天` : '';
  }
  // A learned expression: big, its meaning, the sentence it came in, and where from.
  function sentenceCard(x, from, title) {
    const W = 1080, H = 1440, cv = document.createElement('canvas'); cv.width = W; cv.height = H;
    const g = cv.getContext('2d'), green = '#1f9d55', ink = '#1b1d1a', muted = '#6f7369';
    const bg = g.createLinearGradient(0, 0, 0, H); bg.addColorStop(0, '#f6fbf7'); bg.addColorStop(1, '#e6f2ea'); g.fillStyle = bg; g.fillRect(0, 0, W, H);
    // measured first (each block with its own font), then drawn as one block centred above the footer
    let size = 84, big;
    do { g.font = shareFont(size, 700, true); big = wrapLines(g, x.text, W - 160).slice(0, 4); size -= 6; } while (big.length > 3 && size > 48);
    size += 6;
    g.font = shareFont(38, 500); const mean = x.meaning ? wrapLines(g, x.meaning, W - 160).slice(0, 3) : [];
    g.font = shareFont(34, 400, true); const quote = from ? wrapLines(g, from, W - 200).slice(0, 4) : [];
    const height = 60 + big.length * size * 1.25 + (mean.length ? 20 + mean.length * 56 : 0) + (quote.length ? 56 + quote.length * 50 : 0) + (title ? 70 : 0);
    let y = Math.max(150, Math.round((H - 330 - height) / 2) + 40);
    g.fillStyle = green; g.font = shareFont(32, 700); g.fillText('今天学会的一句', 80, y); y += 60 + size;
    g.fillStyle = ink; g.font = shareFont(size, 700, true); big.forEach((l, k) => { if (k) y += size * 1.25; g.fillText(l, 80, y); });
    if (mean.length) { y += 76; g.fillStyle = '#3c4038'; g.font = shareFont(38, 500); mean.forEach((l, k) => { if (k) y += 56; g.fillText(l, 80, y); }); }
    if (quote.length) {
      y += 90; g.fillStyle = green; g.fillRect(80, y - 36, 6, (quote.length - 1) * 50 + 48);
      g.fillStyle = '#3c4038'; g.font = shareFont(34, 400, true); quote.forEach((l, k) => { if (k) y += 50; g.fillText(l, 110, y); });
    }
    if (title) { y += 70; g.fillStyle = muted; g.font = shareFont(28, 400); g.fillText(`出自《${title}》`, 80, y); }
    brandFoot(g, W, H, habitNote(true));
    return cv.toDataURL('image/png');
  }
  // The preview, and the ways out: a long press in WeChat, the share sheet where there is one, else a download.
  function shareSheet(pictures, title) {
    let k = 0;
    const filesOK = !IN_WECHAT && !!(navigator.canShare && window.File);
    openSheet(`<div class="stack"><h2 class="h2" id="sheetTitle">${esc(title)}</h2>
      ${pictures.length > 1 ? `<div class="chips share-pick" role="radiogroup" aria-label="选一句">${pictures.map((p, i) => `<button class="chip" type="button" role="radio" data-pic="${i}" aria-checked="${i === 0}">${esc(p.label)}</button>`).join('')}</div>` : ''}
      <img class="share-img" id="shareImg" alt="分享图片预览">
      <p class="small muted">${IN_WECHAT ? '长按图片，选「保存图片」或「发送给朋友」。' : '长按图片可以保存；也可以用下面的按钮。'}</p>
      <div class="row">${filesOK ? '<button class="btn primary" id="shareGo" type="button">分享…</button>' : ''}${IN_WECHAT ? '' : '<a class="btn" id="shareSave" download="语流-学习卡片.png">保存图片</a>'}<button class="btn ghost" data-close type="button">关闭</button></div></div>`, card => {
      const show = () => {
        const url = pictures[k].url || (pictures[k].url = pictures[k].draw());
        card.querySelector('#shareImg').src = url;
        const a = card.querySelector('#shareSave'); if (a) a.href = url;
      };
      card.querySelectorAll('[data-pic]').forEach(b => b.onclick = () => { k = Number(b.dataset.pic); card.querySelectorAll('[data-pic]').forEach(x => x.setAttribute('aria-checked', String(x === b))); show(); });
      const go = card.querySelector('#shareGo');
      if (go) go.onclick = async () => {
        try {
          const bin = atob(pictures[k].url.split(',')[1]), u = new Uint8Array(bin.length);  // a data: URL, read without fetch (the page's CSP)
          for (let i = 0; i < bin.length; i++) u[i] = bin.charCodeAt(i);
          const file = new File([u], '语流-学习卡片.png', { type: 'image/png' });
          if (navigator.canShare({ files: [file] })) await navigator.share({ files: [file], title: '语流 Flow' }); else toast('这个浏览器不能直接分享，长按图片保存吧');
        } catch (e) { if (e && e.name !== 'AbortError') toast('没有分享出去，长按图片保存吧'); }
      };
      show();
    });
  }
  // From a material: up to three of its expressions, each with the sentence of the text it is in.
  function shareFromMaterial(m) {
    const xs = (m.expressions || []).slice(0, 3); if (!xs.length) return toast('这篇没有可以分享的表达');
    const ls = m.sentences || [];
    shareSheet(xs.map(x => ({ label: x.text, draw: () => sentenceCard(x, ls.find(s => s.toLowerCase().includes(x.text.toLowerCase())) || '', m.title) })), '分享今天学会的一句');
  }

  /* ---------- 小彩蛋 (the user's pick 2026-11-26: 「长按的时候会来一些有意思的特效……每一次都不一样」) ----------
     Hold 今日's greeting (about 0.45 s), or see the day's plan all done for the first time that day: one of four little
     shows drawn from 语流's mark, never the same kind twice in a row, and its numbers, direction and words new each time:
     a row of sound bars sweeping across; rounded squares rippling out from the finger; a handful of bars thrown up and
     falling; 「你好」 in another language with which one under it. Over in 1.5 s; no sound; on top of the page but never in
     the way of a tap (the canvas takes no pointer events, and is made only to play and taken away after); not at all
     with 减少动态效果; nothing kept or sent. B9's drawing (ui-refine/batch1/compare-page.html), sized to the screen. */
  const EGG = (() => {
    // the word, the language in Chinese, and in English (the line under it follows 界面语言: zhEn, 00-i18n.js)
    const HELLO = [['Hello', '英', 'English'], ['Bonjour', '法', 'French'], ['Hola', '西班牙', 'Spanish'], ['Ciao', '意大利', 'Italian'], ['Hallo', '德', 'German'],
      ['Olá', '葡萄牙', 'Portuguese'], ['こんにちは', '日', 'Japanese'], ['안녕하세요', '韩', 'Korean'], ['Merhaba', '土耳其', 'Turkish'], ['Aloha', '夏威夷', 'Hawaiian'],
      ['Namaste', '印地', 'Hindi'], ['Hej', '瑞典', 'Swedish'], ['Sawubona', '祖鲁', 'Zulu'], ['Xin chào', '越南', 'Vietnamese'], ['Habari', '斯瓦希里', 'Swahili'],
      ['Shalom', '希伯来', 'Hebrew']];
    const MS = 1500;
    let last = -1, busy = false;
    const calm = () => matchMedia('(prefers-reduced-motion: reduce)').matches;
    const rnd = (a, b) => a + Math.random() * (b - a);
    const out = t => 1 - Math.pow(1 - t, 3);
    function play(x, y) {
      if (busy || calm()) return false;
      busy = true;
      const W = innerWidth, H = innerHeight, dpr = Math.min(2, window.devicePixelRatio || 1);
      const cv = document.createElement('canvas');
      cv.className = 'egg-layer'; cv.setAttribute('aria-hidden', 'true');
      cv.width = Math.round(W * dpr); cv.height = Math.round(H * dpr);
      document.body.appendChild(cv);
      const ctx = cv.getContext('2d');
      const css = getComputedStyle(document.body), tok = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
      const accent = tok('--green') || '#1a8a4a', ink = tok('--ink') || '#1b1d1a', ink2 = tok('--ink2') || '#4a4d46', muted = tok('--muted') || '#6f7369', paper = tok('--paper') || '#fff';
      const font = css.fontFamily || 'sans-serif';
      if (x == null) { x = W / 2; y = H / 2; }
      const rr = (px, py, w, h, r) => {
        r = Math.min(r, w / 2, h / 2); ctx.beginPath(); ctx.moveTo(px + r, py);
        ctx.arcTo(px + w, py, px + w, py + h, r); ctx.arcTo(px + w, py + h, px, py + h, r); ctx.arcTo(px, py + h, px, py, r); ctx.arcTo(px, py, px + w, py, r);
        ctx.closePath(); ctx.fill();
      };
      // 1 · a row of sound bars sweeping across a band around the finger
      const wave = () => {
        const n = Math.floor(rnd(14, 30)), ph = rnd(0, 6), sp = rnd(1, 3), amp = rnd(0.3, 0.6), dir = Math.random() < 0.5 ? 1 : -1;
        const B = Math.min(260, H * 0.4), top = Math.max(0, Math.min(H - B, y - B / 2));
        return t => {
          const gap = W / n, bw = Math.min(9, gap * 0.42);
          ctx.fillStyle = accent; ctx.globalAlpha = Math.min(1, (1 - t) * 2.4);
          for (let i = 0; i < n; i++) {
            const u = i / (n - 1), on = Math.max(0, Math.min(1, (t * 2 - (dir > 0 ? u : 1 - u) * 0.8) * 3));
            const h = (B * 0.1 + B * amp * Math.abs(Math.sin(u * sp * 6 + ph + t * 7 * dir))) * out(on);
            if (h > 1) rr(gap * i + (gap - bw) / 2, top + (B - h) / 2, bw, h, bw / 2);
          }
        };
      };
      // 2 · the mark's rounded square, rippling out from the finger
      const rings = () => {
        const n = Math.floor(rnd(3, 6)), gap = rnd(0.1, 0.18), big = Math.min(Math.max(W, H) * rnd(0.7, 1.1), 900);
        return t => {
          ctx.strokeStyle = accent; ctx.lineWidth = 3;
          for (let i = 0; i < n; i++) {
            const u = t - i * gap; if (u <= 0) continue;
            const s = out(Math.min(1, u * 1.4)) * big, r = s * 0.24;
            ctx.globalAlpha = Math.max(0, 0.75 * (1 - u * 1.5));
            ctx.beginPath(); ctx.moveTo(x - s / 2 + r, y - s / 2);
            ctx.arcTo(x + s / 2, y - s / 2, x + s / 2, y + s / 2, r); ctx.arcTo(x + s / 2, y + s / 2, x - s / 2, y + s / 2, r);
            ctx.arcTo(x - s / 2, y + s / 2, x - s / 2, y - s / 2, r); ctx.arcTo(x - s / 2, y - s / 2, x + s / 2, y - s / 2, r);
            ctx.closePath(); ctx.stroke();
          }
        };
      };
      // 3 · a handful of small bars thrown up from the finger, falling back
      const burst = () => {
        const n = Math.floor(rnd(22, 44)), ps = [];
        for (let i = 0; i < n; i++) {
          const a = rnd(0, Math.PI * 2), v = rnd(110, 330);
          ps.push({ vx: Math.cos(a) * v, vy: Math.sin(a) * v - 140, r: rnd(0, 6), s: rnd(-7, 7), w: rnd(3, 6), h: rnd(8, 24), c: Math.random() < 0.65 ? accent : ink2 });
        }
        return t => {
          const T = t * 1.4; ctx.globalAlpha = Math.max(0, 1 - t * t);
          ps.forEach(p => { ctx.save(); ctx.translate(x + p.vx * T, y + p.vy * T + 430 * T * T); ctx.rotate(p.r + p.s * T); ctx.fillStyle = p.c; rr(-p.w / 2, -p.h / 2, p.w, p.h, p.w / 2); ctx.restore(); });
        };
      };
      // 4 · 「你好」 in another language, a letter at a time, and which language under it, on a soft card of its own in the
      // middle of the screen (over the page's own words it would not read)
      const hello = () => {
        const w = HELLO[Math.floor(Math.random() * HELLO.length)], chars = Array.from(w[0]), tilt = rnd(-0.04, 0.04);
        return t => {
          ctx.save(); ctx.translate(W / 2, H * 0.42); ctx.rotate(tilt);
          ctx.font = `600 40px ${font}`; ctx.textBaseline = 'middle';
          const tw = ctx.measureText(w[0]).width, bw = Math.max(tw, 150) + 56, fade = Math.min(1, t * 6) * Math.min(1, (1 - t) * 3);
          ctx.globalAlpha = fade * 0.96; ctx.fillStyle = paper; ctx.shadowColor = 'rgba(0,0,0,.14)'; ctx.shadowBlur = 24; ctx.shadowOffsetY = 6;
          rr(-bw / 2, -50, bw, 104, 22); ctx.shadowColor = 'transparent'; ctx.shadowBlur = 0; ctx.shadowOffsetY = 0;
          let px = -tw / 2;
          chars.forEach((ch, i) => {
            const u = Math.max(0, Math.min(1, t * 4 - i * 0.22)), cw = ctx.measureText(ch).width;
            ctx.globalAlpha = out(u) * Math.min(1, (1 - t) * 3); ctx.fillStyle = ink; ctx.fillText(ch, px, -8 + (1 - out(u)) * 18); px += cw;
          });
          ctx.font = `400 13.5px ${font}`; ctx.fillStyle = muted; ctx.globalAlpha = Math.max(0, Math.min(1, t * 4 - 1)) * Math.min(1, (1 - t) * 3);
          const s = zhEn(`${w[1]}语里的「你好」`, `“Hello” in ${w[2]}`); ctx.fillText(s, -ctx.measureText(s).width / 2, 30);
          ctx.restore();
        };
      };
      const kinds = [wave, rings, burst, hello];
      let k;
      do { k = Math.floor(Math.random() * kinds.length); } while (k === last);
      last = k;
      const draw = kinds[k](), t0 = performance.now();
      cv.dataset.kind = ['wave', 'rings', 'burst', 'hello'][k];
      const loop = () => {
        const t = (performance.now() - t0) / MS;
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.clearRect(0, 0, W, H); ctx.globalAlpha = 1;
        if (t >= 1 || !cv.isConnected) { cv.remove(); busy = false; return; }
        draw(t); requestAnimationFrame(loop);
      };
      requestAnimationFrame(loop);
      return true;
    }
    // hold the greeting: a move, a lift or a scroll first is not a hold; the text is never selected
    function bindGreeting(el) {
      if (!el) return;
      let hold = 0, x0 = 0, y0 = 0;
      const stop = () => { clearTimeout(hold); hold = 0; };
      el.addEventListener('pointerdown', e => {
        if (e.button > 0) return;
        x0 = e.clientX; y0 = e.clientY; stop();
        hold = setTimeout(() => { hold = 0; play(x0, y0); }, 450);
      });
      el.addEventListener('pointermove', e => { if (hold && Math.abs(e.clientX - x0) + Math.abs(e.clientY - y0) > 10) stop(); });
      ['pointerup', 'pointercancel', 'pointerleave'].forEach(t => el.addEventListener(t, stop));
      el.addEventListener('contextmenu', e => e.preventDefault());
    }
    // the day's plan all done, seen on 今日 for the first time that day: once, by itself
    function planDone(p) {
      if (!p || !p.total || p.done < p.total) return;
      const day = new Date().toDateString();
      if (load('flow-egg-done') === day) return;
      save('flow-egg-done', day);
      setTimeout(() => play(), 350);
    }
    return { play, bindGreeting, planDone };
  })();

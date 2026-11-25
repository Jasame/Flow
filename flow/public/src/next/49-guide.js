  /* ---------- 操作指南: the same source as the PDF (flow/public/guide/guide.md, rendered by user_guide.py) ---------- */
  async function guideView(id) {
    if (!S.guide) S.guide = await api('/api/next/guide');
    const g = S.guide;
    view.innerHTML = `<h1 class="h1">操作指南</h1><p class="muted small">${esc(g.updated)} · 从第一次打开到每一个页面，一步一步讲清楚。</p>
      <div class="row">${g.pdf ? `<a class="btn small primary" href="${g.pdf}" download="语流操作指南.pdf">下载 PDF 版</a>` : ''}<a class="btn small" href="#/practice">去练习</a></div>
      <label class="field section"><span class="sr-only">在指南里搜索</span><input class="guide-search" id="gq" type="search" placeholder="搜一搜：比如 复习、录音、提醒" autocomplete="off"></label>
      <nav class="card flat guide-toc" id="gtoc" aria-label="指南目录">${g.chapters.map((ch, k) => `<a href="#/guide/${ch.id}" data-ch="${ch.id}"><span class="n">${k + 1}</span><span>${esc(ch.title)}</span></a>`).join('')}</nav>
      <p class="muted small" id="gnone" hidden>没有找到，换个词试试，或者看看「常见问题」。</p>
      <div class="guide-body">${g.chapters.map((ch, k) => `<section id="g-${ch.id}" data-ch="${ch.id}"><h2>${k + 1}. ${esc(ch.title)}</h2>${ch.html}</section>`).join('')}</div>
      <div class="section row"><a class="btn small" href="#/guide">回到目录</a>${g.pdf ? `<a class="btn small" href="${g.pdf}" download="语流操作指南.pdf">下载 PDF 版</a>` : ''}</div>`;
    const q = document.getElementById('gq'), none = document.getElementById('gnone');
    q.oninput = () => {
      const t = q.value.trim().toLowerCase();
      let shown = 0;
      g.chapters.forEach(ch => {
        const hit = !t || ch.text.toLowerCase().includes(t) || ch.title.toLowerCase().includes(t);
        view.querySelectorAll(`[data-ch="${ch.id}"]`).forEach(el => { el.hidden = !hit; });
        if (hit) shown++;
      });
      none.hidden = shown > 0;
    };
    // #/guide/<id> (a link from anywhere, or opened directly): to that chapter. The page keeps settling after it is drawn
    // (the router's own scroll, pictures, the enter animation), so it is put there again a few times until the reader
    // scrolls themselves.
    if (id) {
      const sec = document.getElementById('g-' + id);
      if (sec) {
        let mine = true; const off = () => { mine = false; };
        ['wheel', 'touchstart', 'keydown'].forEach(t => addEventListener(t, off, { once: true, passive: true }));
        const go = () => { if (mine && sec.isConnected) sec.scrollIntoView({ block: 'start' }); };
        requestAnimationFrame(go); [120, 400, 1000].forEach(ms => setTimeout(go, ms));
      }
    }
  }


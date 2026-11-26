  /* ---------- 看中文 under the AI's English explanations (全英文界面, 语流 E1; the AI side is 语流 B7's ai_lang.py) ---------- */
  // In English mode the AI explains in English. Each block of AI feedback (data-ex-block: a result, a look-up's
  // explanation, a dialog's chat) gets one 「Show Chinese · 看中文」 button right after it, in both languages. Tapped, the
  // block's explanation lines (data-ex) go to /api/next/zh, 20 to a request (not counted as AI uses), and each comes
  // back in Chinese under its line: data-zh (left as it is, read with a Chinese voice), with 「AI 生成」 beside the button,
  // since an AI translated it. While it is on, lines added later (a dialog's next turn) come in Chinese too; tapped
  // again, the Chinese is hidden. In Chinese mode nothing here runs (the explanations are Chinese already).
  const EXZH_MAX = 20;
  // &nbsp; around the dot: a button lays its text out as flex items, which drop plain spaces at their ends
  const EXZH_SHOW = '<span lang="en">Show Chinese</span>&nbsp;·&nbsp;<span lang="zh-CN">看中文</span>';  // i18n: keep (both languages)
  const EXZH_HIDE = '<span lang="en">Hide Chinese</span>&nbsp;·&nbsp;<span lang="zh-CN">收起中文</span>';  // i18n: keep (both languages)
  const exZhLines = block => [...block.querySelectorAll('[data-ex]')].filter(el => !el.querySelector('.ex-zh') && el.textContent.trim());
  function exZhRow(block) {
    const next = block.nextElementSibling;
    if (next && next.classList.contains('ex-zh-row')) return next;
    const row = document.createElement('div');
    row.className = 'ex-zh-row'; row.setAttribute('translate', 'no');
    row.innerHTML = `<button class="link small" type="button" aria-pressed="false">${EXZH_SHOW}</button>`;
    block.insertAdjacentElement('afterend', row);
    row.querySelector('button').onclick = () => exZhToggle(block, row);
    return row;
  }
  async function exZhFill(block) {
    const lines = exZhLines(block);
    for (let k = 0; k < lines.length; k += EXZH_MAX) {
      const part = lines.slice(k, k + EXZH_MAX);
      const r = await api('/api/next/zh', { texts: part.map(el => el.textContent.trim().slice(0, 600)) });
      part.forEach((el, i) => {
        const zh = r && r.zh && r.zh[i];
        if (zh && el.isConnected && !el.querySelector('.ex-zh')) el.insertAdjacentHTML('beforeend', `<span class="ex-zh" data-zh lang="zh-CN">${esc(zh)}</span>`);
      });
    }
  }
  async function exZhToggle(block, row) {
    const b = row.querySelector('button');
    if (b.disabled) return;
    if (block.dataset.exzh === 'on') {
      block.dataset.exzh = 'off'; b.setAttribute('aria-pressed', 'false'); b.innerHTML = EXZH_SHOW; return;
    }
    b.disabled = true; b.classList.add('busy');
    try {
      await exZhFill(block);
      block.dataset.exzh = 'on'; b.setAttribute('aria-pressed', 'true'); b.innerHTML = EXZH_HIDE;
      if (!row.querySelector('.ai-mark')) b.insertAdjacentHTML('beforebegin', aiTag());
    } catch (e) { toast(e.message); }
    b.disabled = false; b.classList.remove('busy');
  }
  if (uiLang() === 'en') {
    // a block as it is drawn, or a line added to one (a dialog's next turn)
    const exZhScan = n => {
      const blocks = [];
      if (n.matches('[data-ex-block]')) blocks.push(n);
      n.querySelectorAll('[data-ex-block]').forEach(b => blocks.push(b));
      const up = n.parentElement && n.parentElement.closest('[data-ex-block]');
      if (up) blocks.push(up);
      blocks.forEach(b => {
        if (!exZhLines(b).length) return;
        exZhRow(b);
        if (b.dataset.exzh === 'on') exZhFill(b).catch(() => { /* the button stays; a tap asks again */ });
      });
    };
    new MutationObserver(ms => ms.forEach(m => m.addedNodes.forEach(n => { if (n.nodeType === 1 && !n.classList.contains('ex-zh') && !n.classList.contains('ex-zh-row')) exZhScan(n); })))
      .observe(document.body, { childList: true, subtree: true });
  }

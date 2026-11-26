  /* ---------- 界面语言: 中文 | English (我的 → 使用习惯, on its title row; 全英文界面, 语流 E1) ---------- */
  // Kept like 主题色 (07-accent.js): signed in, with the account (/api/next/lang → profile.lang), so another phone or
  // computer opens in it too; before signing in, on this device, handed to the account once after signing in. The
  // device keeps its own copy (flow-lang), read before the first page is drawn (uiLang(), 00-i18n.js).
  // Switching reloads the page once, on the same page, with this device's copies of 今日 and the texts cleared (they
  // hold the server's words). The two halves of the switch are each written in their own language, and what is said
  // around it in both, so a learner who opened English by mistake can always find the way back; for 10 s after the
  // switch a line offers to undo it. Going to English first says what changes (word meanings stay in Chinese) and, at
  // 入门 or before the level is known, that B1 is a better time for it. Chinese is never chosen for the learner.
  const LANG_UNDO_MS = 10000;
  function langSwitchHTML() {
    if (!uiLangOpen()) return '';
    const cur = uiLang();
    // the look of 列表 | 卡片 and 简 | 详 (.vt, 30-words.css; B9)
    return /* i18n: keep (each half in its own language) */ `<div class="vt lang-seg" role="radiogroup" aria-label="界面语言 Language" translate="no">${[['zh', '中文', 'zh-CN'], ['en', 'English', 'en']].map(([v, l, lg]) =>
      `<button type="button" role="radio" data-lang="${v}" lang="${lg}" class="${v === cur ? 'on' : ''}" aria-checked="${v === cur}">${l}</button>`).join('')}</div>`;
  }
  function langSwitchWire(root) {
    (root || document).querySelectorAll('.lang-seg [data-lang]').forEach(b => b.onclick = () => {
      if (b.getAttribute('aria-checked') === 'true') return;
      if (b.dataset.lang === 'en') langAskEnglish(); else setLang('zh');
    });
  }
  // Before English: what changes, in both languages, and a word for learners at 入门
  function langAskEnglish() {
    const lv = S.home && S.home.profile ? S.home.profile.level : (S.guest && S.guest.level) || '';
    const early = !lv || lv === 'A2';
    openSheet(/* i18n: keep (both languages) */ `<div class="stack" translate="no"><h2 class="h2" id="sheetTitle"><span lang="zh-CN">换成英文界面</span> · <span lang="en">Switch to English</span></h2>
      <p lang="zh-CN">按钮、标题和说明都会换成英文，AI 也用英文讲解（每段讲解下面能看中文）。单词的中文意思还在。随时可以在「我的 → 使用习惯」换回中文。</p>
      <p class="small muted" lang="en">Buttons, titles and instructions will be in English, and the AI will explain in English (with Chinese one tap away). Chinese word meanings stay. Switch back any time in Me → Preferences.</p>
      ${early ? /* i18n: keep */ `<p class="small" lang="zh-CN">你现在是入门水平，建议到中级（B1）再换。</p><p class="small muted" lang="en">At this level, Chinese may still be easier. B1 (intermediate) is a good time to switch.</p>` : ''}
      <button class="btn primary" type="button" id="langGo"><span lang="zh-CN">换成英文</span> · <span lang="en">Switch</span></button>
      <button class="btn ghost" type="button" data-close><span lang="zh-CN">取消</span> · <span lang="en">Cancel</span></button></div>`, card => {
      card.querySelector('#langGo').onclick = () => setLang('en');
    });
  }
  async function setLang(l, undoing) {
    l = l === 'en' ? 'en' : 'zh';
    const was = uiLang();
    if (l === was) return;
    if (S.user) {
      let r = null;
      try { r = await api('/api/next/lang', { lang: l }); } catch (e) { toast(e.message); return; }  // nothing changes here either
      if (r && r.kept === false) save('flow-lang-guest', l);  // no 学习目标 yet: handed to the account once there is one
    } else save('flow-lang-guest', l);
    save('flow-lang', l === 'en' ? 'en' : null);
    save('flow-lang-undo', undoing ? null : { from: was, at: Date.now() });
    langReload();
  }
  function langReload() {
    save(SNAP, null); DATA.mem.clear();  // 今日 and the texts kept on the device were written in the other language
    location.reload();
  }
  // With the profile (refreshHome, 02-shell.js): a choice made here before signing in goes to the account, once; else
  // the account's choice, made on another phone or computer, is followed (once per page: never a loop of reloads).
  function langFromAccount(p) {
    if (!uiLangOpen()) return;
    const g = load('flow-lang-guest');
    if (g) {
      save('flow-lang-guest', null);
      if (g !== (p.lang || 'zh')) {
        p.lang = g;
        api('/api/next/lang', { lang: g }).then(r => { if (r && r.kept === false) save('flow-lang-guest', g); }).catch(() => save('flow-lang-guest', g));
      }
      return;
    }
    const want = p.lang === 'en' ? 'en' : 'zh';
    if (want === uiLang() || langFromAccount.done) return;
    langFromAccount.done = true;
    save('flow-lang', want === 'en' ? 'en' : null);
    if ((load('flow-lang') === 'en') === (want === 'en')) langReload();  // only when this device could keep it
  }
  // Just switched: 10 s to take it back, said in both languages
  (function langUndoLine() {
    const u = load('flow-lang-undo');
    if (!u) return;
    save('flow-lang-undo', null);
    if (!(Date.now() - u.at < 30000) || !uiLangOpen()) return;
    const en = uiLang() === 'en';
    const el = document.createElement('div');
    el.className = 'easy-bar lang-undo'; el.setAttribute('role', 'status'); el.setAttribute('translate', 'no');  // the look of 复习's 太简单 · 撤销
    el.innerHTML = /* i18n: keep */ (en ? '<span lang="en">Now in English</span><span lang="zh-CN">已换成英文</span>' : '<span lang="zh-CN">已换成中文</span><span lang="en">Now in Chinese</span>')
      + /* i18n: keep */ `<button type="button" class="link small">${en ? '<span lang="en">Undo</span> · <span lang="zh-CN">撤销</span>' : '<span lang="zh-CN">撤销</span> · <span lang="en">Undo</span>'}</button>`;
    el.querySelector('button').onclick = () => { el.remove(); setLang(u.from, true); };
    document.body.appendChild(el);
    setTimeout(() => el.remove(), LANG_UNDO_MS);
  })();

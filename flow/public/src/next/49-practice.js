  /* ---------- 练习: every kind of practice in one place, grouped by skill, with one suggestion on top ---------- */
  // B9's batch 1 (the user, 2026-11-26 15:3x; ui-refine/batch1/practice-*.png): the suggestion is a white card with the
  // page's one green button under it; each group a white card, two columns, one row per practice (44 high, an icon in
  // front, 99-icons.css); something due shows a small ink dot, the number said to a screen reader. A row shows its name
  // only; the line on what it is for stays where it says what AI does. What has an entry of its own elsewhere is not
  // repeated here (今天的材料 is 今日; 周报 and 我的进步 are in 我的; 能力雷达 is its own tab).
  // Each practice: [href, title, one line on what it is for, icon (00-icons.js), 'due' for the word review's count].
  const PRACTICE = [
    ['语法', 'right', [
      ['#/graph', '知识图谱', '44 个语法点按顺序连成路线，点亮一个学一个', 'graph'],
      ['#/mix', '混合练习', '几个语法点打乱一起练，记得更牢', 'shuffle']]],
    ['听和读', 'left', [
      ['#/easy', '轻松读', '读比你低一级的短文，练速度、攒阅读量', 'read'],
      ['#/library', '全部材料', '按话题和级别挑一篇来学', 'layers'],
      ['#/import', '我的文章', '贴一段任何英文，变成可以学的材料', 'docpen']]],
    ['说和写', 'right', [
      ['#/speak', '口语路线', '12 个生活和校园情景，和 AI 对话', 'chat'],
      ['#/sounds', '发音入门', '中国学习者容易混的音，听辨再跟读', 'mic']]],
    ['单词', 'left', [
      ['#/review', '复习单词', '到期的单词和短语，一张张过', 'stack', 'due'],
      ['#/words/confuse', '词汇辨析', '最容易混的词放在一起练', 'venn'],
      ['#/vocab/plan', '背词计划', '换词书、改每天学多少', 'cal'],
      ['#/vocab/test', '测词汇量', '5 分钟估一估你认识多少词', 'gauge']]],
    ['考试和测评', 'right', [
      ['#/exam', '考试练习', '中考高考、四六级、考研、专四专八、雅思，限时做', 'exam'],
      ['#/placement', '语法起点小测', '16 题定出你的语法起点', 'flag']]]];
  // A row: the icon, the name, a dot when something is due (its number in the row's name for a screen reader)
  // said: what a screen reader hears instead of 「有 N 项到期」 (复习单词: its new words are not due, B9's audit 第 1 条)
  function practiceRow([href, title, line, icon], n, tap, said) {
    return `<a class="pc-row" href="${href}"${tap ? ` data-tap="${tap}"` : ''}${n ? ` aria-label="${said || `${title}，有 ${n} 项到期`}"` : ''}>${fi(icon)}
      <span class="pc-name">${title}${/AI/.test(line) ? `<span class="pc-sub">${line}</span>` : ''}</span>${n ? '<i class="pc-dot" aria-hidden="true"></i>' : ''}</a>`;
  }
  const practiceGroup = (name, rows) => `<section class="pc-card" aria-label="${name}"><h2 class="pc-h">${name}</h2>${rows}</section>`;
  // 复习 (the user, 2026-11-25: 「单词复习不要和其他的东西混在一起，其他东西复习单独开个板块」): the mistakes, sentence
  // patterns and whole sentences due again (#/review/other, B2's review-split), with 错题本 beside it; the 「练习」 tab
  // carries their dot (02-shell.js setDueBadge). Nothing due: the row stays, so the way in is always there.
  function reviewGroup(st) {
    if (!S.user) return '';
    const n = st ? st.other_due || 0 : 0;
    return practiceGroup('复习', practiceRow(['#/review/other', '错题和句型', '', 'retry'], n, 'practice-review-other') + practiceRow(['#/cards/mistake', '错题本', '', 'bookx'], 0));
  }
  async function practiceView(fresh) {
    // today's words as the review gives them (today's share, the same as the 单词 tab's dot): reviews due and new words
    const st = S.home && S.home.stats, words = { due: st ? st.due || 0 : 0, new: st ? st.new || 0 : 0 }, due = words.due + words.new;
    const said = words.due && words.new ? `复习单词，${words.due} 个到期，${words.new} 个新词` : words.due ? '' : `复习单词，今天还有 ${words.new} 个新词`;
    const col = side => (side === 'left' ? reviewGroup(st) : '') + PRACTICE.filter(g => g[1] === side)
      .map(([name, , items]) => practiceGroup(name, items.map(x => x[4] === 'due' ? practiceRow(x, due, '', said) : practiceRow(x, 0)).join(''))).join('');
    view.innerHTML = `<h1 class="h1">练习</h1>
      <div id="pSuggest">${practiceTip(null, words)}</div>
      <div class="pc-cols"><div class="pc-col">${col('left')}</div><div class="pc-col">${col('right')}</div></div>
      ${tipSeen('guide') === false ? '<a class="guide-cta link" href="#/guide" data-tip-seen="guide">第一次用？看操作指南 ›</a>' : ''}`;  // 一次性 (08-tips.js)
    // the dots from fresher home data (words come due during the day; a review just done elsewhere): drawn again quietly,
    // once (fresh: drawn from data just fetched)
    if (S.user && !fresh) { const drawnFor = location.hash; refreshHome().then(changed => { if (changed) redrawQuietly(drawnFor); }).catch(() => {}); }
    if (S.user) api('/api/next/radar').then(r => {
      const el = document.getElementById('pSuggest'); if (el && r && r.gap) el.innerHTML = practiceTip(r, words);
    }).catch(() => { /* the plain suggestion stays */ });
  }
  // 今天建议: the skill furthest from the learner's goal (能力雷达), else the words due, else today's plan. A white card
  // (its icon the one accent tile on the page) and the page's one green button under it.
  const TIP_ICON = { '#/library': 'layers', '#/easy': 'read', '#/vocab/plan': 'cal', '#/mix': 'shuffle', '#/speak': 'chat', '#/': 'docpen', '#/review': 'stack' };
  // words: {due, new} of today's share; only the due ones are 「等你复习」, new words are said as new (B9's audit 第 1 条)
  function practiceTip(radar, words) {
    const d = radar && radar.dims.find(x => x.id === radar.gap), w = words || { due: 0, new: 0 };
    const [href, head, sub, go, icon] = d ? [d.href, d.tip, `${d.label}离你的目标最远，先练它`, `去练${d.label}`, TIP_ICON[d.href] || 'target']
      : w.due ? ['#/review', `有 ${w.due} 个词等你复习`, w.new ? `复习完还有 ${w.new} 个新词。` : '先复习再学新的，记得最牢。', '开始复习', 'stack']
      : w.new ? ['#/review', `今天还有 ${w.new} 个新词`, '背完今天的新词，再去练别的。', '开始背新词', 'stack']
      : ['#/', '先做今天的计划', '今日页已经按你的水平排好了顺序。', '打开今日', 'target'];
    return `<section class="pc-tip" aria-labelledby="pcTipH"><div class="pc-tip-t"><h2 class="pc-tip-h" id="pcTipH">今天建议</h2><b class="pc-tip-b">${esc(head)}</b><span class="pc-tip-s">${esc(sub)}</span></div>
      <span class="pc-tip-i" aria-hidden="true">${fi(icon)}</span></section>
      <a class="btn primary block pc-go" href="${esc(href)}" data-tap="practice-tip">${esc(go)}</a>`;
  }

  /* ---------- 练习: every kind of practice in one place, grouped by skill, with one suggestion on top ---------- */
  // Each tile: [href, title, one line on what it is for, extra]. The guide (#/guide) explains each one step by step.
  // extra 'due' adds the review count; 'map' makes the tile the grammar map's wide card (the map has no tab of its own).
  const PRACTICE = [
    ['语法', [  // first: the map used to be a tab of its own, so it is on the first screen
      ['#/graph', '知识图谱', '44 个语法点按顺序连成路线，点亮一个学一个', 'map'],
      ['#/mix', '混合练习', '几个语法点打乱一起练，记得更牢'],
      ['#/placement', '语法起点小测', '16 题定出你的语法起点']]],
    ['听和读', [
      ['#/', '今天的材料', '听一遍、读一遍、答几题、用出来，每天 10–20 分钟'],
      ['#/easy', '轻松读', '读比你低一级的短文，练速度、攒阅读量'],
      ['#/library', '全部材料', '按话题和级别挑一篇来学'],
      ['#/import', '我的文章', '贴一段任何英文，变成可以学的材料']]],
    ['说和写', [
      ['#/speak', '口语路线', '12 个生活和校园情景，和 AI 对话'],
      ['#/sounds', '发音入门', '中国学习者容易混的音，听辨再跟读']]],
    ['单词', [
      ['#/review', '复习单词', '到期的词和错过的题，一张张过', 'due'],
      ['#/words/confuse', '词汇辨析', '最容易混的词放在一起练'],
      ['#/cards/mistake', '错题本', '做错过的词和题都在这里'],
      ['#/vocab/plan', '词书和每天新词', '换词书、改每天学多少'],
      ['#/vocab/test', '词汇量测试', '5 分钟估一估你认识多少词']]],
    ['考试和测评', [
      ['#/exam', '考试练习', '四六级、考研、雅思题型，限时做'],
      ['#/radar', '能力雷达', '六项能力对照你的目标，定期测一测']]],
    ['看进步', [
      ['#/report', '这周的报告', '这周学了什么、哪里进步了'],
      ['#/growth', '我的进步', '这个月和上个月比，里程碑']]]];

  const PICON = {
    '#/mix': '<path d="M4 7h3l10 10h3"/><path d="M4 17h3l2.5-2.5"/><path d="M14.5 9.5 17 7h3"/><path d="m18 5 2 2-2 2"/><path d="m18 15 2 2-2 2"/>',
    '#/placement': '<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="3.5"/>',
    '#/': '<rect x="4" y="5" width="16" height="15" rx="2"/><path d="M4 10h16M9 3v4m6-4v4"/>',
    '#/easy': '<path d="M5 19c8 0 14-6 14-14-8 0-14 6-14 14z"/><path d="m5 19 8-8"/>',
    '#/library': '<rect x="4" y="4" width="7" height="7" rx="1.5"/><rect x="13" y="4" width="7" height="7" rx="1.5"/><rect x="4" y="13" width="7" height="7" rx="1.5"/><rect x="13" y="13" width="7" height="7" rx="1.5"/>',
    '#/import': '<path d="M6 3h8l4 4v14H6z"/><path d="M14 3v4h4M12 11v6m-3-3h6"/>',
    '#/speak': '<path d="M4 5h16v11H9l-5 4z"/>',
    '#/sounds': '<path d="M12 4a3 3 0 0 1 3 3v5a3 3 0 0 1-6 0V7a3 3 0 0 1 3-3z"/><path d="M6 11a6 6 0 0 0 12 0M12 17v3"/>',
    '#/review': '<path d="M20 12a8 8 0 1 1-2.3-5.6"/><path d="M20 4v5h-5"/>',
    '#/words/confuse': '<circle cx="9" cy="12" r="5.5"/><circle cx="15" cy="12" r="5.5"/>',
    '#/cards/mistake': '<path d="M6 3h12v18H6z"/><path d="m9.5 9.5 5 5m0-5-5 5"/>',
    '#/vocab/plan': '<path d="M5 5a2 2 0 0 1 2-2h11v15H7a2 2 0 0 0-2 2z"/><path d="M5 20a2 2 0 0 0 2 1h11v-3"/>',
    '#/vocab/test': '<path d="M4 17a8 8 0 0 1 16 0"/><path d="m12 17 4-5"/>',
    '#/exam': '<circle cx="12" cy="13" r="7"/><path d="M12 9v4l3 2M10 3h4"/>',
    '#/radar': '<path d="M12 3 20 8v8l-8 5-8-5V8z"/><path d="m12 8 4 3-1.5 5h-5L8 11z"/>',
    '#/report': '<path d="M5 20V10m5 10V5m5 15v-7m5 7V8"/>',
    '#/growth': '<path d="m4 17 6-6 4 4 6-7"/><path d="M15 8h5v5"/>'};
  // One row per practice (icon, title, one line on what it is for): a phone shows a whole group at a glance.
  const prow = ([href, title, line, badge], due) => `<a class="prow" href="${href}"><span class="pico" aria-hidden="true"><svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${PICON[href] || ''}</svg></span>
    <span class="t"><b>${title}${badge === 'due' && due ? ` <i class="pbadge">${due > 99 ? '99+' : due}</i>` : ''}</b><span class="tiny muted">${line}</span></span><span class="go" aria-hidden="true">›</span></a>`;

  async function practiceView() {
    const st = S.home && S.home.stats, due = st ? (st.due || 0) + (st.new || 0) : 0;
    view.innerHTML = `<h1 class="h1">练习</h1>
      <p class="muted small">想练哪一项，就从这里进。不知道先练什么，看最上面的建议。</p>
      <div id="pSuggest">${practiceTip(null, due)}</div>
      ${PRACTICE.map(([group, items]) => `<section class="pgroup stack-s"><h2 class="h2 pgroup-h">${group}</h2>
        ${items.filter(x => x[3] === 'map').map(([href, title, line]) => mapTile(href, title, line)).join('')}
        <div class="plist">${items.filter(x => x[3] !== 'map').map(x => prow(x, due)).join('')}</div></section>`).join('')}
      <a class="card flat place-cta guide-cta" href="#/guide"><b>第一次用？看操作指南</b><span class="small muted">每个页面怎么用、按哪里、学完去哪，一步一步讲清楚；也可以下载 PDF。</span></a>`;
    requestAnimationFrame(() => requestAnimationFrame(() => view.querySelectorAll('.gbar i').forEach(i => { i.style.width = i.dataset.w + '%'; })));
    if (S.user) api('/api/next/radar').then(r => {
      const el = document.getElementById('pSuggest'); if (el && r && r.gap) el.innerHTML = practiceTip(r, due);
    }).catch(() => { /* the plain suggestion stays */ });
  }
  // The grammar map, as wide as the row: how much of it is lit, and what needs a look first.
  function mapTile(href, title, line) {
    const g = S.home && S.home.graph, total = g ? g.total : 44, lit = g ? total - g.untouched : 0;
    const look = g && g.watch.length ? '需要留意：' + g.watch.map(w => esc(w.title)).join('、') : g && g.due && g.due.length ? '该复习：' + g.due.map(w => esc(w.title)).join('、') : line;
    return `<a class="ptile pmap card flat" href="${href}" data-tap="practice-map"><span class="row between"><b>${title}</b>${g ? `<span class="pill green">已点亮 ${lit} / ${total}</span>` : ''}</span>
      <span class="small muted">${look}</span>
      ${g ? `<span class="gbar" aria-hidden="true">${['solid', 'used', 'met', 'watch'].map(k => `<i class="st st-${k}" data-w="${g[k] / total * 100}"></i>`).join('')}</span>` : ''}</a>`;
  }
  function practiceTip(radar, due) {
    const d = radar && radar.dims.find(x => x.id === radar.gap);
    if (d) return `<a class="card psuggest" data-tap="practice-tip" href="${esc(d.href)}"><span class="tiny">今天建议</span><b>${esc(d.label)}离目标最远（${d.score} 分）</b><span class="small">${esc(d.tip)}</span><span class="btn small primary">去练 ${esc(d.label)}</span></a>`;
    if (due) return `<a class="card psuggest" data-tap="practice-tip" href="#/review"><span class="tiny">今天建议</span><b>有 ${due} 个词等你复习</b><span class="small">先复习再学新的，记得最牢。</span><span class="btn small primary">开始复习</span></a>`;
    return `<a class="card psuggest" data-tap="practice-tip" href="#/"><span class="tiny">今天建议</span><b>先做今天的计划</b><span class="small">今日页已经按你的水平排好了顺序。</span><span class="btn small primary">打开今日</span></a>`;
  }


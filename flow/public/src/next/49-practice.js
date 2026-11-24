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
      ['#/exam', '考试练习', '中考高考、四六级、考研、专四专八、雅思，限时做'],
      ['#/radar', '能力雷达', '六项能力对照你的目标，定期测一测']]],
    ['看进步', [
      ['#/report', '这周的报告', '这周学了什么、哪里进步了'],
      ['#/growth', '我的进步', '这个月和上个月比，里程碑']]]];

  async function practiceView() {
    const st = S.home && S.home.stats, due = st ? (st.due || 0) + (st.new || 0) : 0;
    view.innerHTML = `<h1 class="h1">练习</h1>
      <p class="muted small">想练哪一项，就从这里进。不知道先练什么，看最上面的建议。</p>
      <div id="pSuggest">${practiceTip(null, due)}</div>
      ${PRACTICE.map(([group, items]) => `<section class="pgroup stack-s"><h2 class="h2 pgroup-h">${group}</h2><div class="ptiles">
        ${items.map(([href, title, line, badge]) => badge === 'map' ? mapTile(href, title, line)
          : `<a class="ptile card flat" href="${href}"><b>${title}${badge === 'due' && due ? ` <i class="pbadge">${due > 99 ? '99+' : due}</i>` : ''}</b><span class="small muted">${line}</span></a>`).join('')}
      </div></section>`).join('')}
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


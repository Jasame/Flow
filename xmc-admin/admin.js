/* xmc.hk/flow · 语流 Flow 运营后台。数据来自 /flow/api/（只在 xmc.hk 的 Cloudflare Access 后面可达）。 */
(function () {
  'use strict';
  var API = '/flow/api';
  var main = document.getElementById('main');
  var ST = { tab: 'overview', filters: { role: '', level: '', flow: '' }, page: 1, q: '', def: null };
  var DIST = ['#d4553f', '#e79a4a', '#c9c9c2', '#7cc79c', '#1f9d55'];

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function n(v) { return Number(v || 0).toLocaleString('zh-CN'); }
  function pct(a, b) { return b ? Math.round(100 * a / b) : 0; }
  function getJSON(path) {
    return fetch(API + path, { credentials: 'same-origin' }).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (j) {
        if (!r.ok) throw new Error(j.error || ('HTTP ' + r.status));
        return j;
      });
    });
  }
  function postJSON(path, body) {
    return fetch(API + path, {
      method: 'POST', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'xmc' },
      body: JSON.stringify(body)
    }).then(function (r) { return r.json().then(function (j) { if (!r.ok) throw new Error(j.error || ('HTTP ' + r.status)); return j; }); });
  }
  function fail(e) { main.innerHTML = '<div class="card"><p class="err">' + esc(e.message) + '</p><p class="muted">Flow 服务没有启动管理端口，或 nginx 的 /flow/api/ 转发没有配置。</p></div>'; }

  function bars(options, total, opts) {
    opts = opts || {};
    if (total == null) total = options.reduce(function (a, o) { return a + o.count; }, 0);
    var max = Math.max.apply(null, options.map(function (o) { return o.count; }).concat([1]));
    var list = opts.sort ? options.slice().sort(function (a, b) { return b.count - a.count; }) : options;
    return '<div class="bars">' + list.map(function (o) {
      return '<div class="bar' + (o.count === max && o.count > 0 ? ' top' : '') + '"><span class="bar-label">' + esc(o.label) + '</span>' +
        '<span class="bar-val">' + n(o.count) + ' · ' + pct(o.count, total) + '%</span>' +
        '<div class="bar-track"><div class="bar-fill" style="width:' + pct(o.count, max) + '%"></div></div></div>';
    }).join('') + '</div>';
  }

  /* ---------- 概览 ---------- */
  function overview() {
    getJSON('/overview').then(function (d) {
      var ai = d.ai, max = Math.max.apply(null, ai.week.map(function (x) { return x.count; }).concat([1]));
      main.innerHTML =
        '<div class="head-row"><div><h1>语流 Flow 概览</h1><p class="muted">flow.jasa.hk · 更新于 ' + new Date(d.generated_at * 1000).toLocaleString('zh-CN') + '</p></div>' +
        '<div class="toolbar"><button class="btn" id="reload">刷新</button></div></div>' +
        '<div class="kpi-grid">' +
          kpi('注册用户', n(d.users), '其中管理员 ' + n(d.admins)) +
          kpi('近 7 天活跃', n(d.active_7d), '近 24 小时 ' + n(d.active_1d) + ' 人') +
          kpi('今日 AI 调用', n(ai.today), ai.site_limit ? ('全站上限 ' + n(ai.site_limit) + ' · 已用 ' + pct(ai.today, ai.site_limit) + '%') : '全站不设上限') +
          kpi('问卷回答', n(d.survey_responses), '<a href="#survey" style="color:var(--accent)">查看统计 →</a>') +
        '</div>' +
        '<div class="grid2">' +
          '<section class="card"><h2>近 7 天 AI 调用</h2>' +
            '<div class="spark">' + ai.week.map(function (x) { return '<div title="' + esc(x.day + '：' + x.count) + '" style="height:' + Math.max(3, pct(x.count, max)) + '%"></div>'; }).join('') + '</div>' +
            '<div class="spark-days">' + ai.week.map(function (x) { return '<span>' + esc(x.day.slice(5)) + '</span>'; }).join('') + '</div></section>' +
          '<section class="card"><h2>AI 额度设置</h2><div class="resp-grid">' +
            '<dt>模型</dt><dd>' + esc(ai.model || '未配置') + '</dd>' +
            '<dt>每账号每日上限</dt><dd>' + (ai.user_limit ? n(ai.user_limit) + ' 次（管理员不受限）' : '不限') + '</dd>' +
            '<dt>全站每日上限</dt><dd>' + (ai.site_limit ? n(ai.site_limit) + ' 次' : '不限') + '</dd>' +
            '<dt>今天用满的账号</dt><dd>' + n(ai.users_at_limit) + '</dd>' +
            '<dt>重置时间</dt><dd>每天北京时间 08:00（UTC 0 点）</dd>' +
            '<dt>修改方式</dt><dd class="muted">服务器 /etc/flow.env 中的 FLOW_AI_USER_DAILY_LIMIT、FLOW_AI_DAILY_LIMIT，改后重启 flow</dd>' +
          '</div></section>' +
        '</div>';
      document.getElementById('reload').onclick = overview;
    }).catch(fail);
  }
  function kpi(label, val, sub) { return '<div class="kpi"><div class="kpi-label">' + label + '</div><div class="kpi-val">' + val + '</div><div class="kpi-sub">' + sub + '</div></div>'; }

  /* ---------- 问卷统计 ---------- */
  function filterSelect(id, q) {
    if (!q) return '';
    return '<label class="muted" style="font-size:12.5px">' + esc(q.label.replace(/[？?].*$/, '')) + ' <select data-filter="' + id + '"><option value="">全部</option>' +
      q.options.map(function (o) { return '<option' + (ST.filters[id] === o ? ' selected' : '') + '>' + esc(o) + '</option>'; }).join('') + '</select></label>';
  }
  function surveyStats() {
    var qs = Object.keys(ST.filters).filter(function (k) { return ST.filters[k]; }).map(function (k) { return k + '=' + encodeURIComponent(ST.filters[k]); }).join('&');
    Promise.all([ST.def ? Promise.resolve(ST.def) : getJSON('/survey/definition'), getJSON('/survey/summary' + (qs ? '?' + qs : ''))]).then(function (res) {
      var def = ST.def = res[0], s = res[1];
      var byId = {}; def.sections.forEach(function (sec) { sec.questions.forEach(function (q) { byId[q.id] = q; }); });
      var max = Math.max.apply(null, s.by_day.map(function (x) { return x.count; }).concat([1]));
      var html =
        '<div class="head-row"><div><h1>' + esc(s.survey.title) + '</h1><p class="muted">匿名问卷 · 共 ' + n(s.total) + ' 份有效回答' +
          (s.hidden ? '（另有 ' + n(s.hidden) + ' 份已隐藏）' : '') + (s.median_seconds ? ' · 中位用时 ' + Math.round(s.median_seconds / 60 * 10) / 10 + ' 分钟' : '') + '</p></div>' +
        '<div class="toolbar"><a class="btn" href="https://flow.jasa.hk/survey" target="_blank" rel="noopener">问卷链接</a><button class="btn" id="copyLink">复制链接</button><a class="btn primary" href="' + API + '/survey/export.csv">导出 CSV</a></div></div>' +
        '<div class="card toolbar">' + filterSelect('role', byId.role) + filterSelect('level', byId.level) + filterSelect('flow', byId.flow) +
          (qs ? '<button class="btn" id="clearF">清除筛选</button>' : '') + '</div>';
      if (!s.total) {
        main.innerHTML = html + '<div class="card empty">' + (qs ? '这个筛选条件下还没有回答。' : '还没有人填写。把问卷链接 https://flow.jasa.hk/survey 发出去吧。') + '</div>';
        bindStats(); return;
      }
      if (s.by_day.length > 1) {
        html += '<section class="card"><h2>每日回收</h2><div class="spark">' + s.by_day.slice(-30).map(function (x) { return '<div title="' + esc(x.day + '：' + x.count) + '" style="height:' + Math.max(3, pct(x.count, max)) + '%"></div>'; }).join('') + '</div></section>';
      }
      var cards = s.questions.map(function (q) {
        var head = '<h2>' + esc(q.label) + '</h2><p class="muted" style="margin:-8px 0 12px;font-size:12px">' + n(q.answered) + ' 人作答' + (q.type === 'multi' ? ' · 多选，比例按作答人数计' : '') + '</p>';
        if (q.type === 'single' || q.type === 'multi') return '<section class="card">' + head + bars(q.options, q.answered, { sort: q.type === 'multi' }) + '</section>';
        if (q.type === 'matrix') {
          var rows = q.rows.slice().sort(function (a, b) { return (b.average || 0) - (a.average || 0); });
          return '<section class="card">' + head + '<div class="bars">' + rows.map(function (r) {
            var tot = r.distribution.reduce(function (a, b) { return a + b; }, 0) || 1;
            return '<div class="bar"><span class="bar-label">' + esc(r.label) + '</span><span class="bar-val">平均 ' + (r.average == null ? '—' : r.average.toFixed(2)) + ' / 5</span>' +
              '<div class="dist">' + r.distribution.map(function (c, i) { return '<i style="width:' + (100 * c / tot) + '%;background:' + DIST[i] + '" title="' + (i + 1) + ' 分：' + c + ' 人"></i>'; }).join('') + '</div></div>';
          }).join('') + '</div><div class="legend">' + DIST.map(function (c, i) { return '<span style="--c:' + c + '">' + (i + 1) + ' 分</span>'; }).join('') + '</div></section>';
        }
        return '<section class="card" style="grid-column:1/-1">' + head + (q.samples.length ? '<div class="quotes">' + q.samples.map(function (x) {
          return '<div class="quote">' + esc(x.text) + '<small>#' + x.id + ' · ' + esc(x.day) + '</small></div>'; }).join('') + '</div>' : '<p class="muted">暂无</p>') +
          (q.answered > q.samples.length ? '<p class="muted" style="margin-top:8px;font-size:12px">只显示最近 ' + q.samples.length + ' 条，完整内容见「逐条回答」或导出 CSV。</p>' : '') + '</section>';
      });
      main.innerHTML = html + '<div class="grid2">' + cards.join('') + '</div>';
      bindStats();
    }).catch(fail);
  }
  function bindStats() {
    main.querySelectorAll('[data-filter]').forEach(function (el) {
      el.onchange = function () { ST.filters[el.dataset.filter] = el.value; surveyStats(); };
    });
    var c = document.getElementById('clearF'); if (c) c.onclick = function () { ST.filters = { role: '', level: '', flow: '' }; surveyStats(); };
    var cp = document.getElementById('copyLink');
    if (cp) cp.onclick = function () {
      var url = 'https://flow.jasa.hk/survey';
      (navigator.clipboard ? navigator.clipboard.writeText(url) : Promise.reject()).then(function () { cp.textContent = '已复制'; }, function () { prompt('复制问卷链接', url); });
    };
  }

  /* ---------- 逐条回答 ---------- */
  function fmt(q, v) {
    if (v == null || v === '') return '<span class="muted">未填</span>';
    if (Array.isArray(v)) return esc(v.join('；'));
    if (typeof v === 'object') return (q && q.rows ? q.rows : Object.keys(v)).map(function (r) { return esc(r) + '：' + (v[r] || '—'); }).join('<br>');
    return esc(v);
  }
  function responses() {
    Promise.all([ST.def ? Promise.resolve(ST.def) : getJSON('/survey/definition'), getJSON('/survey/responses?page=' + ST.page + '&q=' + encodeURIComponent(ST.q))]).then(function (res) {
      var def = ST.def = res[0], d = res[1];
      var qs = []; def.sections.forEach(function (s) { qs = qs.concat(s.questions); });
      var pages = Math.max(1, Math.ceil(d.total / d.per_page));
      main.innerHTML =
        '<div class="head-row"><div><h1>逐条回答</h1><p class="muted">共 ' + n(d.total) + ' 条（含已隐藏）。隐藏的回答不计入统计，也不导出。</p></div>' +
        '<form class="toolbar" id="searchF"><input class="input" id="q" type="search" placeholder="搜索回答内容" value="' + esc(ST.q) + '"><button class="btn">搜索</button></form></div>' +
        (d.items.length ? '<div class="resp">' + d.items.map(function (r) {
          return '<article class="resp-item' + (r.hidden ? ' hidden' : '') + '"><div class="resp-head"><b>#' + r.id + '</b>' +
            '<span class="muted">' + esc(new Date(r.created * 1000).toLocaleString('zh-CN')) + ' · 用时 ' + Math.round((r.seconds || 0) / 60 * 10) / 10 + ' 分钟</span>' +
            '<span>' + (r.hidden ? '<span class="pill off">已隐藏</span> ' : '') + '<button class="btn" data-hide="' + r.id + '" data-v="' + (r.hidden ? 0 : 1) + '">' + (r.hidden ? '恢复' : '隐藏（无效回答）') + '</button></span></div>' +
            '<dl class="resp-grid">' + qs.map(function (q) { return '<dt>' + esc(q.label) + '</dt><dd>' + fmt(q, r.answers[q.id]) + '</dd>'; }).join('') + '</dl></article>';
        }).join('') + '</div>' : '<div class="card empty">没有找到回答。</div>') +
        (pages > 1 ? '<div class="pager"><button class="btn" id="prev"' + (ST.page <= 1 ? ' disabled' : '') + '>上一页</button><span class="muted num">' + ST.page + ' / ' + pages + '</span><button class="btn" id="next"' + (ST.page >= pages ? ' disabled' : '') + '>下一页</button></div>' : '');
      document.getElementById('searchF').onsubmit = function (e) { e.preventDefault(); ST.q = document.getElementById('q').value.trim(); ST.page = 1; responses(); };
      var p = document.getElementById('prev'), nx = document.getElementById('next');
      if (p) p.onclick = function () { ST.page--; responses(); };
      if (nx) nx.onclick = function () { ST.page++; responses(); };
      main.querySelectorAll('[data-hide]').forEach(function (b) {
        b.onclick = function () {
          b.disabled = true;
          postJSON('/survey/hide', { id: Number(b.dataset.hide), hidden: b.dataset.v === '1' }).then(responses).catch(function (e) { alert(e.message); b.disabled = false; });
        };
      });
    }).catch(fail);
  }

  /* ---------- 学习数据 ---------- */
  var BOOK = { core: '基础', mid: '进阶', high: '高阶', adv: '精通', ext: '拓展', cet4: '四级', cet6: '六级', ky: '考研', ielts: '雅思', toefl: '托福', gre: 'GRE' };
  var STEP = { listen: '听', read: '读', check: '理解题', output: '用出来（AI 改写）' };
  var AIK = { 'next-rewrite': '仿写改写', 'next-explain': '句子讲解', 'next-variant': '难度改写', 'next-shadow': '跟读点评', 'next-examples': 'AI 例句',
    'next-retell': '复述', 'next-dialog': '情景对话', 'next-essay': '短文批改', 'next-translate': '翻译批改', 'next-transsrc': '翻译原句', 'next-say': '发音检查', 'next-enrich': '导入文章出题' };
  var RATE = { again: '忘了', hard: '模糊', good: '记得', easy: '很熟', known: '标为熟知', used: '写作用对', misused: '写作用错', lookup: '阅读时查词' };
  function learningView() {
    getJSON('/learning').then(function (d) {
      var max = Math.max.apply(null, d.active_days.map(function (x) { return x.count; }).concat([1]));
      var c = d.cohort, f = d.funnel_7d;
      var list = function (obj, names) {
        var keys = Object.keys(obj || {}); if (!keys.length) return '<p class="muted">暂无数据</p>';
        return bars(keys.map(function (k) { return { label: names[k] || k, count: obj[k] }; }), null, { sort: true });
      };
      main.innerHTML =
        '<div class="head-row"><div><h1>学习数据</h1><p class="muted">按北京时间统计 · 更新于 ' + new Date(d.generated_at * 1000).toLocaleString('zh-CN') + '</p></div>' +
        '<div class="toolbar"><button class="btn" id="reload">刷新</button></div></div>' +
        '<div class="kpi-grid">' +
          kpi('今天在学', n(d.active_today), '近 7 天 ' + n(d.active_7d) + ' 人 · 近 30 天 ' + n(d.active_30d) + ' 人') +
          kpi('次日回来', c.joined ? pct(c.d1, c.joined) + '%' : '—', '近 30 天开始学习的 ' + n(c.joined) + ' 人；一周内回来 ' + (c.joined ? pct(c.week, c.joined) + '%' : '—')) +
          kpi('近 7 天复习', n(d.reviews_7d), d.true_retention == null ? '还没有隔天的复习' : '隔天复习记得的比例 ' + Math.round(d.true_retention * 100) + '%（目标约 90%）') +
          kpi('开了背词计划', n(Object.keys(d.vocab_plans).reduce(function (a, k) { return a + d.vocab_plans[k]; }, 0)), '开启复习提醒 ' + n(d.reminders_on) + ' 人 · 全站单词卡 ' + n(d.cards_total)) +
        '</div>' +
        '<section class="card"><h2>近 14 天每天在学的人数</h2>' +
          '<div class="spark">' + d.active_days.map(function (x) { return '<div title="' + esc(x.day + '：' + x.count + ' 人') + '" style="height:' + Math.max(3, pct(x.count, max)) + '%"></div>'; }).join('') + '</div>' +
          '<div class="spark-days">' + d.active_days.map(function (x, i) { return '<span>' + (i % 2 ? '' : esc(x.day.slice(5))) + '</span>'; }).join('') + '</div></section>' +
        '<div class="grid2">' +
          '<section class="card"><h2>近 7 天学习步骤</h2><p class="muted">每篇材料完成到哪一步（次数）。从「读」到「用出来」掉得越多，越说明后面的步骤需要更好的引导。</p>' +
            bars(['listen', 'read', 'check', 'output'].map(function (k) { return { label: STEP[k], count: f[k] || 0 }; }), null, {}) + '</section>' +
          '<section class="card"><h2>近 7 天复习的选择</h2>' + list(d.ratings_7d, RATE) + '</section>' +
          '<section class="card"><h2>词书选择</h2>' + list(d.vocab_plans, BOOK) + '</section>' +
          '<section class="card"><h2>近 7 天新加的词</h2>' + list(d.words_added_7d, { book: '词书每日新词', saved: '读文章时收藏', import: '自己导入' }) + '</section>' +
          '<section class="card"><h2>近 7 天 AI 功能使用</h2>' + list(d.ai_7d, AIK) + '</section>' +
          '<section class="card"><h2>近 7 天最多人学的材料</h2>' + (d.top_materials_7d.length ? bars(d.top_materials_7d.map(function (m) { return { label: m.title, count: m.learners }; }), null, {}) : '<p class="muted">暂无数据</p>') +
            '<p class="muted">共 ' + n(d.materials) + ' 篇精选材料</p></section>' +
        '</div>';
      document.getElementById('reload').onclick = learningView;
    }).catch(fail);
  }

  /* ---------- 路由 ---------- */
  function route() {
    ST.tab = (location.hash || '#overview').slice(1);
    if (['overview', 'learning', 'survey', 'responses'].indexOf(ST.tab) < 0) ST.tab = 'overview';
    document.querySelectorAll('.adm-tabs a').forEach(function (a) {
      if (a.dataset.tab === ST.tab) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current');
    });
    main.innerHTML = '<p class="muted">正在加载…</p>';
    ({ overview: overview, learning: learningView, survey: surveyStats, responses: responses })[ST.tab]();
  }
  document.getElementById('themeBtn').onclick = function () {
    var next = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem('xmc-theme', next); } catch (e) { /* ignore */ }
  };
  window.addEventListener('hashchange', route);
  route();
})();

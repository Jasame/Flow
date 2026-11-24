/* xmc.hk/flow · 语流 Flow 运营后台。数据来自 /flow/api/（只在 xmc.hk 的 Cloudflare Access 后面可达）。 */
(function () {
  'use strict';
  var API = '/flow/api';
  var main = document.getElementById('main');
  var ST = { tab: 'overview', filters: { role: '', level: '', flow: '' }, page: 1, q: '', def: null, me: null };
  // 管理员 sees everything and may change things; 只看数据 sees the numbers only (the server enforces it, the page just
  // leaves out what would answer 403).
  function isAdmin() { return !ST.me || ST.me.role === 'admin'; }
  function when(t) { return t ? new Date(t * 1000).toLocaleString('zh-CN', { hour12: false }) : '—'; }
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
        '<div class="head-row"><div><h1>语流 Flow 概览</h1><p class="muted">flowlang.cn · ' + (d.server ? '数据来自' + esc(d.server) + ' · ' : '') + '更新于 ' + new Date(d.generated_at * 1000).toLocaleString('zh-CN') + '</p></div>' +
        '<div class="toolbar"><button class="btn" id="reload">刷新</button></div></div>' +
        '<div class="kpi-grid">' +
          kpi('注册用户', n(d.users), d.admins ? '其中 ' + n(d.admins) + ' 个员工账号，AI 次数不限' : '学习网站上没有管理功能') +
          kpi('近 7 天活跃', n(d.active_7d), '近 24 小时 ' + n(d.active_1d) + ' 人') +
          kpi('今日 AI 调用', n(ai.today), ai.site_limit ? ('全站上限 ' + n(ai.site_limit) + ' · 已用 ' + pct(ai.today, ai.site_limit) + '%') : '全站不设上限') +
          kpi('问卷回答', n(d.survey_responses), '<a href="#survey" style="color:var(--accent)">查看统计 →</a>') +
          (isAdmin() && d.feedback_open != null ? kpi('待处理反馈', n(d.feedback_open), '<a href="#feedback" style="color:var(--accent)">去处理 →</a>') : '') +
        '</div>' +
        '<div class="grid2">' +
          '<section class="card"><h2>近 7 天 AI 调用</h2>' +
            '<div class="spark">' + ai.week.map(function (x) { return '<div title="' + esc(x.day + '：' + x.count) + '" style="height:' + Math.max(3, pct(x.count, max)) + '%"></div>'; }).join('') + '</div>' +
            '<div class="spark-days">' + ai.week.map(function (x) { return '<span>' + esc(x.day.slice(5)) + '</span>'; }).join('') + '</div></section>' +
          '<section class="card"><h2>备份和每日热点</h2><div class="resp-grid">' +
            '<dt>最近备份</dt><dd>' + (d.backup ? (d.backup.ok ? '成功 · ' : '<span class="err">失败</span> · ') + esc(when(d.backup.created)) : '还没有备份记录') + '</dd>' +
            '<dt>今日热点</dt><dd>' + esc(({ complete: '已生成', running: '正在生成', failed: '生成失败', interrupted: '中断了', waiting: '还没生成' })[d.daily.status] || d.daily.status) +
              (d.daily.enabled ? '' : '（服务器没有开启联网检索，FLOW_AI_GROUNDING）') + (d.daily.error ? '<div class="muted">' + esc(d.daily.error) + '</div>' : '') + '</dd>' +
            '<dt>最近几天</dt><dd>' + (d.daily.latest.length ? d.daily.latest.map(function (x) { return esc(x.day.slice(5)); }).join('、') : '—') + '</dd>' +
          '</div>' + (isAdmin() ? '<p><button class="btn" id="dailyRun"' + (d.daily.status === 'complete' || d.daily.status === 'running' ? ' disabled' : '') + '>现在生成今日热点</button></p>' : '') + '</section>' +
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
      var dr = document.getElementById('dailyRun');
      if (dr) dr.onclick = function () {
        dr.disabled = true;
        postJSON('/daily/run', {}).then(function (r) { dr.textContent = r.message; }).catch(function (e) { alert(e.message); dr.disabled = false; });
      };
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
        '<div class="toolbar"><a class="btn" href="https://flowlang.cn/survey" target="_blank" rel="noopener">问卷链接</a><button class="btn" id="copyLink">复制链接</button>' + (isAdmin() ? '<a class="btn primary" href="' + API + '/survey/export.csv">导出 CSV</a>' : '') + '</div></div>' +
        '<div class="card toolbar">' + filterSelect('role', byId.role) + filterSelect('level', byId.level) + filterSelect('flow', byId.flow) +
          (qs ? '<button class="btn" id="clearF">清除筛选</button>' : '') + '</div>';
      if (!s.total) {
        main.innerHTML = html + '<div class="card empty">' + (qs ? '这个筛选条件下还没有回答。' : '还没有人填写。把问卷链接 https://flowlang.cn/survey 发出去吧。') + '</div>';
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
      var url = 'https://flowlang.cn/survey';
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

  // 页面报错: what learners' browsers reported (field_service.py), grouped by problem; which phones and releases.
  function clientIssues(c) {
    if (!c) return '';
    return '<div class="head-row fd-gap"><div><h1>页面报错</h1><p class="muted">学员的浏览器上报的问题（近 ' + c.days + ' 天，共 ' + n(c.total) + ' 次）：脚本出错、资源没加载出来、请求失败、声音放不出来。不记账号和地址。</p></div></div>' +
      (c.groups.length ? '<section class="card"><table class="cmp fd-issues"><thead><tr><th>问题</th><th>页面</th><th class="num">次数</th><th>手机和浏览器</th><th>版本</th></tr></thead><tbody>' +
        c.groups.map(function (g) {
          return '<tr><td><span class="pill">' + esc(g.kind_label) + '</span> ' + esc(g.message) + (g.source ? '<div class="muted small">' + esc(g.source) + '</div>' : '') + '</td>' +
            '<td>' + esc(g.page) + '</td><td class="num">' + n(g.count) + '<div class="muted small">' + g.days + ' 天</div></td>' +
            '<td class="small">' + g.platforms.map(function (x) { return esc(x[0]) + ' ' + n(x[1]); }).join('<br>') + '</td>' +
            '<td class="small">' + g.releases.map(function (x) { return esc(x[0]); }).join('、') + '</td></tr>';
        }).join('') + '</tbody></table></section>' : '<section class="card"><p>没有页面报错。</p></section>');
  }

  // 打开速度: how long learners waited for the first page (field_service.speed), and where the time went.
  var SP = { days: 7 };
  function speedView() {
    getJSON('/speed?days=' + SP.days).then(function (d) {
      var o = d.overall, sec = function (v) { return v == null ? '—' : (v / 1000).toFixed(1) + ' 秒'; };
      var PH = { dns: '查域名', connect: '建立连接', tls: '加密握手', ttfb: '服务器响应', html: '下载页面', scripts: '等脚本下载完', home_api: '取首页数据', render: '画出页面' };
      var tot = Object.keys(PH).reduce(function (a, k) { return a + (d.phases[k] || 0); }, 0) || 1;
      var table = function (title, rows) {
        return '<section class="card"><h2>' + title + '</h2><table class="cmp"><thead><tr><th></th><th class="num">打开次数</th><th class="num">中位数</th><th class="num">75%</th><th class="num">90%</th><th class="num">没等到就离开</th></tr></thead><tbody>' +
          rows.map(function (r) { return '<tr><td>' + esc(r.group) + '</td><td class="num">' + n(r.visits) + '</td><td class="num">' + sec(r.p50) + '</td><td class="num">' + sec(r.p75) + '</td><td class="num">' + sec(r.p90) + '</td><td class="num">' + r.left_pct + '%</td></tr>'; }).join('') +
          '</tbody></table></section>';
      };
      main.innerHTML = '<div class="head-row"><div><h1>打开速度</h1><p class="muted">学员打开网站后，多久看到第一个页面（每次打开记一次，不记账号和地址）。「75%」表示四分之三的人在这个时间内看到了页面。</p></div>' +
        '<div class="toolbar"><select id="spDays"><option value="7"' + (SP.days === 7 ? ' selected' : '') + '>近 7 天</option><option value="30"' + (SP.days === 30 ? ' selected' : '') + '>近 30 天</option></select></div></div>' +
        '<div class="kpi-grid">' + kpi('打开次数', n(o.visits), '近 ' + d.days + ' 天') + kpi('中位数', sec(o.p50), '一半的人在这个时间内看到页面') + kpi('90% 的人', sec(o.p90), '慢的那一成要等这么久') + kpi('没等到就离开', o.left_pct + '%', n(o.left) + ' 次，页面还没出来就关了') + '</div>' +
        (o.visits ? '<section class="card"><h2>时间花在哪（各段的中位数）</h2><div class="sp-bar">' + Object.keys(PH).map(function (k, i) {
          var v = d.phases[k]; return v ? '<i style="flex:' + v + ' 1 0;--k:' + i + '" title="' + esc(PH[k] + ' ' + sec(v)) + '"></i>' : '';
        }).join('') + '</div><div class="sp-legend">' + Object.keys(PH).map(function (k, i) {
          return '<span style="--k:' + i + '"><i></i>' + PH[k] + ' ' + sec(d.phases[k]) + '</span>';
        }).join('') + '</div><p class="muted small">「查域名」「建立连接」「加密握手」慢，多半是网络线路的问题；「服务器响应」「取首页数据」慢，是服务器的问题；「等脚本下载完」慢，是网页太大或网络带宽不够。</p></section>' +
          table('按访问的网址', d.by.domain) + table('按手机', d.by.platform) + table('按浏览器（微信、Safari…）', d.by.browser) +
          table('先显示上次的内容 / 等服务器的回答', d.by.snap || []) + table('第一次打开 / 再次打开', d.by.repeat) + table('从桌面打开 / 在浏览器里', d.by.standalone) + table('按网络（安卓浏览器会告诉）', d.by.net) +
          table('按天', d.daily.map(function (x) { return Object.assign({ group: x.day }, x); })) : '<section class="card"><p class="muted">还没有数据：发版后学员打开网站就会开始记录。</p></section>');
      document.getElementById('spDays').onchange = function (e) { SP.days = Number(e.target.value); speedView(); };
    }).catch(fail);
  }

  function errorsView() {
    getJSON('/errors').then(function (d) {
      var t = function (s) { return new Date(s * 1000).toLocaleString('zh-CN'); };
      main.innerHTML =
        '<div class="head-row"><div><h1>服务器错误</h1><p class="muted">学习者看到「服务暂时异常」的请求，按出错位置分组（近 ' + d.days + ' 天，只记路径，不记提交的内容）</p></div>' +
        '<div class="toolbar"><button class="btn" id="reload">刷新</button></div></div>' +
        '<div class="kpi-grid">' + kpi('近 24 小时', n(d.last_24h), '次') + kpi('近 ' + d.days + ' 天', n(d.total), '次，' + n(d.groups.length) + ' 处代码') + '</div>' +
        (d.groups.length ? d.groups.map(function (g) {
          return '<section class="card"><h2>' + esc(g.kind) + '：' + esc(g.message || '') + '</h2>' +
            '<p class="muted">' + n(g.count) + ' 次 · 最近 ' + esc(t(g.last)) + ' · 最早 ' + esc(t(g.first)) + '</p>' +
            '<p>' + g.paths.map(esc).join('<br>') + '</p>' +
            '<details><summary>最近一次的调用栈</summary><pre class="trace">' + esc(g.trace) + '</pre></details></section>';
        }).join('') : '<section class="card"><p>没有错误。</p></section>') + clientIssues(d.client);
      document.getElementById('reload').onclick = errorsView;
    }).catch(fail);
  }

  /* ---------- 账号：给忘了密码、又没绑定邮箱的学习者生成一次性重设链接 ---------- */
  function accountsView(q) {
    q = q == null ? (ST.aq || '') : q; ST.aq = q;
    getJSON('/users' + (q ? '?q=' + encodeURIComponent(q) : '')).then(function (d) {
      main.innerHTML =
        '<div class="head-row"><div><h1>账号</h1><p class="muted">学习者忘了密码：绑定过邮箱的，让他在登录框点「忘记密码？」自己找回；没绑定邮箱的，在这里生成一次性重设链接发给他本人。</p></div>' +
        '<form class="toolbar" id="accF"><input class="input" id="aq" type="search" placeholder="用户名或邮箱" value="' + esc(q) + '"><button class="btn">搜索</button></form></div>' +
        '<div class="kpi-grid">' + kpi('账号', n(d.total), '个') + kpi('没绑定邮箱', n(d.without_email), '个，忘了密码只能在这里重设') + '</div>' +
        '<section class="card"><h2>' + (q ? '搜索结果' : '最近注册的 30 个') + '</h2>' +
        (d.users.length ? '<div class="acc-list">' + d.users.map(function (u) {
          return '<div class="acc-row"><div><b>' + esc(u.username) + '</b><div class="muted">' + (u.has_email ? esc(u.email) : '没有绑定邮箱') + '</div></div>' +
            '<button class="btn" data-reset="' + esc(u.username) + '">生成重设链接</button></div>';
        }).join('') + '</div>' : '<p class="muted">没有找到。</p>') + '</section>' +
        '<section class="card" id="accOut" hidden></section>';
      document.getElementById('accF').onsubmit = function (e) { e.preventDefault(); accountsView(document.getElementById('aq').value.trim()); };
      main.querySelectorAll('[data-reset]').forEach(function (b) {
        b.onclick = function () {
          var name = b.getAttribute('data-reset');
          if (!confirm('给「' + name + '」生成重设密码的链接？\n\n先确认对方是本人。链接 24 小时内有效、只能用一次；生成新链接后，旧链接作废。')) return;
          b.disabled = true;
          postJSON('/users/reset-link', { user: name }).then(function (r) {
            var out = document.getElementById('accOut'); out.hidden = false;
            out.innerHTML = '<h2>「' + esc(r.username) + '」的重设链接</h2>' +
              '<p><input class="input acc-link" id="accLink" readonly value="' + esc(r.link) + '"> <button class="btn" id="accCopy" type="button">复制</button></p>' +
              '<p class="muted">' + r.hours + ' 小时内有效，只能用一次。请当面或私信发给本人，不要发到群里。对方打开链接、设好新密码后，用新密码登录。这个链接只显示这一次。</p>';
            document.getElementById('accCopy').onclick = function () {
              var i = document.getElementById('accLink'); i.select();
              (navigator.clipboard ? navigator.clipboard.writeText(i.value) : Promise.reject()).then(function () { document.getElementById('accCopy').textContent = '已复制'; }, function () { document.execCommand('copy'); });
            };
            out.scrollIntoView({ block: 'center' }); b.disabled = false;
          }).catch(function (e) { alert(e.message); b.disabled = false; });
        };
      });
    }).catch(fail);
  }

  /* ---------- 发版对比：发版前后各几天的日均数字，和几个入口的点击次数 ---------- */
  function compareView() {
    getJSON('/releases').then(function (rel) {
      var at = ST.at || (rel.items[0] && rel.items[0].at) || null, days = ST.days || 14;
      var pick = '<form class="toolbar" id="cmpF"><label class="muted">发版 <select id="cmpRel"><option value="">按日期</option>' + rel.items.map(function (r) {
          return '<option value="' + r.at + '"' + (Number(r.at) === Number(at) ? ' selected' : '') + '>' + esc(r.tag) + ' · ' + esc(when(r.at)) + '</option>'; }).join('') + '</select></label>' +
        '<label class="muted">或日期 <input class="input" type="date" id="cmpDay"></label>' +
        '<label class="muted">前后各 <select id="cmpDays">' + [7, 14, 30].map(function (x) { return '<option' + (x === days ? ' selected' : '') + '>' + x + '</option>'; }).join('') + '</select> 天</label></form>';
      var head = '<div class="head-row"><div><h1>发版对比</h1><p class="muted">发版前后各 ' + days + ' 天的日均数字（北京时间）。发版后不满 ' + days + ' 天的，按已经过去的天数算。</p></div>' + pick + '</div>';
      if (!at) { main.innerHTML = head + '<section class="card"><p>还没有记下发版时间。下一次发版后会自动记下；也可以先选一个日期。</p></section>'; return bindCmp(); }
      return getJSON('/compare?at=' + at + '&days=' + days).then(function (d) {
        var ch = function (b, a) { if (b == null || a == null) return '—'; if (!b) return a ? '新出现' : '—'; var p = Math.round(100 * (a - b) / b); return '<span class="' + (p > 0 ? 'up' : p < 0 ? 'down' : '') + '">' + (p > 0 ? '+' : '') + p + '%</span>'; };
        main.innerHTML = head +
          '<section class="card"><h2>' + esc(when(d.at)) + ' 前后</h2><p class="muted">发版后已经过了 ' + d.after_days + ' 天。人少的时候，几个人的变化就会让比例跳得很大；「新学员一周内回来的比例」要等发版满一周才准。</p>' +
          '<table class="cmp"><thead><tr><th></th><th class="num">发版前</th><th class="num">发版后</th><th class="num">变化</th></tr></thead><tbody>' + d.metrics.map(function (m) {
            return '<tr><td>' + esc(m.label) + '</td><td class="num">' + (m.before == null ? '—' : m.before) + '</td><td class="num">' + (m.after == null ? '—' : m.after) + '</td><td class="num">' + ch(m.before, m.after) + '</td></tr>'; }).join('') +
          '</tbody></table></section>' +
          '<section class="card"><h2>入口点击（合计次数）</h2><p class="muted">学习网站上几个入口被点了多少次，只按天计数，不记是谁。发版当天前后都不算。</p>' + (d.taps.length ?
          '<table class="cmp"><thead><tr><th></th><th class="num">发版前</th><th class="num">发版后</th><th class="num">变化</th></tr></thead><tbody>' + d.taps.map(function (t) {
            return '<tr><td>' + esc(t.label) + '</td><td class="num">' + n(t.before) + '</td><td class="num">' + n(t.after) + '</td><td class="num">' + ch(t.before, t.after) + '</td></tr>'; }).join('') +
          '</tbody></table>' : '<p class="muted">还没有点击记录。</p>') + '</section>';
        bindCmp();
      });
    }).catch(fail);
    function bindCmp() {
      var f = document.getElementById('cmpF'); if (!f) return;
      document.getElementById('cmpRel').onchange = function (e) { ST.at = e.target.value || null; compareView(); };
      document.getElementById('cmpDay').onchange = function (e) { if (e.target.value) { ST.at = new Date(e.target.value + 'T00:00:00+08:00').getTime() / 1000; compareView(); } };
      document.getElementById('cmpDays').onchange = function (e) { ST.days = Number(e.target.value); compareView(); };
    }
  }

  /* ---------- 操作记录：管理员改了什么、导出了什么 ---------- */
  /* ---------- 问题反馈（只有管理员）：学员在「我的 → 问题反馈」提交的说明和截图 ---------- */
  var FB = { status: 'new', page: 1 };
  function fbBadge(k) {
    var b = document.getElementById('fbBadge');
    if (b) { b.textContent = k > 99 ? '99+' : String(k || 0); b.hidden = !k; }
  }
  function feedbackView() {
    getJSON('/feedback?status=' + FB.status + '&page=' + FB.page).then(function (d) {
      fbBadge(d.counts.new);
      var dev = function (v) {
        var bits = [];
        if (v.w) bits.push(v.w + '×' + v.h + (v.dpr ? ' @' + v.dpr + 'x' : ''));
        bits.push(v.theme === 'dark' ? '深色' : '浅色');
        if (v.standalone) bits.push('从桌面打开');
        if (v.wechat) bits.push('在微信里');
        if (v.asset) bits.push('页面 ' + v.asset);
        return bits.join(' · ');
      };
      var filters = [['new', '待处理', d.counts.new], ['done', '已处理', d.counts.done], ['all', '全部', d.counts.new + d.counts.done]];
      main.innerHTML = '<div class="head-row"><div><h1>问题反馈</h1><p class="muted">学员在「我的 → 问题反馈」提交的说明和截图。处理完点「标记已处理」，会记进操作记录。</p></div>' +
        '<div class="toolbar">' + filters.map(function (f) {
          return '<button type="button" class="btn' + (FB.status === f[0] ? ' primary' : '') + '" data-fs="' + f[0] + '">' + f[1] + ' ' + n(f[2]) + '</button>';
        }).join('') + '</div></div>' +
        (d.items.length ? d.items.map(function (x) {
          var v = x.device || {};
          return '<section class="card fb-item"><div class="fb-head"><b>' + esc(x.kind_label) + '</b><span class="pill' + (x.status === 'new' ? '' : ' off') + '">' + esc(x.status_label) + '</span>' +
            '<span class="muted">#' + x.id + ' · ' + when(x.created) + ' · ' + esc(x.who) + (x.release ? ' · ' + esc(x.release) : '') + '</span></div>' +
            '<p class="fb-text">' + esc(x.text) + '</p>' +
            (x.images.length ? '<div class="fb-imgs">' + x.images.map(function (nm) {
              var u = API + '/feedback/image?id=' + x.id + '&n=' + encodeURIComponent(nm);
              return '<a href="' + u + '" target="_blank" rel="noopener" title="看原图"><img src="' + u + '" alt="截图" loading="lazy"></a>';
            }).join('') + '</div>' : '') +
            '<dl class="fb-meta"><dt>页面</dt><dd>' + (x.page ? '<a href="https://flow.jasa.hk/' + esc(x.page) + '" target="_blank" rel="noopener">' + esc(x.page) + '</a>' : '—') + '</dd>' +
            '<dt>设备</dt><dd>' + esc(dev(v)) + '<div class="muted small fb-ua">' + esc(v.ua || '') + '</div></dd>' +
            (x.contact ? '<dt>联系方式</dt><dd>' + esc(x.contact) + '</dd>' : '') +
            (v.errors && v.errors.length ? '<dt>页面报错</dt><dd><code class="fb-err">' + v.errors.map(esc).join('<br>') + '</code></dd>' : '') +
            (x.status === 'done' ? '<dt>处理</dt><dd>' + esc(x.handled_by || '—') + ' · ' + when(x.handled_at) + '</dd>' : '') + '</dl>' +
            '<div class="toolbar"><button type="button" class="btn' + (x.status === 'new' ? ' primary' : '') + '" data-fb="' + x.id + '" data-to="' + (x.status === 'new' ? 'done' : 'new') + '">' +
            (x.status === 'new' ? '标记已处理' : '重新打开') + '</button></div></section>';
        }).join('') : '<section class="card"><p class="muted">' + (FB.status === 'new' ? '没有待处理的反馈。' : '还没有反馈。') + '</p></section>') +
        (d.pages > 1 ? '<div class="toolbar"><button type="button" class="btn" id="fbPrev"' + (FB.page <= 1 ? ' disabled' : '') + '>上一页</button><span class="muted">' + FB.page + ' / ' + d.pages +
          '</span><button type="button" class="btn" id="fbNext"' + (FB.page >= d.pages ? ' disabled' : '') + '>下一页</button></div>' : '');
      main.querySelectorAll('[data-fs]').forEach(function (b) { b.onclick = function () { FB.status = b.dataset.fs; FB.page = 1; feedbackView(); }; });
      var pv = document.getElementById('fbPrev'), nx = document.getElementById('fbNext');
      if (pv) pv.onclick = function () { FB.page--; feedbackView(); };
      if (nx) nx.onclick = function () { FB.page++; feedbackView(); };
      main.querySelectorAll('[data-fb]').forEach(function (b) {
        b.onclick = function () {
          b.disabled = true;
          postJSON('/feedback/status', { id: Number(b.dataset.fb), status: b.dataset.to }).then(feedbackView).catch(function (e) { alert(e.message); b.disabled = false; });
        };
      });
    }).catch(fail);
  }

  function logView() {
    getJSON('/log').then(function (d) {
      main.innerHTML =
        '<div class="head-row"><div><h1>操作记录</h1><p class="muted">生成重设密码链接、隐藏问卷回答、导出问卷、生成今日热点，都记在这里：谁、什么时候、对哪一项。链接本身不记录。</p></div>' +
        '<div class="toolbar"><button class="btn" id="reload">刷新</button></div></div>' +
        (ST.me && !ST.me.roles_set ? '<section class="card"><p><b>现在所有能登录后台的人都是管理员。</b>想让一部分人只看数据：在服务器的 /etc/flow.env 里加一行 <code>FLOW_ADMIN_EMAILS=你的邮箱,另一个管理员的邮箱</code>，再重启 flow。不在名单里的人就只能看概览、学习数据、发版对比和问卷统计。</p></section>' : '') +
        '<section class="card">' + (d.items.length ? '<table class="cmp"><thead><tr><th>时间</th><th>谁</th><th>做了什么</th><th>对象</th><th>结果</th></tr></thead><tbody>' + d.items.map(function (r) {
          return '<tr><td>' + esc(when(r.created)) + '</td><td>' + esc(r.email) + '<div class="muted">' + esc(r.role_label) + '</div></td><td>' + esc(r.action_label) + '</td><td>' + esc(r.target) + '</td><td>' + esc(r.detail) + '</td></tr>'; }).join('') +
          '</tbody></table>' : '<p class="muted">还没有记录。</p>') + '</section>';
      document.getElementById('reload').onclick = logView;
    }).catch(fail);
  }

  /* ---------- 路由 ---------- */
  function route() {
    ST.tab = (location.hash || '#overview').slice(1);
    if (['overview', 'learning', 'compare', 'speed', 'errors', 'survey', 'responses', 'feedback', 'accounts', 'log'].indexOf(ST.tab) < 0) ST.tab = 'overview';
    if (!isAdmin() && ['errors', 'responses', 'feedback', 'accounts', 'log'].indexOf(ST.tab) >= 0) ST.tab = 'overview';
    document.querySelectorAll('.adm-tabs a').forEach(function (a) {
      if (a.dataset.tab === ST.tab) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current');
    });
    main.innerHTML = '<p class="muted">正在加载…</p>';
    ({ overview: overview, learning: learningView, compare: compareView, speed: speedView, errors: errorsView, survey: surveyStats, responses: responses, feedback: feedbackView, accounts: accountsView, log: logView })[ST.tab]();
  }
  document.getElementById('themeBtn').onclick = function () {
    var next = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem('xmc-theme', next); } catch (e) { /* ignore */ }
  };
  // Who is signed in (Cloudflare Access) and with which role; which server the data comes from (香港 or 杭州), on
  // every tab: the two panels look alike, the data must not.
  function whoAmI() {
    return getJSON('/me').then(function (me) {
      ST.me = me;
      var w = document.getElementById('who');
      if (w) { w.textContent = (me.email || '未识别的账号') + ' · ' + me.label; w.hidden = false; }
      var el = document.getElementById('srv');
      if (el && me.server) { el.textContent = '数据来自' + me.server; el.hidden = false; }
      document.querySelectorAll('.adm-tabs [data-admin]').forEach(function (a) { a.hidden = !isAdmin(); });
      if (isAdmin()) getJSON('/feedback?status=new&page=1').then(function (d) { fbBadge(d.counts.new); }).catch(function () { /* an older Flow */ });
    }).catch(function () { /* an older Flow without /me: everything as before */ });
  }
  window.addEventListener('hashchange', route);
  whoAmI().then(route);
})();

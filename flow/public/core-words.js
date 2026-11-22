'use strict';

let coreWordsQuery = {q: '', level: '', scope: 'all', page: '1'};
let coreWordsData = null;

async function openCoreWords(values = {}) {
  const owner = user.id;
  const epoch = ++flowEpoch;
  const request = {...coreWordsQuery, ...values};
  coreWordsQuery = request;
  view = 'vocab';
  stopRecording();
  shell(pagehead('核心词表', '正在加载分级词汇…'));
  try {
    const data = await api('vocab/core?' + new URLSearchParams(request));
    if (!flowCurrent(owner, epoch) || view !== 'vocab') return;
    coreWordsData = data;
    renderCoreWords(data, request);
  } catch (error) {
    if (!flowCurrent(owner, epoch) || view !== 'vocab') return;
    shell(pagehead('核心词表', esc(error.message)) + '<button class="btn" data-core-words="1">重新加载</button>');
  }
}

function renderCoreWords(data, request) {
  const select = (id, name, label, choices) => `<label for="${id}">${label}</label>
    <select id="${id}" name="${name}">${choices.map(([key, text]) =>
      `<option value="${key}" ${request[name] === key ? 'selected' : ''}>${text}</option>`).join('')}</select>`;
  shell(pagehead('核心词表', data.core_count.toLocaleString('zh-CN') + ' 个词形 · A1–C1 · 测试期间免费') +
    `<div class="actions"><button class="quiet-button" data-view="vocab">返回练习词库</button>
    <button class="quiet-button" data-reference-home="1">打开完整参考词典</button></div>
    <form id="core-words-search" class="corpus-search" method="post">
    <label class="sr-only" for="core-word-query">搜索核心词表</label>
    <input id="core-word-query" name="q" maxlength="100" type="search" value="${esc(request.q)}" placeholder="输入英文词头或中文释义">
    ${select('core-word-level', 'level', '级别', [['', '全部'], ...['A1','A2','B1','B2','C1'].map(level => [level, level])])}
    ${select('core-word-scope', 'scope', '内容', [['all','全部'],['examples','带例句'],['cloze','可填空']])}
    <button class="btn">搜索</button></form>
    <p class="small muted">词表等级来自 <a href="https://github.com/X-Trivle/LexiCore">LexiCore-5000 v1.0.0</a>（<a href="https://creativecommons.org/licenses/by/4.0/">CC BY 4.0</a>）。
    Flow 补充缺少的中文释义并添加教学词卡。来源词典的例句尚未全面校对。</p>
    <p role="status" id="core-words-status">${data.total.toLocaleString('zh-CN')} 项 · 第 ${data.page} / ${data.pages} 页</p>
    <div class="reference-grid">${data.items.map((item, index) => `<article class="card reference-word">
      <p class="small muted">${esc(item.level)}</p><h2 lang="en">${esc(item.word)}</h2>
      ${item.phonetic ? `<p class="small muted">${esc(item.phonetic)}</p>` : ''}
      <p>${esc(item.meaning)}</p>${item.study_card ? `<p class="small">教学词卡：${esc(item.study_card.meaning)}</p>` : ''}<p class="small muted">${item.meaning_source === 'Flow' ? 'Flow 补充释义' : '来源词典释义'}</p>
      ${item.cloze ? `<details><summary>做一道填空题</summary>
        <form method="post" class="core-word-cloze" data-item="${index}">
          <p lang="en">${esc(item.cloze.prompt)}</p><p>${esc(item.cloze.translation)}</p><small>${esc(item.cloze.source)} · 此题即时核对</small>
          <label class="sr-only" for="core-cloze-${index}">填写缺少的英文词</label>
          <input id="core-cloze-${index}" name="answer" maxlength="80" required autocomplete="off" spellcheck="false">
          <button class="quiet-button">核对</button><p role="status"></p>
        </form></details>` : ''}
      ${item.examples.length ? `<details><summary>查看来源例句</summary>
        ${item.examples.map(ex => `<p lang="en">${esc(ex.english)}</p><p class="small muted">${esc(ex.translation)}</p>`).join('')}</details>` : ''}
      <div class="actions">${item.study_entry ? `<button class="text-button" data-flow-word="${esc(item.study_entry)}">打开教学词卡</button>` : ''}
      ${item.reference ? `<button class="text-button" data-reference-entry="${esc(item.reference)}">查看来源与用法</button>` : ''}
      <button class="text-button" data-flow-pronounce="${esc(item.word)}">朗读</button></div>
    </article>`).join('') || '<p>没有匹配项。可以换一个词或调整筛选条件。</p>'}</div>
    <div class="actions"><button class="quiet-button" data-core-page="${data.page - 1}" ${data.page === 1 ? 'disabled' : ''}>上一页</button>
    <button class="quiet-button" data-core-page="${data.page + 1}" ${data.page === data.pages ? 'disabled' : ''}>下一页</button></div>`);
}

app.addEventListener('click', event => {
  const button = event.target.closest('button');
  if (!button || !user) return;
  if (button.dataset.coreWords) {
    coreWordsQuery = {q: '', level: '', scope: 'all', page: '1'};
    openCoreWords();
  }
  if (button.dataset.corePage) openCoreWords({page: button.dataset.corePage});
});

app.addEventListener('submit', event => {
  const form = event.target;
  if (form.id === 'core-words-search') {
    event.preventDefault();
    openCoreWords({...Object.fromEntries(new FormData(form)), page: '1'});
  }
  if (form.matches('.core-word-cloze')) {
    event.preventDefault();
    const exercise = coreWordsData?.items[Number(form.dataset.item)]?.cloze;
    if (!exercise) return;
    const value = String(new FormData(form).get('answer')).trim().toLowerCase().replaceAll('’', "'");
    const correct = value === exercise.answer.toLowerCase().replaceAll('’', "'");
    form.querySelector('[role="status"]').textContent =
      (correct ? '答对了。' : '参考答案是 ' + exercise.answer + '。') + ' ' + exercise.example;
  }
});

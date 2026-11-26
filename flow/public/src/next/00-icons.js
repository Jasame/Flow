  /* ---------- 语流's own icons (B9, 2026-11-26; the user: 有些地方纯文字有点太干巴巴了……做一些原创图标上去) ----------
     One set for every page: a 24 grid, a 1.6 line, round ends and corners. A shape with class "w" is a soft patch behind
     the main outline, class "t" a thin line; nothing is coloured: an icon takes the colour of the text around it (99-icons.css).
       fi('mic')        the icon, 22px, in the text colour: in front of a row's name, in a tool tile
       fiTile('bell')   the icon in a 34px soft square: the rows of a settings list
     Icons are decoration (aria-hidden): the row's own words name it. Add a new one here, not in a page's own file. */
  const FI = {
    clock: '<circle class="w" cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="8"/><path d="M12 7.8V12l3 1.8"/>',  // 练习记录
    retry: '<rect class="w" x="4" y="4" width="16" height="16" rx="4.5"/><rect x="4" y="4" width="16" height="16" rx="4.5"/><path d="M8.5 12.3l2.4 2.4 4.6-5.2"/>',  // 错题和句型复习
    bookx: '<path class="w" d="M6 4h11a1 1 0 0 1 1 1v15H7a1 1 0 0 1-1-1z"/><path d="M6 4h11a1 1 0 0 1 1 1v15H7a1 1 0 0 1-1-1z"/><path d="M10 9.5l4 4m0-4-4 4"/>',  // 错题本
    graph: '<circle class="w" cx="12" cy="6" r="2.6"/><circle cx="12" cy="6" r="2.6"/><circle cx="6" cy="17.5" r="2.6"/><circle cx="18" cy="17.5" r="2.6"/><path d="M10.8 8.3 7.3 15.2M13.2 8.3l3.5 6.9M8.6 17.5h6.8"/>',  // 知识图谱
    shuffle: '<path d="M4 7.5h3c2 0 3.2 1 4.2 3l1.6 3c1 2 2.2 3 4.2 3H20M4 16.5h3c1 0 1.8-.3 2.5-.9M20 7.5h-3c-1 0-1.8.3-2.5.9"/><path d="M17.5 5l2.5 2.5-2.5 2.5M17.5 14l2.5 2.5-2.5 2.5"/>',  // 混合练习
    flag: '<path class="w" d="M6.5 5H17l-2.5 4 2.5 4H6.5z"/><path d="M6.5 21V5H17l-2.5 4 2.5 4H6.5"/>',  // 语法起点小测
    read: '<path class="w" d="M3.5 6.5c2.8-1 5.7-1 8.5.5v12c-2.8-1.5-5.7-1.5-8.5-.5z"/><path d="M12 7c-2.8-1.5-5.7-1.5-8.5-.5v12c2.8-1 5.7-1 8.5.5 2.8-1.5 5.7-1.5 8.5-.5v-12c-2.8-1-5.7-1-8.5.5zm0 0v12"/>',  // 轻松读
    layers: '<path class="w" d="M12 4l8 4.5-8 4.5-8-4.5z"/><path d="M12 4l8 4.5-8 4.5-8-4.5z"/><path d="M4 12.5l8 4.5 8-4.5M4 16.5l8 4.5 8-4.5"/>',  // 全部材料
    docpen: '<path class="w" d="M6 3h8l4 4v13a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1z"/><path d="M14 3H6a1 1 0 0 0-1 1v16a1 1 0 0 0 1 1h11a1 1 0 0 0 1-1V7z"/><path d="M14 3v4h4M8.5 12.5h7M8.5 16.5h4.5"/>',  // 写作、贴一篇
    chat: '<path class="w" d="M5 5h14a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-7l-4 3v-3H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2z"/><path d="M5 5h14a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-7l-4 3v-3H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2z"/><path d="M8 11h.01M12 11h.01M16 11h.01"/>',  // 口语情景
    mic: '<rect class="w" x="9" y="3" width="6" height="11" rx="3"/><rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21"/>',  // 发音
    stack: '<rect class="w" x="4" y="8" width="13" height="12" rx="2.5"/><rect x="4" y="8" width="13" height="12" rx="2.5"/><path d="M8 4.5h10a2 2 0 0 1 2 2V16M8 14h5"/>',  // 背单词、新词
    venn: '<circle class="w" cx="9" cy="12" r="5.5"/><circle cx="9" cy="12" r="5.5"/><circle cx="15" cy="12" r="5.5"/>',  // 词汇辨析
    cal: '<rect class="w" x="4" y="5" width="16" height="15" rx="3"/><rect x="4" y="5" width="16" height="15" rx="3"/><path d="M4 10h16M8.5 3v4M15.5 3v4M8.5 14.5h3.5"/>',  // 背词计划
    gauge: '<path class="w" d="M4 16.5a8 8 0 0 1 16 0z"/><path d="M4 16.5a8 8 0 0 1 16 0"/><path d="M12 16.5l3.5-5M4 20h16"/>',  // 测词汇量
    exam: '<rect class="w" x="5" y="4.5" width="14" height="16.5" rx="2.5"/><rect x="5" y="4.5" width="14" height="16.5" rx="2.5"/><path d="M9 3h6v3H9zM8.5 11.5h7M8.5 15.5h4.5"/>',  // 考试练习
    hex: '<path d="M12 3 19.8 7.5v9L12 21l-7.8-4.5v-9z"/><path class="t" d="M12 12V3M12 12l7.8 4.5M12 12l-7.8 4.5"/><path class="w" d="M12 7.5l3.4 6.4-6.9-.2z"/><path d="M12 7.5l3.4 6.4-6.9-.2z"/>',  // 能力 (the tab's icon: a web, three axes, a shape; the user chose it)
    spark: '<path class="w" d="M11 4l1.9 4.9 4.9 1.9-4.9 1.9L11 17.6l-1.9-4.9-4.9-1.9 4.9-1.9z"/><path d="M11 4l1.9 4.9 4.9 1.9-4.9 1.9L11 17.6l-1.9-4.9-4.9-1.9 4.9-1.9z"/><path d="M18.5 16v4M16.5 18h4"/>',  // 今天建议
    again: '<circle class="w" cx="12" cy="12" r="7.5"/><path d="M19.5 12a7.5 7.5 0 1 1-2.2-5.3"/><path d="M19.5 4.5v4.2h-4.2"/>',  // 复习
    book: '<path class="w" d="M6 4h11a1 1 0 0 1 1 1v13H7.5A1.5 1.5 0 0 0 6 19.5z"/><path d="M6 19.5V5a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v13H7.5a1.5 1.5 0 0 0 0 3H18"/><path d="M10 8.5h4.5"/>',  // 词书
    trend: '<path class="w" d="M4 20l5-7 4 3 7-9v13z"/><path d="M4 16.5l5-5.5 4 3 7-8"/><path d="M15.5 6H20v4.5"/>',  // 我的进步
    week: '<rect class="w" x="4" y="5" width="16" height="15" rx="3"/><rect x="4" y="5" width="16" height="15" rx="3"/><path d="M8.5 16v-3M12 16V9.5M15.5 16v-4.5"/>',  // 周报
    target: '<circle class="w" cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="3.5"/><path d="M12 12h.01"/>',  // 学习目标
    cap: '<path class="w" d="M12 5l9 4.5-9 4.5-9-4.5z"/><path d="M12 5l9 4.5-9 4.5-9-4.5z"/><path d="M7 12v4c1.5 1.4 3.2 2 5 2s3.5-.6 5-2v-4M21 9.5V15"/>',  // 水平
    calok: '<rect class="w" x="4" y="5" width="16" height="15" rx="3"/><rect x="4" y="5" width="16" height="15" rx="3"/><path d="M4 10h16M8.5 3v4M15.5 3v4M9 15l2 2 4-4"/>',  // 每天的目标
    voice: '<path class="w" d="M4 10h3.5L12 6v12l-4.5-4H4z"/><path d="M4 10h3.5L12 6v12l-4.5-4H4z"/><path d="M15.5 9.5a4 4 0 0 1 0 5M18 7a7.5 7.5 0 0 1 0 10"/>',  // 朗读声音
    sliders: '<path d="M5 8h8.5M18.5 8H19M5 16h.5M10.5 16H19"/><circle class="w" cx="16" cy="8" r="2.4"/><circle cx="16" cy="8" r="2.4"/><circle class="w" cx="8" cy="16" r="2.4"/><circle cx="8" cy="16" r="2.4"/>',  // 使用习惯
    bell: '<path class="w" d="M6.5 16v-5a5.5 5.5 0 0 1 11 0v5l1.5 2h-14z"/><path d="M6.5 16v-5a5.5 5.5 0 0 1 11 0v5l1.5 2h-14z"/><path d="M10.5 20.5h3"/>',  // 提醒
    compass: '<circle class="w" cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="8"/><path d="M15.2 8.8l-1.9 4.5-4.5 1.9 1.9-4.5z"/>',  // 新手引导
    people: '<circle class="w" cx="9" cy="9" r="3"/><circle cx="9" cy="9" r="3"/><path d="M3.5 19a5.5 5.5 0 0 1 11 0M15.5 6.3a3 3 0 0 1 0 5.4M17.3 14.7a5 5 0 0 1 3.2 4.3"/>',  // 班级
    shield: '<path class="w" d="M12 3.5l7 2.5v5.5c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9V6z"/><path d="M12 3.5l7 2.5v5.5c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9V6z"/><path d="M9.2 12l2 2 3.6-3.8"/>',  // 账号和隐私
    help: '<circle class="w" cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="8"/><path d="M9.8 9.8a2.3 2.3 0 1 1 3.3 2.1c-.7.4-1.1.9-1.1 1.6M12 16.4h.01"/>',  // 帮助
    bars: '<rect class="w" x="4" y="5" width="16" height="15" rx="3"/><path d="M7.5 17v-5M12 17V8M16.5 17v-3"/>',  // 统计
    inbox: '<path class="w" d="M5 15.5h14V19a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1z"/><path d="M12 4v9.5m0 0l-3.5-3.5m3.5 3.5l3.5-3.5M5 16v3a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-3"/>',  // 反馈
  };
  function fi(name, cls) { return `<svg class="fi${cls ? ' ' + cls : ''}" viewBox="0 0 24 24" aria-hidden="true">${FI[name] || ''}</svg>`; }
  function fiTile(name) { return `<span class="fi-tile" aria-hidden="true">${fi(name)}</span>`; }

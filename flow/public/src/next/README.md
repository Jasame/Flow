# Flow front end, by feature

`tools/build_front.py` joins these in name order into `../../next.js` and `../../next.css` (byte for byte).
The script is one closure: `00-head.js` opens it and `99-boot.js` closes it, so every part can use every
other part's names. `20`–`24` are consecutive slices of `study()` (the four learning steps), not standalone files.

| part | what it holds |
| --- | --- |
| `00-head.js` | page elements, state, utilities, input helpers (touch, typing, scrolling), icons |
| `01-audio-offline.js` | browser voice, Kokoro narration, word and sentence clips, mini player, offline review queue |
| `02-shell.js` | sheets (focus, swipe), keyboard shortcuts, session and sign-in, router |
| `09-start.js` | 启动动画 (the mark in next.html, timed against the first page drawn) and 选方向和目标: one page for a new learner (goal, exam and date, the level to reach), the same page edits it from 我的; the 今日 notice for a guessed level |
| `10-welcome-today.js` | today's page |
| `11-progress.js` | 这周进步 (r27): the card at the top of 今日 and its details, 每周进度邮件 in 我的, the mail's unsubscribe page |
| `20-study.js` | `study()`: material header, step bar, step bookkeeping |
| `21-study-listen.js` | 听: whole-text playback, shadowing, dictation |
| `22-study-read.js` | 读: reader, read-along, new words, keyboard reading |
| `23-study-check.js` | 理解: comprehension questions |
| `24-study-output.js` | 用出来: model sentence, retell, dialogue, translation, essay (closes `study()`) |
| `25-finish.js` | 这篇完成了 (r27): the finish card after any 用出来, with three lines on what the text gave (expressions, words, a grammar point) |
| `30-lookup.js` | word look-up, AI sentence explanation, saving cards |
| `40-graph.js` | knowledge graph: learning route and full map; grammar-point pages (Chinese-speaker trap, connected points, rounds of 4 from a bank of 10) |
| `41-placement.js` | 语法起点小测: 16 questions band by band, places the learner and lights the graph |
| `42-exam.js` | 考试练习: timed sets for 中考 … 专八 / IELTS, results and their trend |
| `42-sprint.js` | 考试冲刺 (r27): the exam hub (my exam and its date, the countdown word plan, the score trend), the line on 今日, 我的考试, the date on 背词计划, question-type practice (exam_sprint.py, exam_types.py) |
| `43-mix.js` | mixed grammar rounds: today's review, confusable pairs, a whole topic (interleaved) |
| `44-easy.js` | 轻松读: easy texts a level down, reading speed, words read |
| `45-confuse.js` | 词汇辨析: word groups Chinese speakers mix up, interleaved rounds |
| `46-speak.js` | 口语路线: twelve role-play scenes with the AI |
| `47-growth.js` | 我的进步: this month against the last, milestones |
| `48-radar.js` | 能力雷达: goals, the radar against them, the test hub and the reading/listening/speaking/writing checks |
| `49-guide.js` | 操作指南: the in-site guide (table of contents, search, PDF link), rendered from `public/guide/guide.md` by `user_guide.py` |
| `49-practice.js` | 练习 tab: every kind of practice grouped by skill, with one suggestion from the radar on top |
| `50-words.js` | 单词 page, word cards, word-list import, plan, vocabulary test |
| `60-review.js` | review session (keys, swipes, mistake cards) |
| `70-learner.js` | ability profile, daily plan, level suggestion, microphone |
| `71-import.js` | 我的文章 |
| `72-sounds.js` | 发音入门 and its listening quiz |
| `73-report.js` | weekly report and share picture |
| `80-library.js` | 全部材料, serial stories and their episode list |
| `81-me.js` | 我的, email binding |
| `99-boot.js` | start-up |
| `05-start.css` | 启动动画 and 选方向和目标 |
| `00-base.css` … `70-input-devices.css` | tokens and base; pages; motion and graph; words; listening; phone pass; learner pages; input methods and devices |
| `80-flat.css` | the flat look: surfaces instead of outlines, frosted bars, the home plan and its next-step button, review focus mode |
| `89-radar.css` | the radar chart and its rows |
| `90-practice.css` | the 练习 hub tiles and the in-site guide |
| `88-more.css` | easy reading, word confusables, speaking scenes, my progress |
| `87-route.css` | learning route, relation map, Chinese-speaker traps, mixed rounds, review passage |
| `86-loop.css` | starting check, re-check tags, exam practice, serial episode list |
| `86-sprint.css` | 考试冲刺: the line on 今日, the exam hub, the score trend, question-type practice |
| `85-phone.css` | phone layout from a 360 px audit (16px fields, card layouts, listen controls, one level of surface), the knowledge graph tiles and grammar-point pages |
| `96-tidy.css` | phone tidy-up from a full-length audit: 存到手机 on the kicker line, 听's settings folded into one line, 读's tools in one row, the word-book picker folded, the 练习 list, 全部材料 filters |
| `97-progress.css` | 这周进步: the four-number card, its details sheet, the three lines after a text, the unsubscribe page |

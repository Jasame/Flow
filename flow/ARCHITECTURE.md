# v2.1 新增架构

`growth_service.py` 从 append-only learning_events 生成可解释复习队列、持续诊断、主题课程、七日对比与证据成就；排程和报告无需模型。新阶段写入现有 coach_missions，单元、顺序、图谱路径与证据编号保存在 growth_mission_meta，重复请求由 growth_stage_requests 约束。历史阶段、作品和账号不删除。

`quality_service.py` 进行结构检查和绑定内容哈希的人工审核。AI候选不会自动成为阶段推荐材料；原有原创示例保留。修改材料生成新pack，原始作答仍引用旧pack；词汇/语法关联及原文锚点在修订时校验。候选仍可在语料库明确选择并看到审核状态。

`teaching_corrections` 审计学习者的纠正；被纠正的AI观察退出推荐队列。私教快照优先携带最近纠正，但仍是有界上下文与摘要检索，非模型参数训练。完整对话保存在SQLite。

状态和成就由原始证据重建，不是掌握概率。延迟与迁移汇总只保留两个最早不同语境锚点，避免长历史的两两扫描。报告按北京时间的自然日分组。所有接口复用登录用户身份和CSRF，管理员审核复用admin权限。

新增前端 growth.js/css，私教增加学习证据、本周进展入口；浏览器只负责交互展示，调度与判分保持服务端为准。单人调用没有应用次数上限；供应商配额、并发和账单独立。

下面保留先前版本架构参考。

# Flow 2.0 coach architecture

The primary surface is now a persistent personal coach. The existing v1.0 typed graph, event store, adaptive objective tasks and language studio remain learning tools behind the conversation.

## coach_service.py

Owns coach_profiles, coach_assessments, coach_turns, coach_memories, coach_reflections, coach_missions and coach_drafts. All reads and mutations are scoped to the authenticated user; mutations use existing session CSRF. No supplied user ID controls ownership.

placement_content.py holds eight original starting checks with server-side answer keys. It is not a validated CEFR examination. Optional and skipped dimensions remain unknown. Grammar, vocabulary, reading and listening evidence use the appropriate nodes; writing and speaking are not fabricated from multiple-choice performance.

Each coach reply is a bounded structured object containing natural text, an episode summary, quoted teaching memories, evidence-linked private observations and an optional complete six-dimension mission set. Partial plans and unknown references are rejected before publication. Existing active plans are preserved unless a new stage is explicitly requested. Previous stages and all completed records persist.

Model context retrieves profile, teaching memories, relevant reflection summaries, bounded recent dialogue, recent actual work and feedback, prerequisite evidence, and goal/interest/level-matched materials and vocabulary. The complete dialogue remains stored and paginates independently of prompt size. This is contextual adaptation, not model fine-tuning.

First placement can automatically trigger one initial plan. Returning from new practice can trigger a single idempotent reflection keyed by work ID. System-generated reflection prompts do not create supposed learner preferences. A pending result is polled only while the coach view remains active. Client response updates check account and view epoch before displaying private state.

Mission completion derives from real owned objective events or owned studio submissions after assignment. Voice missions require an audio-feedback-backed speaking submission; a text-only speaking draft does not complete them. Custom mission instructions are passed to the studio and validated against the authenticated mission when feedback or work is submitted. XP reflects task participation, never proficiency.

## Invocation policy

No per-user daily call ceiling. Usage counters remain for monitoring. FLOW_AI_DAILY_LIMIT=0 and GATEWAY_DAILY_LIMIT=0 disable application-level daily totals. The upgrade configures both while preserving credentials and backups. Authentication, origin restrictions, body size, request deadlines and concurrency protection stay active. Provider quotas and billing remain external constraints. Operators can explicitly configure a positive global limit later; none is imposed by this upgrade.

## Migration and validation

Version2.0 adds tables and preserves v0.8/v1.0 data. Tests exercise real prior snapshot migration, persistence, owner isolation, idempotent turns, quoted memories, complete mission coverage, immutable prior plans, task completion and more than20 successive coach calls. Live model behavior and real browser rendering require deployment-side verification.

The retained v1.0 core architecture follows for compatibility details.

# Flow 1.0 architecture

## Boundaries

- app.py: authenticated HTTP routing, sessions, CSRF, static asset allowlist. Remains standard-library Python behind BaoTa Nginx.
- lexicon_service.py: stable word-sense identities, published/private/draft lexicon, versions, graph indexing, original corpus links and candidate ingestion.
- graph_service.py: owner-filtered typed graph, visible adjacency and local evidence projections. Administrative drafts never become public graph nodes before publication.
- event_service.py: append-only, deduplicated learning observations; descriptive state calculation and evidence report.
- adaptive_service.py: goals, deterministic recommendations, bounded task sessions, server-side hint tracking, objective grading, scheduling, AI context explanation and private observations.
- lab_service.py: existing four-skill studio, preserved work versions, feedback and audio. New studio-support tracking and unified event adapters preserve compatibility.
- learning_service.py: existing immutable grammar items and review cards; submissions also emit unified evidence.
- chat_service.py / gateway.py: existing bounded Gemini access, shared quota and request authentication. Gateway stays v0.8.
- daily_service.py: existing grounded news generation and provenance; vocabulary becomes editorial candidates, not silently published dictionary content.

## Typed graph

Node kinds: word, sense, pattern, grammar, material, skill. Public and private nodes remain owner-filtered. Relations:

| Relation | Meaning |
| --- | --- |
| has_sense | word contains a separately identified sense |
| has_pattern | sense has a taught usage pattern |
| uses_grammar | reviewed pattern refers to a grammar subskill |
| prerequisite | curriculum teaching order, not causal diagnosis |
| introduced_by | word sense was introduced by the teaching material |
| occurs_in | lexical surface form occurs in material, not proof of sense equivalence |
| practised_in | grammar topic is taught or practised in material |
| trains | material supports the corresponding studio activity |

AI-produced private observations do not directly rewrite public graph edges. They are scoped to the learner and require quoted evidence that exists in that learner's answer or audio transcript.

## Learning evidence

learning_events has UNIQUE(user_id,node,source). Sources identify actual attempts, work versions, task tokens, or AI requests. Correctness and assistance are nullable; unknown historical information is retained as unknown.

Evaluators are rule, legacy, practice, self, ai. Self confidence, submitted text, AI advice and exact-answer checks remain different kinds of evidence. Displayed states are rule summaries, not fitted latent traits or probabilities.

Independent evidence requires an objective successful check and assisted=0. Delayed evidence additionally requires at least24h from the preceding independent success. Transfer requires that delayed success in a different item/context. Early repeated correct answers cannot lengthen scheduled intervals. Limits are described in the UI and deployment guide.

Grammar attempt IDs, historical item labels, original material IDs and existing work references are preserved. Adaptive grammar tasks write into the existing attempts table; the adapter emits exactly one unified observation for the same attempt.

## API groups

- GET /api/adaptive, /api/adaptive/report
- POST /api/adaptive/goal, /next, /hint, /submit, /skip, /observation/dismiss
- GET /api/vocab, /api/vocab/entry?id=...
- POST /api/vocab/enroll, /unenroll, /rate, /draft, /feedback, /explain
- GET /api/graph, /api/graph/node?id=...
- Admin: GET /api/vocab/manage; POST /api/vocab/import, /publish, /generate
- Studio: POST /api/lab/support; existing studio/grammar/chat/account endpoints retained

All application APIs require login except the pre-existing account/session/health operations. Mutations require session-bound CSRF. Administration requires users.admin. Queries never use a client-supplied user ID.

## AI and cache behavior

AI output must pass bounded JSON validation. Private diagnostic links must refer to known grammar nodes and quote the actual submitted text. No model claim directly sets objective correctness or mastery.

Shared AI quotas and idempotency are reserved through lab_service.run_job before network IO, and database write locks are released while waiting for Gemini. Context explanations cache by learner, entry version and actual owned material sentence. Public dictionary generation produces drafts; publication has a version guard and audit trail.

Current policy is flow-rules-1.0. It prioritises due words, goals, prerequisites, observed grammar failures and unverified AI observations. It is not DKT, IRT or model fine-tuning. The code does not infer demographic, psychological, exam or certified CEFR scores.

## Migration and operations

Additive tables, stable identifiers and one-time event backfill. An original v0.8 archive snapshot is exercised in the source-workspace migration test; where that optional fixture is absent, only that test skips.

All user data stays in data/flow.sqlite3. Python3.11 and the existing SQLite are sufficient; JSON1 is not required. No new pip, Node, browser, vector database or graph database dependency is introduced. Source graph indices remain rebuildable from the lexicon and corpus; evidence and work are primary data.

The upgrade installs an explicit module/asset list into an empty-directory-tested application closure. Backup precedes migration and service startup. Failed startup attempts to restore the prior database, code, private environment, Nginx routes and daily timer state.

## Current limits

This release is suitable for the existing small deployment. Evidence aggregation and graph projections use local SQLite reads and have not been load-tested at large scale. Model output can remain linguistically inaccurate despite structural validation; source data and public candidate reviews matter. Browser-level visual QA and live v1.0 AI calls require deployment-side verification.

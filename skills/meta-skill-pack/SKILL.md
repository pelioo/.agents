---
name: meta-skill-pack
description: 整理、打包、重组、拆分、或为新 skill 选包时使用本 skill。它定义了"技能包 (Pack) + 渐进式披露"方法论：如何把多个 leaf skill 聚成一个 Pack、如何写 Pack 的 frontmatter 与路由表、如何保持可逆合并、如何按用户场景或能力维度分组、以及何时该新建 / 拆分 / 合并 Pack。当用户说"整理 skills""打包 skill""分组 skill""新增 skill 放进哪个包""评估是否要拆包""按场景聚合 skill"时触发本 skill。
---

# Meta Skill Pack

本 skill 是元 Pack 手册：教 agent 用"技能包 (Pack) + 渐进式披露"方法论来**组织、聚合、路由一组已有 skill**——不论这组 skill 是 5 个、50 个还是 500 个。后续用户再说"整理 skills"时，agent 读完本手册即可掌握方法，对当前 skill 库规模零依赖。

## 1. Pack 模式定义

**Leaf skill**：单一能力的自包含包，如 `search` / `docx` / `tdd`。目录 `skills/<name>/SKILL.md`，frontmatter 写 `name` + `description`，body 描述一个能力。

**Pack skill**：把多个 leaf skill 按场景或能力聚合成一个入口。它本身仍是一个标准 leaf skill——有目录、有 `SKILL.md`、有 frontmatter——只是 body 不是"教一件事"，而是"路由表"：告诉 agent 在什么子场景下应该 `Read` 哪个 leaf 的 `SKILL.md`。

**关键认识**：Pack 与 leaf 的运行时加载流程完全相同。runtime 不区分"普通 leaf"和"Pack"——只看 frontmatter 的 `name` + `description` 决定是否触发。Pack 之所以"包"其他 skill，只是因为它的 body 是一个路由表，agent 读到后按表去 `Read` 对应的 leaf。

## 2. 渐进式披露三层结构

技能包采用三层加载，控制上下文占用：

| 层 | 内容 | 何时加载 | 预算 |
|---|---|---|---|
| 1. frontmatter | `name` + `description` | 始终在上下文 | ~100 词 |
| 2. Pack body | 路由表（子 skill 名 + 触发条件 + 调用方式） | 触发时一次加载 | < 500 行 |
| 3. leaf body | 具体 leaf 的 `SKILL.md` | agent 按路由表 `Read` 时按需加载 | < 500 行/leaf |

**收益**：runtime 常驻 N 个 skill 的 frontmatter（N = skill 库总量），触发后加载 1 个 Pack body（< 500 行），再按需加载若干 leaf body。所有 leaf 的 frontmatter 始终常驻（这是 agentskills.io 标准的代价，无法绕过），但 leaf body 只在真正用时才进上下文。Pack 不能减少 frontmatter 的常驻成本，但能把"leaf body 的触发后加载"从"每次都全量"压缩成"按路由按需"。

## 3. 命名规范

**格式**：`<领域>-<能力>`，全小写、连字符分隔。

**领域取词库**（可组合）：
- `research` / `search` / `content` / `design` / `dev` / `docs` / `data`
- `platform` / `browser` / `media` / `agents` / `meta`

**能力取词库**：
- `and-search` / `and-blog` / `and-frontend` / `and-runtime`
- `orchestration` / `pipeline` / `publishing` / `extensions`

**反例**（不要）：
- 太宽：`skills` / `tools` / `everything`
- 太窄：`image-png-to-jpg`（应是 `media-conversion` 下的 leaf）
- 跟 leaf 同名：`search` 既是 leaf 也是潜在 Pack 候选——若用 `search` 做 Pack 名则需先把 leaf 改名为 `web-search` 或 `tavily-search`

**Pack 名必须唯一**，且不与任何 leaf `name` 字段冲突。

## 4. frontmatter 模板

Pack 的 frontmatter 与 leaf 相同（runtime 不区分），但 `description` 写法有讲究。

```yaml
---
name: <pack-name>
description: <单句，含"做什么 + 何时触发">。当用户说<关键词 A>、<关键词 B>、<关键词 C>时触发本 skill。
---
```

**触发关键词必须显式列在 description 里**。runtime 用 description 做匹配，不读 body。所以"触发条件"章节写在 body 里是给人看的，不影响 runtime 决策。

**当前 validator（`quick_validate.py`）仅允许 5 个键**：`name` / `description` / `license` / `allowed-tools` / `metadata`。**不要写 `version` / `tags` / `compatibility` 等**——会被拒绝。本 skill 不依赖这些键。

## 5. 路由表写法

Pack body 的核心是路由表。建议结构：

```markdown
# <Pack 名>

[一句话说明本 Pack 聚合什么场景]

## 何时用本 Pack

[用户场景描述，2-3 行]

## 子技能路由

| 子场景 | 触发关键词 | 调用的 leaf | 调用方式 |
|---|---|---|---|
| ... | "..." | `skills/<leaf>/SKILL.md` | `Read skills/<leaf>/SKILL.md` |
| ... | "..." | `skills/<leaf>/SKILL.md` | `Read skills/<leaf>/SKILL.md` |

## 调用约定

读取 leaf 之前**不要**先全量扫描它的 frontmatter——直接按路由表 `Read` 对应 leaf 的 `SKILL.md` 即可，frontmatter 已在 runtime 常驻。

## 与其他 Pack 的边界

[一句话说明本 Pack 不覆盖什么，指向哪个相邻 Pack]
```

**路由表的核心字段**：子场景、触发关键词、leaf 路径、调用方式。前两个给人读，后两个给 agent 读。

## 6. 分组启发式

两种分组维度，二选一或组合：

**A. 按能力聚类**（推荐起点）
- 同类工具 / 同类工作流放一个 Pack
- 例：`docs-and-office` 聚合所有文档处理 skill
- 优点：agent 找"我能处理 X 吗"时一目了然
- 缺点：跨能力的真实场景需要多次 `Read` 多个 Pack

**B. 按用户场景聚类**
- 一个用户目标可能跨多个能力 → 多个 leaf 共享一个 Pack
- 例：`launch-a-website` 聚合设计 + 前端 + 部署
- 优点：用户视角一个入口
- 缺点：Pack 数量膨胀，每个 leaf 被多个 Pack 引用

**推荐**：先按 A 做底（10 个左右的 Pack），再视需求做少量 B（场景型 Pack）作为补充。

**分组判据（满足任一即应独立成 Pack）**：
- ≥ 3 个 leaf 围绕同一动词或同一产出
- leaf 之间的描述关键词重叠 ≥ 50%
- 真实任务流经常连续触发 2-3 个 leaf

**判据（应保持独立 leaf，不入 Pack）**：
- 只用一次的小工具
- 高度垂直的单一能力（如 `weather-query`）
- 已有独立生态的扩展创建类（`create-extension` 等可单独成 Pack 但不强求）

## 7. Pack 分组示例（仅供参考，非处方）

> 下表是**一组示例 Pack**——用于演示第 6 节的"分组启发式"如何落地，**不是必须照搬的方案**。任何 agent 拿到一组 leaf 后，都应根据该组 leaf 的真实 `name` + `description` 重新打标。本表里出现的 leaf 名仅作举例，当前 skill 库是否真有该 leaf 需要 `ls C:\Users\peli\.agents\skills\` 自行核对。

| Pack 名（示例） | 覆盖场景（示例） | 候选 leaf（示例，仅供参考） |
|---|---|---|
| `research-and-search` | 联网搜索、抓取、摘要 | `search` / `multi-search-engine` / `anysearch-skill` / `web-scraper` / `summarize` / `agent-reach` |
| `content-and-blog` | 长文创作、博客、邮件 | `blog-author` / `copywriter` / `email-drafter` / `baoyu-translate` |
| `design-and-frontend` | 前端 / UI / 设计 / 性能 | `frontend-design` / `frontend-skill` / `canvas-design` / `web-design-guidelines` / `web-quality-audit` / `make-interfaces-feel-better` / `userinterface-wiki` / `core-web-vitals` / `react-best-practices` / `accessibility` / `a2ui` / `nuxt-ui` / `product-design` |
| `docs-and-office` | Office / PDF 文档 | `docx` / `xlsx` / `pptx` / `pdf` / `officeCLI` / `excel-processor` / `write-docs` / `explain-code` |
| `dev-orchestration` | 编码工作流（写 / 测 / 审 / 重构） | `code` / `tdd` / `test` / `review` / `lint` / `debug-like-expert` / `dependency-upgrade` / `code-optimizer` / `refactor-expert` / `architecture` / `api-design` / `design-an-interface` / `design-by-contract` / `security-review` / `observability` / `verify-before-complete` / `create-plan` / `decompose-into-slices` / `write-milestone-brief` / `grill-me` / `handoff` / `best-practices` |
| `platform-and-extensions` | 扩展 / MCP / 工作流 / skill 创建 | `create-extension` / `create-gsd-extension` / `create-mcp-server` / `create-workflow` / `create-skill` / `skill-creator` / `sap-extension-creator` |
| `browser-and-automation` | 浏览器自动化 | `agent-browser` / `browser-automation` / `playwright-dev` |
| `data-and-pipeline` | 数据处理 / 分析 | `csv-pipeline` / `data-analyst` |
| `media-and-publishing` | 社媒 / OCR / 翻译 | `image-ocr` / `xiaohongshu-creator` / `xiaohongshu-search` / `post-to-x` / `wechat-ui-sender` |
| `agents-and-runtime` | 调度 / 自省 / spike 复盘 | `find-skills` / `clawhub` / `self-improving-1.2.10` / `forensics` / `spike-wrap-up` / `skill-1773491216424` / `btw` |

**孤立 leaf 处理原则**（通用规则，与具体库无关）：高度垂直或低频使用的 leaf 保留独立目录，不强求入包。判断标准见第 6 节的"判据（应保持独立 leaf，不入 Pack）"。

## 8. 可逆合并规则

**重要原则**：建 Pack 的每一步都应可逆。Pack 本质是 frontmatter 描述 + 路由表文档，**不动 leaf 自身的 `SKILL.md` 文件**。

**创建 Pack 的最小动作**：
1. 新建目录 `skills/<pack-name>/`
2. 写入 `SKILL.md`（frontmatter + 路由表 body）
3. 跑 `quick_validate.py` 校验
4. 在 description 里写明触发关键词

**回滚动作**（用户改主意时）：
1. 删除 `skills/<pack-name>/` 目录
2. leaf 的 `SKILL.md` 全部未动过，无需回滚

**`name` 字段冲突处理**：若 Pack 想用的 `name` 已被 leaf 占用，必须**先重命名 leaf**（`mv skills/old-name skills/new-name` + 改 leaf 自己的 frontmatter `name`），**再**用原名建 Pack。重命名是破坏性动作，需要用户明确同意。

**`name` 重命名后**：
- 同步更新引用该 leaf 的其它 Pack 路由表
- 检查 `.skill-lock.json`（若是 tracked skill，工具会处理；若是手装，不需要管）
- 检查调用 leaf 的脚本（`scripts/*.py` 中可能有 `skills/<old-name>` 路径硬编码）

## 9. 常见陷阱

| 陷阱 | 后果 | 规避 |
|---|---|---|
| Pack 描述里只写"做什么"不写"何时触发" | runtime 不加载，Pack 形同虚设 | description 末尾必须含"当用户说 X / Y / Z 时触发" |
| 触发关键词与 leaf 高度重叠 | runtime 决策时随机挑一个 | Pack 描述聚焦"何时**先**到 Pack"，leaf 描述聚焦"何时**直接**用 leaf" |
| Pack body 写了具体操作步骤 | 越权——具体步骤应在 leaf body | Pack body 只做路由，不复制 leaf 内容 |
| 把 leaf 全部内容塞进 Pack body | 上下文爆炸 | Pack body 控制在路由表 + 调用约定，< 200 行最佳 |
| Pack 名带版本号 `xxx-1.0` | 与现行规范冲突 | 不加版本号 |
| Pack frontmatter 写了 `version` / `tags` | validator 拒绝 | 只用 `name` / `description` / `license` / `allowed-tools` / `metadata` |
| 一个 leaf 被 3+ Pack 引用 | 维护成本高 | 考虑该 leaf 是否应升为"枢纽 skill"独立保留 |
| 路由表用 leaf 的"功能描述"做关键词 | 触发模糊 | 关键词用"用户原话里的动词 + 名词" |

## 10. 验证步骤

每次新建 / 修改 Pack 后跑：

```bash
python3 <skill-creator 路径>/scripts/quick_validate.py <skill 库根>/<pack-name>
```

`<skill-creator 路径>` 取决于运行时已装在哪里；通常就是 `<skill 库根>/skill-creator/scripts/quick_validate.py`。

期望输出：`Skill is valid!` 退出码 0。

**手动 checklist**：
- [ ] frontmatter 仅有 5 个允许键之一
- [ ] `name` 与目录名一致、符合 `^[a-z0-9-]+$`
- [ ] `description` ≤ 1024 字符、不含尖括号
- [ ] body < 500 行
- [ ] description 含触发关键词
- [ ] 路由表里每个 leaf 路径真实存在（`ls <skill 库根>/<leaf>` 验证）

**触发测试**（人工）：
- 提一个属于本 Pack 场景的请求 → 期望 runtime 加载本 Pack 的 body
- 提一个属于本 Pack 内某 leaf 的请求 → 期望直接加载 leaf，跳过 Pack（如果 leaf 的 description 已覆盖该触发）

## 11. 与 `skill-creator` 的边界

| skill | 职责 | 何时用 |
|---|---|---|
| `skill-creator` | 教 agent **写一个 leaf skill**（frontmatter schema、references/scripts 目录、6 步流程） | 新建 leaf 时 |
| `meta-skill-pack`（本 skill） | 教 agent **把已有 leaf 打成 Pack**（分组、路由、可逆合并） | 整理 / 重组 leaf 时 |

两者互补。`meta-skill-pack` 的路由表里**可以**引用 `skill-creator`（作为"新写 leaf 的官方指南"），但本 skill 不重复 `skill-creator` 的内容。

## 12. 何时建 Pack / 何时拆 Pack / 何时不动

**建 Pack**（满足任一）：
- ≥ 3 个 leaf 关键词高度重叠
- 用户重复说"整理 skills"
- 真实任务流经常 1 次触发 ≥ 2 个 leaf

**拆 Pack**（满足任一）：
- Pack body > 500 行（路由表太胖）
- Pack 内出现 2 个独立子场景，几乎从不一起被触发
- 触发测试发现 runtime 经常误触发不该触发的 leaf

**不动**（保持现状）：
- leaf 数量 < 3
- 用户没要求整理
- 改造成本 > 收益

## 13. 工作流（agent 拿到本 skill 后的标准动作）

1. `ls <skill 库根目录>/` 列出全部 leaf（skill 库根目录 = runtime 实际扫描路径，按当前环境而定）
2. 对每个 leaf `Read skills/<name>/SKILL.md` 读前 30 行（只取 description + 标题）
3. 按"分组判据"打标：候选 Pack / 独立保留
4. 草拟 Pack 列表与每个 Pack 的候选 leaf
5. 与用户确认（**必做**——批量操作不可逆前要拍板）
6. 按"创建 Pack 的最小动作"逐个落地
7. 每个 Pack 跑 `quick_validate.py`
8. 全部完成后做一次触发测试，报告

**第 5 步不可省**。本 skill 是手册，不是脚本——执行细节由 agent 根据用户上下文决定。

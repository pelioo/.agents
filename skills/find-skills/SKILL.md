---
name: find-skills
description: 当用户提出"如何做 X"、"找一个能做 X 的技能"、"是否有能……的技能"之类的问题，或表达出希望扩展能力时，帮助用户发现并安装代理技能。当用户寻找可能以可安装技能形式存在的功能时，应使用本技能。
---

# 查找技能

本技能可帮助你发现并安装来自开放代理技能生态的技能。

## 何时使用本技能

在以下场景使用本技能：

- 用户询问"如何做 X"，其中 X 可能有现成的技能
- 用户说"找一个能做 X 的技能"或"是否有能做 X 的技能"
- 用户询问"你能做 X 吗"，其中 X 是一项专业能力
- 表达出希望扩展代理能力的意愿
- 想要搜索工具、模板或工作流
- 提到希望在某个特定领域（设计、测试、部署等）获得帮助

## 什么是 Skills CLI？

Skills CLI（`npx skills`）是开放代理技能生态的包管理器。技能是模块化的软件包，通过专业知识、工作流和工具来扩展代理的能力。

**关键命令：**

- `npx skills find [query]` - 以交互方式或按关键词搜索技能
- `npx skills add <package>` - 从 GitHub 或其他来源安装技能
- `npx skills check` - 检查技能更新
- `npx skills update` - 更新所有已安装的技能

**浏览技能：** https://skills.sh/

## 如何帮助用户查找技能

### 步骤 1：理解用户需求

当用户寻求帮助时，识别：

1. 所属领域（例如：React、测试、设计、部署）
2. 具体任务（例如：编写测试、创建动画、审查 PR）
3. 这是否是一个足够常见的任务，以至于可能存在对应技能

### 步骤 2：搜索技能

使用相关查询运行 find 命令：

```bash
npx skills find [query]
```

例如：

- 用户询问"如何让我的 React 应用更快？" → `npx skills find react performance`
- 用户询问"你能帮我审查 PR 吗？" → `npx skills find pr review`
- 用户询问"我需要创建一个更新日志" → `npx skills find changelog`

命令会返回如下结果：

```
Install with npx skills add <owner/repo@skill>

vercel-labs/agent-skills@vercel-react-best-practices
└ https://skills.sh/vercel-labs/agent-skills/vercel-react-best-practices
```

### 步骤 3：向用户展示选项

当你找到相关技能时，向用户展示以下信息：

1. 技能名称及其功能
2. 用户可以运行的安装命令
3. 在 skills.sh 上了解更多信息的链接

回复示例：

```
我找到了一个可能有用的技能！"vercel-react-best-practices"技能
提供了来自 Vercel 工程团队的 React 和 Next.js 性能优化指南。

要安装它：
npx skills add vercel-labs/agent-skills@vercel-react-best-practices

了解更多：https://skills.sh/vercel-labs/agent-skills/vercel-react-best-practices
```

### 步骤 4：提供安装

如果用户希望继续，你可以为他们安装该技能：

```bash
npx skills add <owner/repo@skill> -g -y
```

`-g` 标志表示全局安装（用户级），`-y` 跳过确认提示。

## 常见技能类别

搜索时，可参考以下常见类别：

| 类别          | 示例查询                                    |
| ------------- | ------------------------------------------- |
| Web 开发      | react, nextjs, typescript, css, tailwind    |
| 测试          | testing, jest, playwright, e2e             |
| DevOps        | deploy, docker, kubernetes, ci-cd           |
| 文档          | docs, readme, changelog, api-docs           |
| 代码质量      | review, lint, refactor, best-practices      |
| 设计          | ui, ux, design-system, accessibility        |
| 生产力        | workflow, automation, git                   |

## 高效搜索的技巧

1. **使用具体关键词**："react testing" 比仅用 "testing" 更好
2. **尝试替代术语**：如果 "deploy" 没结果，试试 "deployment" 或 "ci-cd"
3. **查看热门来源**：许多技能来自 `vercel-labs/agent-skills` 或 `ComposioHQ/awesome-claude-skills`

## 当未找到任何技能时

如果没有任何相关技能：

1. 坦诚告知未找到现有技能
2. 主动提出可使用通用能力直接帮助完成任务
3. 建议用户可以使用 `npx skills init` 创建自己的技能

例如：

```
我搜索了与 "xyz" 相关的技能，但没有找到匹配项。
我仍然可以直接帮你完成这项任务！是否需要我继续？

如果你经常做这件事，可以创建自己的技能：
npx skills init my-xyz-skill
```

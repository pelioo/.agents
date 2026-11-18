#!/usr/bin/env python3
"""
arch_mcp.py - Zero-dependency Stdio MCP (Model Context Protocol) Server
exposing native Tool Calls backed by arch_cli.py state machine.
"""

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

# Ensure sibling arch_cli module is importable regardless of working directory
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import arch_cli  # noqa: E402

# The engine keeps state in a relative `.arch/` directory. Hosts launch MCP
# servers from different working directories (Claude Desktop and global configs
# often do not use the project folder), so ARCH_ROOT pins the project root.
_ARCH_ROOT = os.environ.get("ARCH_ROOT", "").strip()
if _ARCH_ROOT:
    os.chdir(os.path.expanduser(_ARCH_ROOT))


TOOLS: List[Dict[str, Any]] = [
    {
        "name": "arch_init",
        "description": "初始化项目架构图状态机（在 .arch/ 下创建带 '?' 未知空洞的 3 节点初始主干与 Shadow Git 仓库）。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "seed": {"type": "string", "description": "用户最初模糊想法的一句话总结（北极星锚点）"},
            },
            "required": ["seed"],
        },
    },
    {
        "name": "arch_focus",
        "description": "获取当前焦点 '?' 空洞节点的 1-Hop 上下文切片、北极星约束与可行走主干（Walking Skeleton）状态。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "node_id": {"type": "string", "description": "可选：指定聚焦的节点 ID；不传则自动聚焦首个未决空洞"},
            },
        },
    },
    {
        "name": "arch_collapse",
        "description": "确定待定节点或更新已确定节点的规范，并生成 Shadow Git 快照。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "node_id": {"type": "string", "description": "目标节点 ID"},
                "label": {"type": "string", "description": "锁定后的简洁业务/模块名称"},
                "spec": {"type": "string", "description": "确定性的功能职责与技术原语描述"},
                "file_path": {"type": "string", "description": "可选：预期落地的代码文件路径"},
                "in_contract": {"type": "string", "description": "可选：覆盖全部入边的契约"},
                "out_contract": {"type": "string", "description": "可选：覆盖全部出边的契约"},
                "node_type": {
                    "type": "string",
                    "enum": ["port", "adapter", "reality_gate"],
                    "description": "节点类型（默认 port）",
                },
                "stage": {"type": "string", "description": "可选：指定归属的生命周期 Stage 阶段名称"},
            },
            "required": ["node_id", "label", "spec"],
        },
    },
    {
        "name": "arch_set_edge_contract",
        "description": "按起点和终点更新一条已有连线的契约，并生成 Shadow Git 快照。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "from_node": {"type": "string", "description": "起点节点 ID"},
                "to_node": {"type": "string", "description": "终点节点 ID"},
                "contract": {"type": "string", "description": "新契约"},
            },
            "required": ["from_node", "to_node", "contract"],
        },
    },
    {
        "name": "arch_add_node",
        "description": "在图中生长新节点（可插入两个节点之间，或作为 'fog' 迷雾支线暂存）。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "node_id": {"type": "string"},
                "label": {"type": "string"},
                "spec": {"type": "string"},
                "status": {"type": "string", "enum": ["hole", "solid", "fog"]},
                "node_type": {"type": "string", "enum": ["port", "adapter", "reality_gate"]},
                "stage": {"type": "string", "description": "可选：指定归属的生命周期 Stage 阶段名称"},
                "after_node": {"type": "string", "description": "可选：上游前驱节点 ID"},
                "before_node": {"type": "string", "description": "可选：下游后继节点 ID"},
                "contract": {"type": "string", "description": "连线契约描述"},
            },
            "required": ["node_id", "label", "spec"],
        },
    },
    {
        "name": "arch_add_fog",
        "description": "快捷工具：将用户提出但暂不实现的发散想法挂入侧边战争迷雾区（fog），保持主干轻盈。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "node_id": {"type": "string"},
                "label": {"type": "string"},
                "spec": {"type": "string"},
                "after_node": {"type": "string", "description": "可选：挂载在哪个节点之后"},
            },
            "required": ["node_id", "label", "spec"],
        },
    },
    {
        "name": "arch_deactivate",
        "description": "将活跃的实心（solid）或空洞（hole）节点平稳下线移入战争迷雾区（fog），并自动缝合上下游边缘。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "node_id": {"type": "string", "description": "目标节点 ID"},
                "reason": {"type": "string", "description": "暂缓/移入迷雾的原因说明"},
                "bypass_contract": {"type": "string", "description": "可选：上下游缝合连线的新契约"},
            },
            "required": ["node_id"],
        },
    },
    {
        "name": "arch_activate",
        "description": "将战争迷雾区（fog）中的储备节点激活为待定空洞（hole）并重新接入主干连线。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "node_id": {"type": "string", "description": "目标迷雾节点 ID"},
                "after_node": {"type": "string", "description": "可选：挂载在哪个上游节点之后"},
                "before_node": {"type": "string", "description": "可选：插入在哪个下游节点之前"},
                "contract": {"type": "string", "description": "连线契约描述"},
            },
            "required": ["node_id"],
        },
    },
    {
        "name": "arch_fold",
        "description": (
            "将已确定（solid / super_node）、彼此连通的子图折叠为一个超级节点，压缩认知负荷。"
            "子节点与内部连线完整保存在超级节点内，对外连线改接到超级节点并保留契约。"
            "当 focus 提示活跃实心节点过多时使用。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "node_ids": {"type": "array", "items": {"type": "string"}, "description": "待折叠的节点 ID（至少 2 个）"},
                "super_id": {"type": "string", "description": "超级节点 ID"},
                "label": {"type": "string", "description": "模块名称"},
                "spec": {"type": "string", "description": "模块整体职责描述"},
                "stage": {"type": "string", "description": "可选：所属 Stage；缺省时若子节点同属一个 Stage 则沿用"},
            },
            "required": ["node_ids", "super_id", "label", "spec"],
        },
    },
    {
        "name": "arch_unfold",
        "description": (
            "展开超级节点，原样恢复子节点、内部连线与对外连线。折叠期间新增的连线自动接到唯一的入口/出口子节点；"
            "无法自动归位时会报错并列出候选，此时向用户确认后通过 attach 指定。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "node_id": {"type": "string", "description": "超级节点 ID"},
                "attach": {
                    "type": "object",
                    "additionalProperties": {"type": "string"},
                    "description": "可选：{外部节点ID: 子节点ID}，指定折叠期间新增连线接到哪个子节点",
                },
            },
            "required": ["node_id"],
        },
    },
    {
        "name": "arch_verify",
        "description": "将用户刚刚在现实环境中实测确认的客观事实与硬约束永久沉淀进 .arch/ground_truth.md。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "fact": {"type": "string", "description": "已验证的客观现实结论"},
                "constraint": {"type": "string", "description": "由此推导出的架构硬约束"},
            },
            "required": ["fact", "constraint"],
        },
    },
    {
        "name": "arch_ground",
        "description": "向可插拔 Grounding 设置器（.arch/grounding.json）动态注册文档、命令行探针或人工验证源。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source_type": {
                    "type": "string",
                    "enum": ["human_verify", "doc_ref", "probe_cmd", "code_ref"],
                },
                "source": {"type": "string", "description": "文件路径、命令行探针或验证说明"},
                "note": {"type": "string", "description": "可选补充说明"},
            },
            "required": ["source_type", "source"],
        },
    },
    {
        "name": "arch_export_task",
        "description": "导出单个已确定节点的独立编码任务卡（含 Shadow Git 人工防覆盖校验），专供独立子代理在沙箱中执行。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "node_id": {"type": "string", "description": "要导出任务的节点 ID"},
            },
            "required": ["node_id"],
        },
    },
    {
        "name": "arch_commit_node",
        "description": "子代理完成单节点代码编写并测试通过后，提交 Shadow Git 快照并绑定代码文件路径。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "node_id": {"type": "string"},
                "file_path": {"type": "string"},
            },
            "required": ["node_id", "file_path"],
        },
    },
    {
        "name": "arch_sync_manual",
        "description": "当检测到人类在 IDE 手动修改了节点代码后，同步修改摘要并更新影子仓库快照以解除覆盖拦截。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "node_id": {"type": "string"},
                "summary": {"type": "string", "description": "一句话总结人类手动修改的逻辑"},
            },
            "required": ["node_id", "summary"],
        },
    },
    {
        "name": "arch_reset_node",
        "description": "现实运行踩坑时，保持主干拓扑不变，将报错叶子节点重置为 '?' 待定状态并把失败原因记录进 graveyard.md 避坑备忘。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "node_id": {"type": "string"},
                "reason": {"type": "string", "description": "踩坑原因（自动记入 graveyard.md）"},
            },
            "required": ["node_id", "reason"],
        },
    },
    {
        "name": "arch_fork",
        "description": "分支回滚：从指定 Shadow Git 快照标签安全回滚图状态（自动保留所有历史避坑记录与现实事实）。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "from_tag": {"type": "string", "description": "目标历史快照标签，如 arch-step-02"},
            },
            "required": ["from_tag"],
        },
    },
    {
        "name": "arch_export_ui",
        "description": "导出单文件交互式架构看板 HTML（阶段分组、主干与分支连线、待定/储备节点、契约详情、搜索与深链），离线可用；图变更后需重新导出。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "out_path": {"type": "string", "description": "可选：输出 HTML 路径，默认 .arch/dashboard.html"},
            },
        },
    },
]


def _dispatch_tool(name: str, args: Dict[str, Any]) -> str:
    if name == "arch_init":
        return arch_cli.op_init(args["seed"])
    if name == "arch_focus":
        return arch_cli.op_focus(args.get("node_id"))
    if name == "arch_collapse":
        return arch_cli.op_collapse(
            node_id=args["node_id"],
            label=args["label"],
            spec=args["spec"],
            file_path=args.get("file_path", ""),
            in_contract=args.get("in_contract", ""),
            out_contract=args.get("out_contract", ""),
            node_type=args.get("node_type", "port"),
            stage=args.get("stage", ""),
        )
    if name == "arch_set_edge_contract":
        return arch_cli.op_set_edge_contract(args["from_node"], args["to_node"], args["contract"])
    if name == "arch_add_node":
        return arch_cli.op_add_node(
            node_id=args["node_id"],
            label=args["label"],
            spec=args["spec"],
            status=args.get("status", "hole"),
            node_type=args.get("node_type", "port"),
            stage=args.get("stage", ""),
            after_node=args.get("after_node", ""),
            before_node=args.get("before_node", ""),
            contract=args.get("contract", "TBD"),
        )
    if name == "arch_add_fog":
        return arch_cli.op_add_node(
            node_id=args["node_id"],
            label=args["label"],
            spec=args["spec"],
            status="fog",
            node_type="port",
            stage=args.get("stage", ""),
            after_node=args.get("after_node", ""),
            contract="optional_fog",
        )
    if name == "arch_deactivate":
        return arch_cli.op_deactivate_node(
            node_id=args["node_id"],
            reason=args.get("reason", ""),
            bypass_contract=args.get("bypass_contract", ""),
        )
    if name == "arch_activate":
        return arch_cli.op_activate_node(
            node_id=args["node_id"],
            after_node=args.get("after_node", ""),
            before_node=args.get("before_node", ""),
            contract=args.get("contract", "TBD"),
        )
    if name == "arch_fold":
        return arch_cli.op_fold(
            node_ids=args["node_ids"],
            super_id=args["super_id"],
            label=args["label"],
            spec=args["spec"],
            stage=args.get("stage", ""),
        )
    if name == "arch_unfold":
        return arch_cli.op_unfold(args["node_id"], args.get("attach") or {})
    if name == "arch_verify":
        return arch_cli.op_verify(args["fact"], args["constraint"])
    if name == "arch_ground":
        return arch_cli.op_ground(args["source_type"], args["source"], args.get("note", ""))
    if name == "arch_export_task":
        return arch_cli.op_export_task(args["node_id"])
    if name == "arch_commit_node":
        return arch_cli.op_commit_node(args["node_id"], args["file_path"])
    if name == "arch_sync_manual":
        return arch_cli.op_sync_manual(args["node_id"], args["summary"])
    if name == "arch_reset_node":
        return arch_cli.op_reset_node(args["node_id"], args["reason"])
    if name == "arch_fork":
        return arch_cli.op_fork(args["from_tag"])
    if name == "arch_export_ui":
        return arch_cli.op_export_ui(args.get("out_path", ""))
    raise arch_cli.ArchEngineError(f"未知 MCP 工具：{name}")


def _send_response(msg_id: Any, result: Dict[str, Any]) -> None:
    payload = {"jsonrpc": "2.0", "id": msg_id, "result": result}
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _send_error(msg_id: Any, code: int, message: str) -> None:
    payload = {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def serve_stdio() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue

        msg_id = req.get("id")
        method = req.get("method")
        params = req.get("params") or {}

        # Notifications without id do not expect a response
        if msg_id is None:
            continue

        if method == "initialize":
            _send_response(
                msg_id,
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "arch-grower-mcp", "version": "0.1.0"},
                },
            )
        elif method == "tools/list":
            _send_response(msg_id, {"tools": TOOLS})
        elif method == "tools/call":
            tool_name = params.get("name", "")
            tool_args = params.get("arguments") or {}
            try:
                output_text = _dispatch_tool(tool_name, tool_args)
                _send_response(
                    msg_id,
                    {
                        "content": [{"type": "text", "text": output_text}],
                        "isError": False,
                    },
                )
            except arch_cli.ArchEngineError as exc:
                _send_response(
                    msg_id,
                    {
                        "content": [{"type": "text", "text": str(exc)}],
                        "isError": True,
                    },
                )
            except Exception as exc:
                _send_response(
                    msg_id,
                    {
                        "content": [{"type": "text", "text": f"Internal Error: {exc}"}],
                        "isError": True,
                    },
                )
        else:
            _send_error(msg_id, -32601, f"Method not found: {method}")


if __name__ == "__main__":
    serve_stdio()

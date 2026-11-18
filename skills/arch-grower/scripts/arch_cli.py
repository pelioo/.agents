#!/usr/bin/env python3
"""
arch_cli.py - Zero-dependency State Machine, 1-Hop Slicer & Shadow Git Guardrail
for Autoregressive Architecture Co-Creation.
"""

import argparse
import html
import json
import os
import re
import subprocess
import sys
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ARCH_DIR = Path(".arch")
GRAPH_FILE = ARCH_DIR / "graph.json"
SEED_FILE = ARCH_DIR / "SEED.md"
GROUND_TRUTH_FILE = ARCH_DIR / "ground_truth.md"
GRAVEYARD_FILE = ARCH_DIR / "graveyard.md"
GROUNDING_FILE = ARCH_DIR / "grounding.json"
SHADOW_GIT_DIR = ARCH_DIR / ".git"
DASHBOARD_TEMPLATE = Path(__file__).resolve().parent / "dashboard_template.html"

MAX_ACTIVE_HOLES = 3
MAX_UNFOLDED_SOLID = 7

# A changed diff line that declares a function / type, across common languages
# (Python, JS/TS, Go, Rust, C#/Java-style modifiers). Anchored at the start of the
# line so keywords inside strings or comments do not count.
SIGNATURE_LINE = re.compile(
    r"^[+-]\s*(?:"
    # Declarations: def / class / function / fn / func / struct ...
    r"(?:(?:export|default|pub(?:\([^)]*\))?|public|private|protected|internal|static|abstract|async|unsafe)\s+)*"
    r"(?:def|class|function|interface|fn|func|struct|trait|enum|type|impl)\b"
    # Any export statement is public API: bindings (`export const f = ...`),
    # `export default`, export lists (`export { a }`), re-exports
    # (`export * from "./x"`), TypeScript `export =`; and CommonJS exports.
    r"|export\b"
    r"|(?:module\.)?exports(?:\.[\w$]+)?\s*="
    r")"
)


class ArchEngineError(Exception):
    """Domain error carrying JIT instructions for the Agent."""
    pass


def _run_shadow_git(args: List[str], check: bool = True) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["GIT_DIR"] = str(SHADOW_GIT_DIR.resolve())
    env["GIT_WORK_TREE"] = str(Path(".").resolve())
    return subprocess.run(
        ["git"] + args,
        env=env,
        capture_output=True,
        text=True,
        check=check,
    )


def _init_shadow_git() -> None:
    if not SHADOW_GIT_DIR.exists():
        SHADOW_GIT_DIR.mkdir(parents=True, exist_ok=True)
        _run_shadow_git(["init"])
        _run_shadow_git(["config", "user.name", "arch-grower"])
        _run_shadow_git(["config", "user.email", "arch@local"])


def _shadow_commit(tag_name: str, message: str, paths: Optional[List[str]] = None) -> None:
    _init_shadow_git()
    targets = paths if paths else [str(ARCH_DIR)]
    for p in targets:
        if Path(p).exists():
            _run_shadow_git(["add", "-f", p], check=False)
    res = _run_shadow_git(["diff", "--cached", "--quiet"], check=False)
    if res.returncode != 0:
        _run_shadow_git(["commit", "-m", message], check=False)
    _run_shadow_git(["tag", "-f", tag_name], check=False)


def _load_graph() -> Dict[str, Any]:
    if not GRAPH_FILE.exists():
        raise ArchEngineError(
            "未找到 .arch/graph.json。请先调用 arch_init 初始化项目骨架。"
        )
    return json.loads(GRAPH_FILE.read_text(encoding="utf-8"))


def _save_graph(data: Dict[str, Any]) -> None:
    GRAPH_FILE.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


SOLID_STATUSES = ("solid", "super_node")


def _active_topology(graph: Dict[str, Any]) -> Tuple[Dict[str, List[str]], Dict[str, int], Dict[str, int]]:
    """Adjacency and degrees of the active graph (every node that is not fog)."""
    active_ids = {n["id"] for n in graph["nodes"] if n["status"] != "fog"}
    adj: Dict[str, List[str]] = {nid: [] for nid in active_ids}
    in_deg: Dict[str, int] = {nid: 0 for nid in active_ids}
    out_deg: Dict[str, int] = {nid: 0 for nid in active_ids}
    for e in graph["edges"]:
        u, v = e["from"], e["to"]
        if u in active_ids and v in active_ids:
            adj[u].append(v)
            in_deg[v] += 1
            out_deg[u] += 1
    return adj, in_deg, out_deg


def _iter_all_nodes(nodes: List[Dict[str, Any]]):
    """Yield every node, descending into the children of folded super nodes."""
    for n in nodes:
        yield n
        yield from _iter_all_nodes(n.get("children", []))


def _find_container(graph: Dict[str, Any], node_id: str) -> Optional[Dict[str, Any]]:
    """Return the top-level super node that (transitively) holds node_id."""
    for n in graph["nodes"]:
        if n["status"] == "super_node" and any(
            c["id"] == node_id for c in _iter_all_nodes(n.get("children", []))
        ):
            return n
    return None


def _get_node(graph: Dict[str, Any], node_id: str, allow_super: bool = True) -> Dict[str, Any]:
    """Look up a top-level node, with JIT guidance for folded or super nodes."""
    for n in graph["nodes"]:
        if n["id"] == node_id:
            if not allow_super and n["status"] == "super_node":
                raise ArchEngineError(
                    f"节点 '{node_id}' 是折叠后的超级节点，不能直接执行该操作。\n"
                    f"JIT 指令：先调用 arch_unfold(node_id='{node_id}') 展开，再对其中的子节点操作。"
                )
            return n
    container = _find_container(graph, node_id)
    if container:
        raise ArchEngineError(
            f"节点 '{node_id}' 已折叠在超级节点 '{container['id']}' 内。\n"
            f"JIT 指令：先调用 arch_unfold(node_id='{container['id']}') 展开后再操作。"
        )
    raise ArchEngineError(f"节点 '{node_id}' 不存在。")


def _next_focus_hole(graph: Dict[str, Any]) -> Optional[str]:
    """Cognitive serialization: the most upstream hole is settled first."""
    holes = [n["id"] for n in graph["nodes"] if n["status"] == "hole"]
    if not holes:
        return None
    hole_ids = set(holes)
    return next((nid for nid in _topological_order(graph) if nid in hole_ids), holes[0])


def _compact_node(node: Dict[str, Any]) -> Dict[str, Any]:
    """Super nodes appear in slices as one module: children shown as id/label only."""
    if node["status"] != "super_node":
        return node
    view = {k: v for k, v in node.items()
            if k not in ("children", "inner_edges")}
    view["folded_children"] = [{"id": c["id"], "label": c["label"]} for c in node["children"]]
    return view


def _flatten_folds(graph: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, str]]:
    """Expand every super node into its original nodes and edges.

    Returns the flat graph and a map from each flat node to the top-level node
    that currently shows it (itself, or the outermost super node holding it).
    Edges are taken from their members, so an edge drawn to a module attaches
    to the child it really reaches. An endpoint that is still a super node
    (an edge attached while folded) resolves through the module's entry /
    exit children; when there are several, the edge connects to all of them.
    """
    flat_nodes: List[Dict[str, Any]] = []
    top_of: Dict[str, str] = {}
    supers: Dict[str, Dict[str, Any]] = {}
    for top in graph["nodes"]:
        for n in _iter_all_nodes([top]):
            if n["status"] == "super_node":
                supers[n["id"]] = n
            else:
                flat_nodes.append(n)
                top_of[n["id"]] = top["id"]

    def resolve(nid: str, side: str, seen: frozenset = frozenset()) -> List[str]:
        if nid in top_of:
            return [nid]
        if nid not in supers or nid in seen:
            return []
        candidates = supers[nid]["entry_children" if side == "to" else "exit_children"]
        return [leaf for c in candidates for leaf in resolve(c, side, seen | {nid})]

    raw = list(graph["edges"]) + [e for sn in supers.values() for e in sn.get("inner_edges", [])]
    flat_edges = []
    for e in raw:
        for m in _edge_members(e):
            # An endpoint that is still ambiguous connects to every candidate:
            # extra dependencies can only remove entries and exits, so the
            # skeleton is never reported ready on a guess.
            for u in resolve(m["from"], "from"):
                for v in resolve(m["to"], "to"):
                    flat_edges.append({"from": u, "to": v, "contract": m.get("contract", "")})
    return {"nodes": flat_nodes, "edges": flat_edges}, top_of


def _solid_path(graph: Dict[str, Any]) -> Optional[List[str]]:
    """BFS for a path of >= 2 solid nodes from a real entry to a real exit."""
    nodes = {n["id"]: n for n in graph["nodes"]}
    adj, in_deg, out_deg = _active_topology(graph)
    solid_ids = {nid for nid in adj if nodes[nid]["status"] in SOLID_STATUSES}
    starts = [nid for nid in adj if in_deg[nid] == 0 and nid in solid_ids]
    ends = {nid for nid in adj if out_deg[nid] == 0 and nid in solid_ids}
    for s in starts:
        queue = deque([[s]])
        visited = {s}
        while queue:
            path = queue.popleft()
            curr = path[-1]
            if curr in ends and len(path) >= 2:
                return path
            for nxt in adj[curr]:
                if nxt in solid_ids and nxt not in visited:
                    visited.add(nxt)
                    queue.append(path + [nxt])
    return None


def _find_walking_skeleton(graph: Dict[str, Any]) -> Optional[List[str]]:
    """A complete solid path from a real entry to a real exit, in top-level ids.

    Entries and exits are judged on the whole active graph (fog excluded), not on
    the solid sub-graph alone; otherwise a solid node whose successor is still a
    hole would wrongly count as an exit. Folded modules are expanded first, so a
    path must really get through a module's interior (in through one child, out
    through a reachable one); steps inside one module collapse to its id, and a
    trunk folded whole is reported as that single module.
    """
    flat, top_of = _flatten_folds(graph)
    path = _solid_path(flat)
    if not path:
        return None
    shown: List[str] = []
    for nid in path:
        if not shown or shown[-1] != top_of[nid]:
            shown.append(top_of[nid])
    return shown


def _topological_order(graph: Dict[str, Any]) -> List[str]:
    """Kahn order of the active graph; nodes left over (cycles) keep insertion order."""
    adj, in_deg, _ = _active_topology(graph)
    order_index = {n["id"]: i for i, n in enumerate(graph["nodes"])}
    remaining = dict(in_deg)
    ready = sorted((nid for nid, d in remaining.items() if d == 0), key=order_index.get)
    order: List[str] = []
    while ready:
        curr = ready.pop(0)
        order.append(curr)
        for nxt in adj[curr]:
            remaining[nxt] -= 1
            if remaining[nxt] == 0:
                ready.append(nxt)
        ready.sort(key=order_index.get)
    seen = set(order)
    order += [n["id"] for n in graph["nodes"] if n["id"] in adj and n["id"] not in seen]
    return order


def _check_node_drift(node: Dict[str, Any]) -> None:
    file_path = node.get("file_path")
    last_tag = node.get("last_tag")
    if not file_path or not last_tag or not Path(file_path).exists() or not SHADOW_GIT_DIR.exists():
        return

    diff_res = _run_shadow_git(["diff", last_tag, "--", file_path], check=False)
    if diff_res.stdout.strip():
        sig_changed = any(
            not line.startswith(("+++", "---")) and SIGNATURE_LINE.match(line)
            for line in diff_res.stdout.splitlines()
        )
        if sig_changed:
            raise ArchEngineError(
                f"[ContractDriftError] 检测到人类手动修改了 {file_path} 的函数/接口签名！\n"
                f"JIT 指令：\n"
                f"1. 严禁直接覆盖该文件。\n"
                f"2. 立即向用户确认：是以当前代码签名为准同步更新上下游契约，还是回退签名？\n"
                f"3. 确认后运行 sync-manual 更新快照。"
            )
        raise ArchEngineError(
            f"[ManualDriftError] 检测到人类手动微调了 {file_path} 的内部实现！\n"
            f"JIT 指令：\n"
            f"1. 严禁直接覆盖该文件。\n"
            f"2. 拉起轻量子代理阅读 diff 并用一句话总结人类改动。\n"
            f"3. 调用 sync-manual (node='{node['id']}', summary='...') 更新影子快照后再继续。"
        )


# =====================================================================
# Core Operations (Shared by CLI and MCP Server)
# =====================================================================

def op_init(seed: str) -> str:
    ARCH_DIR.mkdir(parents=True, exist_ok=True)
    _init_shadow_git()

    SEED_FILE.write_text(f"# 项目初始意图 (SEED)\n\n{seed.strip()}\n", encoding="utf-8")
    if not GROUND_TRUTH_FILE.exists():
        GROUND_TRUTH_FILE.write_text("# 已验证现实事实与硬约束 (Ground Truth)\n\n", encoding="utf-8")
    if not GRAVEYARD_FILE.exists():
        GRAVEYARD_FILE.write_text("# 废弃分支与踩坑记录 (Graveyard)\n\n", encoding="utf-8")
    if not GROUNDING_FILE.exists():
        GROUNDING_FILE.write_text(json.dumps({"sources": []}, indent=2) + "\n", encoding="utf-8")

    graph = {
        "step": 1,
        "nodes": [
            {
                "id": "entry_input",
                "label": "? 触发与输入边界",
                "status": "hole",
                "type": "port",
                "spec": "待定义系统如何接收初始触发或输入数据",
                "file_path": "",
                "last_tag": "",
            },
            {
                "id": "core_transform",
                "label": "? 核心处理黑盒",
                "status": "hole",
                "type": "port",
                "spec": "待定义核心业务变换逻辑",
                "file_path": "",
                "last_tag": "",
            },
            {
                "id": "final_output",
                "label": "? 最终输出与动作",
                "status": "hole",
                "type": "port",
                "spec": "待定义系统的最终交付形态或副作用",
                "file_path": "",
                "last_tag": "",
            },
        ],
        "edges": [
            {"from": "entry_input", "to": "core_transform", "contract": "TBD"},
            {"from": "core_transform", "to": "final_output", "contract": "TBD"},
        ],
    }
    _save_graph(graph)
    _shadow_commit("arch-step-01", f"init: {seed[:40]}")
    return op_focus()


def op_focus(node_id: Optional[str] = None) -> str:
    graph = _load_graph()
    nodes = {n["id"]: n for n in graph["nodes"]}

    holes = [n for n in graph["nodes"] if n["status"] == "hole"]
    solids = [n for n in graph["nodes"] if n["status"] == "solid"]
    settled = [n for n in graph["nodes"] if n["status"] in SOLID_STATUSES]

    target = None
    if node_id:
        target = _get_node(graph, node_id)
    elif holes:
        target = nodes[_next_focus_hole(graph)]
    elif settled:
        target = settled[-1]

    seed_txt = SEED_FILE.read_text(encoding="utf-8").strip() if SEED_FILE.exists() else ""
    gt_txt = GROUND_TRUTH_FILE.read_text(encoding="utf-8").strip() if GROUND_TRUTH_FILE.exists() else ""
    gy_txt = GRAVEYARD_FILE.read_text(encoding="utf-8").strip() if GRAVEYARD_FILE.exists() else ""

    out: List[str] = [
        "=== 北极星锚点与硬约束 ===",
        seed_txt,
        gt_txt,
        gy_txt,
        "========================",
    ]

    if len(holes) > MAX_ACTIVE_HOLES:
        out.append(
            f"[CIRCUIT_BREAKER_WARNING] 当前未决空洞数 ({len(holes)}) 已超过上限 ({MAX_ACTIVE_HOLES})！"
            "请先收敛现有主干空洞，禁止继续发散新分支。"
        )
    if len(solids) > MAX_UNFOLDED_SOLID:
        out.append(
            f"[CIRCUIT_BREAKER_WARNING] 当前活跃实心节点 ({len(solids)}) 超过 {MAX_UNFOLDED_SOLID} 个，"
            "建议调用 arch_fold 将已稳定的子图折叠为超级节点，以降低认知负荷。"
        )

    skeleton = _find_walking_skeleton(graph)
    if skeleton:
        out.append(f"[WALKING_SKELETON_READY] 检测到无空洞可运行主干: {' -> '.join(skeleton)}")

    if not target:
        out.append("当前图为空。")
        return "\n".join(out)

    tid = target["id"]
    in_edges = [e for e in graph["edges"] if e["to"] == tid]
    out_edges = [e for e in graph["edges"] if e["from"] == tid]
    neighbor_ids = {e["from"] for e in in_edges} | {e["to"] for e in out_edges}
    fog_nodes = [n for n in graph["nodes"] if n["status"] == "fog"]

    slice_payload = {
        "current_step": graph["step"],
        "focus_node": _compact_node(target),
        "upstream_edges": [_public_edge(e) for e in in_edges],
        "downstream_edges": [_public_edge(e) for e in out_edges],
        "neighbors": [_compact_node(nodes[nid]) for nid in neighbor_ids if nid in nodes],
        "fog_backlog": [{"id": f["id"], "label": f["label"]} for f in fog_nodes],
    }
    out.append("=== 当前焦点 1-Hop 切片 ===")
    out.append(json.dumps(slice_payload, indent=2, ensure_ascii=False))
    return "\n".join(out)


def op_collapse(
    node_id: str,
    label: str,
    spec: str,
    file_path: str = "",
    in_contract: str = "",
    out_contract: str = "",
    node_type: str = "port",
    stage: str = "",
) -> str:
    _reject_manual_super_type(node_type)
    graph = _load_graph()
    nodes = {n["id"]: n for n in graph["nodes"]}
    _get_node(graph, node_id, allow_super=False)

    node = nodes[node_id]
    node["label"] = label
    node["spec"] = spec
    node["status"] = "solid"
    node["type"] = node_type
    if stage:
        node["stage"] = stage
    if file_path:
        node["file_path"] = file_path

    if in_contract:
        for e in graph["edges"]:
            if e["to"] == node_id:
                e["contract"] = in_contract
    if out_contract:
        for e in graph["edges"]:
            if e["from"] == node_id:
                e["contract"] = out_contract

    graph["step"] += 1
    tag = f"arch-step-{graph['step']:02d}"
    _save_graph(graph)
    _shadow_commit(tag, f"collapse {node_id}: {label}")
    return f"已锁定节点 '{node_id}' ({label})，快照 {tag}。\n\n" + op_focus()


def op_set_edge_contract(from_node: str, to_node: str, contract: str) -> str:
    graph = _load_graph()
    matches = [
        edge for edge in graph["edges"]
        if edge["from"] == from_node and edge["to"] == to_node
    ]
    edge_label = f"{from_node} -> {to_node}"
    if len(matches) != 1:
        raise ArchEngineError(f"需要唯一的连线 '{edge_label}'，找到 {len(matches)} 条。")

    edge = matches[0]
    if edge.get("contract") == contract:
        return f"连线 '{edge_label}' 已使用该契约。"

    edge["contract"] = contract
    graph["step"] += 1
    tag = f"arch-step-{graph['step']:02d}"
    _save_graph(graph)
    _shadow_commit(tag, f"set-edge-contract {edge_label}")
    return f"已更新连线 '{edge_label}' 的契约，快照 {tag}。\n\n" + op_focus(from_node)


def op_add_node(
    node_id: str,
    label: str,
    spec: str,
    status: str = "hole",
    node_type: str = "port",
    stage: str = "",
    after_node: str = "",
    before_node: str = "",
    contract: str = "TBD",
) -> str:
    _reject_manual_super_type(node_type)
    graph = _load_graph()
    if any(n["id"] == node_id for n in _iter_all_nodes(graph["nodes"])):
        raise ArchEngineError(f"节点 '{node_id}' 已存在。")
    for ref in (after_node, before_node):
        if ref:
            _get_node(graph, ref)

    holes = [n for n in graph["nodes"] if n["status"] == "hole"]
    if status == "hole" and len(holes) >= MAX_ACTIVE_HOLES:
        raise ArchEngineError(
            f"[CircuitBreakerError] 未决空洞已达上限 ({MAX_ACTIVE_HOLES})！"
            "JIT 指令：禁止继续新增 '?' 空洞，必须先通过 collapse 收敛现有空洞，或将非核心想法设为 status='fog'。"
        )

    graph["nodes"].append({
        "id": node_id,
        "label": label,
        "status": status,
        "type": node_type,
        "stage": stage,
        "spec": spec,
        "file_path": "",
        "last_tag": "",
    })

    if after_node and before_node:
        graph["edges"] = [
            e for e in graph["edges"]
            if not (e["from"] == after_node and e["to"] == before_node)
        ]
        graph["edges"].append({"from": after_node, "to": node_id, "contract": contract})
        graph["edges"].append({"from": node_id, "to": before_node, "contract": contract})
    elif after_node:
        graph["edges"].append({"from": after_node, "to": node_id, "contract": contract})
    elif before_node:
        graph["edges"].append({"from": node_id, "to": before_node, "contract": contract})

    graph["step"] += 1
    tag = f"arch-step-{graph['step']:02d}"
    _save_graph(graph)
    _shadow_commit(tag, f"add-node {node_id} ({status})")
    return f"已添加节点 '{node_id}' ({status})。\n\n" + op_focus(node_id if status == "hole" else None)


def op_verify(fact: str, constraint: str) -> str:
    ARCH_DIR.mkdir(parents=True, exist_ok=True)
    if not GROUND_TRUTH_FILE.exists():
        GROUND_TRUTH_FILE.write_text("# 已验证现实事实与硬约束 (Ground Truth)\n\n", encoding="utf-8")

    existing = GROUND_TRUTH_FILE.read_text(encoding="utf-8")
    idx = existing.count("- [GT-") + 1
    entry = f"- [GT-{idx:02d}] (已验证) {fact.strip()} -> 架构约束：{constraint.strip()}\n"
    GROUND_TRUTH_FILE.write_text(existing + entry, encoding="utf-8")
    _shadow_commit(f"gt-{idx:02d}", f"verify GT-{idx:02d}")
    return f"已永久沉淀现实事实：\n{entry}"


def op_ground(source_type: str, source: str, note: str = "") -> str:
    ARCH_DIR.mkdir(parents=True, exist_ok=True)
    data = json.loads(GROUNDING_FILE.read_text(encoding="utf-8")) if GROUNDING_FILE.exists() else {"sources": []}
    data["sources"].append({
        "type": source_type,
        "source": source,
        "note": note,
        "added_at": datetime.now().isoformat(timespec="seconds"),
    })
    GROUNDING_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return f"已挂载 Grounding 数据源 ({source_type}): {source}"


def op_export_task(node_id: str) -> str:
    graph = _load_graph()
    nodes = {n["id"]: n for n in graph["nodes"]}
    _get_node(graph, node_id, allow_super=False)

    node = nodes[node_id]
    if node["status"] == "hole":
        raise ArchEngineError(f"节点 '{node_id}' 仍处于 '?' 待定状态，请先通过 collapse 确定节点规范后再导出编码任务。")

    _check_node_drift(node)

    in_edges = [e for e in graph["edges"] if e["to"] == node_id]
    out_edges = [e for e in graph["edges"] if e["from"] == node_id]
    gt_txt = GROUND_TRUTH_FILE.read_text(encoding="utf-8").strip() if GROUND_TRUTH_FILE.exists() else ""
    gy_txt = GRAVEYARD_FILE.read_text(encoding="utf-8").strip() if GRAVEYARD_FILE.exists() else ""

    task = {
        "worker_instruction": (
            "你是独立的实现子代理。严格仅实现以下单节点契约："
            "1) 采用 Port/Adapter 分离易变外部接口；"
            "2) 按主代理给定的变更范围和项目规则验证上下游契约；"
            "3) 若 type=='reality_gate'，按项目要求验证真实环境约束；"
            "4) 按主代理给定的快照安排处理 commit-node，并返回 <=3 行结果摘要。"
        ),
        "target_node": node,
        "input_contracts": [_public_edge(e) for e in in_edges],
        "output_contracts": [_public_edge(e) for e in out_edges],
        "global_ground_truth": gt_txt,
        "global_graveyard": gy_txt,
    }
    return json.dumps(task, indent=2, ensure_ascii=False)


def op_commit_node(node_id: str, file_path: str) -> str:
    graph = _load_graph()
    nodes = {n["id"]: n for n in graph["nodes"]}
    _get_node(graph, node_id, allow_super=False)

    graph["step"] += 1
    tag = f"node-{node_id}-s{graph['step']:02d}"
    nodes[node_id]["file_path"] = file_path
    nodes[node_id]["last_tag"] = tag
    _save_graph(graph)
    _shadow_commit(tag, f"implement {node_id} -> {file_path}", paths=[str(ARCH_DIR), file_path])
    return f"节点 '{node_id}' 代码已锚定至 {file_path}，影子快照 {tag} 已生成。"


def op_sync_manual(node_id: str, summary: str) -> str:
    graph = _load_graph()
    nodes = {n["id"]: n for n in graph["nodes"]}
    _get_node(graph, node_id, allow_super=False)

    node = nodes[node_id]
    file_path = node.get("file_path", "")
    node["spec"] = f"{node['spec']} | [人工微调: {summary.strip()}]"
    graph["step"] += 1
    tag = f"manual-{node_id}-s{graph['step']:02d}"
    node["last_tag"] = tag
    _save_graph(graph)
    paths = [str(ARCH_DIR)] + ([file_path] if file_path else [])
    _shadow_commit(tag, f"sync-manual {node_id}: {summary[:40]}", paths=paths)
    return f"已同步人工修改摘要并更新快照 {tag}。"


def op_reset_node(node_id: str, reason: str) -> str:
    graph = _load_graph()
    nodes = {n["id"]: n for n in graph["nodes"]}
    _get_node(graph, node_id, allow_super=False)

    node = nodes[node_id]
    old_label = node["label"]
    node["status"] = "hole"
    node["label"] = f"? 待替换: {old_label}"
    node["last_tag"] = ""

    existing_gy = GRAVEYARD_FILE.read_text(encoding="utf-8") if GRAVEYARD_FILE.exists() else "# 踩坑记录\n\n"
    GRAVEYARD_FILE.write_text(
        existing_gy + f"- ❌ [节点 {node_id} / {old_label}] 废弃原因：{reason.strip()}\n",
        encoding="utf-8",
    )

    graph["step"] += 1
    tag = f"reset-{node_id}-s{graph['step']:02d}"
    _save_graph(graph)
    _shadow_commit(tag, f"reset {node_id}: {reason[:40]}")
    return f"已将节点 '{node_id}' 重置为 '?' 待定状态并记录进踩坑备忘。\n\n" + op_focus(node_id)


def op_fork(from_tag: str) -> str:
    _init_shadow_git()
    gy_backup = GRAVEYARD_FILE.read_text(encoding="utf-8") if GRAVEYARD_FILE.exists() else ""
    gt_backup = GROUND_TRUTH_FILE.read_text(encoding="utf-8") if GROUND_TRUTH_FILE.exists() else ""

    branch_name = f"fork-{from_tag}-{datetime.now().strftime('%H%M%S')}"
    res = _run_shadow_git(["checkout", "-b", branch_name, from_tag], check=False)
    if res.returncode != 0:
        raise ArchEngineError(f"无法从快照 '{from_tag}' 分叉：{res.stderr.strip()}")

    if gy_backup:
        GRAVEYARD_FILE.write_text(gy_backup, encoding="utf-8")
    if gt_backup:
        GROUND_TRUTH_FILE.write_text(gt_backup, encoding="utf-8")
    _shadow_commit(f"{branch_name}-start", f"fork from {from_tag}")
    return f"已成功安全回滚至 {from_tag} 并开启新分支 {branch_name}（已保留所有避坑记录）。\n\n" + op_focus()


def op_deactivate_node(node_id: str, reason: str = "", bypass_contract: str = "") -> str:
    graph = _load_graph()
    nodes = {n["id"]: n for n in graph["nodes"]}
    _get_node(graph, node_id, allow_super=False)

    node = nodes[node_id]
    if node["status"] == "fog":
        return f"节点 '{node_id}' 已经在迷雾区 (fog) 中。\n\n" + op_focus()

    old_status = node["status"]
    node["status"] = "fog"
    node["last_tag"] = ""

    # 提取并缝合关联边
    incoming = [e for e in graph["edges"] if e["to"] == node_id]
    outgoing = [e for e in graph["edges"] if e["from"] == node_id]

    graph["edges"] = [
        e for e in graph["edges"]
        if e["from"] != node_id and e["to"] != node_id
    ]

    bridged_edges = []
    for inc in incoming:
        for out in outgoing:
            u, v = inc["from"], out["to"]
            if u == v:
                continue
            ct = bypass_contract or inc.get("contract") or out.get("contract") or "Bypass-Bridged"
            # Join the original endpoints on both sides, so a bypass touching a
            # folded module still knows which child it really starts or ends at.
            bypass = [
                {"from": a["from"], "to": b["to"], "contract": ct}
                for a in _edge_members(inc) for b in _edge_members(out) if a["from"] != b["to"]
            ]
            existing = next((e for e in graph["edges"] if e["from"] == u and e["to"] == v), None)
            if existing is None:
                graph["edges"].append(_edge_from_members(u, v, bypass))
                bridged_edges.append(f"{u} -> {v}")
                continue
            known = {(m["from"], m["to"]) for m in _edge_members(existing)}
            extra = [m for m in bypass if (m["from"], m["to"]) not in known]
            if extra:
                graph["edges"][graph["edges"].index(existing)] = _edge_from_members(
                    u, v, _edge_members(existing) + extra
                )

    graph["step"] += 1
    tag = f"deactivate-{node_id}-s{graph['step']:02d}"
    _save_graph(graph)
    msg = f"deactivate {node_id} ({old_status} -> fog)"
    if reason:
        msg += f": {reason[:30]}"
    _shadow_commit(tag, msg)

    info = f"已将节点 '{node_id}' 移入战争迷雾区 (fog)。"
    if bridged_edges:
        info += f"\n已自动缝合主干旁路：{', '.join(bridged_edges)}。"
    return info + "\n\n" + op_focus()


def op_activate_node(
    node_id: str,
    after_node: str = "",
    before_node: str = "",
    contract: str = "TBD",
) -> str:
    graph = _load_graph()
    nodes = {n["id"]: n for n in graph["nodes"]}
    _get_node(graph, node_id, allow_super=True)

    node = nodes[node_id]
    if node["status"] != "fog":
        return f"节点 '{node_id}' 当前状态为 '{node['status']}'，并非处于迷雾区。\n\n" + op_focus(node_id)

    holes = [n for n in graph["nodes"] if n["status"] == "hole"]
    if len(holes) >= MAX_ACTIVE_HOLES:
        raise ArchEngineError(
            f"[CircuitBreakerError] 未决空洞已达上限 ({MAX_ACTIVE_HOLES})！"
            "JIT 指令：必须先通过 collapse 收敛现有空洞，才能激活新的迷雾节点。"
        )
    for ref in (after_node, before_node):
        if ref:
            _get_node(graph, ref)

    node["status"] = "hole"
    if not node["label"].startswith("?"):
        node["label"] = f"? {node['label']}"

    if after_node and before_node:
        graph["edges"] = [
            e for e in graph["edges"]
            if not (e["from"] == after_node and e["to"] == before_node)
        ]
        graph["edges"].append({"from": after_node, "to": node_id, "contract": contract})
        graph["edges"].append({"from": node_id, "to": before_node, "contract": contract})
    elif after_node:
        graph["edges"].append({"from": after_node, "to": node_id, "contract": contract})
    elif before_node:
        graph["edges"].append({"from": node_id, "to": before_node, "contract": contract})

    graph["step"] += 1
    tag = f"activate-{node_id}-s{graph['step']:02d}"
    _save_graph(graph)
    _shadow_commit(tag, f"activate {node_id} (fog -> hole)")
    return f"已成功从迷雾区激活节点 '{node_id}' 并接入主干！\n\n" + op_focus(node_id)


def _reject_manual_super_type(node_type: str) -> None:
    if node_type == "super_node":
        raise ArchEngineError(
            "超级节点只能通过 arch_fold 折叠已确定的子图生成，不能用 collapse / add-node 直接指定类型。"
        )


def _merge_contracts(contracts: List[str]) -> str:
    unique = list(dict.fromkeys(c for c in contracts if c))
    return " | ".join(unique) if unique else "TBD"


# Edge provenance for folding
# ---------------------------
# An edge that touches a super node may stand for several original edges. It
# carries them in "members" (each a plain {from, to, contract}) together with
# "auto_contract", the merged contract the engine wrote. Provenance lives on
# the edge rather than inside the super node, so it travels with the edge when
# the neighbour on the other side is folded or unfolded later, in any order.


def _edge_members(e: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Original edges this edge stands for; a contract edited while folded wins."""
    members = e.get("members")
    if not members:
        return [{"from": e["from"], "to": e["to"], "contract": e.get("contract", "")}]
    if "auto_contract" in e and e.get("contract") != e["auto_contract"]:
        return [{**m, "contract": e.get("contract", "")} for m in members]
    return [dict(m) for m in members]


def _edge_from_members(u: str, v: str, members: List[Dict[str, Any]]) -> Dict[str, Any]:
    if len(members) == 1 and (members[0]["from"], members[0]["to"]) == (u, v):
        return {"from": u, "to": v, "contract": members[0].get("contract", "")}
    contract = _merge_contracts([m.get("contract", "") for m in members])
    return {"from": u, "to": v, "contract": contract, "auto_contract": contract, "members": members}


def _public_edge(e: Dict[str, Any]) -> Dict[str, Any]:
    """Edge as shown to the agent: provenance bookkeeping left out."""
    return {k: v for k, v in e.items() if k not in ("members", "auto_contract")}


def op_fold(
    node_ids: List[str],
    super_id: str,
    label: str,
    spec: str,
    stage: str = "",
) -> str:
    """Fold a settled, connected, convex sub-graph into a single super node.

    Children and inner edges are stored inside the super node. Edges crossing
    the fold boundary are re-pointed at the super node; parallel edges to the
    same neighbour are merged (contracts joined with " | ") and keep the
    original edges as members, so arch_unfold can restore them exactly.
    """
    graph = _load_graph()
    ids = list(dict.fromkeys(i.strip() for i in node_ids if i and i.strip()))
    if len(ids) < 2:
        raise ArchEngineError("折叠至少需要 2 个节点。")
    if any(n["id"] == super_id for n in _iter_all_nodes(graph["nodes"])):
        raise ArchEngineError(f"节点 '{super_id}' 已存在，请换一个超级节点 ID。")

    members = {nid: _get_node(graph, nid) for nid in ids}
    unsettled = [f"{nid}({n['status']})" for nid, n in members.items() if n["status"] not in SOLID_STATUSES]
    if unsettled:
        raise ArchEngineError(
            f"只能折叠已确定的节点，以下节点尚未确定：{', '.join(unsettled)}。\n"
            "JIT 指令：折叠用于收起已稳定的子图；待定节点请先 collapse，迷雾节点不应纳入折叠。"
        )

    member_set = set(ids)
    inner = [e for e in graph["edges"] if e["from"] in member_set and e["to"] in member_set]
    incoming = [e for e in graph["edges"] if e["to"] in member_set and e["from"] not in member_set]
    outgoing = [e for e in graph["edges"] if e["from"] in member_set and e["to"] not in member_set]

    # Weak connectivity: the members must form one module.
    undirected: Dict[str, set] = {nid: set() for nid in ids}
    for e in inner:
        undirected[e["from"]].add(e["to"])
        undirected[e["to"]].add(e["from"])
    seen, stack = {ids[0]}, [ids[0]]
    while stack:
        for nxt in undirected[stack.pop()]:
            if nxt not in seen:
                seen.add(nxt)
                stack.append(nxt)
    if seen != member_set:
        raise ArchEngineError(
            f"待折叠节点之间并不连通（与 {ids[0]} 不相连：{', '.join(sorted(member_set - seen))}）。\n"
            "JIT 指令：只折叠彼此有连线的同一模块，不相关的部分请分别折叠。"
        )

    # Convexity: no path may leave the set and come back in, or folding would
    # create a cycle through the super node.
    frontier = [e["to"] for e in outgoing]
    reachable_outside = set(frontier)
    while frontier:
        curr = frontier.pop()
        for e in graph["edges"]:
            if e["from"] == curr:
                if e["to"] in member_set:
                    raise ArchEngineError(
                        f"外部节点 '{curr}' 位于待折叠子图的中间（存在 子图 → {curr} → 子图 的路径），"
                        "折叠后会形成环。\nJIT 指令：把它一并纳入折叠，或缩小折叠范围。"
                    )
                if e["to"] not in reachable_outside:
                    reachable_outside.add(e["to"])
                    frontier.append(e["to"])

    entry_children = [nid for nid in ids if not any(e["to"] == nid for e in inner)]
    exit_children = [nid for nid in ids if not any(e["from"] == nid for e in inner)]

    grouped: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    for e in incoming:
        grouped.setdefault((e["from"], super_id), []).extend(_edge_members(e))
    for e in outgoing:
        grouped.setdefault((super_id, e["to"]), []).extend(_edge_members(e))
    folded_edges = [_edge_from_members(u, v, ms) for (u, v), ms in grouped.items()]

    child_stages = {members[nid].get("stage", "") for nid in ids}
    super_node = {
        "id": super_id,
        "label": label,
        "status": "super_node",
        "type": "super_node",
        "stage": stage or (child_stages.pop() if len(child_stages) == 1 else ""),
        "spec": spec,
        "file_path": "",
        "last_tag": "",
        "children": [members[nid] for nid in ids],
        "inner_edges": inner,
        "entry_children": entry_children,
        "exit_children": exit_children,
    }

    # Put the super node where its first member was, so ordering stays stable.
    insert_at = min(i for i, n in enumerate(graph["nodes"]) if n["id"] in member_set)
    remaining = [n for n in graph["nodes"] if n["id"] not in member_set]
    graph["nodes"] = remaining[:insert_at] + [super_node] + remaining[insert_at:]
    graph["edges"] = [
        e for e in graph["edges"] if e["from"] not in member_set and e["to"] not in member_set
    ] + folded_edges

    graph["step"] += 1
    tag = f"fold-{super_id}-s{graph['step']:02d}"
    _save_graph(graph)
    _shadow_commit(tag, f"fold {', '.join(ids)} -> {super_id}")
    return (
        f"已将 {len(ids)} 个节点折叠为超级节点 '{super_id}' ({label})，快照 {tag}。\n"
        f"入口子节点：{', '.join(entry_children)}；出口子节点：{', '.join(exit_children)}。\n\n"
        + op_focus()
    )


def op_unfold(super_id: str, attach: Optional[Dict[str, str]] = None) -> str:
    """Restore a super node's children, inner edges and boundary edges.

    Each edge on the super node is split back into the original edges it
    stands for (its members), regrouped by the child that now holds each
    endpoint. A contract edited while folded overrides the members' contracts.
    Edges attached after folding go to the unique entry / exit child, or to the
    child named in `attach` (neighbour -> child).
    """
    attach = attach or {}
    graph = _load_graph()
    sn = _get_node(graph, super_id)
    if sn["status"] != "super_node":
        raise ArchEngineError(f"节点 '{super_id}' 不是超级节点，无需展开。")

    child_ids = {c["id"] for c in sn["children"]}
    bad = {k: v for k, v in attach.items() if v not in child_ids}
    if bad:
        raise ArchEngineError(
            f"attach 指定的子节点不在 '{super_id}' 内：{bad}。可选子节点：{', '.join(sorted(child_ids))}。"
        )

    # Which child of this super node holds a given node id (at any depth).
    owner = {d["id"]: c["id"] for c in sn["children"] for d in _iter_all_nodes([c])}

    grouped: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    unresolved: List[str] = []
    for e in (e for e in graph["edges"] if super_id in (e["from"], e["to"])):
        inbound = e["to"] == super_id
        neighbour = e["from"] if inbound else e["to"]
        inner_end = "to" if inbound else "from"
        for m in _edge_members(e):
            child = owner.get(m[inner_end])
            if child is None:
                # Attached while folded: route it to the right child and record
                # that child as the real endpoint for any later unfold.
                candidates = sn["entry_children"] if inbound else sn["exit_children"]
                child = attach.get(neighbour) or (candidates[0] if len(candidates) == 1 else "")
                if not child:
                    arrow = f"{neighbour} -> {super_id}" if inbound else f"{super_id} -> {neighbour}"
                    item = f"{arrow}（可选：{', '.join(candidates or sorted(child_ids))}）"
                    if item not in unresolved:
                        unresolved.append(item)
                    continue
                m = {**m, inner_end: child}
            key = (neighbour, child) if inbound else (child, neighbour)
            grouped.setdefault(key, []).append(m)

    restored: List[Dict[str, Any]] = [dict(e) for e in sn["inner_edges"]]
    restored += [_edge_from_members(u, v, ms) for (u, v), ms in grouped.items()]

    if unresolved:
        raise ArchEngineError(
            f"超级节点 '{super_id}' 折叠期间新增了无法自动归位的连线：\n  - "
            + "\n  - ".join(unresolved)
            + "\nJIT 指令：向用户确认每条连线应接到哪个子节点，然后带上 attach={外部节点ID: 子节点ID} 重新调用 arch_unfold。"
        )

    idx = next(i for i, n in enumerate(graph["nodes"]) if n["id"] == super_id)
    graph["nodes"] = graph["nodes"][:idx] + sn["children"] + graph["nodes"][idx + 1:]
    graph["edges"] = [e for e in graph["edges"] if super_id not in (e["from"], e["to"])] + restored

    graph["step"] += 1
    tag = f"unfold-{super_id}-s{graph['step']:02d}"
    _save_graph(graph)
    _shadow_commit(tag, f"unfold {super_id}")
    return (
        f"已展开超级节点 '{super_id}'，恢复 {len(sn['children'])} 个子节点，快照 {tag}。\n\n"
        + op_focus()
    )


def _md_bullets(path: Path) -> List[str]:
    if not path.exists():
        return []
    return [ln[2:].strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.startswith("- ")]


def op_export_ui(out_path: str = "") -> str:
    """Render the stage-swimlane dashboard from dashboard_template.html.

    The page is fully self-contained (no network). Graph data is embedded as
    JSON inside <script type="application/json">, with <, > and & escaped so
    node text can never close the script element.
    """
    graph = _load_graph()
    target = Path(out_path).resolve() if out_path else (ARCH_DIR / "dashboard.html")
    target.parent.mkdir(parents=True, exist_ok=True)

    seed_raw = SEED_FILE.read_text(encoding="utf-8") if SEED_FILE.exists() else ""
    seed = "\n".join(
        ln for ln in seed_raw.splitlines() if ln.strip() and not ln.lstrip().startswith("#")
    ).strip() or "架构图"

    payload = {
        "seed": seed,
        "step": graph.get("step", 1),
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "graph": graph,
        "topo_order": _topological_order(graph),
        "skeleton": _find_walking_skeleton(graph),
        "next_focus": _next_focus_hole(graph),
        "limits": {"holes": MAX_ACTIVE_HOLES, "solids": MAX_UNFOLDED_SOLID},
        "ground_truth": _md_bullets(GROUND_TRUTH_FILE),
        "graveyard": _md_bullets(GRAVEYARD_FILE),
    }
    data = (
        json.dumps(payload, ensure_ascii=False)
        .replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    )
    template = DASHBOARD_TEMPLATE.read_text(encoding="utf-8")
    tokens = {"__ARCH_TITLE__": html.escape(seed[:40]), "__ARCH_DATA__": data}
    html_content = re.sub(r"__ARCH_(?:TITLE|DATA)__", lambda m: tokens[m.group(0)], template)
    target.write_text(html_content, encoding="utf-8")
    return f"已成功导出阶段泳道架构看板 HTML 至：{target}"


# =====================================================================
# CLI Entrypoint
# =====================================================================

def main() -> None:
    parser = argparse.ArgumentParser(description="Autoregressive Architecture State Machine CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init")
    p_init.add_argument("--seed", required=True)

    p_focus = sub.add_parser("focus")
    p_focus.add_argument("--node", default=None)

    p_col = sub.add_parser("collapse")
    p_col.add_argument("--node", required=True)
    p_col.add_argument("--label", required=True)
    p_col.add_argument("--spec", required=True)
    p_col.add_argument("--file-path", default="")
    p_col.add_argument("--in-contract", default="")
    p_col.add_argument("--out-contract", default="")
    p_col.add_argument("--type", default="port")
    p_col.add_argument("--stage", default="")

    p_edge = sub.add_parser("set-edge-contract", help="更新指定连线的契约")
    p_edge.add_argument("--from", dest="from_node", required=True)
    p_edge.add_argument("--to", dest="to_node", required=True)
    p_edge.add_argument("--contract", required=True)

    p_add = sub.add_parser("add-node")
    p_add.add_argument("--node", required=True)
    p_add.add_argument("--label", required=True)
    p_add.add_argument("--spec", required=True)
    p_add.add_argument("--status", default="hole", choices=["hole", "solid", "fog"])
    p_add.add_argument("--type", default="port")
    p_add.add_argument("--stage", default="")
    p_add.add_argument("--after", default="")
    p_add.add_argument("--before", default="")
    p_add.add_argument("--contract", default="TBD")

    p_exp_ui = sub.add_parser("export-ui", help="导出 Stage 泳道交互式架构看板 HTML")
    p_exp_ui.add_argument("--out", default="")

    p_deact = sub.add_parser("deactivate", help="将活跃节点下线并移入战争迷雾区，自动缝合上下游边")
    p_deact.add_argument("--node", required=True)
    p_deact.add_argument("--reason", default="")
    p_deact.add_argument("--bypass-contract", default="")

    p_act = sub.add_parser("activate", help="将迷雾区节点激活为待定空洞并接入主干")
    p_act.add_argument("--node", required=True)
    p_act.add_argument("--after", default="")
    p_act.add_argument("--before", default="")
    p_act.add_argument("--contract", default="TBD")

    p_fold = sub.add_parser("fold", help="将已确定、相互连通的子图折叠为一个超级节点")
    p_fold.add_argument("--nodes", required=True, help="逗号分隔的待折叠节点 ID，如 a,b,c")
    p_fold.add_argument("--id", required=True, help="超级节点 ID")
    p_fold.add_argument("--label", required=True)
    p_fold.add_argument("--spec", required=True)
    p_fold.add_argument("--stage", default="")

    p_unfold = sub.add_parser("unfold", help="展开超级节点，恢复其子节点与连线")
    p_unfold.add_argument("--node", required=True)
    p_unfold.add_argument(
        "--attach", action="append", default=[], metavar="NEIGHBOUR=CHILD",
        help="折叠期间新增连线的归位：外部节点ID=子节点ID（可重复）",
    )

    p_ver = sub.add_parser("verify")
    p_ver.add_argument("--fact", required=True)
    p_ver.add_argument("--constraint", required=True)

    p_gnd = sub.add_parser("ground")
    p_gnd.add_argument("--type", required=True, choices=["human_verify", "doc_ref", "probe_cmd", "code_ref"])
    p_gnd.add_argument("--source", required=True)
    p_gnd.add_argument("--note", default="")

    p_exp = sub.add_parser("export-task")
    p_exp.add_argument("--node", required=True)

    p_com = sub.add_parser("commit-node")
    p_com.add_argument("--node", required=True)
    p_com.add_argument("--file-path", required=True)

    p_syn = sub.add_parser("sync-manual")
    p_syn.add_argument("--node", required=True)
    p_syn.add_argument("--summary", required=True)

    p_rst = sub.add_parser("reset-node")
    p_rst.add_argument("--node", required=True)
    p_rst.add_argument("--reason", required=True)

    p_frk = sub.add_parser("fork")
    p_frk.add_argument("--from-tag", required=True)

    args = parser.parse_args()
    try:
        if args.cmd == "init":
            print(op_init(args.seed))
        elif args.cmd == "focus":
            print(op_focus(args.node))
        elif args.cmd == "collapse":
            print(op_collapse(
                args.node, args.label, args.spec,
                args.file_path, args.in_contract, args.out_contract, args.type, args.stage
            ))
        elif args.cmd == "set-edge-contract":
            print(op_set_edge_contract(args.from_node, args.to_node, args.contract))
        elif args.cmd == "add-node":
            print(op_add_node(
                args.node, args.label, args.spec,
                args.status, args.type, args.stage, args.after, args.before, args.contract
            ))
        elif args.cmd == "export-ui":
            print(op_export_ui(args.out))
        elif args.cmd == "deactivate":
            print(op_deactivate_node(args.node, args.reason, args.bypass_contract))
        elif args.cmd == "activate":
            print(op_activate_node(args.node, args.after, args.before, args.contract))
        elif args.cmd == "fold":
            print(op_fold(args.nodes.split(","), args.id, args.label, args.spec, args.stage))
        elif args.cmd == "unfold":
            attach = {}
            for pair in args.attach:
                neighbour, sep, child = pair.partition("=")
                if not sep or not neighbour.strip() or not child.strip():
                    raise ArchEngineError(f"--attach 格式应为 外部节点ID=子节点ID，收到：{pair}")
                attach[neighbour.strip()] = child.strip()
            print(op_unfold(args.node, attach))
        elif args.cmd == "verify":
            print(op_verify(args.fact, args.constraint))
        elif args.cmd == "ground":
            print(op_ground(args.type, args.source, args.note))
        elif args.cmd == "export-task":
            print(op_export_task(args.node))
        elif args.cmd == "commit-node":
            print(op_commit_node(args.node, args.file_path))
        elif args.cmd == "sync-manual":
            print(op_sync_manual(args.node, args.summary))
        elif args.cmd == "reset-node":
            print(op_reset_node(args.node, args.reason))
        elif args.cmd == "fork":
            print(op_fork(args.from_tag))
    except ArchEngineError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

"""Regression tests for the arch_cli engine (standard library only).

Run from the repository root:
    python3 -m unittest discover -s tests
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import arch_cli  # noqa: E402


class EngineTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._old_cwd = os.getcwd()
        self._tmp = tempfile.TemporaryDirectory()
        os.chdir(self._tmp.name)
        arch_cli.op_init("test seed")

    def tearDown(self) -> None:
        os.chdir(self._old_cwd)
        self._tmp.cleanup()

    def collapse(self, node_id: str) -> str:
        return arch_cli.op_collapse(node_id, f"{node_id} done", "spec")


class WalkingSkeletonTest(EngineTestCase):
    def test_not_ready_while_final_output_is_hole(self) -> None:
        self.collapse("entry_input")
        out = self.collapse("core_transform")
        self.assertNotIn("WALKING_SKELETON_READY", out)

    def test_not_ready_while_entry_is_hole(self) -> None:
        self.collapse("core_transform")
        out = self.collapse("final_output")
        self.assertNotIn("WALKING_SKELETON_READY", out)

    def test_ready_when_whole_trunk_is_solid(self) -> None:
        self.collapse("entry_input")
        self.collapse("core_transform")
        out = self.collapse("final_output")
        self.assertIn(
            "[WALKING_SKELETON_READY] 检测到无空洞可运行主干: "
            "entry_input -> core_transform -> final_output",
            out,
        )

    def test_fog_branch_does_not_block_skeleton(self) -> None:
        arch_cli.op_add_node(
            "fog_backup", "云端备份", "later", status="fog", after_node="final_output"
        )
        for nid in ("entry_input", "core_transform", "final_output"):
            out = self.collapse(nid)
        self.assertIn("WALKING_SKELETON_READY", out)

    def test_parallel_hole_branch_does_not_block_solid_path(self) -> None:
        # A Fan-out sibling that is still a hole should not hide a finished trunk.
        self.collapse("entry_input")  # stay under MAX_ACTIVE_HOLES before adding
        arch_cli.op_add_node("wav_dump", "? 录音落盘", "tbd", after_node="core_transform")
        for nid in ("core_transform", "final_output"):
            out = self.collapse(nid)
        self.assertIn("entry_input -> core_transform -> final_output", out)


class FocusOrderTest(EngineTestCase):
    def test_focus_picks_most_upstream_hole(self) -> None:
        # Insert a hole between entry and core; it is appended last in the node
        # list but sits upstream of core_transform in the graph.
        self.collapse("entry_input")
        arch_cli.op_add_node(
            "decoder", "? 解码", "tbd", after_node="entry_input", before_node="core_transform"
        )
        out = arch_cli.op_focus()
        self.assertIn('"id": "decoder"', out.split('"focus_node"')[1].split("}")[0])


def _snapshot(graph):
    """Order-insensitive view of the top-level graph for round-trip checks."""
    nodes = sorted((json.dumps(n, sort_keys=True, ensure_ascii=False) for n in graph["nodes"]))
    edges = sorted((e["from"], e["to"], e.get("contract", "")) for e in graph["edges"])
    return nodes, edges


class FoldTest(EngineTestCase):
    """Trunk used below: entry_input -> decoder -> core_transform -> final_output (all solid)."""

    def setUp(self) -> None:
        super().setUp()
        for nid in ("entry_input", "core_transform", "final_output"):
            self.collapse(nid)
        arch_cli.op_add_node(
            "decoder", "解码", "spec", status="solid",
            after_node="entry_input", before_node="core_transform", contract="Frame",
        )

    def graph(self):
        return arch_cli._load_graph()

    def test_fold_replaces_members_and_keeps_skeleton(self) -> None:
        out = arch_cli.op_fold(["decoder", "core_transform"], "proc", "处理模块", "解码并翻译")
        g = self.graph()
        ids = [n["id"] for n in g["nodes"]]
        self.assertNotIn("decoder", ids)
        self.assertIn("proc", ids)
        self.assertEqual(
            sorted((e["from"], e["to"]) for e in g["edges"]),
            [("entry_input", "proc"), ("proc", "final_output")],
        )
        self.assertIn("entry_input -> proc -> final_output", out)

    def test_unfold_round_trip_is_exact(self) -> None:
        before = _snapshot(self.graph())
        arch_cli.op_fold(["decoder", "core_transform"], "proc", "处理模块", "spec")
        arch_cli.op_unfold("proc")
        self.assertEqual(_snapshot(self.graph()), before)

    def test_nested_fold_round_trip(self) -> None:
        before = _snapshot(self.graph())
        arch_cli.op_fold(["decoder", "core_transform"], "proc", "处理模块", "spec")
        arch_cli.op_fold(["entry_input", "proc"], "front", "前端", "spec")
        with self.assertRaisesRegex(arch_cli.ArchEngineError, "front"):
            arch_cli.op_collapse("decoder", "x", "y")  # points at the outermost container
        arch_cli.op_unfold("front")
        arch_cli.op_unfold("proc")
        self.assertEqual(_snapshot(self.graph()), before)

    def test_rejects_unsettled_nodes(self) -> None:
        arch_cli.op_add_node("idea", "? 想法", "tbd", after_node="final_output")
        with self.assertRaisesRegex(arch_cli.ArchEngineError, "尚未确定"):
            arch_cli.op_fold(["final_output", "idea"], "s", "l", "s")

    def test_rejects_disconnected_members(self) -> None:
        with self.assertRaisesRegex(arch_cli.ArchEngineError, "不连通"):
            arch_cli.op_fold(["entry_input", "final_output"], "s", "l", "s")

    def test_rejects_fold_that_would_create_cycle(self) -> None:
        g = self.graph()
        g["edges"].append({"from": "entry_input", "to": "core_transform", "contract": "skip"})
        arch_cli._save_graph(g)
        # entry -> decoder -> core leaves the set and comes back in.
        with self.assertRaisesRegex(arch_cli.ArchEngineError, "形成环"):
            arch_cli.op_fold(["entry_input", "core_transform"], "s", "l", "s")

    def test_contract_changed_while_folded_is_restored(self) -> None:
        arch_cli.op_fold(["decoder", "core_transform"], "proc", "处理模块", "spec")
        arch_cli.op_collapse("final_output", "输出", "spec", in_contract="Subtitle[]")
        arch_cli.op_unfold("proc")
        edge = next(e for e in self.graph()["edges"] if e["to"] == "final_output")
        self.assertEqual((edge["from"], edge["contract"]), ("core_transform", "Subtitle[]"))

    def test_edge_added_while_folded_attaches_to_unique_exit(self) -> None:
        arch_cli.op_fold(["decoder", "core_transform"], "proc", "处理模块", "spec")
        arch_cli.op_add_node("logger", "日志", "spec", status="solid", after_node="proc")
        arch_cli.op_unfold("proc")
        edges = {(e["from"], e["to"]) for e in self.graph()["edges"]}
        self.assertIn(("core_transform", "logger"), edges)

    def test_ambiguous_new_edge_needs_attach(self) -> None:
        arch_cli.op_add_node("wav", "录音", "spec", status="solid", after_node="core_transform")
        arch_cli.op_fold(["core_transform", "final_output", "wav"], "back", "后端", "spec")
        arch_cli.op_add_node("archive", "归档", "spec", status="solid", after_node="back")
        with self.assertRaisesRegex(arch_cli.ArchEngineError, "attach"):
            arch_cli.op_unfold("back")
        arch_cli.op_unfold("back", {"archive": "wav"})
        edges = {(e["from"], e["to"]) for e in self.graph()["edges"]}
        self.assertIn(("wav", "archive"), edges)

    def test_super_node_blocks_node_level_operations(self) -> None:
        arch_cli.op_fold(["decoder", "core_transform"], "proc", "处理模块", "spec")
        for call in (
            lambda: arch_cli.op_collapse("proc", "x", "y"),
            lambda: arch_cli.op_export_task("proc"),
            lambda: arch_cli.op_reset_node("proc", "why"),
            lambda: arch_cli.op_deactivate_node("proc"),
        ):
            with self.assertRaisesRegex(arch_cli.ArchEngineError, "arch_unfold"):
                call()
        with self.assertRaisesRegex(arch_cli.ArchEngineError, "已折叠在超级节点 'proc'"):
            arch_cli.op_export_task("decoder")

    def test_focus_shows_super_node_compactly(self) -> None:
        arch_cli.op_fold(["decoder", "core_transform"], "proc", "处理模块", "spec")
        out = arch_cli.op_focus("proc")
        self.assertIn('"folded_children"', out)
        self.assertNotIn('"inner_edges"', out)

    def _adjacent_modules_graph(self):
        """entry -> decoder -> core -> final, plus a skip edge decoder -> final."""
        g = self.graph()
        for e in g["edges"]:
            if (e["from"], e["to"]) == ("decoder", "core_transform"):
                e["contract"] = "decoder->core"
        g["edges"].append({"from": "decoder", "to": "final_output", "contract": "decoder->final"})
        arch_cli._save_graph(g)
        return _snapshot(self.graph())

    def _assert_plain_edges(self) -> None:
        for e in self.graph()["edges"]:
            self.assertNotIn("members", e)
            self.assertNotIn("auto_contract", e)

    def test_adjacent_folds_round_trip_in_every_order(self) -> None:
        # Review finding: fold front, fold back, unfold front, unfold back lost
        # decoder -> final and merged its contract into decoder -> core.
        before = self._adjacent_modules_graph()
        orders = [
            (("front", "back"), ("front", "back")),
            (("front", "back"), ("back", "front")),
            (("back", "front"), ("front", "back")),
            (("back", "front"), ("back", "front")),
        ]
        groups = {"front": ["entry_input", "decoder"], "back": ["core_transform", "final_output"]}
        for fold_order, unfold_order in orders:
            with self.subTest(fold=fold_order, unfold=unfold_order):
                for sid in fold_order:
                    arch_cli.op_fold(groups[sid], sid, sid, "spec")
                for sid in unfold_order:
                    arch_cli.op_unfold(sid)
                self.assertEqual(_snapshot(self.graph()), before)
                self._assert_plain_edges()

    def test_contract_edited_between_two_modules_reaches_the_original_edges(self) -> None:
        self._adjacent_modules_graph()
        arch_cli.op_fold(["entry_input", "decoder"], "front", "前端", "spec")
        arch_cli.op_fold(["core_transform", "final_output"], "back", "后端", "spec")
        g = self.graph()
        edge = next(e for e in g["edges"] if (e["from"], e["to"]) == ("front", "back"))
        edge["contract"] = "Frame v2"  # edited while both sides are folded
        arch_cli._save_graph(g)
        arch_cli.op_unfold("front")
        arch_cli.op_unfold("back")
        edges = {(e["from"], e["to"]): e["contract"] for e in self.graph()["edges"]}
        self.assertEqual(edges[("decoder", "core_transform")], "Frame v2")
        self.assertEqual(edges[("decoder", "final_output")], "Frame v2")
        self._assert_plain_edges()

    def test_edge_attached_while_folded_survives_neighbour_folds(self) -> None:
        arch_cli.op_fold(["decoder", "core_transform"], "proc", "处理", "spec")
        arch_cli.op_add_node("logger", "日志", "spec", status="solid", after_node="proc")
        arch_cli.op_add_node("sink", "落盘", "spec", status="solid", after_node="logger")
        arch_cli.op_fold(["logger", "sink"], "obs", "观测", "spec")
        arch_cli.op_unfold("proc")   # logger edge is routed to proc's only exit child
        arch_cli.op_unfold("obs")
        edges = {(e["from"], e["to"]) for e in self.graph()["edges"]}
        self.assertIn(("core_transform", "logger"), edges)
        self.assertIn(("logger", "sink"), edges)
        self._assert_plain_edges()

    def test_focus_hides_edge_bookkeeping(self) -> None:
        arch_cli.op_fold(["decoder", "core_transform"], "proc", "处理模块", "spec")
        out = arch_cli.op_focus("proc")
        self.assertNotIn('"members"', out)
        self.assertNotIn('"auto_contract"', out)

    def test_folding_the_whole_trunk_keeps_the_skeleton(self) -> None:
        # Review finding: folding a finished trunk into one module dropped
        # WALKING_SKELETON_READY although nothing was undecided.
        out = arch_cli.op_fold(
            ["entry_input", "decoder", "core_transform", "final_output"], "all", "全部", "spec"
        )
        self.assertIn("[WALKING_SKELETON_READY] 检测到无空洞可运行主干: all", out)

    def test_whole_trunk_with_a_hole_inside_is_not_a_skeleton(self) -> None:
        g = self.graph()
        g["nodes"].append({"id": "gap", "label": "? 缺口", "status": "hole", "type": "port",
                           "spec": "", "file_path": "", "last_tag": ""})
        g["edges"].append({"from": "final_output", "to": "gap", "contract": "TBD"})
        arch_cli._save_graph(g)
        arch_cli.op_fold(["entry_input", "decoder", "core_transform", "final_output"], "all", "全部", "spec")
        self.assertIsNone(arch_cli._find_walking_skeleton(self.graph()))

    def _custom_graph(self, solids, holes, edges) -> None:
        mk = lambda i, st: {"id": i, "label": i, "status": st, "type": "port",
                            "spec": "", "file_path": "", "last_tag": ""}
        g = self.graph()
        g["nodes"] = [mk(i, "solid") for i in solids] + [mk(i, "hole") for i in holes]
        g["edges"] = [{"from": u, "to": v, "contract": "c"} for u, v in edges]
        arch_cli._save_graph(g)

    def test_skeleton_must_get_through_the_module_interior(self) -> None:
        # Review finding: s -> c enters the module at c, but only a -> t leaves
        # it and there is no path c -> a inside, so nothing is runnable.
        self._custom_graph(
            ["s", "a", "c", "t"], ["h1", "h2"],
            [("s", "c"), ("h1", "a"), ("a", "c"), ("a", "t"), ("c", "h2")],
        )
        self.assertIsNone(arch_cli._find_walking_skeleton(self.graph()))
        out = arch_cli.op_fold(["a", "c"], "m", "模块", "spec")
        self.assertNotIn("WALKING_SKELETON_READY", out)
        self.assertIsNone(arch_cli._find_walking_skeleton(self.graph()))

    def test_skeleton_through_module_when_interior_connects(self) -> None:
        self._custom_graph(["s", "a", "c", "t"], [], [("s", "a"), ("a", "c"), ("c", "t")])
        arch_cli.op_fold(["a", "c"], "m", "模块", "spec")
        self.assertEqual(arch_cli._find_walking_skeleton(self.graph()), ["s", "m", "t"])
        arch_cli.op_fold(["s", "m"], "outer", "外层", "spec")  # nested fold
        self.assertEqual(arch_cli._find_walking_skeleton(self.graph()), ["outer", "t"])

    def test_ambiguous_attachment_never_reports_a_false_skeleton(self) -> None:
        # Review finding: h2 hangs off a module with two exits; dropping that
        # undecided edge made the module look like a finished trunk.
        self._custom_graph(["a", "b", "c"], ["h1"], [("a", "b"), ("a", "c"), ("c", "h1")])
        arch_cli.op_fold(["a", "b", "c"], "m", "模块", "spec")
        out = arch_cli.op_add_node("h2", "? 待定", "spec", after_node="m")
        self.assertNotIn("WALKING_SKELETON_READY", out)
        # While h2's attachment is undecided the engine stays conservative.
        self.assertIsNone(arch_cli._find_walking_skeleton(self.graph()))
        folded = self.graph()
        arch_cli.op_unfold("m", {"h2": "b"})  # both exits blocked: not ready
        self.assertIsNone(arch_cli._find_walking_skeleton(self.graph()))
        arch_cli._save_graph(folded)
        arch_cli.op_unfold("m", {"h2": "c"})  # a -> b is free: ready
        self.assertEqual(arch_cli._find_walking_skeleton(self.graph()), ["a", "b"])

    def test_bypass_around_deactivated_neighbour_keeps_the_real_child(self) -> None:
        # Review finding: a -> x -> t with x deactivated came back as b -> t.
        self._custom_graph(["a", "b", "x", "t"], ["h"], [("a", "b"), ("a", "x"), ("x", "t"), ("b", "h")])
        arch_cli.op_fold(["a", "b"], "m", "模块", "spec")
        arch_cli.op_deactivate_node("x")
        arch_cli.op_unfold("m")
        edges = {(e["from"], e["to"]) for e in self.graph()["edges"]}
        self.assertIn(("a", "t"), edges)
        self.assertNotIn(("b", "t"), edges)
        self._assert_plain_edges()

    def test_bypass_merges_into_an_existing_module_edge(self) -> None:
        # m already reaches t through b; the bypass through x adds a -> t.
        self._custom_graph(["a", "b", "x", "t"], [], [("a", "b"), ("a", "x"), ("x", "t"), ("b", "t")])
        arch_cli.op_fold(["a", "b"], "m", "模块", "spec")
        arch_cli.op_deactivate_node("x")
        self.assertEqual(sum(1 for e in self.graph()["edges"] if (e["from"], e["to"]) == ("m", "t")), 1)
        arch_cli.op_unfold("m")
        edges = {(e["from"], e["to"]) for e in self.graph()["edges"]}
        self.assertTrue({("a", "t"), ("b", "t")} <= edges)

    def test_super_type_cannot_be_set_by_hand(self) -> None:
        with self.assertRaisesRegex(arch_cli.ArchEngineError, "arch_fold"):
            arch_cli.op_add_node("fake", "假的", "spec", status="solid", node_type="super_node")


class EdgeContractTest(EngineTestCase):
    def edge(self, u: str, v: str) -> dict:
        graph = json.loads(Path(".arch/graph.json").read_text(encoding="utf-8"))
        return next(e for e in graph["edges"] if (e["from"], e["to"]) == (u, v))

    def test_updates_exactly_one_edge(self) -> None:
        arch_cli.op_set_edge_contract("entry_input", "core_transform", "PCM 16k chunk")
        self.assertEqual(self.edge("entry_input", "core_transform")["contract"], "PCM 16k chunk")
        self.assertEqual(self.edge("core_transform", "final_output")["contract"], "TBD")

    def test_same_contract_is_a_no_op(self) -> None:
        arch_cli.op_set_edge_contract("entry_input", "core_transform", "x")
        step = json.loads(Path(".arch/graph.json").read_text(encoding="utf-8"))["step"]
        self.assertIn("已使用该契约", arch_cli.op_set_edge_contract("entry_input", "core_transform", "x"))
        self.assertEqual(json.loads(Path(".arch/graph.json").read_text(encoding="utf-8"))["step"], step)

    def test_missing_edge_is_rejected(self) -> None:
        with self.assertRaisesRegex(arch_cli.ArchEngineError, "找到 0 条"):
            arch_cli.op_set_edge_contract("final_output", "entry_input", "x")


class ExportUiTest(EngineTestCase):
    def export(self) -> str:
        arch_cli.op_export_ui()
        return Path(".arch/dashboard.html").read_text(encoding="utf-8")

    def embedded(self, page: str) -> dict:
        start = page.index('<script id="arch-data" type="application/json">') + len(
            '<script id="arch-data" type="application/json">')
        return json.loads(page[start:page.index("</script>", start)])

    def test_dashboard_is_self_contained(self) -> None:
        page = self.export()
        self.assertNotIn("__ARCH_", page)
        self.assertNotRegex(page, r"(src|href)=\"https?://")

    def test_node_text_cannot_break_out_of_the_data_script(self) -> None:
        arch_cli.op_collapse("entry_input", "</script><script>alert(1)</script>", "a < b && c")
        page = self.export()
        self.assertNotIn("</script><script>alert(1)", page)
        data = self.embedded(page)
        labels = [n["label"] for n in data["graph"]["nodes"]]
        self.assertIn("</script><script>alert(1)</script>", labels)

    def test_payload_carries_engine_decisions(self) -> None:
        self.collapse("entry_input")
        data = self.embedded(self.export())
        self.assertEqual(data["next_focus"], "core_transform")
        self.assertEqual(data["topo_order"], ["entry_input", "core_transform", "final_output"])
        self.assertIsNone(data["skeleton"])
        self.assertEqual(data["seed"], "test seed")


class SignatureDetectionTest(unittest.TestCase):
    def check(self, line: str) -> bool:
        return bool(arch_cli.SIGNATURE_LINE.match(line))

    def test_detects_declarations_across_languages(self) -> None:
        for line in (
            "+def read(frame):",
            "-    async def read(frame):",
            "+export function encode(x) {",
            "+export default class Router {",
            "+func Encode(b []byte) error {",
            "+pub fn encode(b: &[u8]) -> Vec<u8> {",
            "+pub(crate) struct Frame {",
            "+public interface Port {",
            "+type Frame = { ts: number }",
            # Review finding: exported bindings are public API as well.
            "+export const encode = (value: number) => value",
            "-export const encode = (value: string) => value",
            "+export let handler = async (req) => {",
            "+export default (frame) => frame",
            "+module.exports = { encode }",
            "-export { encode }",
            "+export { decode as encode } from './codec'",
            "+export * from './frames'",
            "+export type { Frame } from './types'",
            "+export = Codec;",
            "+exports.encode = function (v) {",
        ):
            self.assertTrue(self.check(line), line)

    def test_ignores_keywords_inside_ordinary_lines(self) -> None:
        for line in (
            '+    print("def is a keyword")',
            "+    node_type = 'port'",
            "+    # refactor: function signature unchanged",
            "+    return classify(x)",
            "+    const local = (x) => x * 2",
            "+    exportedCount = 3",
        ):
            self.assertFalse(self.check(line), line)


if __name__ == "__main__":
    unittest.main()

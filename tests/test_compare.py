import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mailtrace.parsing import compare_headers  # noqa: E402
from mailtrace.parsing.compare import _align, _node_key  # noqa: E402
from mailtrace.parsing.sample import SAMPLE_HEADERS, SAMPLE_HEADERS_B  # noqa: E402

T0 = "Wed, 23 Sep 2026 02:00:00 +0000"
T1 = "Wed, 23 Sep 2026 02:00:10 +0000"
T2 = "Wed, 23 Sep 2026 02:00:20 +0000"
T3 = "Wed, 23 Sep 2026 02:00:30 +0000"


def make_headers(*received_values: str) -> str:
    """按投递顺序（最早 -> 最晚）生成头部文本（Received 书写顺序相反）。"""
    lines = [f"Received: {value}" for value in reversed(received_values)]
    return "\n".join(lines) + "\n"


def hop(by: str | None, ip: str | None, date: str | None) -> str:
    parts = []
    if ip:
        parts.append(f"from peer.example (peer.example [{ip}])")
    else:
        parts.append("from peer.example")
    if by:
        parts.append(f"by {by}")
    parts.append("with ESMTP")
    value = " ".join(parts)
    if date:
        value += f"; {date}"
    return value


class AlignTests(unittest.TestCase):
    def test_repeated_names_use_global_order_preserving_alignment(self):
        # A = [x, a, x]，B = [a, x, x]：贪心“首次命中”会产生交叉配对，
        # 保序全局对齐应得到 2 对匹配且顺序不交叉。
        keys_a = [("x", None), ("a", None), ("x", None)]
        keys_b = [("a", None), ("x", None), ("x", None)]
        pairs = _align(keys_a, keys_b)
        self.assertEqual(len(pairs), 2)  # 最优匹配对数（首次命中会得到交叉的 3 对）
        a_idx = [i for i, _ in pairs]
        b_idx = [j for _, j in pairs]
        self.assertEqual(a_idx, sorted(a_idx))
        self.assertEqual(b_idx, sorted(b_idx))
        # 确定性的对齐结果：a↔a 配对，A 的第二个 x 配 B 的第一个 x
        self.assertEqual(pairs, [(1, 0), (2, 1)])

    def test_identityless_nodes_never_match(self):
        pairs = _align([None, ("x", None)], [None, ("x", None)])
        self.assertEqual(pairs, [(1, 1)])

    def test_node_key_requires_identity(self):
        self.assertIsNone(_node_key({"by_host": None, "ip": None}))
        self.assertEqual(
            _node_key({"by_host": "MX.Example.", "ip": None}),
            ("mx.example", None),
        )
        self.assertEqual(
            _node_key({"by_host": None, "ip": "192.0.2.1"}),
            (None, "192.0.2.1"),
        )


class CompareBasicTests(unittest.TestCase):
    def test_common_added_missing_counts_and_order(self):
        headers_a = make_headers(
            hop("n1.example", None, T0),
            hop("n2.example", None, T1),
            hop("n3.example", None, T2),
        )
        headers_b = make_headers(
            hop("n1.example", None, T0),
            hop("nx.example", None, T1),
            hop("n2.example", None, T2),
            hop("n3.example", None, T3),
        )
        result = compare_headers(headers_a, headers_b)
        self.assertIsNone(result["error"])
        self.assertEqual(result["counts"]["common"], 3)
        self.assertEqual(result["counts"]["added"], 1)
        self.assertEqual(result["counts"]["missing"], 0)

        kinds = [row["kind"] for row in result["rows"]]
        self.assertEqual(kinds, ["common", "added", "common", "common"])
        added = result["rows"][1]
        self.assertIsNone(added["a"])
        self.assertEqual(added["b"]["by_host"], "nx.example")

    def test_common_row_delay_diff(self):
        headers_a = make_headers(
            hop("n1.example", None, T0),
            hop("n2.example", None, T2),  # A 侧相邻耗时 20 秒
        )
        headers_b = make_headers(
            hop("n1.example", None, T0),
            hop("n2.example", None, T1),  # B 侧相邻耗时 10 秒
        )
        result = compare_headers(headers_a, headers_b)
        row = result["rows"][1]
        self.assertEqual(row["kind"], "common")
        delay = row["delay"]
        self.assertTrue(delay["comparable"])
        self.assertEqual(delay["a_seconds"], 20)
        self.assertEqual(delay["b_seconds"], 10)
        self.assertEqual(delay["diff_seconds"], 10)
        self.assertEqual(delay["diff_human"], "+10 秒")

    def test_first_hop_delay_not_comparable(self):
        headers_a = make_headers(hop("n1.example", None, T0))
        headers_b = make_headers(hop("n1.example", None, T0))
        result = compare_headers(headers_a, headers_b)
        delay = result["rows"][0]["delay"]
        self.assertFalse(delay["comparable"])
        self.assertIsNone(delay["diff_seconds"])

    def test_repeated_same_name_nodes_align_in_order(self):
        # 两侧都重复出现同一节点名：配对必须保序（第 2 个配第 2 个）。
        headers_a = make_headers(
            hop("dup.example", None, T0),
            hop("mid.example", None, T1),
            hop("dup.example", None, T2),
        )
        headers_b = make_headers(
            hop("dup.example", None, T0),
            hop("dup.example", None, T1),
        )
        result = compare_headers(headers_a, headers_b)
        self.assertEqual(result["counts"]["common"], 2)
        commons = [r for r in result["rows"] if r["kind"] == "common"]
        # A 的第 1 个 dup 配 B 的第 1 个，A 的第 2 个配 B 的第 2 个
        self.assertEqual(commons[0]["a"]["path_index"], 1)
        self.assertEqual(commons[0]["b"]["path_index"], 1)
        self.assertEqual(commons[1]["a"]["path_index"], 3)
        self.assertEqual(commons[1]["b"]["path_index"], 2)
        # mid.example 仅 A 有 -> 缺失，且位于两对共有节点之间
        kinds = [row["kind"] for row in result["rows"]]
        self.assertEqual(kinds, ["common", "missing", "common"])


class IdentityTests(unittest.TestCase):
    def test_same_by_host_different_ip_not_matched(self):
        headers_a = make_headers(hop("mx.example", "192.0.2.1", T0))
        headers_b = make_headers(hop("mx.example", "192.0.2.2", T0))
        result = compare_headers(headers_a, headers_b)
        self.assertEqual(result["counts"]["common"], 0)
        self.assertEqual(result["counts"]["missing"], 1)
        self.assertEqual(result["counts"]["added"], 1)

    def test_host_matching_is_case_and_dot_insensitive(self):
        headers_a = make_headers(hop("MX.Example.", None, T0))
        headers_b = make_headers(hop("mx.example", None, T0))
        result = compare_headers(headers_a, headers_b)
        self.assertEqual(result["counts"]["common"], 1)

    def test_identityless_nodes_not_matched_by_time(self):
        # 两侧节点都没有 by/ IP 身份，即使时间完全相同也不能配成同一跳
        headers_a = make_headers(hop(None, None, T0))
        headers_b = make_headers(hop(None, None, T0))
        result = compare_headers(headers_a, headers_b)
        self.assertEqual(result["counts"]["common"], 0)
        self.assertEqual(result["counts"]["missing"], 1)
        self.assertEqual(result["counts"]["added"], 1)


class DelayValidityTests(unittest.TestCase):
    def test_invalid_time_not_comparable_and_no_splicing(self):
        # A 中间跳缺时间：n3 的相邻耗时不可计算（不允许跳过 n2 拼接 T3-T0）
        headers_a = make_headers(
            hop("n1.example", None, T0),
            hop("n2.example", None, None),
            hop("n3.example", None, T3),
        )
        headers_b = make_headers(
            hop("n1.example", None, T0),
            hop("n2.example", None, T1),
            hop("n3.example", None, T3),
        )
        result = compare_headers(headers_a, headers_b)
        self.assertEqual(result["counts"]["common"], 3)
        last = result["rows"][-1]
        self.assertEqual(last["kind"], "common")
        self.assertIsNone(last["a"]["delay_seconds"])  # 未拼接耗时
        self.assertEqual(last["b"]["delay_seconds"], 20)
        self.assertFalse(last["delay"]["comparable"])
        self.assertIsNone(last["delay"]["diff_seconds"])
        self.assertIsNone(last["delay"]["diff_human"])

    def test_unparseable_time_side_not_comparable(self):
        headers_a = make_headers(
            hop("n1.example", None, T0),
            hop("n2.example", None, "totally-not-a-date"),
        )
        headers_b = make_headers(
            hop("n1.example", None, T0),
            hop("n2.example", None, T1),
        )
        result = compare_headers(headers_a, headers_b)
        last = result["rows"][-1]
        self.assertEqual(last["kind"], "common")
        self.assertFalse(last["delay"]["comparable"])


class ErrorTests(unittest.TestCase):
    def test_side_a_without_received_is_clear_error(self):
        result = compare_headers("Subject: hi\nFrom: a@example\n", make_headers(hop("n1", None, T0)))
        self.assertIn("头部 A", result["error"])
        self.assertEqual(result["side"], "a")
        self.assertEqual(result["rows"], [])

    def test_side_b_without_received_is_clear_error(self):
        result = compare_headers(make_headers(hop("n1", None, T0)), "Subject: hi\n")
        self.assertIn("头部 B", result["error"])
        self.assertEqual(result["side"], "b")

    def test_empty_input_reports_error(self):
        result = compare_headers("", "")
        self.assertIsNotNone(result["error"])


class SampleDataTests(unittest.TestCase):
    def test_sample_pair_aligns_as_documented(self):
        result = compare_headers(SAMPLE_HEADERS, SAMPLE_HEADERS_B)
        self.assertIsNone(result["error"])
        counts = result["counts"]
        # B 新增 relay3 与“换了上游 IP 的 relay2”两跳；
        # A 原 relay2 跳因身份不同记为缺失
        self.assertEqual(counts["added"], 2)
        self.assertEqual(counts["missing"], 1)
        self.assertEqual(counts["common"], 6)
        self.assertEqual(counts["a_total"], 7)
        self.assertEqual(counts["b_total"], 8)

        kinds = [row["kind"] for row in result["rows"]]
        # 结构顺序：共有段之间夹着 缺失/新增 段
        self.assertEqual(
            kinds,
            ["common", "common", "common", "missing", "added", "added",
             "common", "common", "common"],
        )

        # A 侧前三跳（坏时间/无时间/上游无时间）均不可比较
        commons = [r for r in result["rows"] if r["kind"] == "common"]
        self.assertFalse(commons[0]["delay"]["comparable"])
        self.assertFalse(commons[1]["delay"]["comparable"])
        self.assertFalse(commons[2]["delay"]["comparable"])
        # mx1 跳：A 10 秒 vs B 5 秒 -> 差值 +5 秒
        mx1 = commons[3]
        self.assertEqual(mx1["matched_on"], {"by_host": "mx1.final.example", "ip": "203.0.113.22"})
        self.assertTrue(mx1["delay"]["comparable"])
        self.assertEqual(mx1["delay"]["diff_seconds"], 5)


if __name__ == "__main__":
    unittest.main()

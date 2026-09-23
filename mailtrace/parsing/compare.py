"""双份邮件头部投递路径对照（复用单份解析结果）。

匹配与对齐规则：
- 节点身份 = ``(by 主机名规范化, 对端 IP)`` 二元组，两项都缺失的节点
  没有身份，**不参与匹配**——不会仅凭时间相近就被当作同一跳；
- 同名节点重复出现时，使用**保序全局对齐**（LCS 动态规划，最大化匹配
  对数且保持两侧结构顺序），而不是“首次命中”式的贪心配对；
- 共有节点的耗时直接取各自单份分析中的“相邻节点耗时”，任一侧无效
  即标记为不可比较，**绝不跳过中间无时间的节点拼接耗时**。
"""

from __future__ import annotations

from .parser import analyze_headers, humanize_delay

# 对照结果中行的类别
KIND_COMMON = "common"    # 两侧共有
KIND_ADDED = "added"      # 仅头部 B 出现（相对 A 新增）
KIND_MISSING = "missing"  # 仅头部 A 出现（相对 B 缺失）


def _normalize_host(host: str | None) -> str | None:
    """主机名规范化：去空白、小写、去 FQDN 末尾点号。"""
    if not host:
        return None
    normalized = host.strip().lower().rstrip(".")
    return normalized or None


def _node_key(hop: dict) -> tuple[str | None, str | None] | None:
    """节点身份键：``(by 主机, 对端 IP)``；两者皆无则返回 ``None``（不可匹配）。"""
    by_host = _normalize_host(hop.get("by_host"))
    ip = hop.get("ip") or None
    if by_host is None and ip is None:
        return None
    return (by_host, ip)


def _align(keys_a: list, keys_b: list) -> list[tuple[int, int]]:
    """保序全局对齐：返回匹配下标对 ``[(i, j), ...]``（两侧均升序）。

    等价于在“仅允许身份完全相同的节点配对”的约束下求最多匹配对的
    全局对齐（LCS 动态规划）。回溯时优先跳过本侧多余节点，使并列解中
    靠前的节点优先配对，结果确定且保持结构顺序；身份为 ``None`` 的
    节点永远不相等，因此绝不会被配对。
    """
    n, m = len(keys_a), len(keys_b)
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        key_i = keys_a[i - 1]
        row, prev = dp[i], dp[i - 1]
        for j in range(1, m + 1):
            if key_i is not None and key_i == keys_b[j - 1]:
                row[j] = prev[j - 1] + 1
            else:
                row[j] = prev[j] if prev[j] >= row[j - 1] else row[j - 1]

    pairs: list[tuple[int, int]] = []
    i, j = n, m
    while i > 0 and j > 0:
        if dp[i - 1][j] == dp[i][j]:
            i -= 1  # A 侧该节点无法提升匹配数：记为未配对
        elif dp[i][j - 1] == dp[i][j]:
            j -= 1  # B 侧同理
        else:
            # 此时两侧身份必然相同（否则 dp[i][j] 等于某一相邻值）
            pairs.append((i - 1, j - 1))
            i -= 1
            j -= 1
    pairs.reverse()
    return pairs


def _humanize_diff(seconds: float) -> str:
    """耗时差值格式化：带正负号，便于直观看哪一侧更慢。"""
    if seconds == 0:
        return "0 秒"
    sign = "+" if seconds > 0 else "-"
    magnitude = abs(seconds)
    if float(magnitude).is_integer():
        magnitude = int(magnitude)
    return sign + humanize_delay(magnitude)


def _delay_compare(hop_a: dict, hop_b: dict) -> dict:
    """共有节点的相邻耗时对照；任一侧无效则不可比较（不拼接耗时）。"""
    delay_a = hop_a.get("delay_seconds")
    delay_b = hop_b.get("delay_seconds")
    comparable = delay_a is not None and delay_b is not None
    diff = (delay_a - delay_b) if comparable else None
    return {
        "comparable": comparable,
        "a_seconds": delay_a,
        "a_human": hop_a.get("delay_human"),
        "b_seconds": delay_b,
        "b_human": hop_b.get("delay_human"),
        "diff_seconds": diff,
        "diff_human": _humanize_diff(diff) if comparable else None,
    }


def _side_brief(result: dict) -> dict:
    return {
        "hop_count": result["hop_count"],
        "timed_count": result["timed_count"],
        "missing_count": result["missing_count"],
        "total_span_seconds": result["total_span_seconds"],
        "total_span_human": result["total_span_human"],
    }


def _empty_counts() -> dict:
    return {"common": 0, "added": 0, "missing": 0, "a_total": 0, "b_total": 0}


def compare_headers(text_a: str, text_b: str) -> dict:
    """对照两份原始头部的投递路径，返回供页面/API 使用的结构化结果。

    任一侧没有 ``Received`` 字段时返回带明确 ``error`` 的字典。
    """
    result_a = analyze_headers(text_a)
    result_b = analyze_headers(text_b)

    for label, result in (("A", result_a), ("B", result_b)):
        if result["hop_count"] == 0:
            return {
                "error": f"头部 {label} 中未找到任何 Received 字段，无法进行路径对照",
                "side": label.lower(),
                "counts": _empty_counts(),
                "rows": [],
            }

    path_a = result_a["path"]
    path_b = result_b["path"]
    keys_a = [_node_key(h) for h in path_a]
    keys_b = [_node_key(h) for h in path_b]

    pairs = _align(keys_a, keys_b)

    # 按结构顺序合并两侧：未配对段 -> 新增/缺失行，配对 -> 共有行
    rows: list[dict] = []

    def emit(
        kind: str,
        hop_a: dict | None,
        hop_b: dict | None,
        key: tuple[str | None, str | None] | None = None,
    ) -> None:
        row: dict = {
            "index": len(rows) + 1,
            "kind": kind,
            "a": hop_a,
            "b": hop_b,
            "matched_on": None,
            "delay": None,
        }
        if kind == KIND_COMMON:
            by_host, ip = key
            row["matched_on"] = {"by_host": by_host, "ip": ip}
            row["delay"] = _delay_compare(hop_a, hop_b)
        rows.append(row)

    cursor_a = cursor_b = 0
    for idx_a, idx_b in pairs:
        for k in range(cursor_a, idx_a):
            emit(KIND_MISSING, path_a[k], None)
        for k in range(cursor_b, idx_b):
            emit(KIND_ADDED, None, path_b[k])
        emit(KIND_COMMON, path_a[idx_a], path_b[idx_b], keys_a[idx_a])
        cursor_a, cursor_b = idx_a + 1, idx_b + 1
    for k in range(cursor_a, len(path_a)):
        emit(KIND_MISSING, path_a[k], None)
    for k in range(cursor_b, len(path_b)):
        emit(KIND_ADDED, None, path_b[k])

    counts = {
        "common": sum(1 for r in rows if r["kind"] == KIND_COMMON),
        "added": sum(1 for r in rows if r["kind"] == KIND_ADDED),
        "missing": sum(1 for r in rows if r["kind"] == KIND_MISSING),
        "a_total": len(path_a),
        "b_total": len(path_b),
    }

    return {
        "error": None,
        "counts": counts,
        "side_a": _side_brief(result_a),
        "side_b": _side_brief(result_b),
        "rows": rows,
    }

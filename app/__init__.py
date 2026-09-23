"""邮件投递路径检查 Flask 应用。"""

from __future__ import annotations

import os

from flask import Flask, jsonify, render_template, request

from mailtrace.parsing import analyze_headers, compare_headers
from mailtrace.parsing.sample import SAMPLE_HEADERS, SAMPLE_HEADERS_B


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def create_app() -> Flask:
    app = Flask(__name__)
    max_input_kb = _env_int("MAX_INPUT_KB", 256)
    app.config["MAX_INPUT_BYTES"] = max_input_kb * 1024
    app.config["SAMPLE_HEADERS"] = SAMPLE_HEADERS
    app.config["SAMPLE_HEADERS_B"] = SAMPLE_HEADERS_B

    def render_index(**extra):
        context = {
            "sample": SAMPLE_HEADERS,
            "sample_b": SAMPLE_HEADERS_B,
            "max_input_kb": max_input_kb,
        }
        context.update(extra)
        return render_template("index.html", **context)

    @app.get("/")
    def index():
        return render_index()

    def _check_size(raw_headers: str, side: str | None = None) -> str | None:
        """返回错误消息；未超限返回 None。side 用于对照场景的 “A 侧/B 侧” 提示。"""
        max_bytes = app.config["MAX_INPUT_BYTES"]
        if len(raw_headers.encode("utf-8", errors="ignore")) > max_bytes:
            prefix = f"{side} 侧" if side else ""
            return f"{prefix}输入超过 {max_input_kb} KB 上限，请截取头部后重试"
        return None

    def _do_analyze(raw_headers: str) -> dict:
        error = _check_size(raw_headers)
        if error:
            return {"error": error, "hop_count": 0, "path": []}
        if not raw_headers.strip():
            return {
                "error": "请先粘贴邮件原始头部（包含至少一个 Received 字段）",
                "hop_count": 0,
                "path": [],
            }
        return analyze_headers(raw_headers)

    def _do_compare(headers_a: str, headers_b: str) -> dict:
        for side, raw in (("A", headers_a), ("B", headers_b)):
            error = _check_size(raw, side)
            if error:
                return {"error": error}
        if not headers_a.strip() or not headers_b.strip():
            return {
                "error": "请在 A、B 两侧分别粘贴邮件原始头部"
                "（各包含至少一个 Received 字段）"
            }
        return compare_headers(headers_a, headers_b)

    @app.post("/analyze")
    def analyze_form():
        raw_headers = request.form.get("headers_a", "") or request.form.get("headers", "")
        result = _do_analyze(raw_headers)
        return render_index(
            headers_a=raw_headers,
            headers_b=request.form.get("headers_b", ""),
            result=result,
        )

    @app.post("/compare")
    def compare_form():
        headers_a = request.form.get("headers_a", "")
        headers_b = request.form.get("headers_b", "")
        compare = _do_compare(headers_a, headers_b)
        return render_index(
            headers_a=headers_a,
            headers_b=headers_b,
            compare=compare,
        )

    @app.post("/api/analyze")
    def analyze_api():
        if request.is_json:
            payload = request.get_json(silent=True) or {}
            raw_headers = payload.get("headers", "")
        else:
            raw_headers = request.form.get("headers", "")
        if not isinstance(raw_headers, str):
            return jsonify({"error": "headers 必须是字符串"}), 400
        result = _do_analyze(raw_headers)
        status = 400 if result.get("error") else 200
        return jsonify(result), status

    @app.post("/api/compare")
    def compare_api():
        if request.is_json:
            payload = request.get_json(silent=True) or {}
            headers_a = payload.get("headers_a", "")
            headers_b = payload.get("headers_b", "")
        else:
            headers_a = request.form.get("headers_a", "")
            headers_b = request.form.get("headers_b", "")
        if not isinstance(headers_a, str) or not isinstance(headers_b, str):
            return jsonify({"error": "headers_a 和 headers_b 必须是字符串"}), 400
        result = _do_compare(headers_a, headers_b)
        status = 400 if result.get("error") else 200
        return jsonify(result), status

    @app.get("/healthz")
    def healthz():
        return jsonify({"status": "ok"})

    return app

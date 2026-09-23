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

    def _page_context(**extra) -> dict:
        context = {
            "sample": SAMPLE_HEADERS,
            "sample_b": SAMPLE_HEADERS_B,
            "max_input_kb": max_input_kb,
        }
        context.update(extra)
        return context

    @app.get("/")
    def index():
        return render_template("index.html", **_page_context())

    def _check_size(raw_headers: str, label: str = "输入") -> str | None:
        max_bytes = app.config["MAX_INPUT_BYTES"]
        if len(raw_headers.encode("utf-8", errors="ignore")) > max_bytes:
            return f"{label}超过 {max_input_kb} KB 上限，请截取头部后重试"
        return None

    def _do_analyze(raw_headers: str) -> dict:
        oversize = _check_size(raw_headers)
        if oversize:
            return {"error": oversize, "hop_count": 0, "path": []}
        if not raw_headers.strip():
            return {
                "error": "请先粘贴邮件原始头部（包含至少一个 Received 字段）",
                "hop_count": 0,
                "path": [],
            }
        return analyze_headers(raw_headers)

    @app.post("/analyze")
    def analyze_form():
        raw_headers = request.form.get("headers", "")
        result = _do_analyze(raw_headers)
        return render_template(
            "index.html",
            **_page_context(raw_headers=raw_headers, result=result),
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

    def _do_compare(headers_a: str, headers_b: str) -> dict:
        for label, text in (("A", headers_a), ("B", headers_b)):
            oversize = _check_size(text, label=f"头部 {label} ")
            if oversize:
                return {"error": oversize, "rows": []}
        for label, text in (("A", headers_a), ("B", headers_b)):
            if not text.strip():
                return {
                    "error": f"头部 {label} 为空，请粘贴包含 Received 字段的原始头部",
                    "side": label.lower(),
                    "rows": [],
                }
        return compare_headers(headers_a, headers_b)

    @app.post("/compare")
    def compare_form():
        headers_a = request.form.get("headers_a", "")
        headers_b = request.form.get("headers_b", "")
        compare = _do_compare(headers_a, headers_b)
        return render_template(
            "index.html",
            **_page_context(
                headers_a=headers_a,
                headers_b=headers_b,
                compare=compare,
            ),
        )

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
            return jsonify({"error": "headers_a 与 headers_b 必须是字符串"}), 400
        result = _do_compare(headers_a, headers_b)
        status = 400 if result.get("error") else 200
        return jsonify(result), status

    @app.get("/healthz")
    def healthz():
        return jsonify({"status": "ok"})

    return app

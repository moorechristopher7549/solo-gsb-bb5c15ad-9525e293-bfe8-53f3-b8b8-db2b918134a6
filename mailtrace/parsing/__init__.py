"""邮件原始头部解析包。"""

from .compare import compare_headers
from .parser import analyze_headers, parse_header_blocks

__all__ = ["analyze_headers", "compare_headers", "parse_header_blocks"]

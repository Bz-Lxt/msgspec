"""msgspec 跨版本消息定义兼容性检查。

典型用法::

    from schema_compat import check_compat, format_report

    report = check_compat(OldMessage, NewMessage)
    print(format_report(report))

结论按「方向（旧数据给新解码器 / 新数据给旧解码器）× 线格式（JSON /
MessagePack）」四个格子分别给出，每条原因都带有稳定的 ``code`` 与可定位的
``path``；依赖 enc_hook/dec_hook 或 MessagePack Ext type code 的部分一律标记为
``UNKNOWN``。
"""

from __future__ import annotations

import json
from typing import Any

from ._checker import (
    DIRECTIONS,
    JSON,
    MSGPACK,
    NEW_TO_OLD,
    OLD_TO_NEW,
    PROTOCOLS,
    CompatReport,
    Issue,
    Issue as IssueType,
    Severity,
    check_compat,
)

__all__ = [
    "check_compat",
    "format_report",
    "report_to_jsonish",
    "report_to_json",
    "Severity",
    "CompatReport",
    "Issue",
]

_LABELS = {
    OLD_TO_NEW: "旧数据 → 新解码器",
    NEW_TO_OLD: "新数据 → 旧解码器",
}

_SEV_MARK = {
    Severity.SAFE: "✅ SAFE",
    Severity.LOSSY: "⚠️  LOSSY",
    Severity.UNSAFE: "❌ UNSAFE",
    Severity.UNKNOWN: "❓ UNKNOWN",
}


def format_report(report: CompatReport) -> str:
    """把报告渲染为可读文本（中文）。"""
    lines: list[str] = []
    lines.append(f"旧定义: {report.old_root}")
    lines.append(f"新定义: {report.new_root}")
    lines.append("")
    lines.append("兼容性矩阵:")
    header = "方向".ljust(20) + "".join(p.ljust(12) for p in ("JSON", "MessagePack"))
    lines.append(header)
    for d in DIRECTIONS:
        row = _LABELS[d].ljust(20)
        for p in PROTOCOLS:
            row += report.verdict(d, p).ljust(12)
        lines.append(row)
    lines.append("")

    if not report.issues:
        lines.append("未发现兼容性问题：四个方向均可安全交换。")
        return "\n".join(lines)

    # 按最高严重度排序，UNKNOWN/UNSAFE 在前；同级别保持产生顺序（稳定）。
    from ._checker import _ORDER

    ordered = sorted(
        report.issues,
        key=lambda iss: -max(_ORDER[s] for s in iss.cells.values()),
    )
    lines.append(f"问题明细（{len(report.issues)} 条，按严重度排序）:")
    for iss in ordered:
        top = _top_severity(iss)
        lines.append("")
        lines.append(f"{_SEV_MARK[top]} [{iss.code}]  {iss.path}")
        lines.append(f"    {iss.message}")
        if iss.old is not None or iss.new is not None:
            lines.append(f"    旧: {iss.old}")
            lines.append(f"    新: {iss.new}")
        impact = _format_cells(iss)
        lines.append(f"    影响: {impact}")
    return "\n".join(lines)


def _top_severity(iss: IssueType) -> str:
    from ._checker import _ORDER

    return max(iss.cells.values(), key=lambda s: _ORDER[s])


def _format_cells(iss: IssueType) -> str:
    parts = []
    for d in DIRECTIONS:
        sevs = []
        for p in PROTOCOLS:
            sevs.append(f"{p}={iss.cells.get((d, p), Severity.SAFE)}")
        parts.append(f"{_LABELS[d]}（{', '.join(sevs)}）")
    return "；".join(parts)


def report_to_jsonish(report: CompatReport) -> dict[str, Any]:
    """把报告导出为可 JSON 序列化的普通 dict。"""
    return {
        "old_root": report.old_root,
        "new_root": report.new_root,
        "matrix": report.matrix,
        "issues": [
            {
                "code": iss.code,
                "path": iss.path,
                "message": iss.message,
                "old": iss.old,
                "new": iss.new,
                "cells": [
                    {
                        "direction": d,
                        "protocol": p,
                        "severity": iss.cells.get((d, p), Severity.SAFE),
                    }
                    for d in DIRECTIONS
                    for p in PROTOCOLS
                ],
            }
            for iss in report.issues
        ],
    }


def report_to_json(report: CompatReport, *, indent: int = 2) -> str:
    return json.dumps(report_to_jsonish(report), ensure_ascii=False, indent=indent)

"""命令行入口：

    python -m schema_compat pkg.module_v1:Message pkg.module_v2:Message
    python -m schema_compat pkg.module_v1:Message pkg.module_v2:Message --json
"""

from __future__ import annotations

import argparse
import importlib
import sys
from typing import Any

from schema_compat import check_compat, format_report, report_to_json


def _load(ref: str) -> Any:
    if ":" not in ref:
        raise SystemExit(
            f"类型引用 {ref!r} 格式应为 'module.path:TypeName'"
        )
    module_name, attr = ref.split(":", 1)
    module = importlib.import_module(module_name)
    try:
        return getattr(module, attr)
    except AttributeError:
        raise SystemExit(f"模块 {module_name!r} 中不存在类型 {attr!r}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m schema_compat",
        description="比较 msgspec 消息的新旧定义，判断跨版本 JSON/MessagePack "
                    "交换是否安全。",
    )
    parser.add_argument("old_type", help="旧定义，形如 pkg.mod_v1:Message")
    parser.add_argument("new_type", help="新定义，形如 pkg.mod_v2:Message")
    parser.add_argument("--json", action="store_true",
                        help="输出机器可读的 JSON 报告")
    args = parser.parse_args(argv)

    report = check_compat(_load(args.old_type), _load(args.new_type))
    if args.json:
        print(report_to_json(report))
    else:
        print(format_report(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())

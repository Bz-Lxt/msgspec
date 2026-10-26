"""运行全部演示：python -m schema_compat.demo.demo

也可以对任意一对类型单独使用命令行::

    python -m schema_compat schema_compat.demo.v1:Payment \\
        schema_compat.demo.v2:Payment
"""

from __future__ import annotations

from schema_compat import check_compat, format_report
from schema_compat.demo import arr_v1, arr_v2, hooks_v1, hooks_v2, v1, v2


CASES = [
    ("① object 线格式：支付事件 v1 -> v2（字段/别名/标签/枚举/约束/嵌套）",
     v1.Payment, v2.Payment),
    ("② array_like 线格式：遥测采样 v1 -> v2（位置重排/尾部追加/长度约束）",
     arr_v1.Sample, arr_v2.Sample),
    ("③ 钩子与扩展：GeoPoint(CustomType) + msgpack.Ext",
     hooks_v1.Envelope, hooks_v2.Envelope),
]


def main() -> None:
    for title, old, new in CASES:
        print("=" * 78)
        print(title)
        print("=" * 78)
        report = check_compat(old, new)
        print(format_report(report))
        print()


if __name__ == "__main__":
    main()

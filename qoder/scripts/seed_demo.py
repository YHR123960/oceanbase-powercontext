#!/usr/bin/env python3
"""Load the demo dataset used by the runbook and the verification samples.

Everything written here becomes PowerContext Atomic Memory - the script keeps no copy.
Re-running is safe: existing entries from a previous seed are detected and skipped.

The dataset is CONSTRUCTED SAMPLE TEXT written for this repository to exercise retrieval,
tasks and the progress timeline. It is not real classmate feedback and is not usage data,
so every note carries the "构造样例" tag and every demo progress memo repeats that marker.

    python scripts/seed_demo.py [--pc-url http://127.0.0.1:2893] [--workspace default]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from yanxi.pc import PCClient  # noqa: E402
from yanxi.store import Workbench  # noqa: E402

SEED_MARK = "seed:demo-v2"
SAMPLE_TAG = "构造样例"

NOTES = [
    {
        "title": "检索增强生成的引用可靠性（RAG citation）",
        "course": "科研阅读",
        "tags": [SAMPLE_TAG, "RAG", "引用核查", "待复现"],
        "keywords": ["preprint", "attribution", "hallucinated citation"],
        "body": (
            "（构造样例，非真实反馈）预印本报告的提升主要来自检索粒度变细，而不是模型本身；"
            "正式发表版把实验表 3 的对比模型换了，"
            "结论从“稳定提升”改成“在长文档上提升”。\n\n"
            "对我自己的启示：做小样本实验时，必须先固定评测集版本，否则“提升”可能只是数据换了。\n\n"
            "待办里要先完成：核对两个版本的实验表差异。"
        ),
        "status": "reading",
        "tasks": [("找出正式发表版本并对照实验表", True), ("把版本差异写进文献卡片", False)],
    },
    {
        "title": "索引选择率与统计信息（数据库课程第 8 讲）",
        "course": "数据库",
        "tags": [SAMPLE_TAG, "索引", "查询优化", "考试重点"],
        "keywords": ["选择率", "直方图", "B+树", "LSM"],
        "body": (
            "（构造样例，非真实反馈）选择率估计错误的两个典型来源：列间相关性被忽略、直方图桶数太少导致高频值被平均。\n"
            "B+ 树适合高选择性的点查与范围查；LSM 用写放大换写入吞吐，读侧需要布隆过滤器兜底。\n\n"
            "老师课上强调：混合检索里全文召回和向量召回的分数不可直接相加，要先归一化再融合（RRF 是一种做法）。"
        ),
        "status": "unread",
        "tasks": ["做 3 道选择率计算题", "整理 B+树 / LSM 对照表"],
    },
    {
        "title": "文献管理：为什么每周整理一次反而更快",
        "course": "学习方法",
        "tags": [SAMPLE_TAG, "复盘"],
        "keywords": ["整理频率", "命名规范"],
        "body": (
            "（构造样例，非真实反馈）之前的做法是攒到写综述时一次性整理，结果一半时间花在“这篇到底讲什么”。\n"
            "改成每次读完立刻写三行：结论、和我课题的关系、下一步。三行写不出来就说明这篇没读懂，当场重读比一周后重读便宜。"
        ),
        "status": "mastered",
        "tasks": [],
    },
    {
        "title": "组会汇报骨架：问题-方法-证据-局限",
        "course": "科研写作",
        "tags": [SAMPLE_TAG, "汇报", "模板"],
        "keywords": ["组会", "四段式"],
        "body": (
            "（构造样例，非真实反馈）四段式模板：问题（为什么要做，一段话）、方法（一张图）、证据（一张表，只留关键对比）、局限（主动说，别等提问）。\n"
            "把“局限”固定放在最后一页，可以显著减少被追问时的临时组织成本。"
        ),
        "status": "reading",
        "tasks": ["把上周的汇报按四段式重写一遍"],
        # 两条状态变化演示时间线；文字同样是构造样例，不代表任何人的真实反馈。
        "progress": [
            ("mastered", "演练了一遍四段式，证据页补了对照表"),
            ("reading", "把局限页拆成两页，另加一页对照数据"),
        ],
    },
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pc-url", default="http://127.0.0.1:2893")
    parser.add_argument("--workspace", default="default")
    args = parser.parse_args()

    workbench = Workbench(PCClient(base_url=args.pc_url), workspace=args.workspace)
    scope_id = workbench.ensure_scope()
    existing = workbench.load()
    demo_titles = {note["title"] for note in NOTES}
    stale = [item for item in existing["notes"]
             if item["title"] in demo_titles and SAMPLE_TAG not in item["tags"]]
    for item in stale:
        workbench.update_note(item["id"], tags=[SAMPLE_TAG, *item["tags"]])
    already = [item for item in existing["notes"] if item["title"] in demo_titles]
    if already:
        if stale:
            print(f"旧版演示笔记 {len(stale)} 条已补上「{SAMPLE_TAG}」标签（追加新修订，旧记录仍可查）")
        print(f"演示数据已存在（{len(already)} 条），跳过写入。Scope={scope_id}")
        return 0

    for note in NOTES:
        created = workbench.create_note(title=note["title"], body=note["body"], course=note["course"],
                                       tags=note["tags"], keywords=note["keywords"])
        steps = note.get("progress") or ([(note["status"], "初始演示状态")] if note["status"] != "unread" else [])
        for status, memo in steps:
            workbench.set_note_status(created["id"], status, memo=f"{SAMPLE_TAG}｜{memo}")
        for task in note["tasks"]:
            title, done = task if isinstance(task, tuple) else (task, False)
            made = workbench.create_task(created["id"], title)
            if done:
                workbench.set_task_done(made["id"], True)
        print(f"written {created['id']} chunks={created['chunks']} {note['title']}")

    state = workbench.load()
    print(f"\nScope={scope_id}  seed={SEED_MARK}")
    print(f"PowerContext 记录：笔记 {state['record_counts']['note_records']} 条、"
          f"待办 {state['record_counts']['task_records']} 条、"
          f"进度 {state['record_counts']['progress_records']} 条")
    print(f"折叠后可见：{state['record_counts']['notes']} 条笔记、{state['record_counts']['tasks']} 项待办")
    return 0


if __name__ == "__main__":
    sys.exit(main())

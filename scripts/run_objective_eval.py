"""
run_objective_eval.py
客观指标评测：11 个客观题，所有难度（standard / challenge / adversarial）
每个难度分 2 轮，每轮最多 3 个进程并行（按模块隔离，避免 ChromaDB 冲突）
不支持某难度的任务会被自动跳过。

用法：
    python scripts/run_objective_eval.py             # 跑全部难度
    python scripts/run_objective_eval.py standard    # 只跑 standard
    python scripts/run_objective_eval.py challenge   # 只跑 challenge
"""

import subprocess
import sys
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
os.chdir(str(PROJECT_ROOT))

COMMON = ["--fast"]

DIFFICULTIES = ["standard", "challenge", "adversarial"]

ROUND1_CMDS = [
    {
        "name": "legal_qa (1/2)",
        "args": ["--key", "1", "--tasks",
                 "legal_qa.memorization.factual_query",
                 "legal_qa.memorization.legal_knowledge_mcqa",
                 "legal_qa.memorization.statute_recitation",
                 "legal_qa.understanding.reading_comprehension"],
    },
    {
        "name": "contract_review",
        "args": ["--key", "2", "--tasks",
                 "contract_review.clause_correction"],
    },
    {
        "name": "case_prediction",
        "args": ["--key", "3", "--tasks",
                 "case_prediction.article_prediction",
                 "case_prediction.clause_prediction",
                 "case_prediction.prison_term_prediction"],
    },
]

ROUND2_CMDS = [
    {
        "name": "legal_qa (2/2)",
        "args": ["--key", "1", "--tasks",
                 "legal_qa.understanding.argument_understanding",
                 "legal_qa.understanding.issue_understanding",
                 "legal_qa.understanding.case_summarization"],
    },
]


def run_parallel(cmds, difficulty):
    procs = []
    for cmd in cmds:
        full = ([sys.executable, "scripts/run_zhifa_eval.py"]
                + COMMON + ["--difficulty", difficulty] + cmd["args"])
        print(f"  启动: {cmd['name']}")
        p = subprocess.Popen(full)
        procs.append((cmd["name"], p))

    for name, p in procs:
        p.wait()
        status = "OK" if p.returncode == 0 else f"ERROR (code {p.returncode})"
        print(f"  完成: {name} -> {status}")


def run_difficulty(difficulty):
    print(f"\n{'=' * 55}")
    print(f" [{difficulty}] 第 1 轮：8 个客观任务（3 进程并行）")
    print(f"{'=' * 55}")
    run_parallel(ROUND1_CMDS, difficulty)

    print(f"\n{'=' * 55}")
    print(f" [{difficulty}] 第 2 轮：3 个客观任务")
    print(f"{'=' * 55}")
    run_parallel(ROUND2_CMDS, difficulty)


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "all"

    if target in DIFFICULTIES:
        run_difficulty(target)
    elif target == "all":
        for diff in DIFFICULTIES:
            run_difficulty(diff)
        print(f"\n{'=' * 55}")
        print(f" 全部客观题评测完成（{'/'.join(DIFFICULTIES)}），输出: zhifa_outputs/")
        print(f"{'=' * 55}")
    else:
        print(f"用法: python scripts/run_objective_eval.py [all|standard|challenge|adversarial]")

"""
run_subjective_generate.py
主观任务答案生成（仅生成，不评分）— 3 进程并行

用法：
    python scripts/run_subjective_generate.py standard
    python scripts/run_subjective_generate.py challenge
    python scripts/run_subjective_generate.py adversarial
    python scripts/run_subjective_generate.py all           # 全部难度
"""

import subprocess
import sys
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
os.chdir(str(PROJECT_ROOT))

COMMON = ["--fast"]
DIFFICULTIES = ["standard", "challenge", "adversarial"]

GENERATE_CMDS = [
    {
        "name": "legal_qa (主观 3 题)",
        "args": ["--key", "1", "--tasks",
                 "legal_qa.application.consultation_fact_inquiry",
                 "legal_qa.application.case_analysis",
                 "legal_qa.application.legal_document_generation"],
    },
    {
        "name": "contract_review (主观 2 题)",
        "args": ["--key", "2", "--tasks",
                 "contract_review.risk_detection",
                 "contract_review.risk_revision"],
    },
    {
        "name": "case_prediction (主观 1 题)",
        "args": ["--key", "3", "--tasks",
                 "case_prediction.comprehensive_judgment_prediction"],
    },
]


def run_parallel(cmds):
    procs = []
    for cmd in cmds:
        print(f"  启动: {cmd['name']}")
        p = subprocess.Popen(cmd["full"])
        procs.append((cmd["name"], p))

    for name, p in procs:
        p.wait()
        status = "OK" if p.returncode == 0 else f"ERROR (code {p.returncode})"
        print(f"  完成: {name} -> {status}")


def run_difficulty(difficulty):
    print(f"\n{'=' * 55}")
    print(f" 生成主观题答案 [{difficulty}]（3 进程并行）")
    print(f"{'=' * 55}")

    cmds = []
    for cmd in GENERATE_CMDS:
        full = ([sys.executable, "scripts/run_zhifa_eval.py"]
                + COMMON + ["--difficulty", difficulty] + cmd["args"])
        cmds.append({"name": cmd["name"], "full": full})
    run_parallel(cmds)


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "all"

    if target in DIFFICULTIES:
        run_difficulty(target)
    elif target == "all":
        for diff in DIFFICULTIES:
            run_difficulty(diff)
        print(f"\n{'=' * 55}")
        print(f" 全部主观题生成完成，输出: zhifa_outputs/")
        print(f"{'=' * 55}")
    else:
        print(f"用法: python scripts/run_subjective_generate.py [standard|challenge|adversarial|all]")

#!/usr/bin/env bash
# 一键流水线：s1 编码 -> s2 清洗 -> s3 切章 -> s4 抽样(供小模型标注) -> s5 组装
# 用法: bash scripts/run_all.sh          # 跑全部（s5 在标注后再跑一次以带上 meta）
#       bash scripts/run_all.sh s3 s5    # 只跑指定阶段
set -euo pipefail
cd "$(dirname "$0")/.."

run() { echo "===== $1 ====="; python3 "scripts/$1.py"; }

if [ $# -eq 0 ]; then
  run s1_to_utf8
  run s2_clean
  run s3_split_chapters
  run s4_sample
  run s5_build_dataset
else
  for s in "$@"; do run "$s"; done
fi

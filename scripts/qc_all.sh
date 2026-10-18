#!/usr/bin/env bash
# 最终 QC：跑一遍全部诊断脚本，日志落在 work/reports/
set -euo pipefail
cd "$(dirname "$0")/.."
R=work/reports
python3 scripts/verify_round2.py        > "$R/qc_verify.log" 2>&1
python3 scripts/diag_chunk_adrate.py    > "$R/qc_adrate.log" 2>&1
python3 scripts/diag_residue.py         > "$R/qc_residue.log" 2>&1
python3 scripts/make_spotcheck.py       > "$R/qc_spotcheck.log" 2>&1
python3 scripts/diag_hitrate.py         > "$R/qc_hitrate.log" 2>&1
echo "QC 完成，日志见 $R/qc_*.log"

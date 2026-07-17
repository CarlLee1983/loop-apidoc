#!/usr/bin/env bash
#
# check-and-refresh.sh — 來源新鮮度排程閘門
#
#   相同版本   → 略過，不花解析成本 (exit 0)
#   版本/內容更新 → 觸發重新解析，並刷新基準 fingerprint (exit 1)
#   無法判定   → 告警，交人工介入 (exit 2)
#
# 用法 (由 cron / CI / headless agent 定期呼叫):
#   FINGERPRINT=./work/source-fingerprint.json \
#   RUN_DIR=./output/<run-id> \
#   SOURCES=./sources \                # 選填:fingerprint 含本地檔時需要
#   REPARSE_CMD='./reparse.sh' \       # 偵測到變動時要跑的重新解析指令
#   ./check-and-refresh.sh
#
set -uo pipefail

FINGERPRINT="${FINGERPRINT:?請設定 FINGERPRINT}"
RUN_DIR="${RUN_DIR:?請設定 RUN_DIR}"
SOURCES="${SOURCES:-}"
REPARSE_CMD="${REPARSE_CMD:?請設定 REPARSE_CMD (偵測到變動時執行的重新解析指令)}"

# 解析 CLI:優先用環境變數 LOOP_APIDOC 覆寫;否則沿用 skill 的 <APIDOC> 規則
if [ -n "${LOOP_APIDOC:-}" ]; then
  read -r -a APIDOC <<< "$LOOP_APIDOC"
elif [ -n "${CLAUDE_PLUGIN_ROOT:-}" ]; then
  APIDOC=(uv run --project "$CLAUDE_PLUGIN_ROOT" loop-apidoc)
else
  APIDOC=(loop-apidoc)
fi

ts() { date -u +%Y-%m-%dT%H:%M:%SZ; }

args=(check-freshness --fingerprint "$FINGERPRINT" --json)
[ -n "$SOURCES" ] && args+=(--sources "$SOURCES")

OUT="$("${APIDOC[@]}" "${args[@]}")"
CODE=$?
echo "$OUT"

case "$CODE" in
  0)
    echo "[$(ts)] unchanged — 版本相同,略過,不花解析成本"
    ;;
  1)
    echo "[$(ts)] changed — 來源更新,觸發重新解析"
    eval "$REPARSE_CMD"
    "${APIDOC[@]}" record-fingerprint --run-dir "$RUN_DIR" --output "$FINGERPRINT" --force
    echo "[$(ts)] 基準 fingerprint 已刷新,下次排程將以新版本為準"
    ;;
  2)
    echo "[$(ts)] inconclusive — 來源無法取得 (連不上/需認證/已搬移),告警人工介入" >&2
    exit 2
    ;;
  *)
    echo "[$(ts)] check-freshness 非預期退出碼 $CODE" >&2
    exit "$CODE"
    ;;
esac

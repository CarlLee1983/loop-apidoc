# 排程用來源新鮮度閘門範例

`check-and-refresh.sh` 把 `check-freshness` 的退出碼包成一個可掛 cron / CI 的排程腳本：

- **相同版本 → 略過**，不花任何解析成本（exit 0）
- **版本 / 內容更新 → 觸發重新解析**，再 `record-fingerprint --force` 刷新基準（exit 1）
- **無法判定**（連不上 / 需認證 / 已搬移）→ 告警，交人工介入（exit 2）

搭配的機制與 v1 限制見 skill 的 `skills/loop-apidoc/reference/freshness-scheduling.md`。

## 前置

先在一份已完成並採用的 run 上記錄基準 fingerprint（只需一次）：

```bash
loop-apidoc record-fingerprint \
  --run-dir ./output/<run-id> \
  --output ./work/source-fingerprint.json
```

## 環境變數

| 變數 | 必填 | 說明 |
| --- | --- | --- |
| `FINGERPRINT` | ✓ | 基準 `source-fingerprint.json` 路徑 |
| `RUN_DIR` | ✓ | 重新解析後用來刷新基準的 run 目錄 |
| `REPARSE_CMD` | ✓ | 偵測到變動時執行的重新解析指令（你的擷取 pipeline） |
| `SOURCES` | | 本地來源根目錄；fingerprint 含本地檔來源時需要 |
| `LOOP_APIDOC` | | 覆寫 CLI 呼叫方式（預設 `loop-apidoc`；plugin 內用 `uv run --project "$CLAUDE_PLUGIN_ROOT" loop-apidoc`） |

## 掛 cron

```cron
*/30 * * * *  FINGERPRINT=/data/fp.json RUN_DIR=/data/run SOURCES=/data/sources \
              REPARSE_CMD=/data/reparse.sh \
              /path/to/examples/freshness-scheduling/check-and-refresh.sh \
              >> /var/log/apidoc-freshness.log 2>&1
```

`REPARSE_CMD` 指向你自己的重新解析腳本——由 headless agent（Claude Code / Codex）依 skill
的正常步驟 2–8 重讀來源、`assemble` 產出新 run-dir。腳本會在重跑後自動 `record-fingerprint --force`，
讓下一次排程以新版本為基準。

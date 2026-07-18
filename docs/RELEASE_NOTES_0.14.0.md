# loop-apidoc 0.14.0 release notes

Release date: 2026-07-18

## Summary

新增 source-facts 語意完整度閘門,以來源事實擋下靜默的擷取不足;教學與推廣文件全面雙語化(英文為主、繁中為輔)。

## Changed

- 新增 `loop_apidoc/source_facts/` 套件:從 manifest 指名的 Markdown 來源機械掃出
  端點宣告、參數表欄位名與範例區塊數,建成 `FactIndex`,作為語意完整度閘的依據。
- `verify-extraction` 與 `assemble` 共用的 `agentcli/gate.py`(`check_extraction`)
  折入來源事實檢查:來源寫了某欄位、擷取卻在所有結構位置都沒有,且未在 `missing[]`
  具名 → 擋下;來源有範例而 `examples[]` 為空 → 擋下。**擋下「該寫沒寫」的靜默遺漏**,
  補上原本只擋「瞎掰」的反向缺口。
- 同閘另加延後語句檢查(`source_facts/deferral.py`):`missing[]` 以外出現
  「需進一步擷取」/「requires further extraction」這類佔位答案 → 擋下。
- 多來源同時記載同一 `(METHOD, path)` 時只取**交集**,歧義一律 fail open——避免總覽
  索引表或已淘汰的 v1 章節把要求放大到擷取本就該忽略的範圍。
- **適用範圍限制**:只有結構良好的 Markdown 能產出事實;HTML 壓平成純文字的來源掃出
  零筆,閘門對它是 no-op。這是刻意的取捨——猜結構會製造假事實,而一條假事實會擋掉
  正確的擷取。因此「閘門乾淨」不等於「擷取完整」。
- 教學與推廣文件(`docs/*.html`)全面雙語化:4 份文件補上英文版並加雙向語言切換;
  文件語言政策改為英文為主、繁中為輔(生成的產品輸出仍維持 zh-TW)。
- `.gitignore` 忽略本機執行產物目錄(`.loop-apidoc/`、`runs/`、`tmp/`)。

## Validation

- `npm run tag:check`
- `uv run ruff check .`
- `uv run pytest --cov=loop_apidoc`
- `uv run python scripts/quality_gate.py`

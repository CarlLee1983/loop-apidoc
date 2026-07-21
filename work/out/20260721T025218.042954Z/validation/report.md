# 驗證報告

結果：**FAIL**（error：1，warning：1）

- **REQUIRED_INFO_MISSING** (error) @ `integration.crypto`
  - 證據：來源出現「加密」訊號詞,但契約未抽到任何加解密/簽章機制
  - 建議修正：重讀相關來源段落,補上 crypto 細節後重跑 assemble
  - 可自動修正：否
- **REQUIRED_INFO_MISSING** (warning) @ `operational`
  - 證據：缺少 rate limit/timeout/retry 等 operational 資訊
  - 建議修正：由來源補上 operational 資訊
  - 可自動修正：否

# 設計：`examples/` 開發者請求範例產物

- 日期：2026-06-28
- 狀態：設計定稿，待寫實作計畫
- 範圍：design doc §9 後續清單中的「開發者導向產物」之一——`examples/`（curl + TypeScript + Python 請求範例）。其餘（`integration-tasks.md`、`postman_collection.json`、`sdk-hints.json`）不在本次範圍。

## 1. 目標與核心不變式

把已 grounded 的契約資料（OpenAPI 端點 + `integration-contract.json` 簽章鏈）轉成對接者可直接複製/執行的三語請求範例，降低初次串接成本。

**核心不變式（非協商）承襲專案根本約束**：來源文件是唯一真實來源。範例**不引入任何新事實**——只重組已驗證資料，並對來源未提供的值輸出**顯式佔位符**。禁止依型別推導樣本值、編造 URL／金額／金鑰。

## 2. 架構與資料流

新增純函式模組 **`loop_apidoc/generate/examples.py`**：

```python
build_examples(openapi: dict, plan: NormalizationPlan) -> dict[str, str]
    # 回傳 {相對路徑: 檔案內容}
    # 例：{
    #   "examples/README.md": "...",
    #   "examples/NPA_F01/request.sh": "...",
    #   "examples/NPA_F01/request.ts": "...",
    #   "examples/NPA_F01/request.py": "...",
    # }
```

- 輸入刻意取**已建好的 `openapi` dict**（非重新解析 plan），與 `openapi.yaml` 同源 → operationId、paths、params、requestBody schema、security 完全一致。
- 簽章鏈取自 `plan.integration.crypto`（契約 leaf）。
- 純函式、無 I/O。`generate/writer.py::generate_outputs` 是唯一寫檔出口（沿用「單一 file-I/O 出口」原則）。

整合點：

- `GenerateResult` 新增 `examples: dict[str, str]` 欄位。
- `build_result` 在 `build_openapi` **之後**呼叫 `build_examples(result.openapi, plan)`（需 operationId 已指派）。
- `generate_outputs` 迭代 `result.examples`，`(run_dir / relpath).parent.mkdir(parents=True, exist_ok=True)` 後 `write_text(..., encoding="utf-8")`。
- 無端點時 `examples` 為空 dict，不建目錄。

## 3. 不臆測規則（生成器內部不變式）

生成器只允許輸出**兩類值**，靠單元測試守住（不另設 validate stage）：

**(A) 來源值** — 欄位值若契約/OpenAPI 明確提供（`example`、enum 單一值、固定常數如 `Version="2.0"`），直接帶入。

**(B) 顯式佔位符** — 來源未提供值的欄位，輸出明白標記：

- shell：`MerchantID="<your_merchant_id>"`
- TS/Python：`merchant_id = "<your_merchant_id>"  # TODO: 來源未提供範例值`
- 佔位符命名取自欄位名（snake/kebab 正規化），不依型別塞假值。

**禁止**：依型別推導樣本（`"string"`/`0`/`true`）、編造 URL、編造金額。生成器若遇到「既非來源值、也無法產生佔位符」（理論上不會），略過該欄位並在檔頭 `# gaps` 區塊列出。

**檔頭註記**（每個產出檔）：

```
# Derived from openapi.yaml + integration-contract.json — NOT a source document.
# Values shown as <placeholder> are not provided by the source; fill them in.
```

## 4. 簽章鏈呈現（混合策略）

契約 `crypto` 記了簽章步驟（如 AES-256-CBC 加密 + SHA256 雜湊產生 CheckValue）。三語各自處理：

- `request.sh`：簽章一律以**編號註解步驟**呈現（shell 無法內嵌加密），並指向 `request.py`/`request.ts` 先取得 CheckValue 再回填。
- `request.ts` / `request.py`：
  - 契約該 crypto entry 的 `algorithm`、`mode`/`hash`、輸入欄位順序皆**非 null**（「明確」）→ 生成**可跑簽章函式**。
  - 任一欄位為 null（「不足」）→ **佔位函式骨架** + `# gap:` 註解，標出缺什麼（如「來源未指明 padding」）。

## 5. 檔案佈局與素材抽取

佈局（run-dir 下，與既有產物平行）：

```
examples/
  README.md                     # 衍生來源、佔位符慣例、簽章鏈須先跑 script
  {operationId}/
    request.sh                  # curl + 註解簽章步驟
    request.ts                  # fetch + 可跑/骨架簽章函式
    request.py                  # httpx + 可跑/骨架簽章函式
```

- **operationId 來源**：直接讀 `openapi` dict 裡每個 operation 的 `operationId`（由 `_assign_operation_ids` 指派，已保證跨 paths+webhooks 唯一且 identifier-safe）。examples 不自造 id → 與 `openapi.yaml`、`provenance.json` target 天然對齊。資料夾名即 operationId。
- **每端點素材**（全來自該 operation 的 openapi 節點）：
  - method + 完整 URL：`servers`/`plan.environments` 的 base_url + path；base_url 為 null → 佔位 `<base_url>`。
  - path/query/header params：name、required、enum 單值或 example → 來源值，否則佔位。
  - requestBody：依 schema 屬性逐欄；media type 取 openapi 宣告的第一個。
  - security：對應 securityScheme → header/query 認證欄位佔位。
  - 簽章鏈：比對 `plan.integration.crypto`；無關聯則於 README 列為通用簽章說明。
- **webhooks/callbacks 端點**（有 method 無 path）：一樣產生範例，URL 改為「你的接收端 URL」佔位 + 註解說明這是「你要實作的接收端」。

## 6. 溯源與驗證

範例為**純衍生**：每個結構欄位都源自已 grounded 的 OpenAPI 位置或契約 leaf（那些已各自有 provenance）。因此：

- 不新增 `provenance.json` 條目（避免與既有 endpoint provenance 重複）。
- 不進 no-speculation validate gate。
- 改以**生成器內部不變式**守住：生成器只允許輸出「來源值」或「顯式佔位符」兩類，靠單元測試鎖死（見 §7）。
- `examples/README.md` 與每個檔頭註明「derived from openapi.yaml + integration-contract.json」。

## 7. 測試策略（TDD）

純函式 `build_examples` 對 dict 輸入斷言字串輸出，分層：

1. **單元（核心不變式守門）** — `tests/test_generate_examples.py`：
   - 來源有 `example`/enum 單值 → 範例帶入該值。
   - 來源無值 → 輸出 `<placeholder>`，且**斷言輸出不含型別樣本**（無裸 `"string"`/`0`/`true` 當值）——(B) 不臆測的回歸鎖。
   - base_url null → URL 含 `<base_url>`。
   - 三語檔頭都有「Derived from… NOT a source」註記。
   - 空端點 → 回空 dict（不建目錄）。
2. **簽章鏈** — crypto 演算法**完整** → TS/Python 含可跑函式（斷言出現 `createCipheriv`/`Cipher` 等關鍵呼叫）；任一欄位 null → 骨架 + `# gap:` 註解，且 curl 一律只有註解步驟。
3. **2-source builder 路徑回歸（教訓）** — 不手刻空 model，而是用 **2-source manifest 跑真實 plan→openapi→examples** 全鏈，斷言：跨源端點 operationId 唯一且 examples 資料夾無碰撞；某源缺值的欄位確實落為佔位而非被另一源「升級」遮蔽。把「單源遮蔽多源」盲點納入測試。
4. **writer 整合** — `generate_outputs` 確實把 `examples/.../request.*` 寫到 run-dir，路徑與 operationId 對齊。

**邊界案例**：

- operationId 撞名 → 已由 `_assign_operation_ids` 去重，examples 直接信任。
- 同 path+method 多源合併 → openapi 已 collapse 成單 operation，examples 隨之單一。
- requestBody 無 schema / schema 無 properties → body 留空 + 註解「來源未定義 body 欄位」。
- 多個 securityScheme → 全部帶入認證佔位。
- CJK 欄位描述 → 註解 UTF-8 安全（`ensure_ascii=False`/`encoding="utf-8"`）。

## 8. 驗收

- `uv run pytest` 全綠、`uv run ruff check .` clean。
- 對 NewebPay/ECPay 既有 e2e run-dir 人眼抽看一個端點三語範例：可讀、佔位符正確、簽章鏈呈現符合 §4（呼應「validation PASS≠產物好，要人眼看產物」）。

## 9. 不在本次範圍（YAGNI）

- `integration-tasks.md`、`postman_collection.json`、`sdk-hints.json`（design doc §9 其餘項，各自獨立 spec）。
- SDK 等級的完整 client 生成、retry/錯誤處理樣板。
- 範例的端到端實跑驗證（需真實金鑰，超出 source-grounding 範圍）。
- 範例值的 schema 推導樣本（明確違反不變式）。

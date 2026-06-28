# 簽章接回 request 欄位 + 驗證範例真用簽章流程

- 日期:2026-06-28
- 範圍:`loop_apidoc/generate/examples.py`、`loop_apidoc/validate/integration.py`、`loop_apidoc/cli.py`
- 不變式:來源是唯一真實依據;未說明者留 placeholder/gap,不臆測。

## 背景與問題

目前 `build_examples` 會為含 request-signing 的 `integration-contract.json`
產生 `sign()` 簽章函式(`request.ts` / `request.py`),但**簽章值從不被接回
request 的 body/header**,也沒有任何驗證確認範例真的用到簽章流程。結果是:
產物能加速實作,卻不是可直接貼上執行的串接程式。

本設計補兩件事:

1. 把 `sign()` 的結果明確接回 request 的目標欄位。
2. 讓驗證能檢查範例是否真的使用了簽章流程。

## 設計決策(已與使用者確認)

- **目標欄位來源 = `CryptoScheme.verify.field`**。模型沒有獨立的「簽章目標
  欄位」;`verify.field` 語意上就是承載簽章值的欄位(如 ECPay `CheckMacValue`)。
  只有當 `verify.field` 能對應到該端點的 body 欄位或 header 時才接回;否則
  維持註解 + gap。
- **payload 組法 = `payload_assembly[].fields` 並集**(僅 body 欄位),組成
  payload 交給 `sign()`,並加註解提醒「確切串接/排序請依 payload_assembly
  核對 source」。串接形式(`k=v` 以 `&` 連)明確標示為**示意**,不偽裝精確。
- **驗證嚴重度**:情境 A(能接卻漏接)→ `OUTPUT_MISMATCH`(error, fixable);
  情境 B(來源未指明目標欄位)→ `REQUIRED_INFO_MISSING`(error)。與既有
  fail-closed 分類一致。

## A. 接回邏輯 — `generate/examples.py`

對每個 request-signing scheme `s`(`_request_signing_schemes` 已篩出):

- 可跑判定:`_signature_explicit(s) and _is_cbc(s)`(沿用)。
- 函式名:沿用現有 `sign` / `sign_<name>`(多 scheme 時)規則。
- 目標欄位:`target = s.verify.field if s.verify else None`。
- payload 欄位:`fields = ` 各 `payload_assembly[].fields` 的並集;與該端點
  body 欄位取交集後使用。

### 接回條件

只有同時滿足才接回某端點範例:

1. scheme 可跑;
2. `target` 非空,且 `target` 出現在該端點的 body 欄位名或 header 名中。

### 三語渲染

- **`request.ts`**:在 `const body = {...}` 之後加入

  ```ts
  // 簽章 payload：來源指定下列欄位進入簽章（確切串接/排序為示意，請依 payload_assembly 核對 source）
  const payload = ['Field1', 'Field2'].map((k) => `${k}=${(body as any)[k]}`).join('&')
  ;(body as any)['CheckMacValue'] = sign(payload)
  ```

  - 目標若為 header,改寫 `headers[...]`。
  - `fields` 為空時:`const payload = '<payload：來源未列出簽章欄位，請依 payload_assembly 組裝>'`,
    仍寫 `body[target] = sign(payload)`(fail-closed,流程接通)。

- **`request.py`**:在 body dict(現用變數名 `payload`)之後加入,簽章 payload
  用獨立變數避免撞名:

  ```py
  # 簽章 payload：來源指定下列欄位進入簽章（確切串接/排序為示意，請依 payload_assembly 核對 source）
  sig_payload = "&".join(f"{k}={payload[k]}" for k in ["Field1", "Field2"])
  payload["CheckMacValue"] = sign(sig_payload)
  ```

  - 目標為 header 時改寫 `headers[...]`。
  - `fields` 為空時:`sig_payload = "<payload：來源未列出簽章欄位，請依 payload_assembly 組裝>"`。

- **`request.sh`(curl)**:shell 無法內嵌 AES/SHA256,**維持註解模式**
  (`_signature_comment_steps` 已提示先跑 .py/.ts)。額外在註解標明簽章值要
  填回哪個欄位(`target`)。curl **不納入驗證 A**。

### 非可跑 scheme

維持現狀:gap 註解 + `throw` / `raise NotImplementedError`,不接回。

## B. 驗證 — `validate/integration.py`

擴充 `check_integration`(已能取得 `result.examples`)。對每個可跑 scheme:

- **情境 B**:`verify.field` 為 None → 一筆 `REQUIRED_INFO_MISSING`
  (error),location `integration.crypto.<name>`,evidence「可生成可跑簽章但
  來源未指明簽章值的目標欄位」,suggested_fix「重讀來源補上 verify.field 後
  重跑 assemble」。

- **情境 A**:`verify.field` 非空。掃描 `result.examples` 中每個
  `request.ts` / `request.py`:若該範例文字含目標欄位名(代表此端點用到該
  欄位)但**不含 `sign(` 接回該欄位的痕跡**(同時出現 `sign(` 與對該欄位的
  指派)→ `OUTPUT_MISMATCH`(error, fixable),location 指該範例檔,
  suggested_fix「重新產生範例使其接回簽章值」。
  - curl(`request.sh`)不檢查。
  - 目標欄位未出現在該範例 → 此端點不適用該簽章,跳過。

## C. 測試(TDD,先寫測試後實作)

新增測試:

1. 可跑 + 有對應 target → `request.ts` / `request.py` 含 `sign(` 接回 target;
   `request.sh` 維持註解(不含接回)。
2. `payload_assembly[].fields` 反映在 payload 串接的欄位清單。
3. fields 為空 → payload placeholder,但仍接回 target。
4. 目標為 header → 接回 `headers`。
5. 驗證 A:人為產生「有 target 卻沒接回」的範例 → `OUTPUT_MISMATCH`。
6. 驗證 B:可跑 scheme 但 `verify.field` 為 None → `REQUIRED_INFO_MISSING`。

更新既有測試:`test_generate_examples.py`、`test_generate_examples_two_source.py`、
`test_generate_writer_examples.py` 可能因輸出新增接回行而需調整斷言。

## D. Task 2 — CLI help

`cli.py` `assemble` 的 `--extraction` help 補上選用 `integration.json`:

> `agent 產出的擷取目錄(inventory.json + endpoints/*.json,選用 integration.json)`

## 不做(YAGNI)

- 不在模型新增獨立 target_field(沿用 `verify.field`)。
- 不為 curl 偽造可跑加密。
- 不嘗試精確重建 source 特定的 payload 串接/排序(標為示意,交由使用者核對)。

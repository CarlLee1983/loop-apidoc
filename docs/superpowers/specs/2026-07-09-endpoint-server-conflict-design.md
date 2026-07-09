# 端點 server 合併衝突 fail-closed(issue #9)

## 問題

`loop_apidoc/plan/builder.py` 的 `_combine_endpoints` 以 `server = a.server or b.server`
合併兩個共用 `method+path` 的端點。當 A 宣稱 `production`、B 宣稱 `reporting` 時,
`or` 靜默選 A,B 的主機事實無聲丟失。這與專案核心原則衝突:來源衝突必須浮出來。

## 設計

### 1. server 衝突 fail-closed

`_combine_endpoints` 改為回傳 `tuple[EndpointEntry, list[SourceConflict]]`;
呼叫者 `_dedupe_endpoints`(唯一拿得到 `plan` 的地方)把衝突 append 進
`plan.source_conflicts`。純函式邊界不變。

判定條件:`a.server` 與 `b.server` 都為 truthy 且相異。此時

- 合併後 `status = _stricter(status, CONFLICTING)`(恆為 `CONFLICTING`)
- `server` 仍取 `a.server` —— 決定性、可重現,不憑空造值
- 產生一筆 `SourceConflict`,`area` 標明是哪個 `method path` 的 server,
  `detail` 列出兩個相衝的宣稱

下游兩條既有錯誤路徑會同時亮,不需新增 issue code:

- `validate/completeness.py` 從 `plan.source_conflicts` 出 `conflict.*` 的
  `SOURCE_CONFLICT` ERROR
- `validate/speculation.py` 因該端點 provenance 帶 `CONFLICTING`,在
  `paths.{path}.{method}` 也出一筆 `SOURCE_CONFLICT` ERROR

### 2. `request` 只釘住現行行為,不判衝突

`_union_endpoint_fields` 的 `request` 同樣是「第一個非 null 者勝」,但這是刻意的:
adyen-payments-multimethod 正是多個支付產品共用一個 gateway 端點、各自不同 request
body(oneOf discriminator)的合法情境。把 `request` 差異判成衝突會誤殺該 benchmark。

差別在語義:`server` 是端點的唯一事實(一個 operation 只在一個主機上),
`request` 是產品維度的合法變體。

作法:補一個明確斷言「取 A」的合約測試把行為釘住,並在註解寫清楚為何兩者判準不同。

### 3. `_multiset_violations` 正名

`agentcli/cross_file.py` 的 `_multiset_violations` 實際做的是 set 對稱差,不是 multiset
比對(重複由 `_duplicate_violations` 抓、總數由 `_count_violations` 抓)。改名為
`_identity_set_violations` 並修正註解。純命名重構,行為不變。

## 測試(TDD)

- `_combine_endpoints`:兩邊 server 相異 → `status is CONFLICTING`,plan 多一筆 source conflict
- 兩邊 server 相同 / 其一為 None → 無衝突,行為不變(回歸)
- `request` 合約測試:兩邊都有且相異 → 取 A,不產生衝突
- E2E:assemble 遇 server 衝突 → validation FAIL 且 report 含 `SOURCE_CONFLICT`
- 全量 benchmark 回歸,確認 adyen-payments-multimethod 仍 0 error

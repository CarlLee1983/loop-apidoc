# 請求範例（examples/）

Derived from openapi.yaml + integration-contract.json — NOT a source document.
Values shown as <placeholder> are not provided by the source; fill them in.

每個端點一資料夾，含 curl / TypeScript / Python 三語版本。
`<...>` 為來源未提供的值，請自行填入。
演算法不支援或來源資訊不足的簽章機制只會顯示缺漏並拋錯，request.py / request.ts 不會產生該值。

## 端點
- `post_vg_sign_up/`
- `post_vg_sign_in/`
- `post_vg_bet_users/`
- `post_vg_bet_limit/`
- `post_vg_bet_limit_list/`
- `post_vg_table_list/`
- `post_bet/`
- `post_cancel/`
- `post_win/`
- `post_resettle/`
- `post_balance/`
- `post_vgtransfer_sign_up/`
- `post_vgtransfer_sign_in/`
- `post_vgtransfer_points/`
- `post_vgtransfer_balance/`
- `post_vgtransfer_log/`
- `post_vgtransfer_bet_users/`
- `post_vgtransfer_bet_limit/`
- `post_vgtransfer_bet_limit_list/`
- `post_vgtransfer_table_list/`

## 通用簽章機制
- MD5 sign (单一钱包)：MD5
- MD5 sign (转账钱包)：MD5

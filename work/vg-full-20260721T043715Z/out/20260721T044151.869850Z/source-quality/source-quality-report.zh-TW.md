# 來源品質報告

結論：**pass**

## SQ-001：missing-server-base-url

- 等級：warning
- 證據：vg-wen-dang.md # VG 文档 — Index and API pages document method+path only; no production/staging host or base URL is stated anywhere in the 40 Markdown pages (only example placeholder https://launch_url appears in sign-in response samples).
- 請補：Official API base URL(s) for 单一钱包 and 转账钱包 merchant-request endpoints, and whether wallet callback paths (/bet,/win,/cancel,/resettle,/balance) are hosted on a merchant-provided base.
- 驗收：A cited host or servers block exists for merchant-request APIs; wallet callback hosting model is stated.

## SQ-002：callback-host-unspecified

- 等級：warning
- 證據：vg-wen-dang/dan-yi-qian-bao/api/qian-bao.md # 钱包 — Wallet section labelled 商户接口 documents POST /bet,/win,/cancel,/resettle,/balance without stating the merchant callback base URL or that these are webhooks.
- 請補：Merchant callback base URL or explicit webhook delivery model for single-wallet 商户接口.
- 驗收：Callback host or webhook semantics are cited from a source page.

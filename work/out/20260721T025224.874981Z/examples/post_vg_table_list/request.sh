# Derived from openapi.yaml + integration-contract.json — NOT a source document.
# Values shown as <placeholder> are not provided by the source; fill them in.

# 簽章步驟（演算法不支援或來源資訊不足；request.py / request.ts 只顯示缺漏，不會產生簽章值）
#   MD5Signature：MD5
#     1. 将所有参数字首按顺序排列 (abcde...等，12345...等)
#     2. 将「值」串成字串，最后加上 API_KEY
#     3. 将此字串由 MD5 加密取得 sign 值

curl -X POST 'https://api.vg-organization.com/vg/table/list' \
  -H 'Content-Type: application/json' \
  --data '{"-------": "<value>", "agent": "<agent>", "sign": "<sign>"}'

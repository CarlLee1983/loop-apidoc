# Derived from openapi.yaml + integration-contract.json — NOT a source document.
# Values shown as <placeholder> are not provided by the source; fill them in.

# 簽章步驟（演算法不支援或來源資訊不足；request.py / request.ts 只顯示缺漏，不會產生簽章值）
#   MD5 sign (单一钱包)：MD5
#     1. 将所有参数字首按顺序排列 (abcde...等，12345...等)
#     2. 将参数的「值」串成字串；JS/Python 示例字段顺序为 agent 再 loginname（字母序）
#     3. 在字串最后加上 API_KEY
#     4. 将此字串由 MD5 加密取得 sign 值（Python 示例为 hashlib.md5(...).hexdigest()）
#   MD5 sign (转账钱包)：MD5
#     1. 将所有参数字首按顺序排列 (abcde...等，12345...等)
#     2. 将参数的「值」串成字串；JS/Python 示例字段顺序为 agent 再 loginname（字母序）
#     3. 在字串最后加上 API_KEY
#     4. 将此字串由 MD5 加密取得 sign 值（Python 示例为 hashlib.md5(...).hexdigest()）

curl -X POST '<base_url>/vg/bet/limit' \
  -H 'Content-Type: application/json' \
  -H 'Content-Type: <content_type>' \
  --data '{"agent": "<agent>", "betlimit": "<betlimit>", "loginname": "<loginname>", "sign": "<sign>"}'

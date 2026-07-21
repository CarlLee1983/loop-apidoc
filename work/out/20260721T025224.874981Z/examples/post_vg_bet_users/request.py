# Derived from openapi.yaml + integration-contract.json — NOT a source document.
# Values shown as <placeholder> are not provided by the source; fill them in.

import httpx

# gap: 簽章 MD5Signature 聲明演算法 MD5（unspecified 模式），但本範例僅支援 AES-CBC；無法生成可跑函式
def sign(payload: str) -> str:
    raise NotImplementedError('來源聲明的加密演算法 MD5／模式 unspecified 不支援，請參考 integration-contract.json 手動實作')


url = "https://api.vg-organization.com/vg/bet/users"
payload = {
    "-----------": "<value>",
    "agent": "<agent>",
    "starttime": "<starttime>",
    "roundid": "<roundid>",
    "betid": "<betid>",
    "page_num": "<page_num>",
    "page_size": "<page_size>",
    "status": "<status>",
    "sign": "<sign>",
    "参数": "<value>",
    "----------": "<value>",
    "username": "<username>",
    "shoeid": "<shoeid>",
    "shoeround": "<shoeround>",
    "casino": "<casino>",
    "valid": "<valid>",
    "bet": "<bet>",
    "win": "<win>",
    "currency": "<currency>",
    "tableidx": "<tableidx>",
    "bettime": "<bettime>",
    "settletime": "<settletime>",
    "ip": "<ip>",
    "bettype": "<bettype>",
    "platform": "<platform>",
    "betresult": "<betresult>",
    "detail": "<detail>",
}
resp = httpx.request("POST", url, json=payload)
print(resp.text)

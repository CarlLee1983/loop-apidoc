// Derived from openapi.yaml + integration-contract.json — NOT a source document.
// Values shown as <placeholder> are not provided by the source; fill them in.

// gap: 簽章 MD5Signature 聲明演算法 MD5（unspecified 模式），但本範例僅支援 AES-CBC；無法生成可跑函式
function sign(payload: string): string {
  throw new Error('來源聲明的加密演算法 MD5／模式 unspecified 不支援，請參考 integration-contract.json 手動實作')
}


const url = "https://api.vg-organization.com/vg/bet/users"
const headers = { 'Content-Type': "application/json" }
const body = {
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
const res = await fetch(url, {
  method: 'POST',
  headers,
  body: JSON.stringify(body),
})
console.log(await res.text())


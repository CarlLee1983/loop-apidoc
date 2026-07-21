// Derived from openapi.yaml + integration-contract.json — NOT a source document.
// Values shown as <placeholder> are not provided by the source; fill them in.

// gap: 簽章 MD5Signature 聲明演算法 MD5（unspecified 模式），但本範例僅支援 AES-CBC；無法生成可跑函式
function sign(payload: string): string {
  throw new Error('來源聲明的加密演算法 MD5／模式 unspecified 不支援，請參考 integration-contract.json 手動實作')
}


const url = "https://api.vg-organization.com/vgtransfer/log"
const headers = { 'Content-Type': "application/json" }
const body = {
  "-----------": "<value>",
  "agent": "<agent>",
  "starttime": "<starttime>",
  "endtime": "<endtime>",
  "page_num": "<page_num>",
  "page_size": "<page_size>",
  "status": "<status>",
  "sid": "<sid>",
  "sign": "<sign>",
  "参数": "<value>",
  "------------": "<value>",
  "username": "<username>",
  "type": "<type>",
  "amount": "<amount>",
  "beforeamount": "<beforeamount>",
  "afteramount": "<afteramount>",
  "busid": "<busid>",
  "anyid": "<anyid>",
  "ip": "<ip>",
  "createtime": "<createtime>",
}
const res = await fetch(url, {
  method: 'POST',
  headers,
  body: JSON.stringify(body),
})
console.log(await res.text())


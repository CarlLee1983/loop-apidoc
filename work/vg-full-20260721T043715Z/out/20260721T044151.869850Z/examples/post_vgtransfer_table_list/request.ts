// Derived from openapi.yaml + integration-contract.json — NOT a source document.
// Values shown as <placeholder> are not provided by the source; fill them in.

// gap: 簽章 MD5 sign (单一钱包) 聲明演算法 MD5（unspecified 模式），但本範例僅支援 AES-CBC；無法生成可跑函式
function sign_md5_sign(payload: string): string {
  throw new Error('來源聲明的加密演算法 MD5／模式 unspecified 不支援，請參考 integration-contract.json 手動實作')
}

// gap: 簽章 MD5 sign (转账钱包) 聲明演算法 MD5（unspecified 模式），但本範例僅支援 AES-CBC；無法生成可跑函式
function sign_md5_sign(payload: string): string {
  throw new Error('來源聲明的加密演算法 MD5／模式 unspecified 不支援，請參考 integration-contract.json 手動實作')
}


const url = "<base_url>/vgtransfer/table/list"
const headers = { 'Content-Type': "application/json", "Content-Type": "<content_type>" }
const body = {
  "agent": "<agent>",
  "sign": "<sign>",
}
const res = await fetch(url, {
  method: 'POST',
  headers,
  body: JSON.stringify(body),
})
console.log(await res.text())


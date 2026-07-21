// Derived from openapi.yaml + integration-contract.json — NOT a source document.
// Values shown as <placeholder> are not provided by the source; fill them in.

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


// Derived from openapi.yaml + integration-contract.json — NOT a source document.
// Values shown as <placeholder> are not provided by the source; fill them in.

const url = "https://api.vg-organization.com/resettle"
const headers = { 'Content-Type': "application/json" }
const body = {
  "-----------": "<value>",
  "agent": "<agent>",
  "loginname": "<loginname>",
  "roundid": "<roundid>",
  "transid": "<transid>",
  "amount": "<amount>",
  "sign": "<sign>",
  "detail": "<detail>",
}
const res = await fetch(url, {
  method: 'POST',
  headers,
  body: JSON.stringify(body),
})
console.log(await res.text())


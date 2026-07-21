// Derived from openapi.yaml + integration-contract.json — NOT a source document.
// Values shown as <placeholder> are not provided by the source; fill them in.

const url = "https://api.vg-organization.com/vgtransfer/sign-up"
const headers = { 'Content-Type': "application/json" }
const body = {
  "-----------": "<value>",
  "agent": "<agent>",
  "betlimit": "<betlimit>",
  "loginname": "<loginname>",
  "sign": "<sign>",
}
const res = await fetch(url, {
  method: 'POST',
  headers,
  body: JSON.stringify(body),
})
console.log(await res.text())


// Derived from openapi.yaml + integration-contract.json — NOT a source document.
// Values shown as <placeholder> are not provided by the source; fill them in.

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


// Derived from openapi.yaml + integration-contract.json — NOT a source document.
// Values shown as <placeholder> are not provided by the source; fill them in.

const url = "https://api.vg-organization.com/vg/sign-in"
const res = await fetch(url, {
  method: 'POST',
})
console.log(await res.text())


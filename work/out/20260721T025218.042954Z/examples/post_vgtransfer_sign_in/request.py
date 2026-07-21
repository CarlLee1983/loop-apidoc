# Derived from openapi.yaml + integration-contract.json — NOT a source document.
# Values shown as <placeholder> are not provided by the source; fill them in.

import httpx

url = "https://api.vg-organization.com/vgtransfer/sign-in"
payload = {
    "------------": "<value>",
    "agent": "<agent>",
    "language": "<language>",
    "loginname": "<loginname>",
    "rid": "<rid>",
    "betlimit": "<betlimit>",
    "return_url": "<return_url>",
    "sign": "<sign>",
}
resp = httpx.request("POST", url, json=payload)
print(resp.text)

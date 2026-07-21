# Derived from openapi.yaml + integration-contract.json — NOT a source document.
# Values shown as <placeholder> are not provided by the source; fill them in.

import httpx

url = "https://api.vg-organization.com/vgtransfer/bet/limit"
payload = {
    "-----------": "<value>",
    "agent": "<agent>",
    "betlimit": "<betlimit>",
    "loginname": "<loginname>",
    "sign": "<sign>",
}
resp = httpx.request("POST", url, json=payload)
print(resp.text)

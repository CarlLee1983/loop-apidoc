# Derived from openapi.yaml + integration-contract.json — NOT a source document.
# Values shown as <placeholder> are not provided by the source; fill them in.

import httpx

url = "https://api.vg-organization.com/win"
payload = {
    "-----------": "<value>",
    "agent": "<agent>",
    "loginname": "<loginname>",
    "roundid": "<roundid>",
    "transid": "<transid>",
    "amount": "<amount>",
    "sign": "<sign>",
    "detail": "<detail>",
}
resp = httpx.request("POST", url, json=payload)
print(resp.text)

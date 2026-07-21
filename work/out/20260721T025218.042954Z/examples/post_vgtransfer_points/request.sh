# Derived from openapi.yaml + integration-contract.json — NOT a source document.
# Values shown as <placeholder> are not provided by the source; fill them in.

curl -X POST 'https://api.vg-organization.com/vgtransfer/points' \
  -H 'Content-Type: application/json' \
  --data '{"-----------": "<value>", "agent": "<agent>", "loginname": "<loginname>", "amount": "<amount>", "sid": "<sid>", "status": "<status>", "sign": "<sign>"}'

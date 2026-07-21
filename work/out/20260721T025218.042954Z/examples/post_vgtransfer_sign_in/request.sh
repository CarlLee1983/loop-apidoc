# Derived from openapi.yaml + integration-contract.json — NOT a source document.
# Values shown as <placeholder> are not provided by the source; fill them in.

curl -X POST 'https://api.vg-organization.com/vgtransfer/sign-in' \
  -H 'Content-Type: application/json' \
  --data '{"------------": "<value>", "agent": "<agent>", "language": "<language>", "loginname": "<loginname>", "rid": "<rid>", "betlimit": "<betlimit>", "return_url": "<return_url>", "sign": "<sign>"}'

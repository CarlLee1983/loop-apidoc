# Developer Integration Tasks

Derived navigation aid — NOT a contract. See `../openapi.yaml` for the schema.

## Run Context

- Primary contract: `../openapi.yaml`
- Integration mechanisms: `../integration-contract.json`
- Validation status: `../validation/report.md`
- Request examples: `../examples/README.md`

## Runtime Configuration

- [ ] `base_url` — initial value: `https://api.vg-organization.com`
- [ ] Auth `MD5Signature` — apiKey (MD5 signature using API_KEY. See 加密说明.)
- [ ] Secret for `MD5Signature` — key=`API_KEY` (`../integration-contract.json#/crypto/0`)

## Implementation Order

- [ ] Implement `post_resettle` (`POST /resettle`)
  - Contract: `../openapi.yaml#/paths/~1resettle/post`
  - Example: `../examples/post_resettle/request.ts`
  - Requires crypto:MD5Signature
- [ ] Implement `post_win` (`POST /win`)
  - Contract: `../openapi.yaml#/paths/~1win/post`
  - Example: `../examples/post_win/request.ts`
  - Requires crypto:MD5Signature
- [ ] Implement `post_cancel` (`POST /cancel`)
  - Contract: `../openapi.yaml#/paths/~1cancel/post`
  - Example: `../examples/post_cancel/request.ts`
  - Requires crypto:MD5Signature
- [ ] Implement `post_bet` (`POST /bet`)
  - Contract: `../openapi.yaml#/paths/~1bet/post`
  - Example: `../examples/post_bet/request.ts`
  - Requires crypto:MD5Signature
- [ ] Implement `post_balance` (`POST /balance`)
  - Contract: `../openapi.yaml#/paths/~1balance/post`
  - Example: `../examples/post_balance/request.ts`
  - Requires crypto:MD5Signature
- [ ] Implement `post_vg_sign_in` (`POST /vg/sign-in`)
  - Contract: `../openapi.yaml#/paths/~1vg~1sign-in/post`
  - Example: `../examples/post_vg_sign_in/request.ts`
  - Requires crypto:MD5Signature
- [ ] Implement `post_vgtransfer_sign_in` (`POST /vgtransfer/sign-in`)
  - Contract: `../openapi.yaml#/paths/~1vgtransfer~1sign-in/post`
  - Example: `../examples/post_vgtransfer_sign_in/request.ts`
  - Requires crypto:MD5Signature
- [ ] Implement `post_vg_table_list` (`POST /vg/table/list`)
  - Contract: `../openapi.yaml#/paths/~1vg~1table~1list/post`
  - Example: `../examples/post_vg_table_list/request.ts`
  - Requires crypto:MD5Signature
- [ ] Implement `post_vgtransfer_table_list` (`POST /vgtransfer/table/list`)
  - Contract: `../openapi.yaml#/paths/~1vgtransfer~1table~1list/post`
  - Example: `../examples/post_vgtransfer_table_list/request.ts`
  - Requires crypto:MD5Signature
- [ ] Implement `post_vg_bet_limit` (`POST /vg/bet/limit`)
  - Contract: `../openapi.yaml#/paths/~1vg~1bet~1limit/post`
  - Example: `../examples/post_vg_bet_limit/request.ts`
  - Requires crypto:MD5Signature
- [ ] Implement `post_vgtransfer_bet_limit` (`POST /vgtransfer/bet/limit`)
  - Contract: `../openapi.yaml#/paths/~1vgtransfer~1bet~1limit/post`
  - Example: `../examples/post_vgtransfer_bet_limit/request.ts`
  - Requires crypto:MD5Signature
- [ ] Implement `post_vg_bet_limit_list` (`POST /vg/bet/limit/list`)
  - Contract: `../openapi.yaml#/paths/~1vg~1bet~1limit~1list/post`
  - Example: `../examples/post_vg_bet_limit_list/request.ts`
  - Requires crypto:MD5Signature
- [ ] Implement `post_vgtransfer_bet_limit_list` (`POST /vgtransfer/bet/limit/list`)
  - Contract: `../openapi.yaml#/paths/~1vgtransfer~1bet~1limit~1list/post`
  - Example: `../examples/post_vgtransfer_bet_limit_list/request.ts`
  - Requires crypto:MD5Signature
- [ ] Implement `post_vg_bet_users` (`POST /vg/bet/users`)
  - Contract: `../openapi.yaml#/paths/~1vg~1bet~1users/post`
  - Example: `../examples/post_vg_bet_users/request.ts`
  - Requires crypto:MD5Signature
- [ ] Implement `post_vgtransfer_bet_users` (`POST /vgtransfer/bet/users`)
  - Contract: `../openapi.yaml#/paths/~1vgtransfer~1bet~1users/post`
  - Example: `../examples/post_vgtransfer_bet_users/request.ts`
  - Requires crypto:MD5Signature
- [ ] Implement `post_vgtransfer_balance` (`POST /vgtransfer/balance`)
  - Contract: `../openapi.yaml#/paths/~1vgtransfer~1balance/post`
  - Example: `../examples/post_vgtransfer_balance/request.ts`
  - Requires crypto:MD5Signature
- [ ] Implement `post_vg_sign_up` (`POST /vg/sign-up`)
  - Contract: `../openapi.yaml#/paths/~1vg~1sign-up/post`
  - Example: `../examples/post_vg_sign_up/request.ts`
  - Requires crypto:MD5Signature
- [ ] Implement `post_vgtransfer_sign_up` (`POST /vgtransfer/sign-up`)
  - Contract: `../openapi.yaml#/paths/~1vgtransfer~1sign-up/post`
  - Example: `../examples/post_vgtransfer_sign_up/request.ts`
  - Requires crypto:MD5Signature
- [ ] Implement `post_vgtransfer_points` (`POST /vgtransfer/points`)
  - Contract: `../openapi.yaml#/paths/~1vgtransfer~1points/post`
  - Example: `../examples/post_vgtransfer_points/request.ts`
  - Requires crypto:MD5Signature
- [ ] Implement `post_vgtransfer_log` (`POST /vgtransfer/log`)
  - Contract: `../openapi.yaml#/paths/~1vgtransfer~1log/post`
  - Example: `../examples/post_vgtransfer_log/request.ts`
  - Requires crypto:MD5Signature

## Integration Mechanisms

- [ ] Signing/encryption `MD5Signature` (`../integration-contract.json#/crypto/0`)

## Blockers & Gaps

- No outstanding blockers, conflicts, unverified items, or gaps.

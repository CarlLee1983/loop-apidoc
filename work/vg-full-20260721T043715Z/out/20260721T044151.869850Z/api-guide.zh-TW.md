# VG 文档

## 文件範圍與來源

VG 文档涵盖单一钱包与转账钱包两套 API。单一钱包：游戏侧商户请求（用户注册、玩家登入、历史纪录、调整限红）与钱包商户接口（投注、派彩、取消等）；转账钱包：商户请求（用户注册、玩家登入、转账、余额与转账记录、历史纪录、调整限红）。请求以 application/json 提交，并以 MD5(参数值按字首排序串联 + API_KEY) 产生 body 字段 sign。

本文件涵蓋的來源：
- `vg-wen-dang.md`
- `vg-wen-dang.md.source.json`
- `vg-wen-dang/dan-yi-qian-bao.md`
- `vg-wen-dang/dan-yi-qian-bao.md.source.json`
- `vg-wen-dang/dan-yi-qian-bao/api.md`
- `vg-wen-dang/dan-yi-qian-bao/api.md.source.json`
- `vg-wen-dang/dan-yi-qian-bao/api/qian-bao.md`
- `vg-wen-dang/dan-yi-qian-bao/api/qian-bao.md.source.json`
- `vg-wen-dang/dan-yi-qian-bao/api/qian-bao/chong-xin-pai-cai.md`
- `vg-wen-dang/dan-yi-qian-bao/api/qian-bao/chong-xin-pai-cai.md.source.json`
- `vg-wen-dang/dan-yi-qian-bao/api/qian-bao/pai-cai.md`
- `vg-wen-dang/dan-yi-qian-bao/api/qian-bao/pai-cai.md.source.json`
- `vg-wen-dang/dan-yi-qian-bao/api/qian-bao/qu-xiao-tou-zhu-jie-suan.md`
- `vg-wen-dang/dan-yi-qian-bao/api/qian-bao/qu-xiao-tou-zhu-jie-suan.md.source.json`
- `vg-wen-dang/dan-yi-qian-bao/api/qian-bao/tou-zhu.md`
- `vg-wen-dang/dan-yi-qian-bao/api/qian-bao/tou-zhu.md.source.json`
- `vg-wen-dang/dan-yi-qian-bao/api/qian-bao/yuecha-xun.md`
- `vg-wen-dang/dan-yi-qian-bao/api/qian-bao/yuecha-xun.md.source.json`
- `vg-wen-dang/dan-yi-qian-bao/api/you-xi.md`
- `vg-wen-dang/dan-yi-qian-bao/api/you-xi.md.source.json`
- `vg-wen-dang/dan-yi-qian-bao/api/you-xi/deng-ru-you-xi.md`
- `vg-wen-dang/dan-yi-qian-bao/api/you-xi/deng-ru-you-xi.md.source.json`
- `vg-wen-dang/dan-yi-qian-bao/api/you-xi/pai-zhuo-lie-biao.md`
- `vg-wen-dang/dan-yi-qian-bao/api/you-xi/pai-zhuo-lie-biao.md.source.json`
- `vg-wen-dang/dan-yi-qian-bao/api/you-xi/wan-jia-xian-hong.md`
- `vg-wen-dang/dan-yi-qian-bao/api/you-xi/wan-jia-xian-hong.md.source.json`
- `vg-wen-dang/dan-yi-qian-bao/api/you-xi/xian-hong-lie-biao.md`
- `vg-wen-dang/dan-yi-qian-bao/api/you-xi/xian-hong-lie-biao.md.source.json`
- `vg-wen-dang/dan-yi-qian-bao/api/you-xi/you-xi-jie-guo.md`
- `vg-wen-dang/dan-yi-qian-bao/api/you-xi/you-xi-jie-guo.md.source.json`
- `vg-wen-dang/dan-yi-qian-bao/api/you-xi/zhu-ce-yong-hu.md`
- `vg-wen-dang/dan-yi-qian-bao/api/you-xi/zhu-ce-yong-hu.md.source.json`
- `vg-wen-dang/dan-yi-qian-bao/fu-lu.md`
- `vg-wen-dang/dan-yi-qian-bao/fu-lu.md.source.json`
- `vg-wen-dang/dan-yi-qian-bao/fu-lu/kai-pai-jie-guo.md`
- `vg-wen-dang/dan-yi-qian-bao/fu-lu/kai-pai-jie-guo.md.source.json`
- `vg-wen-dang/dan-yi-qian-bao/fu-lu/tou-zhu-pai-cai.md`
- `vg-wen-dang/dan-yi-qian-bao/fu-lu/tou-zhu-pai-cai.md.source.json`
- `vg-wen-dang/dan-yi-qian-bao/fu-lu/xiang-ying-dai-ma.md`
- `vg-wen-dang/dan-yi-qian-bao/fu-lu/xiang-ying-dai-ma.md.source.json`
- `vg-wen-dang/dan-yi-qian-bao/fu-lu/yu-xi-lie-biao.md`
- `vg-wen-dang/dan-yi-qian-bao/fu-lu/yu-xi-lie-biao.md.source.json`
- `vg-wen-dang/dan-yi-qian-bao/jia-mi-shuo-ming.md`
- `vg-wen-dang/dan-yi-qian-bao/jia-mi-shuo-ming.md.source.json`
- `vg-wen-dang/zhuan-zhang-qian-bao.md`
- `vg-wen-dang/zhuan-zhang-qian-bao.md.source.json`
- `vg-wen-dang/zhuan-zhang-qian-bao/api.md`
- `vg-wen-dang/zhuan-zhang-qian-bao/api.md.source.json`
- `vg-wen-dang/zhuan-zhang-qian-bao/api/you-xi.md`
- `vg-wen-dang/zhuan-zhang-qian-bao/api/you-xi.md.source.json`
- `vg-wen-dang/zhuan-zhang-qian-bao/api/you-xi/deng-ru-you-xi.md`
- `vg-wen-dang/zhuan-zhang-qian-bao/api/you-xi/deng-ru-you-xi.md.source.json`
- `vg-wen-dang/zhuan-zhang-qian-bao/api/you-xi/pai-zhuo-lie-biao.md`
- `vg-wen-dang/zhuan-zhang-qian-bao/api/you-xi/pai-zhuo-lie-biao.md.source.json`
- `vg-wen-dang/zhuan-zhang-qian-bao/api/you-xi/wan-jia-xian-hong.md`
- `vg-wen-dang/zhuan-zhang-qian-bao/api/you-xi/wan-jia-xian-hong.md.source.json`
- `vg-wen-dang/zhuan-zhang-qian-bao/api/you-xi/xian-hong-lie-biao.md`
- `vg-wen-dang/zhuan-zhang-qian-bao/api/you-xi/xian-hong-lie-biao.md.source.json`
- `vg-wen-dang/zhuan-zhang-qian-bao/api/you-xi/you-xi-jie-guo.md`
- `vg-wen-dang/zhuan-zhang-qian-bao/api/you-xi/you-xi-jie-guo.md.source.json`
- `vg-wen-dang/zhuan-zhang-qian-bao/api/you-xi/yuecha-xun.md`
- `vg-wen-dang/zhuan-zhang-qian-bao/api/you-xi/yuecha-xun.md.source.json`
- `vg-wen-dang/zhuan-zhang-qian-bao/api/you-xi/zhu-ce-yong-hu.md`
- `vg-wen-dang/zhuan-zhang-qian-bao/api/you-xi/zhu-ce-yong-hu.md.source.json`
- `vg-wen-dang/zhuan-zhang-qian-bao/api/you-xi/zhuan-zhang-gong-neng.md`
- `vg-wen-dang/zhuan-zhang-qian-bao/api/you-xi/zhuan-zhang-gong-neng.md.source.json`
- `vg-wen-dang/zhuan-zhang-qian-bao/api/you-xi/zhuan-zhang-ji-lu.md`
- `vg-wen-dang/zhuan-zhang-qian-bao/api/you-xi/zhuan-zhang-ji-lu.md.source.json`
- `vg-wen-dang/zhuan-zhang-qian-bao/fu-lu.md`
- `vg-wen-dang/zhuan-zhang-qian-bao/fu-lu.md.source.json`
- `vg-wen-dang/zhuan-zhang-qian-bao/fu-lu/kai-pai-jie-guo.md`
- `vg-wen-dang/zhuan-zhang-qian-bao/fu-lu/kai-pai-jie-guo.md.source.json`
- `vg-wen-dang/zhuan-zhang-qian-bao/fu-lu/tou-zhu-pai-cai.md`
- `vg-wen-dang/zhuan-zhang-qian-bao/fu-lu/tou-zhu-pai-cai.md.source.json`
- `vg-wen-dang/zhuan-zhang-qian-bao/fu-lu/xiang-ying-dai-ma.md`
- `vg-wen-dang/zhuan-zhang-qian-bao/fu-lu/xiang-ying-dai-ma.md.source.json`
- `vg-wen-dang/zhuan-zhang-qian-bao/fu-lu/yu-xi-lie-biao.md`
- `vg-wen-dang/zhuan-zhang-qian-bao/fu-lu/yu-xi-lie-biao.md.source.json`
- `vg-wen-dang/zhuan-zhang-qian-bao/jia-mi-shuo-ming.md`
- `vg-wen-dang/zhuan-zhang-qian-bao/jia-mi-shuo-ming.md.source.json`
- `https://vg-organization.gitbook.io/vg-docs`

## 串接前置條件

完成串接前，請先確認已取得對應的來源文件並完成驗證設定。

## 環境與 base URL

_來源未提供此項資訊。_

## 驗證／授權

- **sign**（type：`apiKey`，位置：`body`，說明：`将所有参数字首按顺序排列，将值串成字串，最后加上 API_KEY，以 MD5 加密取得 sign 值；sign 放在请求 body。`，原名：sign）

## 共用規則

_來源未提供此項資訊。_

## 整合機制

### 加解密／簽章：MD5 sign (单一钱包)
- 演算法：MD5
- 金鑰來源：key=API_KEY, iv=None
  1. 将所有参数字首按顺序排列 (abcde...等，12345...等)
  2. 将参数的「值」串成字串；JS/Python 示例字段顺序为 agent 再 loginname（字母序）
  3. 在字串最后加上 API_KEY
  4. 将此字串由 MD5 加密取得 sign 值（Python 示例为 hashlib.md5(...).hexdigest()）
- 驗章：sign（MD5）
### 加解密／簽章：MD5 sign (转账钱包)
- 演算法：MD5
- 金鑰來源：key=API_KEY, iv=None
  1. 将所有参数字首按顺序排列 (abcde...等，12345...等)
  2. 将参数的「值」串成字串；JS/Python 示例字段顺序为 agent 再 loginname（字母序）
  3. 在字串最后加上 API_KEY
  4. 将此字串由 MD5 加密取得 sign 值（Python 示例为 hashlib.md5(...).hexdigest()）
- 驗章：sign（MD5）
### 回呼：投注
- 需回應：{"code": 0, "balance": 123456.78}
- 驗證：请求体 sign 须按加密说明以 MD5 验证；签名未包含 detail
### 回呼：派彩
- 需回應：{"code": 0, "balance": 123456.78}
- 驗證：请求体 sign 须按加密说明以 MD5 验证；签名未包含 detail
### 回呼：取消投注/结算
- 需回應：{"code": 0, "balance": 123456.78}
- 驗證：请求体 sign 须按加密说明以 MD5 验证；签名未包含 detail
### 回呼：重新派彩
- 需回應：{"code": 0}
- 驗證：请求体 sign 须按加密说明以 MD5 验证；签名未包含 detail
### 回呼：余额查询
- 需回應：{"code": 0, "balance": 123456.78}
- 驗證：请求体 sign 须按加密说明以 MD5 验证（页面链至加密说明）
- 條件：签名 (未包含 detail)
- 條件：签名 (未包含 detail)
- 條件：签名 (未包含 detail)
- 條件：签名 (未包含 detail)
- 條件：loginname 仅限小写英文字母、数字
- 條件：loginname 仅限小写英文字母、数字

## Endpoint

### `POST` `/vg/sign-up`
注册用户。
分類：`单一钱包`　｜　簽章／認證：`sign`
**參數**
- `Content-Type`（位置 `header`，型別 `-`） — application/json
**請求 Body**
- `agent`（型別 `string`） — 代理名称
- `betlimit`（型別 `string`） — 限红列表(点击查看)
- `loginname`（型別 `string`） — 玩家名称+后缀(suffix)，仅限小写英文字母、数字
- `sign`（型別 `string`） — 签名(点击查看)
**回應**
- `default`：Success envelope with code, message, data (uid, username, betlimit), and TraceId
### `POST` `/vg/sign-in`
取得登入特定游戏的启动URL。
分類：`单一钱包`　｜　簽章／認證：`sign`
**參數**
- `Content-Type`（位置 `header`，型別 `-`） — application/json
**請求 Body**
- `agent`（型別 `string`） — 代理名称
- `language`（型別 `string`） — 用户语系(点击查看)
- `loginname`（型別 `string`） — 玩家名称+后缀(suffix)
- `rid`（型別 `string`） — 桌号 tableid (点击查看)。非必要参数，填入桌号可进指定牌桌。
- `betlimit`（型別 `string`） — 限红列表(点击查看)。非必要参数，可在登入时设置当前玩家限红。
- `return_url`（型別 `string`） — 重新导向 URL
- `token`（型別 `string`） — 身份令牌
- `sign`（型別 `string`） — 签名(点击查看)
**回應**
- `default`：Success envelope with code, message, data.url (launch URL), and TraceId
### `POST` `/vg/bet/users`
查询玩家每笔投注详细记录。
分類：`单一钱包`　｜　簽章／認證：`sign`
**參數**
- `Content-Type`（位置 `header`，型別 `-`） — application/json
**請求 Body**
- `agent`（型別 `string`，必填） — 代理名称
- `starttime`（型別 `datetime`，必填） — 必要(请求参数中使用 roundid、betid 时非必要)。UTC+8, 'YYYY-MM-DD HH:mm:ss'，时间区间不可超过 5 分钟
- `endtime`（型別 `datetime`，必填） — 必要(请求参数中使用 roundid、betid 时非必要)。UTC+8, 'YYYY-MM-DD HH:mm:ss'，时间区间不可超过 5 分钟
- `roundid`（型別 `string`） — 局号(可查询一个月内的记录)
- `betid`（型別 `string`） — 投注号(可查询一个月内的记录)
- `page_num`（型別 `int`，必填） — 页数
- `page_size`（型別 `int`，必填） — 每页笔数，max: 2000
- `status`（型別 `int`） — 1 = 未结算，4 = 已结算，9 = 无效单。若不带此参数默认将回应所有状态纪录。
- `sign`（型別 `string`，必填） — 签名(点击查看)
**回應**
- `default`：Success envelope with pagination fields and betdetail array (roundid, betid, username, shoeid, shoeround, casino, valid, bet, win, currency, tableidx, bettime, settletime, status, ip, bettype, platform, betresult, detail)
### `POST` `/vg/bet/limit`
调整玩家限红。
分類：`单一钱包`　｜　簽章／認證：`sign`
**參數**
- `Content-Type`（位置 `header`，型別 `-`） — application/json
**請求 Body**
- `agent`（型別 `string`） — 代理名称
- `betlimit`（型別 `string`） — 限红列表(点击查看)
- `loginname`（型別 `string`） — 玩家名称
- `sign`（型別 `string`） — 签名(点击查看)
**回應**
- `default`：Success envelope with code, message, and TraceId (no data field in example)
### `POST` `/vg/bet/limit/list`
查询代理当前可用限红。
分類：`单一钱包`　｜　簽章／認證：`sign`
**參數**
- `Content-Type`（位置 `header`，型別 `-`） — application/json
**請求 Body**
- `agent`（型別 `string`） — 代理名称
- `sign`（型別 `string`） — 签名(点击查看)
**回應**
- `default`：Success envelope with code, message, data array of limit-code objects (e.g. {"A": "100-2000"}), and TraceId
### `POST` `/vg/table/list`
查询所有牌桌。
分類：`单一钱包`　｜　簽章／認證：`sign`
**參數**
- `Content-Type`（位置 `header`，型別 `-`） — application/json
**請求 Body**
- `agent`（型別 `string`） — 代理名称
- `sign`（型別 `string`） — 签名(点击查看)
**回應**
- `default`：Success envelope with code, message, data array of table objects (tableid, casino, tablename, tablename_cn, time), and TraceId
### `POST` `/bet`
商户投注接口。
分類：`单一钱包`　｜　簽章／認證：`sign`
**參數**
- `Content-Type`（位置 `header`，型別 `string`）
**請求 Body**
- `agent`（型別 `string`） — 商户名称
- `loginname`（型別 `string`） — 玩家名称
- `token`（型別 `string`） — 玩家令牌
- `roundid`（型別 `string`） — 游戏局号
- `transid`（型別 `string`） — 投注号 (betid)
- `amount`（型別 `number`） — 投注金额
- `sign`（型別 `string`） — 签名 (未包含 detail)
- `detail`（型別 `object`） — 其他资讯
  - `bubalance`（型別 `string`）
  - `tableid`（型別 `string`）
  - `tableidx`（型別 `string`）
  - `shoeid`（型別 `string`）
  - `currency`（型別 `string`）
  - `ts`（型別 `number`）
  - `shoeround`（型別 `string`）
  - `platform`（型別 `string`）
  - `bettype`（型別 `string`）
  - `ip`（型別 `string`）
  - `maxlose`（型別 `number`）
  - `maxwin`（型別 `number`）
  - `bw`（型別 `number`）
  - `pw`（型別 `number`）
  - `tie`（型別 `number`）
  - `bp`（型別 `number`）
  - `pp`（型別 `number`）
  - `big`（型別 `number`）
  - `small`（型別 `number`）
  - `lucky6`（型別 `number`）
  - `ap`（型別 `number`）
  - `pfp`（型別 `number`）
  - `betlimit`（型別 `string`）
**回應**
- `default`：Success
### `POST` `/cancel`
商户取消投注/结算接口。
分類：`单一钱包`　｜　簽章／認證：`sign`
**參數**
- `Content-Type`（位置 `header`，型別 `string`）
**請求 Body**
- `agent`（型別 `string`） — 商户名称
- `loginname`（型別 `string`） — 玩家名称
- `roundid`（型別 `string`） — 游戏局号
- `transid`（型別 `string`） — 投注号 (betid)
- `amount`（型別 `number`） — 取消投注 = 投注金额；取消结算 = 派彩金额 - 投注金额
- `sign`（型別 `string`） — 签名 (未包含 detail)
- `detail`（型別 `object`） — 其他资讯
  - `id`（型別 `integer`）
  - `token`（型別 `string`）
  - `currency`（型別 `string`）
  - `bw`（型別 `string`）
  - `pw`（型別 `string`）
  - `tie`（型別 `string`）
  - `bp`（型別 `string`）
  - `pp`（型別 `string`）
  - `big`（型別 `string`）
  - `small`（型別 `string`）
  - `lucky6`（型別 `string`）
  - `ap`（型別 `string`）
  - `pfp`（型別 `string`）
  - `bw_win`（型別 `string`）
  - `pw_win`（型別 `string`）
  - `tie_win`（型別 `string`）
  - `bp_win`（型別 `string`）
  - `pp_win`（型別 `string`）
  - `big_win`（型別 `string`）
  - `small_win`（型別 `string`）
  - `lucky6_win`（型別 `string`）
  - `ap_win`（型別 `string`）
  - `pfp_win`（型別 `string`）
  - `abet`（型別 `string`）
  - `abet2`（型別 `string`）
  - `tableidx`（型別 `string`）
  - `shoeid`（型別 `integer`）
  - `shoeround`（型別 `integer`）
  - `btimestamp`（型別 `integer`）
  - `bettime`（型別 `string`）
  - `settletime`（型別 `-`）
  - `percentage`（型別 `-`）
  - `fanshui`（型別 `-`）
  - `status`（型別 `integer`）
  - `ip`（型別 `string`）
  - `bettype`（型別 `string`）
  - `platform`（型別 `string`）
  - `detail`（型別 `-`）
**回應**
- `default`：Success
### `POST` `/win`
商户派彩接口。
分類：`单一钱包`　｜　簽章／認證：`sign`
**參數**
- `Content-Type`（位置 `header`，型別 `string`）
**請求 Body**
- `agent`（型別 `string`） — 商户名称
- `loginname`（型別 `string`） — 玩家名称
- `roundid`（型別 `string`） — 游戏局号
- `transid`（型別 `string`） — 投注号 (betid)
- `amount`（型別 `number`） — 派彩金额
- `sign`（型別 `string`） — 签名 (未包含 detail)
- `detail`（型別 `object`） — 其他资讯
  - `id`（型別 `number`）
  - `token`（型別 `string`）
  - `currency`（型別 `string`）
  - `bw`（型別 `string`）
  - `pw`（型別 `string`）
  - `tie`（型別 `string`）
  - `bp`（型別 `string`）
  - `pp`（型別 `string`）
  - `big`（型別 `string`）
  - `small`（型別 `string`）
  - `lucky6`（型別 `string`）
  - `ap`（型別 `string`）
  - `pfp`（型別 `string`）
  - `bw_win`（型別 `string`）
  - `pw_win`（型別 `string`）
  - `tie_win`（型別 `string`）
  - `bp_win`（型別 `string`）
  - `pp_win`（型別 `string`）
  - `big_win`（型別 `string`）
  - `small_win`（型別 `string`）
  - `lucky6_win`（型別 `string`）
  - `ap_win`（型別 `string`）
  - `pfp_win`（型別 `string`）
  - `abet`（型別 `string`）
  - `abet2`（型別 `string`）
  - `tableidx`（型別 `string`）
  - `shoeid`（型別 `number`）
  - `shoeround`（型別 `number`）
  - `btimestamp`（型別 `number`）
  - `bettime`（型別 `string`）
  - `settletime`（型別 `-`）
  - `percentage`（型別 `-`）
  - `fanshui`（型別 `-`）
  - `status`（型別 `number`）
  - `ip`（型別 `string`）
  - `bettype`（型別 `string`）
  - `platform`（型別 `string`）
  - `detail`（型別 `-`）
**回應**
- `default`：Success
### `POST` `/resettle`
商户重新派彩接口。
分類：`单一钱包`　｜　簽章／認證：`sign`
**參數**
- `Content-Type`（位置 `header`，型別 `string`）
**請求 Body**
- `agent`（型別 `string`） — 商户名称
- `loginname`（型別 `string`） — 玩家名称
- `roundid`（型別 `string`） — 游戏局号
- `transid`（型別 `string`） — 投注号 (betid)
- `amount`（型別 `number`） — 当笔资料最终派彩金额，不会扣/补前次派彩金额
- `sign`（型別 `string`） — 签名 (未包含 detail)
- `detail`（型別 `object`） — 其他资讯
**回應**
- `default`：Success
### `POST` `/balance`
查询玩家余额。
分類：`单一钱包`　｜　簽章／認證：`sign`
**參數**
- `Content-Type`（位置 `header`，型別 `string`）
**請求 Body**
- `agent`（型別 `string`） — 商户名称
- `loginname`（型別 `string`） — 玩家名称
- `token`（型別 `string`） — 玩家令牌
- `sign`（型別 `string`） — 签名([点击查看](/vg-docs/vg-wen-dang/dan-yi-qian-bao/jia-mi-shuo-ming.md))
**回應**
- `default`：Success
### `POST` `/vgtransfer/sign-up`
注册用户。
分類：`转账钱包`　｜　簽章／認證：`sign`
**參數**
- `Content-Type`（位置 `header`，型別 `string`）
**請求 Body**
- `agent`（型別 `string`） — 代理名称
- `betlimit`（型別 `string`） — 限红列表([点击查看](/vg-docs/vg-wen-dang/zhuan-zhang-qian-bao/api/you-xi/xian-hong-lie-biao.md))
- `loginname`（型別 `string`） — 玩家名称+后缀(suffix) 仅限小写英文字母、数字
- `sign`（型別 `string`） — 签名([点击查看](/vg-docs/vg-wen-dang/zhuan-zhang-qian-bao/jia-mi-shuo-ming.md))
**回應**
- `default`：Success
### `POST` `/vgtransfer/sign-in`
取得登入特定游戏的启动URL。
分類：`转账钱包`　｜　簽章／認證：`sign`
**參數**
- `Content-Type`（位置 `header`，型別 `-`） — application/json
**請求 Body**
- `agent`（型別 `string`） — 代理名称
- `language`（型別 `string`） — 用户语系([点击查看](/vg-docs/vg-wen-dang/zhuan-zhang-qian-bao/fu-lu/yu-xi-lie-biao.md))
- `loginname`（型別 `string`） — 玩家名称+后缀(suffix)
- `rid`（型別 `string`） — 桌号 tableid ([点击查看](/pages/eKP65RR00NcZ1oYQQOJD))。非必要参数，填入桌号可进指定牌桌。
- `betlimit`（型別 `string`） — 限红列表([点击查看](https://vg-organization.gitbook.io/vg-docs/vg-wen-dang/dan-yi-qian-bao/api/you-xi/xian-hong-lie-biao#id-200))。非必要参数，可在登入时设置当前玩家限红。
- `return_url`（型別 `string`） — 重新导向 URL
- `sign`（型別 `string`） — 签名([点击查看](/vg-docs/vg-wen-dang/zhuan-zhang-qian-bao/jia-mi-shuo-ming.md))
**回應**
- `default`：Success
### `POST` `/vgtransfer/points`
玩家上分 / 下分。
分類：`转账钱包`　｜　簽章／認證：`sign`
**參數**
- `Content-Type`（位置 `header`，型別 `-`） — application/json
**請求 Body**
- `agent`（型別 `string`） — 代理名称
- `loginname`（型別 `string`） — 玩家名称
- `amount`（型別 `int`） — 转账金额
- `sid`（型別 `string`） — 商户产值 ( 商户转账唯一订单号12位以上 )
- `status`（型別 `string`） — in = 转进
out = 转出
- `sign`（型別 `string`） — 签名([点击查看](/vg-docs/vg-wen-dang/zhuan-zhang-qian-bao/jia-mi-shuo-ming.md))
**回應**
- `default`：Success
### `POST` `/vgtransfer/balance`
查询玩家余额。
分類：`转账钱包`　｜　簽章／認證：`sign`
**參數**
- `Content-Type`（位置 `header`，型別 `-`） — application/json
**請求 Body**
- `agent`（型別 `string`） — 代理名称
- `username`（型別 `string`） — 玩家名称
- `sign`（型別 `string`） — 签名([点击查看](/vg-docs/vg-wen-dang/zhuan-zhang-qian-bao/jia-mi-shuo-ming.md))
**回應**
- `default`：Success
### `POST` `/vgtransfer/log`
查询玩家转账记录。时间区间不可超过 5 分钟
分類：`转账钱包`　｜　簽章／認證：`sign`
**參數**
- `Content-Type`（位置 `header`，型別 `-`） — application/json
**請求 Body**
- `agent`（型別 `string`） — 代理名称
- `starttime`（型別 `datetime`） — UTC+8, 'YYYY-MM-DD HH:mm:ss'
- `endtime`（型別 `datetime`） — UTC+8, 'YYYY-MM-DD HH:mm:ss'
- `page_num`（型別 `int`） — 页数
- `page_size`（型別 `int`） — 每页笔数
max: 2000
- `status`（型別 `string`） — in = 转进
out = 转出
若不带此参数默认将回应所有状态纪录。
- `sid`（型別 `string`） — 转账单号
若不带此参数默认将回应所有订单纪录。
- `sign`（型別 `string`） — 签名([点击查看](/vg-docs/vg-wen-dang/zhuan-zhang-qian-bao/jia-mi-shuo-ming.md))
**回應**
- `default`：Success
### `POST` `/vgtransfer/bet/users`
查询玩家每笔投注详细记录。
分類：`转账钱包`　｜　簽章／認證：`sign`
**參數**
- `Content-Type`（位置 `header`，型別 `-`） — application/json
**請求 Body**
- `agent`（型別 `string`，必填） — 代理名称
- `starttime`（型別 `datetime`，必填） — UTC+8, 'YYYY-MM-DD HH:mm:ss'
时间区间不可超过 5 分钟
(请求参数中使用 roundid、betid 时非必要)
- `endtime`（型別 `datetime`，必填） — UTC+8, 'YYYY-MM-DD HH:mm:ss'
时间区间不可超过 5 分钟
(请求参数中使用 roundid、betid 时非必要)
- `roundid`（型別 `string`） — 局号
(可查询一个月内的记录)
- `betid`（型別 `string`） — 投注号
(可查询一个月内的记录)
- `page_num`（型別 `int`，必填） — 页数
- `page_size`（型別 `int`，必填） — 每页笔数
max: 2000
- `status`（型別 `int`） — 1 = 未结算
4 = 已结算
9 = 无效单
若不带此参数默认将回应所有状态纪录。
- `sign`（型別 `string`，必填） — 签名[(点击查看](/pages/xcqV5MT88Fe4CmEAPdRe))
**回應**
- `default`：Success
### `POST` `/vgtransfer/bet/limit`
调整玩家限红。
分類：`转账钱包`　｜　簽章／認證：`sign`
**參數**
- `Content-Type`（位置 `header`，型別 `-`） — application/json
**請求 Body**
- `agent`（型別 `string`） — 代理名称
- `betlimit`（型別 `string`） — 限红列表([点击查看](/vg-docs/vg-wen-dang/zhuan-zhang-qian-bao/api/you-xi/xian-hong-lie-biao.md))
- `loginname`（型別 `string`） — 玩家名称
- `sign`（型別 `string`） — 签名([点击查看](/vg-docs/vg-wen-dang/zhuan-zhang-qian-bao/jia-mi-shuo-ming.md))
**回應**
- `default`：Success
### `POST` `/vgtransfer/bet/limit/list`
查询代理当前可用限红。
分類：`转账钱包`　｜　簽章／認證：`sign`
**參數**
- `Content-Type`（位置 `header`，型別 `-`） — application/json
**請求 Body**
- `agent`（型別 `string`） — 代理名称
- `sign`（型別 `string`） — 签名([点击查看](/vg-docs/vg-wen-dang/zhuan-zhang-qian-bao/jia-mi-shuo-ming.md))
**回應**
- `default`：Success
### `POST` `/vgtransfer/table/list`
查询所有牌桌。
分類：`转账钱包`　｜　簽章／認證：`sign`
**參數**
- `Content-Type`（位置 `header`，型別 `-`） — application/json
**請求 Body**
- `agent`（型別 `string`） — 代理名称
- `sign`（型別 `string`） — 签名[(点击查看](/vg-docs/vg-wen-dang/zhuan-zhang-qian-bao/jia-mi-shuo-ming.md))
**回應**
- `default`：Success

## Request／Response 範例

**POST /vg/sign-up — Success**
```json
{
  "code": 1000,
  "message": "Success",
  "data": {
    "uid": 10208,
    "username": "usernamexox",
    "betlimit": "A"
  },
  "TraceId": "9181f940-f34e-4659-adfb-bda82c92c562"
}
```
**POST /vg/sign-in — Success**
```json
{
  "code": 1000,
  "message": "Success",
  "data": {
    "url": "https://launch_url"
  },
  "TraceId": "4375da61-9d5e-4b19-a637-23983c34dbca"
}
```
**POST /vg/bet/users — Success**
```json
{
  "code": 1000,
  "message": "Success",
  "TraceId": "e5956b0f-8251-49c7-9066-8a6ea31b2149",
  "data": {
    "current_page": 1,
    "current_counts": 1,
    "total_pages": 8,
    "total_counts": 8,
    "betdetail": [
      {
        "roundid": "T66R10205435",
        "betid": "394bbefe-334f-4fc5-8065-0d1ab5467dcd",
        "username": "test1",
        "shoeid": 1044556,
        "shoeround": 49,
        "casino": "HANN",
        "valid": 500,
        "bet": 500,
        "win": 975,
        "currency": "USDT",
        "tableidx": "MB2023",
        "bettime": "2024-05-28T10:19:11.000Z",
        "settletime": "2024-05-28T10:19:44.000Z",
        "status": 4,
        "ip": "36.224.192.78",
        "bettype": "single",
        "platform": "pc",
        "betresult": {
          "bw": "500.00",
          "pw": "0.00",
          "tie": "0.00",
          "bp": "0.00",
          "pp": "0.00",
          "big": "0.00",
          "small": "0.00",
          "lucky6": "0.00",
          "ap": "0.00",
          "pfp": "0.00",
          "bw_win": "975.00",
          "pw_win": "0.00",
          "tie_win": "0.00",
          "bp_win": "0.00",
          "pp_win": "0.00",
          "big_win": "0.00",
          "small_win": "0.00",
          "lucky6_win": "0.00",
          "ap_win": "0.00",
          "pfp_win": "0.00"
        },
        "detail": {
          "b1": "c5",
          "b2": "h11",
          "b3": "0",
          "p1": "h10",
          "p2": "c13",
          "p3": "c3"
        }
      }
    ]
  }
}
```
**POST /vg/bet/limit — Success**
```json
{
  "code": 1000,
  "message": "Success",
  "TraceId": "76ce3739-42bc-4fe3-9bdf-1433d376b73a"
}
```
**POST /vg/bet/limit/list — Success**
```json
{
  "code": 1000,
  "message": "Success",
  "data": [
    {
      "A": "100-2000"
    },
    {
      "A1": "100-5000"
    }
  ],
  "TraceId": "b6c1a14e-48ef-4612-b683-e82547f06bd8"
}
```
**POST /vg/table/list — Success**
```json
{
  "code": 1000,
  "message": "Success",
  "data": [
    {
      "tableid": "t6",
      "casino": "SOLAIRE",
      "tablename": "MD3109",
      "tablename_cn": "晨丽厅",
      "time": 48
    },
    {
      "tableid": "t7",
      "casino": "SOLAIRE",
      "tablename": "MD3110",
      "tablename_cn": "晨丽厅",
      "time": 48
    }
  ],
  "TraceId": "b6c1a14e-48ef-4612-b683-e82547f06bd8"
}
```
**POST /bet — Body params**
```json
{
  "agent": "agentName",
  "loginname": "userName",
  "token": "0bb3dd7cd7949bfe105582dd84a78502",
  "roundid": "T100112R10052197",
  "transid": "b196c26f-619f-484e-9c5f-5afab43105f3",
  "amount": 14,
  "sign": "f939e3bafd829fbwiejdoeb16d2b5940",
  "detail": {
    "bubalance": "386.21",
    "tableid": "MD3110",
    "tableidx": "t7",
    "shoeid": "99926",
    "currency": "USDT",
    "ts": 1775778961,
    "shoeround": "6",
    "platform": "mobile",
    "bettype": "single",
    "ip": "xxx.xxx.xxx.xxx",
    "maxlose": 0,
    "maxwin": 0,
    "bw": 13,
    "pw": 0,
    "tie": 0,
    "bp": 0,
    "pp": 0,
    "big": 0,
    "small": 0,
    "lucky6": 1,
    "ap": 0,
    "pfp": 0,
    "betlimit": "B"
  }
}
```
**POST /bet — Success**
```json
{
  "code": 0,
  "balance": 123456.78
}
```
**POST /cancel — Body params**
```json
{
  "agent": "agentName",
  "loginname": "userName",
  "roundid": "T100112R10052197",
  "transid": "75961a03-4f1d-40c8-93a1-4214bbf4c615",
  "amount": "0.00",
  "sign": "b5228747850d94e333c11183a9d7c2b1",
  "detail": {
    "id": 258,
    "token": "e4dbb48deb1f0718e44599867de96837",
    "currency": "USDT",
    "bw": "0.00",
    "pw": "0.00",
    "tie": "0.00",
    "bp": "0.00",
    "pp": "0.00",
    "big": "0.00",
    "small": "0.00",
    "lucky6": "0.00",
    "ap": "0.00",
    "pfp": "0.00",
    "bw_win": "0.00",
    "pw_win": "0.00",
    "tie_win": "0.00",
    "bp_win": "0.00",
    "pp_win": "0.00",
    "big_win": "0.00",
    "small_win": "0.00",
    "lucky6_win": "0.00",
    "ap_win": "0.00",
    "pfp_win": "0.00",
    "abet": "0.00",
    "abet2": "0.00",
    "tableidx": "MD18909",
    "shoeid": 43585,
    "shoeround": 37,
    "btimestamp": 1759229102,
    "bettime": "2025-09-30T10:45:25.000Z",
    "settletime": null,
    "percentage": null,
    "fanshui": null,
    "status": 1,
    "ip": "xxx.xxx.xxx.xxx",
    "bettype": "single",
    "platform": "pc",
    "detail": null
  }
}
```
**POST /cancel — Success**
```json
{
  "code": 0,
  "balance": 123456.78
}
```
**POST /win — Body params**
```json
{
  "agent": "agentName",
  "loginname": "userName",
  "roundid": "T100112R10052197",
  "transid": "75961a03-4f1d-40c8-93a1-4214bbf4c615",
  "amount": "0.00",
  "sign": "b5228747850d94e333c11183a9d7c2b1",
  "detail": {
    "id": 258,
    "token": "e4dbb48deb1f0718e44599867de96837",
    "currency": "USDT",
    "bw": "0.00",
    "pw": "0.00",
    "tie": "0.00",
    "bp": "0.00",
    "pp": "0.00",
    "big": "0.00",
    "small": "0.00",
    "lucky6": "0.00",
    "ap": "0.00",
    "pfp": "0.00",
    "bw_win": "0.00",
    "pw_win": "0.00",
    "tie_win": "0.00",
    "bp_win": "0.00",
    "pp_win": "0.00",
    "big_win": "0.00",
    "small_win": "0.00",
    "lucky6_win": "0.00",
    "ap_win": "0.00",
    "pfp_win": "0.00",
    "abet": "0.00",
    "abet2": "0.00",
    "tableidx": "MD18909",
    "shoeid": 43585,
    "shoeround": 37,
    "btimestamp": 1759229102,
    "bettime": "2025-09-30T10:45:25.000Z",
    "settletime": null,
    "percentage": null,
    "fanshui": null,
    "status": 1,
    "ip": "xxx.xxx.xxx.xxx",
    "bettype": "single",
    "platform": "pc",
    "detail": null
  }
}
```
**POST /win — Success**
```json
{
  "code": 0,
  "balance": 123456.78
}
```
**POST /resettle — Success**
```json
{
  "code": 0
}
```
**POST /balance — Success**
```json
{
  "code": 0,
  "balance": 123456.78
}
```
**POST /vgtransfer/sign-up — Success**
```json
{
  "code": 1000,
  "message": "Success",
  "data": {
    "uid": 10208,
    "username": "usernamexox",
    "betlimit": "A"
  },
  "TraceId": "9181f940-f34e-4659-adfb-bda82c92c562"
}
```
**POST /vgtransfer/sign-in — Success**
```json
{
  "code": 1000,
  "message": "Success",
  "data": {
    "url": "https://launch_url"
  },
  "TraceId": "4375da61-9d5e-4b19-a637-23983c34dbca"
}
```
**POST /vgtransfer/points — Success**
```json
{
  "code": 1000,
  "message": "Success",
  "balance": "1000.00",
  "TraceId": "ee7db471-4374-416c-9490-269ba29d1cda"
}
```
**POST /vgtransfer/balance — Success**
```json
{
  "code": 1000,
  "message": "Success",
  "balance": "1000.00",
  "TraceId": "ee7db471-4374-416c-9490-269ba29d1cda"
}
```
**POST /vgtransfer/log — Success**
```json
{
  "code": 1000,
  "message": "Success",
  "TraceId": "bd0dbfff-8892-48f4-ba75-83bc076232d2",
  "data": {
    "current_page": 1,
    "current_counts": 3,
    "total_pages": 1,
    "total_counts": 3,
    "betdetail": [
      {
        "username": "test1",
        "type": "in",
        "amount": "1.00",
        "beforeamount": "999.00",
        "afteramount": "1000.00",
        "busid": "SDSI837429749",
        "anyid": "IIT20241001163628",
        "ip": "127.0.0.1",
        "createtime": "2024-10-01T08:36:28.000Z"
      },
      {
        "username": "test1",
        "type": "out",
        "amount": "-1.00",
        "beforeamount": "1000.00",
        "afteramount": "999.00",
        "busid": "SDSI837429749",
        "anyid": "OTT20241001163649",
        "ip": "127.0.0.1",
        "createtime": "2024-10-01T08:36:49.000Z"
      },
      {
        "username": "test1",
        "type": "out",
        "amount": "-1.00",
        "beforeamount": "999.00",
        "afteramount": "998.00",
        "busid": "SDSI837429749",
        "anyid": "OTT20241001163811",
        "ip": "127.0.0.1",
        "createtime": "2024-10-01T08:38:11.000Z"
      }
    ]
  }
}
```
**POST /vgtransfer/bet/users — Success**
```json
{
  "code": 1000,
  "message": "Success",
  "TraceId": "e5956b0f-8251-49c7-9066-8a6ea31b2149",
  "data": {
    "current_page": 1,
    "current_counts": 1,
    "total_pages": 8,
    "total_counts": 8,
    "betdetail": [
      {
        "roundid": "T66R10205435",
        "betid": "394bbefe-334f-4fc5-8065-0d1ab5467dcd",
        "username": "test1",
        "shoeid": 1044556,
        "shoeround": 49,
        "casino": "HANN",
        "valid": 500,
        "bet": 500,
        "win": 975,
        "currency": "USDT",
        "tableidx": "MB2023",
        "bettime": "2024-05-28T10:19:11.000Z",
        "settletime": "2024-05-28T10:19:44.000Z",
        "status": 4,
        "ip": "36.224.192.78",
        "bettype": "single",
        "platform": "pc",
        "betresult": {
          "bw": "500.00",
          "pw": "0.00",
          "tie": "0.00",
          "bp": "0.00",
          "pp": "0.00",
          "big": "0.00",
          "small": "0.00",
          "lucky6": "0.00",
          "ap": "0.00",
          "pfp": "0.00",
          "bw_win": "975.00",
          "pw_win": "0.00",
          "tie_win": "0.00",
          "bp_win": "0.00",
          "pp_win": "0.00",
          "big_win": "0.00",
          "small_win": "0.00",
          "lucky6_win": "0.00",
          "ap_win": "0.00",
          "pfp_win": "0.00"
        },
        "detail": {
          "b1": "c5",
          "b2": "h11",
          "b3": "0",
          "p1": "h10",
          "p2": "c13",
          "p3": "c3"
        }
      }
    ]
  }
}
```
**POST /vgtransfer/bet/limit — Success**
```json
{
  "code": 1000,
  "message": "Success",
  "TraceId": "76ce3739-42bc-4fe3-9bdf-1433d376b73a"
}
```
**POST /vgtransfer/bet/limit/list — Success**
```json
{
  "code": 1000,
  "message": "Success",
  "data": [
    {
      "A": "100-2000"
    },
    {
      "A1": "100-5000"
    }
  ],
  "TraceId": "b6c1a14e-48ef-4612-b683-e82547f06bd8"
}
```
**POST /vgtransfer/table/list — Success**
```json
{
  "code": 1000,
  "message": "Success",
  "data": [
    {
      "tableid": "t6",
      "casino": "SOLAIRE",
      "tablename": "MD3109",
      "tablename_cn": "晨丽厅",
      "time": 48
    },
    {
      "tableid": "t7",
      "casino": "SOLAIRE",
      "tablename": "MD3110",
      "tablename_cn": "晨丽厅",
      "time": 48
    }
  ],
  "TraceId": "b6c1a14e-48ef-4612-b683-e82547f06bd8"
}
```

## 錯誤碼

| code | HTTP | 意義 |
| --- | --- | --- |
| `1000` | `-` | 成功 |
| `1001` | `-` | 系统错误 |
| `1002` | `-` | 未知错误 |
| `5000` | `-` | 验证码错误 |
| `5001` | `-` | 请求参数有误 |
| `5002` | `-` | 请求之币别不支持 |
| `5003` | `-` | 钱包余额不足 |
| `5005` | `-` | 商户不存在 |
| `5006` | `-` | 玩家已存在 |
| `5008` | `-` | 国家/地区代码错误 |
| `5009` | `-` | 玩家账号不存在 |
| `5010` | `-` | 玩家已被锁定 |
| `5012` | `-` | 找不到对应的游戏 |
| `5013` | `-` | Session验证失败 |
| `5014` | `-` | 无效的时间格式 |
| `5015` | `-` | 无效的Provider |
| `5016` | `-` | 无效的金额 |
| `5017` | `-` | API權限不足 |
| `5018` | `-` | 無效的Brand UID |
| `5019` | `-` | 登入 URL 超时 |
| `5040` | `-` | 请求限制，每3秒仅能叫用一次 |
| `5041` | `-` | 请求区段限制，每一个请求区间不超过 24小时，此外可查询资料仅为6个月内的资料。 |
| `5042` | `-` | 下注记录不存在 |
| `5043` | `-` | 下注记录已存在 |
| `5045` | `-` | 转帐钱包上下分，重复的 SID |

## 限制與注意事項

- **请求频率限制**：请求限制，每3秒仅能叫用一次（响应代码 5040）。
- **查询时间区段限制**：每一个请求区间不超过 24小时，此外可查询资料仅为6个月内的资料（响应代码 5041）。

## 已知缺漏與來源衝突

**已知缺漏：**
- [10] API base URL not stated in sources
- [10] Document/API version not stated
- [10] Error HTTP status mapping not stated
- [10] Error code applicable endpoints not stated
- [06] HTTP status code not documented
- [06] body field required flags not documented
- [06] failure/error response body not documented
- [06] required flags not documented for agent, language, loginname, return_url, token, sign
- [06] conditional required semantics for starttime/endtime when roundid or betid is provided not fully specified
- [06] complete list of limit codes not documented (only example codes A and A1 shown)
- [06] response field meanings documented only via JSON example, not prose
- [06] detail sub-fields have no field-description table (types inferred from Body params JSON example only)
- [06] no HTTP status code documented for the response
- [06] no failure-response body documented
- [06] required/optional not stated for Header or Body fields
- [06] detail.settletime, detail.percentage, detail.fanshui, detail.detail have null in example so type unknown
- [06] no Body params JSON request example on this page
- [06] detail field structure not documented beyond type object
- [06] no request-body JSON example on this page
- [06] no HTTP status code documented for Success response
- [06] no error response documented
- [06] starttime and endtime requiredness is conditional on roundid/betid usage

```json
{"missing": ["API base URL not stated in sources", "Document/API version not stated", "Error HTTP status mapping not stated", "Error code applicable endpoints not stated"]}
```

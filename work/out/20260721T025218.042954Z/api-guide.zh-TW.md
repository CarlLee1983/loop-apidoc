# VG 游戏 API 文档

## 文件範圍與來源

VG 游戏单一钱包与转账钱包 API 整合文档。

本文件涵蓋的來源：
- `vg-wen-dang.md`
- `vg-wen-dang/dan-yi-qian-bao.md`
- `vg-wen-dang/dan-yi-qian-bao/api.md`
- `vg-wen-dang/dan-yi-qian-bao/api/qian-bao.md`
- `vg-wen-dang/dan-yi-qian-bao/api/qian-bao/chong-xin-pai-cai.md`
- `vg-wen-dang/dan-yi-qian-bao/api/qian-bao/pai-cai.md`
- `vg-wen-dang/dan-yi-qian-bao/api/qian-bao/qu-xiao-tou-zhu-jie-suan.md`
- `vg-wen-dang/dan-yi-qian-bao/api/qian-bao/tou-zhu.md`
- `vg-wen-dang/dan-yi-qian-bao/api/qian-bao/yuecha-xun.md`
- `vg-wen-dang/dan-yi-qian-bao/api/you-xi.md`
- `vg-wen-dang/dan-yi-qian-bao/api/you-xi/deng-ru-you-xi.md`
- `vg-wen-dang/dan-yi-qian-bao/api/you-xi/pai-zhuo-lie-biao.md`
- `vg-wen-dang/dan-yi-qian-bao/api/you-xi/wan-jia-xian-hong.md`
- `vg-wen-dang/dan-yi-qian-bao/api/you-xi/xian-hong-lie-biao.md`
- `vg-wen-dang/dan-yi-qian-bao/api/you-xi/you-xi-jie-guo.md`
- `vg-wen-dang/dan-yi-qian-bao/api/you-xi/zhu-ce-yong-hu.md`
- `vg-wen-dang/dan-yi-qian-bao/fu-lu.md`
- `vg-wen-dang/dan-yi-qian-bao/fu-lu/kai-pai-jie-guo.md`
- `vg-wen-dang/dan-yi-qian-bao/fu-lu/tou-zhu-pai-cai.md`
- `vg-wen-dang/dan-yi-qian-bao/fu-lu/xiang-ying-dai-ma.md`
- `vg-wen-dang/dan-yi-qian-bao/fu-lu/yu-xi-lie-biao.md`
- `vg-wen-dang/dan-yi-qian-bao/jia-mi-shuo-ming.md`
- `vg-wen-dang/zhuan-zhang-qian-bao.md`
- `vg-wen-dang/zhuan-zhang-qian-bao/api.md`
- `vg-wen-dang/zhuan-zhang-qian-bao/api/you-xi.md`
- `vg-wen-dang/zhuan-zhang-qian-bao/api/you-xi/deng-ru-you-xi.md`
- `vg-wen-dang/zhuan-zhang-qian-bao/api/you-xi/pai-zhuo-lie-biao.md`
- `vg-wen-dang/zhuan-zhang-qian-bao/api/you-xi/wan-jia-xian-hong.md`
- `vg-wen-dang/zhuan-zhang-qian-bao/api/you-xi/xian-hong-lie-biao.md`
- `vg-wen-dang/zhuan-zhang-qian-bao/api/you-xi/you-xi-jie-guo.md`
- `vg-wen-dang/zhuan-zhang-qian-bao/api/you-xi/yuecha-xun.md`
- `vg-wen-dang/zhuan-zhang-qian-bao/api/you-xi/zhu-ce-yong-hu.md`
- `vg-wen-dang/zhuan-zhang-qian-bao/api/you-xi/zhuan-zhang-gong-neng.md`
- `vg-wen-dang/zhuan-zhang-qian-bao/api/you-xi/zhuan-zhang-ji-lu.md`
- `vg-wen-dang/zhuan-zhang-qian-bao/fu-lu.md`
- `vg-wen-dang/zhuan-zhang-qian-bao/fu-lu/kai-pai-jie-guo.md`
- `vg-wen-dang/zhuan-zhang-qian-bao/fu-lu/tou-zhu-pai-cai.md`
- `vg-wen-dang/zhuan-zhang-qian-bao/fu-lu/xiang-ying-dai-ma.md`
- `vg-wen-dang/zhuan-zhang-qian-bao/fu-lu/yu-xi-lie-biao.md`
- `vg-wen-dang/zhuan-zhang-qian-bao/jia-mi-shuo-ming.md`

## 串接前置條件

完成串接前，請先確認已取得對應的來源文件並完成驗證設定。

## 環境與 base URL

| 環境 | base URL | 版本 |
| --- | --- | --- |
| production | `https://api.vg-organization.com` | `-` |

## 驗證／授權

- **MD5Signature**（type：`apiKey`，位置：`body`，說明：`MD5 signature using API_KEY. See 加密说明.`，原名：MD5Signature）

## 共用規則

_來源未提供此項資訊。_

## 整合機制

（來源未提供整合機制資訊)

## Endpoint

### `POST` `/resettle`
重新派彩
分類：`qian-bao`　｜　簽章／認證：`MD5Signature`
**請求 Body**
- `-----------`（型別 `string`，必填） — ----------------------
- `agent`（型別 `string`，必填） — 商户名称
- `loginname`（型別 `string`，必填） — 玩家名称
- `roundid`（型別 `string`，必填） — 游戏局号
- `transid`（型別 `string`，必填） — 投注号 (betid)
- `amount`（型別 `number`，必填） — 当笔资料最终派彩金额，不会扣/补前次派彩金额
- `sign`（型別 `string`，必填） — 签名 (未包含 detail)
- `detail`（型別 `object`，必填） — 其他资讯
**回應**
- `200`：Successful response
### `POST` `/win`
派彩
分類：`qian-bao`　｜　簽章／認證：`MD5Signature`
**請求 Body**
- `-----------`（型別 `string`，必填） — ---------------
- `agent`（型別 `string`，必填） — 商户名称
- `loginname`（型別 `string`，必填） — 玩家名称
- `roundid`（型別 `string`，必填） — 游戏局号
- `transid`（型別 `string`，必填） — 投注号 (betid)
- `amount`（型別 `number`，必填） — 派彩金额
- `sign`（型別 `string`，必填） — 签名 (未包含 detail)
- `detail`（型別 `object`，必填） — 其他资讯
**回應**
- `200`：Successful response
### `POST` `/cancel`
取消投注/结算
分類：`qian-bao`　｜　簽章／認證：`MD5Signature`
**請求 Body**
- `-----------`（型別 `string`，必填） — ----------------------------------------
- `agent`（型別 `string`，必填） — 商户名称
- `loginname`（型別 `string`，必填） — 玩家名称
- `roundid`（型別 `string`，必填） — 游戏局号
- `transid`（型別 `string`，必填） — 投注号 (betid)
- `amount`（型別 `number`，必填） — <p>取消投注 = 投注金额<br>取消结算 = 派彩金额 - 投注金额</p>
- `sign`（型別 `string`，必填） — 签名 (未包含 detail)
- `detail`（型別 `object`，必填） — 其他资讯
**回應**
- `200`：Successful response
### `POST` `/bet`
投注
分類：`qian-bao`　｜　簽章／認證：`MD5Signature`
**請求 Body**
- `-----------`（型別 `string`，必填） — ---------------
- `agent`（型別 `string`，必填） — 商户名称
- `loginname`（型別 `string`，必填） — 玩家名称
- `token`（型別 `string`，必填） — 玩家令牌
- `roundid`（型別 `string`，必填） — 游戏局号
- `transid`（型別 `string`，必填） — 投注号 (betid)
- `amount`（型別 `number`，必填） — 投注金额
- `sign`（型別 `string`，必填） — 签名 (未包含 detail)
- `detail`（型別 `object`，必填） — 其他资讯
**回應**
- `200`：Successful response
### `POST` `/balance`
余额查询
分類：`qian-bao`　｜　簽章／認證：`MD5Signature`
**請求 Body**
- `-----------`（型別 `string`，必填） — --------------------------------------------------------------------
- `agent`（型別 `string`，必填） — 商户名称
- `loginname`（型別 `string`，必填） — 玩家名称
- `token`（型別 `string`，必填） — 玩家令牌
- `sign`（型別 `string`，必填） — 签名([点击查看](/vg-docs/vg-wen-dang/dan-yi-qian-bao/jia-mi-shuo-ming.md))
**回應**
- `200`：Successful response
### `POST` `/vg/sign-in`
登入游戏
分類：`you-xi`　｜　簽章／認證：`MD5Signature`
**回應**
- `200`：Successful response
### `POST` `/vgtransfer/sign-in`
登入游戏
分類：`you-xi`　｜　簽章／認證：`MD5Signature`
**請求 Body**
- `------------`（型別 `string`，必填） — ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
- `agent`（型別 `string`，必填） — 代理名称
- `language`（型別 `string`，必填） — 用户语系([点击查看](/vg-docs/vg-wen-dang/zhuan-zhang-qian-bao/fu-lu/yu-xi-lie-biao.md))
- `loginname`（型別 `string`，必填） — 玩家名称+后缀(suffix)
- `rid`（型別 `string`，必填） — <p>桌号 tableid (<a href="/pages/eKP65RR00NcZ1oYQQOJD">点击查看</a>)。<br>\* <mark style="color:red;">非必要参数，填入桌号可进指定牌桌。</mark> </p>
- `betlimit`（型別 `string`，必填） — <p>限红列表(<a href="https://vg-organization.gitbook.io/vg-docs/vg-wen-dang/dan-yi-qian-bao/api/you-xi/xian-hong-lie-biao#id-200">点击查看</a>)<br>\* <mark style="color:red;">非必要参数，可在登入时设置当前玩家限红。</mark></p>
- `return_url`（型別 `string`，必填） — 重新导向 URL
- `sign`（型別 `string`，必填） — 签名([点击查看](/vg-docs/vg-wen-dang/zhuan-zhang-qian-bao/jia-mi-shuo-ming.md))
**回應**
- `200`：Successful response
### `POST` `/vg/table/list`
牌桌列表
分類：`you-xi`　｜　簽章／認證：`MD5Signature`
**請求 Body**
- `-------`（型別 `string`，必填） — --------------------------------------------------------------------
- `agent`（型別 `string`，必填） — 代理名称
- `sign`（型別 `string`，必填） — 签名[(点击查看](/vg-docs/vg-wen-dang/dan-yi-qian-bao/jia-mi-shuo-ming.md))
**回應**
- `200`：Successful response
### `POST` `/vgtransfer/table/list`
牌桌列表
分類：`you-xi`　｜　簽章／認證：`MD5Signature`
**請求 Body**
- `-------`（型別 `string`，必填） — -------------------------------------------------------------------------
- `agent`（型別 `string`，必填） — 代理名称
- `sign`（型別 `string`，必填） — 签名[(点击查看](/vg-docs/vg-wen-dang/zhuan-zhang-qian-bao/jia-mi-shuo-ming.md))
**回應**
- `200`：Successful response
### `POST` `/vg/bet/limit`
玩家限红
分類：`you-xi`　｜　簽章／認證：`MD5Signature`
**請求 Body**
- `-----------`（型別 `string`，必填） — ------------------------------------------------------------------------------------------
- `agent`（型別 `string`，必填） — 代理名称
- `betlimit`（型別 `string`，必填） — 限红列表([点击查看](/vg-docs/vg-wen-dang/dan-yi-qian-bao/api/you-xi/xian-hong-lie-biao.md#id-200))
- `loginname`（型別 `string`，必填） — 玩家名称
- `sign`（型別 `string`，必填） — 签名[(点击查看](/vg-docs/vg-wen-dang/dan-yi-qian-bao/jia-mi-shuo-ming.md))
**回應**
- `200`：Successful response
### `POST` `/vgtransfer/bet/limit`
玩家限红
分類：`you-xi`　｜　簽章／認證：`MD5Signature`
**請求 Body**
- `-----------`（型別 `string`，必填） — ----------------------------------------------------------------------------------------
- `agent`（型別 `string`，必填） — 代理名称
- `betlimit`（型別 `string`，必填） — 限红列表([点击查看](/vg-docs/vg-wen-dang/zhuan-zhang-qian-bao/api/you-xi/xian-hong-lie-biao.md))
- `loginname`（型別 `string`，必填） — 玩家名称
- `sign`（型別 `string`，必填） — 签名([点击查看](/vg-docs/vg-wen-dang/zhuan-zhang-qian-bao/jia-mi-shuo-ming.md))
**回應**
- `200`：Successful response
### `POST` `/vg/bet/limit/list`
限红列表
分類：`you-xi`　｜　簽章／認證：`MD5Signature`
**請求 Body**
- `-------`（型別 `string`，必填） — --------------------------------------------------------------------
- `agent`（型別 `string`，必填） — 代理名称
- `sign`（型別 `string`，必填） — 签名[(点击查看](/vg-docs/vg-wen-dang/dan-yi-qian-bao/jia-mi-shuo-ming.md))
**回應**
- `200`：Successful response
### `POST` `/vgtransfer/bet/limit/list`
限红列表
分類：`you-xi`　｜　簽章／認證：`MD5Signature`
**請求 Body**
- `-------`（型別 `string`，必填） — -------------------------------------------------------------------------
- `agent`（型別 `string`，必填） — 代理名称
- `sign`（型別 `string`，必填） — 签名([点击查看](/vg-docs/vg-wen-dang/zhuan-zhang-qian-bao/jia-mi-shuo-ming.md))
**回應**
- `200`：Successful response
### `POST` `/vg/bet/users`
游戏结果
分類：`you-xi`　｜　簽章／認證：`MD5Signature`
**請求 Body**
- `-----------`（型別 `string`，必填） — ------
- `agent`（型別 `string`，必填） — string
- `starttime`（型別 `string`，必填）
- `roundid`（型別 `string`，必填） — string
- `betid`（型別 `string`，必填） — string
- `page_num`（型別 `string`，必填） — int
- `page_size`（型別 `string`，必填） — int
- `status`（型別 `string`，必填） — int
- `sign`（型別 `string`，必填） — string
- `参数`（型別 `string`，必填）
- `----------`（型別 `string`，必填）
- `username`（型別 `string`，必填）
- `shoeid`（型別 `string`，必填）
- `shoeround`（型別 `string`，必填）
- `casino`（型別 `string`，必填）
- `valid`（型別 `string`，必填）
- `bet`（型別 `string`，必填）
- `win`（型別 `string`，必填）
- `currency`（型別 `string`，必填）
- `tableidx`（型別 `string`，必填）
- `bettime`（型別 `string`，必填）
- `settletime`（型別 `string`，必填）
- `ip`（型別 `string`，必填）
- `bettype`（型別 `string`，必填）
- `platform`（型別 `string`，必填）
- `betresult`（型別 `string`，必填）
- `detail`（型別 `string`，必填）
**回應**
- `200`：Successful response
### `POST` `/vgtransfer/bet/users`
游戏结果
分類：`you-xi`　｜　簽章／認證：`MD5Signature`
**請求 Body**
- `-----------`（型別 `string`，必填） — ------
- `agent`（型別 `string`，必填） — string
- `starttime`（型別 `string`，必填）
- `roundid`（型別 `string`，必填） — string
- `betid`（型別 `string`，必填） — string
- `page_num`（型別 `string`，必填） — int
- `page_size`（型別 `string`，必填） — int
- `status`（型別 `string`，必填） — int
- `sign`（型別 `string`，必填） — string
- `参数`（型別 `string`，必填）
- `----------`（型別 `string`，必填）
- `username`（型別 `string`，必填）
- `shoeid`（型別 `string`，必填）
- `shoeround`（型別 `string`，必填）
- `casino`（型別 `string`，必填）
- `valid`（型別 `string`，必填）
- `bet`（型別 `string`，必填）
- `win`（型別 `string`，必填）
- `currency`（型別 `string`，必填）
- `tableidx`（型別 `string`，必填）
- `bettime`（型別 `string`，必填）
- `settletime`（型別 `string`，必填）
- `ip`（型別 `string`，必填）
- `bettype`（型別 `string`，必填）
- `platform`（型別 `string`，必填）
- `betresult`（型別 `string`，必填）
- `detail`（型別 `string`，必填）
**回應**
- `200`：Successful response
### `POST` `/vgtransfer/balance`
余额查询
分類：`you-xi`　｜　簽章／認證：`MD5Signature`
**請求 Body**
- `----------`（型別 `string`，必填） — -------------------------------------------------------------------------
- `agent`（型別 `string`，必填） — 代理名称
- `username`（型別 `string`，必填） — 玩家名称
- `sign`（型別 `string`，必填） — 签名([点击查看](/vg-docs/vg-wen-dang/zhuan-zhang-qian-bao/jia-mi-shuo-ming.md))
**回應**
- `200`：Successful response
### `POST` `/vg/sign-up`
注册用户
分類：`you-xi`　｜　簽章／認證：`MD5Signature`
**請求 Body**
- `-----------`（型別 `string`，必填） — ------------------------------------------------------------------------------------------
- `agent`（型別 `string`，必填） — 代理名称
- `betlimit`（型別 `string`，必填） — 限红列表([点击查看](/vg-docs/vg-wen-dang/dan-yi-qian-bao/api/you-xi/xian-hong-lie-biao.md#id-200))
- `loginname`（型別 `string`，必填） — <p>玩家名称+后缀(suffix)<br><mark style="color:red;">仅限小写英文字母、数字</mark></p>
- `sign`（型別 `string`，必填） — 签名[(点击查看](/vg-docs/vg-wen-dang/dan-yi-qian-bao/jia-mi-shuo-ming.md))
**回應**
- `200`：Successful response
### `POST` `/vgtransfer/sign-up`
注册用户
分類：`you-xi`　｜　簽章／認證：`MD5Signature`
**請求 Body**
- `-----------`（型別 `string`，必填） — ----------------------------------------------------------------------------------------
- `agent`（型別 `string`，必填） — 代理名称
- `betlimit`（型別 `string`，必填） — 限红列表([点击查看](/vg-docs/vg-wen-dang/zhuan-zhang-qian-bao/api/you-xi/xian-hong-lie-biao.md))
- `loginname`（型別 `string`，必填） — <p>玩家名称+后缀(suffix)<br><mark style="color:red;">仅限小写英文字母、数字</mark></p>
- `sign`（型別 `string`，必填） — 签名([点击查看](/vg-docs/vg-wen-dang/zhuan-zhang-qian-bao/jia-mi-shuo-ming.md))
**回應**
- `200`：Successful response
### `POST` `/vgtransfer/points`
转账功能
分類：`you-xi`　｜　簽章／認證：`MD5Signature`
**請求 Body**
- `-----------`（型別 `string`，必填） — ----------------------------------------------------------------------------------
- `agent`（型別 `string`，必填） — 代理名称
- `loginname`（型別 `string`，必填） — 玩家名称
- `amount`（型別 `number`，必填） — 转账金额
- `sid`（型別 `string`，必填） — <p>商户产值<br>( 商户转账唯一订单号<mark style="color:red;"><strong>12位以上</strong></mark> )</p>
- `status`（型別 `string`，必填） — <p>in = 转进<br>out = 转出 </p>
- `sign`（型別 `string`，必填） — 签名([点击查看](/vg-docs/vg-wen-dang/zhuan-zhang-qian-bao/jia-mi-shuo-ming.md))
**回應**
- `200`：Successful response
### `POST` `/vgtransfer/log`
转账记录
分類：`you-xi`　｜　簽章／認證：`MD5Signature`
**請求 Body**
- `-----------`（型別 `string`，必填） — --------------------------------------------------------------------------------------------------
- `agent`（型別 `string`，必填） — 代理名称
- `starttime`（型別 `string`，必填） — UTC+8, 'YYYY-MM-DD HH:mm:ss'
- `endtime`（型別 `string`，必填） — UTC+8, 'YYYY-MM-DD HH:mm:ss'
- `page_num`（型別 `number`，必填） — 页数
- `page_size`（型別 `number`，必填） — <p>每页笔数<br>max: 2000</p>
- `status`（型別 `string`，必填） — <p>in = 转进<br>out = 转出 <br><mark style="color:red;"><strong>若不带此参数默认将回应所有状态纪录。</strong></mark></p>
- `sid`（型別 `string`，必填） — <p>转账单号<br><mark style="color:red;"><strong>若不带此参数默认将回应所有订单纪录。</strong></mark></p>
- `sign`（型別 `string`，必填） — 签名([点击查看](/vg-docs/vg-wen-dang/zhuan-zhang-qian-bao/jia-mi-shuo-ming.md))
- `参数`（型別 `string`，必填）
- `------------`（型別 `string`，必填）
- `username`（型別 `string`，必填）
- `type`（型別 `string`，必填）
- `amount`（型別 `string`，必填）
- `beforeamount`（型別 `string`，必填）
- `afteramount`（型別 `string`，必填）
- `busid`（型別 `string`，必填）
- `anyid`（型別 `string`，必填）
- `ip`（型別 `string`，必填）
- `createtime`（型別 `string`，必填）
**回應**
- `200`：Successful response

## Request／Response 範例

**POST /resettle — Response Example**
```json
{
  "code": 0
}
```
**POST /win — Request Example**
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
**POST /win — Response Example**
```json
{
  "code": 0,
  "balance": 123456.78
}
```
**POST /cancel — Request Example**
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
**POST /cancel — Response Example**
```json
{
  "code": 0,
  "balance": 123456.78
}
```
**POST /bet — Request Example**
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
**POST /bet — Response Example**
```json
{
  "code": 0,
  "balance": 123456.78
}
```
**POST /balance — Response Example**
```json
{
  "code": 0,
  "balance": 123456.78
}
```
**POST /vg/sign-in — Response Example**
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
**POST /vgtransfer/sign-in — Response Example**
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
**POST /vg/table/list — Response Example**
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
**POST /vgtransfer/table/list — Response Example**
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
**POST /vg/bet/limit — Response Example**
```json
{
  "code": 1000,
  "message": "Success",
  "TraceId": "76ce3739-42bc-4fe3-9bdf-1433d376b73a"
}
```
**POST /vgtransfer/bet/limit — Response Example**
```json
{
  "code": 1000,
  "message": "Success",
  "TraceId": "76ce3739-42bc-4fe3-9bdf-1433d376b73a"
}
```
**POST /vg/bet/limit/list — Response Example**
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
**POST /vgtransfer/bet/limit/list — Response Example**
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
**POST /vg/bet/users — Response Example**
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
**POST /vgtransfer/bet/users — Response Example**
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
**POST /vgtransfer/balance — Response Example**
```json
{
  "code": 1000,
  "message": "Success",
  "balance": "1000.00",
  "TraceId": "ee7db471-4374-416c-9490-269ba29d1cda"
}
```
**POST /vg/sign-up — Response Example**
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
**POST /vgtransfer/sign-up — Response Example**
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
**POST /vgtransfer/points — Response Example**
```json
{
  "code": 1000,
  "message": "Success",
  "balance": "1000.00",
  "TraceId": "ee7db471-4374-416c-9490-269ba29d1cda"
}
```
**POST /vgtransfer/log — Response Example**
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

## 錯誤碼

_來源未提供此項資訊。_

## 限制與注意事項

_來源未提供此項資訊。_

## 已知缺漏與來源衝突


```json
{"missing": []}
```

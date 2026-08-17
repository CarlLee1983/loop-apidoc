
















































































































































































## 3-2 發送請求

### 1. 請求內文 需為“Msg=傳送的參數(JSON 格式)進行 DES-CBC 加密後的結果”

### 2. 標頭 需有以下 3 項

| 標頭 | 內容 |
| --- | --- |
| X-API-ClientID | 系統提供的 Client ID |
| X-API-Signature | MD5(Client ID+Client Secret+Timestamp+參數加密後的結果) |
| X-API-Timestamp | 當下的 unix timesamp |

### 3. 對欲進行操作的 URL 做 POST 請求

### 4. 常見問題

1. 請求內文 (Request Body) 未加上Msg= ❌ 請求內文 (Request Body) 只有加密後的結果，但未加上Msg= xkf7wEkQvp+LJTravXHY9RDEX24YMjQxnV/5DPCoIKE= ✅ 請求內文 (Request Body) 一定要加上Msg= Msg=xkf7wEkQvp+LJTravXHY9RDEX24YMjQxnV/5DPCoIKE=
2. 請求內文 (Request Body) 使用雙引號 ❌ 請求內文 (Request Body) 使用了雙引號 Msg="xkf7wEkQvp+LJTravXHY9RDEX24YMjQxnV/5DPCoIKE=" ✅ 請求內文 (Request Body) 不需要加上雙引號 Msg=xkf7wEkQvp+LJTravXHY9RDEX24YMjQxnV/5DPCoIKE=
3. 回覆內文 (Response Body) 加上Msg= ❌ 回覆內文 (Response Body) 加上Msg= Msg=xkf7wEkQvp+LJTravXHY9RDEX24YMjQxnV/5DPCoIKE= ✅ 回覆內文 (Response Body) 不需要加上Msg= xkf7wEkQvp+LJTravXHY9RDEX24YMjQxnV/5DPCoIKE=
4. 請求參數的數字型別 (ex. int, decimal) 參數內容誤用雙引號 以 [5-2](#5-api-5-2) 的 API 參數 Balance 為例 ❌ 請求參數的數字型別 (ex. int, decimal) 參數內容誤用雙引號 { "Balance":"100000.05" } ✅ 請求參數的數字型別 (ex. int, decimal) 參數內容不使用雙引號 { "Balance":100000.05 }







































































































































































## 4-1 請求 URL

| 名稱 | 內容 |
| --- | --- |
| URL | http://<server>/<API 名稱> |
| 方法 | POST |

















## 4-4 回傳資訊說明

```
成功時

{
    "ErrorCode":0,
    "ErrorMessage":"OK",
    "Timestamp":1584512886,
    "Data":
    {
    "SystemCode":" TestSystem",
    "WebId":"Uy2m48TRCUo",
    "UserId":"497OHx21A0gInxza7zJj"
    }
}

失敗時
{
    "ErrorCode":2001,
    "ErrorMessage":"Illegal arguments.",
    "Timestamp":1584512886,
    "Data":null
}
```

各 API 不論執行成功或失敗，皆會以 UTF-8 編碼的 JSON 格式經 DES 加密後回傳，且內容包 含下列資訊(Data 中的 JSON 格式資訊請參閱「[5. 遊戲系統 API 說明](#5-api)」)。

| 名稱 | 型別 | 描述 |
| --- | --- | --- |
| ErrorCode | Int | 錯誤代碼，詳細請參考 [8-1](#8-8-1) 錯誤代碼表 |
| ErrorMessage | String | 錯誤訊息，詳細請參考 [8-1](#8-8-1) 錯誤代碼表 |
| Timestamp | Long | 時間戳記 |
| Data | Object | API 呼叫回傳的 JSON 格式的 object / object array |

範例(此範例為明碼) /WithBalance/Player/CreatePlayer 回傳資訊如下表

| 名稱 | 型別 | 描述 |
| --- | --- | --- |
| Data | Object |  |
| Data/SystemCode | String | 系統代碼 |
| Data/WebId | String | 站台代碼 |
| Data/UserId | String | 會員的唯一識別碼 |

成功與失敗的 json 格式如右(點選json選單)











## 5-1 建立會員(幣別帳戶)

### API 名稱：WithBalance/Player/CreatePlayer

- 傳入參數說明

| 名稱 | 型別 | 長度 | 必要 | 描述 |
| --- | --- | --- | --- | --- |
| SystemCode | String | 2~20 | Y | 系統代碼(只限英數) |
| WebId | String | 3~20 | Y | 站台代碼(只限英數) |
| UserId | String | 3~20 | Y | 會員惟一識別碼(只限英數) |
| Currency | String | 2~5 | Y | 幣別代碼(請參照[代碼表](#b)) |

- 回傳資訊說明

- 特定回傳錯訊代碼一覽

| 錯誤代碼 | 錯誤訊息 | 描述 |
| --- | --- | --- |
| 3010 | The player's currency already exists. | 此玩家帳戶已存在 |
| 3011 | Deny permission for system. | 系統商權限不足 |
| 3018 | This currency is not allowed. | 此幣別不被允許 |

補充說明：WebId 請依描述的規則自訂站台代碼 (不需在後台先新增)

## 5-2 存入點數

### API 名稱：WithBalance/Player/Deposit

- 傳入參數說明

| 名稱 | 型別 | 長度 | 必要 | 描述 |
| --- | --- | --- | --- | --- |
| SystemCode | String | 2~20 | Y | 系統代碼(只限英數) |
| WebId | String | 3~20 | Y | 站台代碼(只限英數) |
| UserId | String | 3~20 | Y | 會員惟一識別碼(只限英數) |
| TransactionID | String | 8~20 | Y | 交易惟一識別碼(只限英數) |
| Currency | String | 2~5 | Y | 幣別代碼(請參照[代碼表](#b)) |
| Balance | Decimal |  | Y | 存入點數(小數點兩位) (範圍0.01~9999999999.99) |

- 回傳資訊說明

| 名稱 | 型別 | 描述 |
| --- | --- | --- |
| Data | Object |  |
| Data/TransactionID | String | 交易惟一識別碼 |
| Data/TransactionTime | String | yyyy-MM-dd HH:mm:ss |
| Data/UserId | String | 會員惟一識別碼 |
| Data/PointID | String | 點數交易序號 |
| Data/Balance | Decimal | 存入點數 |
| Data/CurrentPlayerBalance | Decimal | 會員當前點數 |

- 特定回傳錯訊代碼一覽

| 錯誤代碼 | 錯誤訊息 | 描述 |
| --- | --- | --- |
| 3008 | The player's currency doesn't exist. | 此玩家帳戶不存在 |
| 3011 | Deny permission for system. | 系統商權限不足 |
| 3014 | Duplicate TransactionID. | 重複的TransactionID |
| 3018 | This currency is not allowed. | 此幣別不被允許 |
| 3020 | Deny deposit and withdraw for player. | 玩家禁止轉入轉出 |

補充說明： TransactionID請依描述的規則自訂此識別碼

## 5-3 取出點數

### API 名稱：WithBalance/Player/Withdraw

- 傳入參數說明

| 名稱 | 型別 | 長度 | 必要 | 描述 |
| --- | --- | --- | --- | --- |
| SystemCode | String | 2~20 | Y | 系統代碼(只限英數) |
| WebId | String | 3~20 | Y | 站台代碼(只限英數) |
| UserId | String | 3~20 | Y | 會員惟一識別碼(只限英數) |
| TransactionID | String | 8~20 | Y | 交易惟一識別碼(只限英數) |
| Currency | String | 2~5 | Y | 幣別代碼(請參照[代碼表](#b)) |
| Balance | Decimal |  | Y | 取出點數(小數點兩位) (範圍0.01~9999999999.99) |

- 回傳資訊說明

| 名稱 | 型別 | 描述 |
| --- | --- | --- |
| Data | Object |  |
| Data/TransactionID | String | 交易惟一識別碼 |
| Data/TransactionTime | String | yyyy-MM-dd HH:mm:ss |
| Data/UserId | String | 會員惟一識別碼 |
| Data/PointID | String | 點數交易序號 |
| Data/Balance | Decimal | 取出點數 |
| Data/CurrentPlayerBalance | Decimal | 會員當前點數 |

- 特定回傳錯訊代碼一覽

| 錯誤代碼 | 錯誤訊息 | 描述 |
| --- | --- | --- |
| 3005 | Balance is not enough. | 餘額不足 |
| 3008 | The player's currency doesn't exist. | 此玩家帳戶不存在 |
| 3011 | Deny permission for system. | 系統商權限不足 |
| 3014 | Duplicate TransactionID. | 重複的TransactionID |
| 3016 | Deny withdraw, player is in gaming. | 拒絕提點，玩家正在遊戲中 |
| 3018 | This currency is not allowed. | 此幣別不被允許 |
| 3020 | Deny deposit and withdraw for player. | 玩家禁止轉入轉出 |

## 5-4 查詢點數

### API 名稱：WithBalance/Player/GetBalance

- 傳入參數說明

- 回傳資訊說明

| 名稱 | 型別 | 描述 |
| --- | --- | --- |
| Data | Object |  |
| Data/UserId | String | 會員惟一識別碼 |
| Data/CurrentPlayerBalance | Decimal | 會員當前點數 |

- 特定回傳錯訊代碼一覽

| 錯誤代碼 | 錯誤訊息 | 描述 |
| --- | --- | --- |
| 3008 | The player's currency doesn't exist. | 此玩家帳戶不存在 |
| 3011 | Deny permission for system. | 系統商權限不足 |

## 5-5 查詢點數交易結果

### API 名稱：WithBalance/Player/GetTransactionResult

- 傳入參數說明

| 名稱 | 型別 | 長度 | 必要 | 描述 |
| --- | --- | --- | --- | --- |
| SystemCode | String | 2~20 | Y | 系統代碼(只限英數) |
| TransactionID | String | 8~20 | Y | 交易惟一識別碼(只限英數) |

- 回傳資訊說明

| 名稱 | 型別 | 描述 |
| --- | --- | --- |
| Data | Object |  |
| Data/TransactionID | String | 交易惟一識別碼 |
| Data/TransactionTime | String | yyyy-MM-dd HH:mm:ss |
| Data/WebId | String | 站台代碼 |
| Data/UserId | String | 會員惟一識別碼 |
| Data/PointID | String | 點數交易序號 |
| Data/Currency | String | 幣別代碼(請參照[代碼表](#b)) |
| Data/Action | Int | 1.存點 2.取點 |
| Data/Balance | Decimal | 交易點數 |
| Data/AfterBalance | Decimal | 交易後點數 |

- 特定回傳錯訊代碼一覽

| 錯誤代碼 | 錯誤訊息 | 描述 |
| --- | --- | --- |
| 3006 | Transaction is not found. | 找不到交易結果 |
| 3011 | Deny permission for system. | 系統商權限不足 |

## 5-6 查詢點數交易歷程

### API 名稱：WithBalance/Player/GetTransactionHistory

- 傳入參數說明

| 名稱 | 型別 | 長度 | 必要 | 描述 |
| --- | --- | --- | --- | --- |
| SystemCode | String | 2~20 | Y | 系統代碼(只限英數) |
| WebId | String | 3~20 | Y | 站台代碼(只限英數) |
| UserId | String | 3~20 | Y | 會員惟一識別碼(只限英數) |
| Currency | String | 2~5 | Y | 幣別代碼(請參照[代碼表](#b)) |
| DateStart | String | 10 | Y | 查詢開始日期(yyyy-MM-dd) |
| DateEnd | String | 10 | Y | 查詢結束日期(yyyy-MM-dd) |

- 回傳資訊說明

| 名稱 | 型別 | 描述 |
| --- | --- | --- |
| Data | Object |  |
| Data/TranHistory | Array |  |
| Data/TranHistory/TransactionID | String | 交易惟一識別碼 |
| Data/TranHistory/TransactionTime | String | yyyy-MM-dd HH:mm:ss |
| Data/TranHistory/PointID | String | 點數交易序號 |
| Data/TranHistory/Action | Int | 1.存點 2.取點 |
| Data/TranHistory/Balance | Decimal | 交易點數 |
| Data/TranHistory/AfterBalance | Decimal | 交易後點數 |

- 特定回傳錯訊代碼一覽

| 錯誤代碼 | 錯誤訊息 | 描述 |
| --- | --- | --- |
| 3008 | The player's currency doesn't exist. | 此玩家帳戶不存在 |
| 3011 | Deny permission for system. | 系統商權限不足 |
| 3015 | Time is not in the allowed range. | 時間不在允許的範圍內 |

補充說明 :

1. 查詢日期為 2020-04-24，取得的數據範圍為 2020-04-24 12:00:00 至 2020-04-25 11:59:59
2. 可以查詢的範圍為 180 天內。

## 5-7 取得遊戲網址(進入遊戲)

### API 名稱：WithBalance/Player/GetURLToken

- 傳入參數說明

| 名稱 | 型別 | 長度 | 必要 | 描述 |
| --- | --- | --- | --- | --- |
| SystemCode | String | 2~20 | Y | 系統代碼(只限英數) |
| WebId | String | 3~20 | Y | 站台代碼(只限英數) |
| UserId | String | 3~20 | Y | 會員惟一識別碼(只限英數) |
| UserName | String | 1~20 | Y | 會員暱稱 |
| GameId | Int |  | Y | 遊戲代碼(請參照[代碼表](#a-1)) |
| Currency | String | 2~5 | Y | 幣別代碼(請參照[代碼表](#b)) |
| Language | String | 5~10 | Y | 語系代碼(請參照[代碼表](#c)) |
| ExitAction | String | 0~255 | Y | 離開遊戲時導向特定網址 |
| MinBetAmount | Decimal |  | N | 最小下注金額(小數點兩位) (範圍0.00~9999999999.99) |
| MaxBetAmount | Decimal |  | N | 最大下注金額(小數點兩位) (範圍0.00~9999999999.99) |

- 回傳資訊說明

| 名稱 | 型別 | 描述 |
| --- | --- | --- |
| Data | Object |  |
| Data/URL | String | 進入遊戲的網址 |

- 特定回傳錯訊代碼一覽

| 錯誤代碼 | 錯誤訊息 | 描述 |
| --- | --- | --- |
| 3008 | The player's currency doesn't exist. | 此玩家帳戶不存在 |
| 3011 | Deny permission for system. | 系統商權限不足 |
| 3012 | Deny permission for game. | 遊戲權限不足 |
| 3018 | This currency is not allowed. | 此幣別不被允許 |

補充說明：

1. ExitAction 帶空字串 ( ExitAction=”” ) 時，離開遊戲時將關閉視窗
2. [投注參考文件](https://docs.google.com/spreadsheets/d/1NMR6rL5pp7ctXVVX4W5BzWOT98ApGbmW/edit?gid=698558515#gid=698558515)

## 5-8 取得遊戲中的會員

### API 名稱：WithBalance/Player/PlayerOnlineList

- 傳入參數說明

| 名稱 | 型別 | 長度 | 必要 | 描述 |
| --- | --- | --- | --- | --- |
| SystemCode | String | 2~20 | Y | 系統代碼(只限英數) |
| WebId | String | 3~20 | Y | 站台代碼(只限英數) |
| GameId | Int |  | Y | 遊戲代碼(請參照[代碼表](#a-1)) |
| Page | Int |  | Y | 指定目前頁數(從1開始) |
| Rows | Int |  | Y | 每頁筆數(範圍：100~500) |

- 回傳資訊說明

| 名稱 | 型別 | 描述 |
| --- | --- | --- |
| Data | Object |  |
| Data/DataCount | Int | 總筆數 |
| Data/PageSize | Int | 每頁筆數 |
| Data/PageCount | Int | 總頁數 |
| Data/PageNow | Int | 目前頁數 |
| Data/UserList | Array |  |
| Data/UserList/WebId | String | 站台代碼 |
| Data/UserList/UserId | String | 會員惟一識別碼 |
| Data/UserList/GameId | Int | 遊戲代碼(請參照[代碼表](#a-1)) |

- 特定回傳錯訊代碼一覽

| 錯誤代碼 | 錯誤訊息 | 描述 |
| --- | --- | --- |
| 3011 | Deny permission for system. | 系統商權限不足 |
| 3012 | Deny permission for game. | 遊戲權限不足 |

## 5-9 剔除遊戲中的會員

### API 名稱：WithBalance/Player/Kickout

- 傳入參數說明

| 名稱 | 型別 | 長度 | 必要 | 描述 |
| --- | --- | --- | --- | --- |
| KickType | Int |  | Y | 剔除模式，有下列4種 1:System, 2:Web, 3:Game, 4:Player |
| SystemCode | String | 2~20 | Y | 系統代碼(只限英數) |
| WebId | String | 0~20 | Y | 站台代碼(只限英數) |
| UserId | String | 0~20 | Y | 會員惟一識別碼(只限英數) |
| GameId | Int |  | Y | 若KickType 不為3，則填0 |

- 回傳資訊說明

| 名稱 | 型別 | 描述 |
| --- | --- | --- |
| Data | Object |  |
| Data/UserCount | Int | 被剔除的會員數量 |

- 特定回傳錯訊代碼一覽

當 KickType=1，會剔除系統下所有人，KickType=2，會剔除站台下所有人

，KickType=3，會剔除正在該遊戲的所有人，KickType=4，會剔除特定會員

當 KickType=1，WebId、UserId 請填空字串，GameId 請填 0

，KickType=2，UserId 請填空字串，GameId請填 0

，KickType=3，WebId、UserId 請填空字串

，KickType=4，GameId 請填 0

此API會回傳符合剔除條件的會員數量，符合條件者將於數秒內被剔除系統

## 5-10 取得點數不為0的會員帳戶資訊(已離開遊戲)

### API 名稱：WithBalance/Player/GetUnwithdrawn

- 此API已不再支持

## 5-11 取得遊戲列表

### API 名稱：WithBalance/Game/GameList

- 傳入參數說明

| 名稱 | 型別 | 長度 | 必要 | 描述 |
| --- | --- | --- | --- | --- |
| SystemCode | String | 2~20 | Y | 系統代碼(只限英數) |

- 回傳資訊說明

| 名稱 | 型別 | 描述 |
| --- | --- | --- |
| Data | Object |  |
| Data/GameList | Array |  |
| Data/GameList/GameId | Int | 遊戲代碼(請參照[代碼表](#a-1)) |
| Data/GameList/GameType | Int | 遊戲類型(1:老虎機 2:捕魚機) |
| Data/GameList/GameName | Object |  |
| Data/GameList/GameName/en_US | String | 遊戲名稱(英文) |
| Data/GameList/GameName/zh_TW | String | 遊戲名稱(繁體中文) |
| Data/GameList/GameName/zh_CN | String | 遊戲名稱(簡體中文) |
| Data/GameList/GameName/th_TH | String | 遊戲名稱(泰文) |
| Data/GameList/GameName/ko_KR | String | 遊戲名稱(韓文) |
| Data/GameList/GameName/ja_JP | String | 遊戲名稱(日文) |
| Data/GameList/GameName/en_MY | String | 遊戲名稱(緬甸文) |
| Data/GameList/GameName/id_ID | String | 遊戲名稱(印尼文) |
| Data/GameList/RollerSpec | String | 滾輪規格 |
| Data/GameList/LineType | String | 連線類型 |
| Data/GameList/LineNumber | String | 連線數 |
| Data/GameList/GameStatus | Int | 遊戲狀態(1:正常 2:維護) |
| Data/GameList/GamePicUrl | String | 遊戲圖片網址(改由其它方式提供) |
| Data/GameList/GameResUrl | String | 遊戲資源網址(改由其它方式提供) |

- 特定回傳錯訊代碼一覽

| 錯誤代碼 | 錯誤訊息 | 描述 |
| --- | --- | --- |
| 3011 | Deny permission for system. | 系統商權限不足 |

輸出清單排序將會按照上架遊戲時間由最新排序至最舊

## 5-12 取得遊戲詳細資訊

### API 名稱：WithBalance/History/GetGameDetail

- 傳入參數說明

| 名稱 | 型別 | 長度 | 必要 | 描述 |
| --- | --- | --- | --- | --- |
| SystemCode | String | 2~20 | Y | 系統代碼(只限英數) |
| WebId | String | 0~20 | Y | 站台代碼(只限英數) |
| GameType | Int |  | Y | 遊戲類型(1.老虎機 2.捕魚機) |
| TimeStart | String | 16 | Y | 開始時間(yyyy-MM-dd HH:mm) |
| TimeEnd | String | 16 | Y | 結束時間(yyyy-MM-dd HH:mm) |

- 回傳資訊說明

| 名稱 | 型別 | 描述 |
| --- | --- | --- |
| Data | Object |  |
| Data/GameDetail | Array |  |
| Data/GameDetail/Currency | String | 幣別代碼(請參照[代碼表](#b)) |
| Data/GameDetail/WebId | String | 站台代碼 |
| Data/GameDetail/UserId | String | 會員惟一識別碼 |
| Data/GameDetail/SequenNumber | Long | 遊戲紀錄惟一編號 |
| Data/GameDetail/GameId | Int | 遊戲代碼(請參照[代碼表](#a-1)) |
| Data/GameDetail/SubGameType | Int | 子遊戲代碼(請參照[代碼表](#a-2)) |
| Data/GameDetail/BetAmt | Decimal | 下注(小數點兩位) |
| Data/GameDetail/WinAmt | Decimal | 贏分(小數點兩位) |
| Data/GameDetail/PlayTime | String | 遊戲時間 |
| Data/GameDetail/JackpotContribution | Decimal | Jackpot貢獻值(小數點五位) |
| Data/GameDetail/BelongSequenNumber | Long | 遊戲紀錄主編號 |

- 特定回傳錯訊代碼一覽

| 錯誤代碼 | 錯誤訊息 | 描述 |
| --- | --- | --- |
| 3011 | Deny permission for system. | 系統商權限不足 |
| 3015 | Time is not in the allowed range. | 時間不在允許的範圍內 |

1. [捕魚機由於數據量較多，請參考 7-2 的說明](#7-api-7-2)
2. SubGameType ，SequenNumber 和 BelongSequenNumber的關係 SubGameType 子遊戲代碼 (0，3000為付費spin) SequenNumber 遊戲紀錄惟一編號 BelongSequenNumber 遊戲紀錄主編號 同一次付費spin產生出來的紀錄，會有相同的 BelongSequenNumber，不同的 SequenNumber 譬如以下： SequenNumber BelongSequenNumber SubGameType BetAmt WinAmt 1660005 1660005 0 10 10 1660007 1660005 7 0 20 1660011 1660005 7 0 0
3. 可以查詢的範圍為目前時間的３分鐘前，最多可以查詢到目前時間往前 72 小時內。 譬如目前是 2020-04-24 16:30，只能查詢 2020-04-24 16:26 ～ 2020-04-21 16:31
4. WebId 有填值將只回傳該 WebId 底下的資料
5. WebId 為空字串時，將回傳該系統所有資料
6. 每次查詢最多 5 分鐘，譬如 TimeStart = 2020-04-24 16:22，TimeEnd = 2020-04-24 16:26，將取得 2020-04-24 16:22:00 ~

2020-04-24 16:26:59 這 5 分鐘內的資料




















































































































































































































































































































































































































































# 6. FTP 功能

## 6-1 功能說明

### FTP 方式依提供以下三種資料

1. 遊戲詳細交易信息
2. 遊戲每分鐘統計資訊
3. 遊戲每日統計資訊

## 6-2 目錄說明

FTP 內的目錄第一層會先以資料分類與遊戲分類做區分，

第二層會以日期來區分，譬如：20200325，20200326，

每日統計資訊無第二層目錄。

目錄範例：

1. 遊戲詳細交易信息：history_fish / 20200325
2. 遊戲每分鐘統計資訊：report_min_slot / 20200326
3. 遊戲每日統計資訊：report_daily

## 6-3 壓縮檔名說明

### 遊戲詳細交易信息 和 遊戲每分鐘統計資訊 的壓縮檔名

由資料分類、遊戲分類、系統代碼、起始時間、結束時間所組成

檔名範例：

report_min_slot_TestSystem_202003251710_202003251719.zip

該壓縮檔內的資料時間範圍：2020-03-25 17:10:00 ~ 17:19:59

裡面會有最多 10 分鐘內的檔案

每日統計資訊 的壓縮檔名

由資料分類、系統代碼、日期所組成

report_daily_TestSystem_20200325.zip

## 6-4 檔名說明

### 遊戲詳細交易信息 和 遊戲每分鐘統計資訊 的檔名

檔案會依照資料分類、遊戲分類、系統代碼、站台代碼、每分鐘

組成一個 CSV 檔

report_min_slot_TestSystem_web4_20200325_1712.csv

該 CSV 檔內的資料時間範圍：2020-03-25 17:12:00 ~ 17:12:59

### 每日統計資訊的檔名

檔案會依照資料分類、遊戲分類、系統代碼、站台代碼、日期

report_min_slot_TestSystem_web4_20200325.csv

## 6-5 欄位說明

1. 遊戲詳細交易信息：請參照 [5-12](#5-api-5-12) 取得遊戲詳細資訊
2. 遊戲每分鐘統計資訊：請參照 [5-13](#5-api-5-13) 取得遊戲每分鐘統計資訊
3. 遊戲每日統計資訊：請參照 [5-14](#5-api-5-14) 取得遊戲每日統計資訊

















# 8. 錯誤代碼

## 8-1 錯誤代碼表

| 代碼類別 | 描述 |
| --- | --- |
| 0 | 正常 |
| 1xxx | 系統有誤或是維護中 |
| 2xxx | 參數輸入驗證有誤 |
| 3xxx | 邏輯判斷後有誤 |

| 錯誤代碼 | 錯誤訊息 | 描述 |
| --- | --- | --- |
| 0 | OK | 正常 |
| 1001 | Execute failed. | 執行失敗 |
| 1002 | System is in maintenance. | 系統維護中 |
| 2001 | Illegal arguments. | 無效的參數 |
| 2002 | Invalid decrypt. | 解密失敗 |
| 3005 | Balance is not enough. | 餘額不足 |
| 3006 | Transaction is not found. | 找不到交易結果 |
| 3008 | The player's currency doesn't exist. | 此玩家帳戶不存在 |
| 3010 | The player's currency already exists | 此玩家帳戶已存在 |
| 3011 | Deny permission for system. | 系統商權限不足 |
| 3012 | Deny permission for game. | 遊戲權限不足 |
| 3014 | Duplicate TransactionID. | 重複的 TransactionID |
| 3015 | Time is not in the allowed range. | 時間不在允許的範圍內 |
| 3016 | Deny withdraw, player is in gaming. | 拒絕提點，玩家正在遊戲中 |
| 3018 | This currency is not allowed. | 此幣別不被允許 |
| 3020 | Deny deposit and withdraw for player. | 玩家禁止轉入轉出 |

## 8-2 會得到錯誤代碼 2002 的 3 種情況：

1. 加密錯誤
2. POST 資料時，未在 body 以 Msg=xxxxx 的方式傳送
3. X-API-Timestamp 時間有誤，傳入的 Timestamp 超過現在時間 30 秒以上的呼叫

## 8-3 會得到錯誤代碼 2001 的常見情況：

1. 數值型態 ( Int，Long，Decimal ) 的參數，在傳送時請移除雙引號 錯誤 => {"GameId": "36"}，正確 => {"GameId": 36}
2. 時間參數，請注意 API 參數的 長度 以及 描述，總計有以下 3 種 yyyy-MM-dd HH:mm yyyy-MM-dd HH yyyy-MM-dd














































































































































































































































































































































































































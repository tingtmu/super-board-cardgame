# super-board 自主軟體工廠實測紀錄

專案:回合制卡牌 Roguelike 技能引擎(純邏輯、資料驅動)。
目的:用 super-board 從頭到尾跑一次,理解它如何像「自主軟體工廠」一樣運作。
日期:2026-11-17。模型層級:自訂 `haiku`(所有 lane 皆用 haiku)。

## 1. 一句話總結

人只負責「定義需求(票)」與「少數需要人決定的關卡」;其餘的建置、測試、審查、合併,由
GitHub Project 看板驅動、由 dynamic workflow 派出的子 agent 自己完成。看板的欄位就是工廠的流水線。

## 2. 工廠的組成

| 元件 | 角色 |
|---|---|
| GitHub Project 看板 | 唯一的狀態來源。Backlog → Ready → Building → QA → Review → Blocked → Done |
| Issue(票) | 工作單。含 Problem / Context / Fix / 驗收條件(AC) / Risk / Blocked by |
| 協調者(orchestrator) | 本 session。只負責規劃波次、認領、派工、對帳、回報;**不寫產品程式** |
| dynamic workflow | 每一「波」啟動一次,內部為每張卡派出 Build → QA → Review 子 agent |
| Build / QA / Review 三條 lane | 各自獨立 agent,各用自己的 git worktree 與分支 |
| merge gate | 唯一合法的合併路徑:先在目前 staging 上重跑驗證,通過才合併 |
| 安全護欄 | hooks(禁止直推 main/staging、禁止碰密鑰)、合併政策(大 PR、金流、驗證、schema 需人工) |

## 3. 我們這次做了什麼(時間順序)

### 3.1 設定(`/super-board onboard`,8 步)

1. 檢查:補裝缺少的 helper skills(`verification-before-completion`、`testing-strategy`,僅專案層級)。
2. GitHub:確認登入與 scope,決定不用第二個機器人帳號。
3. 看板:建立 Project #1,補齊七個欄位與 `qa` / `bug` / `feature` 三個標籤。
4. 分支:建立 `staging`,所有成品先合併到這裡,不直接動 `main`。
5. AGENTS.md:只加入 super-board 區塊,`CLAUDE.md` 改為匯入 `@AGENTS.md`。
6. 政策:一般變更機器人可自動合併;金流 / 登入 / schema 一律等人;開啟「禁止直推 main」護欄。
7. Bug 來源:只勾 GitHub issues。
8. 寫入:設定檔、`.gitignore`、`settings.json` 權限、文件。

### 3.2 把需求變成票

把 `spec.md` 的四個里程碑拆成四張 issue,每張都有可檢查的驗收條件,並用 `Blocked by` 串成依賴鏈:

`#1 資料結構 → #2 回合流程 → #3 狀態效果 → #4 敵人 AI`

四張全部放進 `Ready`。

### 3.3 跑波次(wave)

每一波都是同一個迴圈:

1. **速率檢查**:GitHub API 額度與用量。
2. **規劃**:`wave-plan` 依依賴圖算出「現在哪些卡是自由的」。
3. **認領**:給 issue 指派機器人身分,並重新讀取確認沒有被搶走(這就是互斥鎖)。
4. **啟動 workflow**:對每張卡跑 Build → QA → Review。
5. **對帳**:釋放認領、寫入執行紀錄、檢查是否觸發 GitHub 限流。
6. **回報**:一段簡短摘要,點出需要人處理的卡。

| 波次 | 卡片 | 結果 | PR | 測試數 |
|---|---|---|---|---|
| 1 | #1 資料結構 + 3 張範例卡 | 自動合併、Done | #6 | 14 |
| 2 | #2 回合流程 | **卡在人工關卡**:PR 454 行,超過 400 行自動合併上限 | #7 | 35 |
| (人工) | #2 | 人決定放行並把上限調到 600,經 merge gate 合併 | #7 | 35 |
| 3 | #3 狀態效果 | 自動合併、Done | #8 | 48 |
| 4 | #4 敵人 AI | 自動合併、Done | #9 | 67 |

最後看板排空:#1~#4 全為 Done,規劃器回傳沒有可跑的卡。

## 4. 每張卡內部發生什麼(三條 lane)

- **Build**:在專屬 worktree 與分支上,先寫測試再實作(TDD),開 draft PR,卡片移到 QA。
- **QA**:另一個 agent 重跑測試、逐條對照驗收條件、留下證據(`docs/super-board/runs/issue-*-qa-v1/`),通過才移到 Review。
- **Review**:再一個 agent 獨立判讀 diff,通過後**只能**透過 merge gate 合併,並綁定「它審過的那個 commit」。
- 失敗會退回上一個階段;反覆失敗會進 `Blocked`。

重點:Build、QA、Review 是不同的 agent,沒有人會審自己剛寫的東西(但見第 6 節的限制)。

## 5. 人在哪裡介入

| 時機 | 原因 | 我們怎麼處理 |
|---|---|---|
| 設定階段 | 選看板、分支、政策 | 回答問卷 |
| 缺 helper skills | 第三方來源需你同意 | 先搜尋、列出來源、你核准後安裝 |
| #2 的 PR 超過 400 行 | 合併政策要求人看大 PR | 你同意後我經 merge gate 合併,並調高上限 |
| 想要全 haiku 層級 | 層級定義在 pack 的 workflow 檔 | 你明確授權後,我修改該檔 |

## 6. 觀察與限制(誠實面)

- **truth-check 沒有執行**:對抗式複查需要子 agent 工具,但 Review lane 本身沒有該工具,所以 #1~#3 的 Review 只靠 haiku 自己判讀。全 haiku 的審查強度偏弱。
- **#3 的小缺口**:shield 沒有做成 status 系統的一部分,審查者判定不阻擋,尚未開票追蹤。
- **使用量守衛是盲的**:沒有記錄 status-line 的用量,所以無法在接近額度上限時自動暫停。
- **本地修改不在 pack 內**:全 haiku 層級是直接改 `.agents/workflows/super-board-wave.js`;升級 pack 會覆蓋。
- **依賴鏈強迫串行**:四張卡互相阻擋,所以每波只跑一張。卡片彼此獨立時才會平行,這是工廠吞吐量的主要來源。
- **沒有 localhost 即時 UI**:即時觀察靠 GitHub Project 看板、`/workflows`、`/super-board status`。

## 7. 這個流程可以怎麼複用

1. 把需求寫成「有可檢查驗收條件、有 `Blocked by`」的票。
2. 票放進 `Ready`,執行 `/super-board run`。
3. 只處理 `Blocked` 且帶 🙋 的卡。
4. 想省用量用 `--low`;要最強審查用 `--high`;兩者之間是預設。

## 8. 重要檔案

- 設定:`.claude/super-board/configs/super-board-cardgame.json`
- 執行紀錄:`docs/super-board/runs/2026-11-17-super-board-cardgame.md`
- QA 證據:`docs/super-board/runs/issue-*-qa-v1/`
- 專案規則:`AGENTS.md`、`CLAUDE.md`
- 成品:`src/cardgame/`、`data/`、`tests/`(67 個測試全過)

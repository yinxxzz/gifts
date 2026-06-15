---
name: sales-gift-strategy-ops
description: 销售赠品策略静态页（sales-gift-strategy/）每月上新专用。用户提到赠品策略上新、新一期赠品、periods.json、改卖点话术、预览或上线 sales-gift-strategy 时使用。只涉及该 HTML 静态站，不涉及供应链仓库其他模块。
---

# 销售赠品策略页 · 独立 Skill

> 只服务 `sales-gift-strategy/` 这一个文件夹（index.html + data/periods.json + assets/）。  
> 销售在斑马驿站 → **赠品策略** 只读查看。

---

## 新电脑怎么用（3 件事）

1. **装 Skill**  
   解压下载包，把 `sales-gift-strategy-ops/` 放到本机 Cursor 技能目录：
   - Mac：`~/.cursor/skills/sales-gift-strategy-ops/`
   - Windows：`%USERPROFILE%\.cursor\skills\sales-gift-strategy-ops/`  
   （放用户目录即可，**不要**求整个供应链项目里有 `.cursor/skills/`）

2. **打开项目文件夹**  
   在 Cursor 里 **File → Open Folder**，只打开 `sales-gift-strategy/` 这一层（可从 Git 拉、或找研发要整个文件夹）。

3. **对 Cursor 说话**  
   把本期清单（文字/石墨/截图）发过来，说：「帮我上 7 月赠品策略」。

---

## 运营要准备什么（发给 Cursor）

### 本期赠品清单（必发）

石墨、文字、截图均可。写清：

- 活动名
- 每档礼包：几选几 + 品名列表
- 主推哪几个
- 哪些是新品

示例：

```
7月系统课加赠
- 主礼包：4选1 → 斑马书包、语数英点读书、词典笔、汉语拼音学习机
- 副礼包：6选2 → 仿真早教机、小风扇、得力地球仪、科学绘本、恐龙翻翻书、太空翻翻书
- 主推：主礼包推汉语拼音学习机；副礼包推恐龙翻翻书 + 仿真早教机
- 新品：汉语拼音学习机、仿真早教机、小风扇、恐龙翻翻书、太空翻翻书
```

### 图片

- 放进 `assets/YYYY-MM/`（如 `assets/2026-07/`）
- 告诉 Cursor：「图片已在 assets/2026-07/，按品名配路径」
- 路径写法本地和线上一致，用 `assets/2026-07/品名/xxx.jpg`，不用写完整 URL

### Cursor 负责生成（运营只审）

- 每个品 **2 句卖点**
- **策略总述**（蓝色卡片）
- **礼包推荐语**（绿框）
- 更新 `data/periods.json`

---

## Cursor 执行步骤

1. 复制最近一期 → 新建 `2026-07`（或用户给的 id）
2. 旧期改 `已结束`，新期改 `即将上线` 或 `已上线`
3. 改 `title`、`subtitle`（一行含日期，`dateRange` 留空）
4. 改 `bundles`：礼包名、rule、salesScript、recommended、gifts（含 image、sellingPoints、isNew）
5. 文案纯文本，**不要 HTML**
6. 提醒用户预览（见下）

### 文案口径

- 说给家长：口语化、具体、不硬广
- 卖点每句 15–30 字，每品 2 句
- summary 200–350 字，含几选几、不用加钱
- `recommended` 数量 = 规则里的 M（N选M）

---

## 预览（给运营确认）

在 `sales-gift-strategy/` 目录下终端执行：

```bash
python3 -m http.server 8765
```

浏览器打开：`http://127.0.0.1:8765/?period=2026-07`

检查：期次日期、策略介绍、图、卖点、主推标签、状态。

页面上 **三击** 可微调；**三击只改本机浏览器，销售看不到**。定稿以 `data/periods.json` 文件为准。

若有三击改动：页面 **⌘+Shift+E** 导出，用导出内容覆盖 `data/periods.json`。

---

## 上线（Run 平台）

线上：**https://gift-strategy.run.zhenguanyu.com**

预览 OK 后，**整包 `sales-gift-strategy/` 上传覆盖**（含 `data/periods.json` 和 `assets/`）。

### 用 Cursor 部署

用户说「帮我把 sales-gift-strategy 部署上线」时：

1. 确认 `data/periods.json` 和 `assets/YYYY-MM/` 已保存  
2. 读 `env.md` + `id_ed25519`，SSH 到 Run 机器  
3. `tar` 上传至 `/home/shared/workspace/gift-strategy`（排除 `env.md`、`id_ed25519`、`_backup`）  
4. 远程执行 `./start-server.sh`（8080）  
5. 打开 `https://gift-strategy.run.zhenguanyu.com/?period=YYYY-MM` 验收

### 驿站 iframe（首次一次性）

驿站 `.env.local`：`GIFT_STRATEGY_URL=https://gift-strategy.run.zhenguanyu.com`，重启驿站。

### 验收

- 直接访问静态站 `?period=YYYY-MM`  
- 驿站 → 赠品策略，下拉有新期次、文案和图片正确  
- 通知销售刷新使用

---

## 不要做的事

- 不要改 `index.html`（除非用户明确要求改功能）
- 不要把浏览器三击/localStorage 当已上线
- 不要动供应链仓库里其他项目文件
- 不要和「赠品采购预测工作台」混用

---

## JSON 字段速查

| 字段 | 说明 |
|------|------|
| id | 期次，如 `2026-07` |
| title | 页标题 |
| subtitle | 副标题一行（含日期） |
| status / statusLabel | upcoming·即将上线 / active·已上线 / ended·已结束 |
| summary | 策略总述 |
| bundles[].rule | 如 `4选1` |
| bundles[].salesScript | 礼包绿框推荐语 |
| bundles[].recommended | 主推品名数组 |
| gifts[].sellingPoints | 2 句卖点 |
| gifts[].image | `assets/2026-07/...` |

---

## 开场话术（运营可复制）

> 用 sales-gift-strategy-ops skill，帮我上 **2026-07** 赠品策略。  
> 清单如下：[粘贴或截图]  
> 图片在 assets/2026-07/。6 月改已结束，7 月即将上线。

# 销售赠品策略 · 文字 Demo

## 架构说明

- **本目录**可单独部署为静态站点（与驿站分离）
- **斑马驿站**通过环境变量 `GIFT_STRATEGY_URL` 指向此外链，在 `/gift-strategy` 用 iframe 嵌入
- 单独访问外链 / 驿站内嵌，共用同一份静态资源

## 本地预览

**终端 1 · 驿站（3000）**

```bash
npm run dev
```

**终端 2 · 赠品策略（8765）**

```bash
npm run gift-strategy:dev
```

| 用途 | 地址 |
|------|------|
| 单独打开 | http://127.0.0.1:8765/?period=2026-06 |
| 驿站内嵌 | http://localhost:3000/gift-strategy |

## 线上地址

**https://gift-strategy.run.zhenguanyu.com/?period=2026-06**

部署在 Run 平台，凭证见 `env.md` + `id_ed25519`（勿提交 Git）。

## 部署 / 更新（Run 平台）

推荐通过 GitHub 协作：大家先改仓库，线上服务器再 `git pull` 更新。

详细步骤见：`docs/同事部署说明.md`

快速命令：

```bash
cd /home/shared/workspace/gift-strategy
git pull
chmod +x ./start-server.sh
./start-server.sh
```

首次部署时，把仓库克隆到 `/home/shared/workspace/gift-strategy`；后续更新只需要 `git pull` 后重启。`start-server.sh` 会监听 **8080**，域名自动转发。

```bash
ssh -i id_ed25519 -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -p 9999 \
  root@gift-strategy.test.run.k8s.zhenguanyu.com
cd /home/shared/workspace/gift-strategy && ./start-server.sh
```

## 驿站 iframe 嵌入（首次一次性）

驿站 `.env.local` 配置：

```bash
GIFT_STRATEGY_URL=https://gift-strategy.run.zhenguanyu.com
```

重启驿站后，左侧 **「赠品策略」** 会在站内 iframe 加载此外链。

## 运营私密操作（不在页面展示）

| 操作 | 方法 |
|------|------|
| 改文案 / 礼包名 / 卖点 | 页面上**三击**对应文字 |
| 改期次状态 | 三击右上角状态标签（即将上线 → 已上线 → 已结束） |
| 导出 JSON | **Ctrl + Shift + E**（Mac：**⌘ + Shift + E**） |
| 下载 Cursor Skill | 页面最底部 **···** **三击** → 解压到本机 `~/.cursor/skills/sales-gift-strategy-ops/` |

快捷键 **Ctrl + Shift + D**（Mac：**⌘ + Shift + D**）也可打包下载图片，与按钮效果相同。

Skill 为独立包，只涉及 `sales-gift-strategy/`，内含运营全流程说明。

## 运营怎么改（JSON）

| 改什么 | 怎么做 |
|--------|--------|
| 礼包正式名称 | 页面上三击编辑 |
| 礼包话术 | 页面上三击编辑（`showSalesScript: true` 的礼包） |
| 主推品卖点 | 页面上三击每条卖点编辑 |
| 策略介绍 | 页面上三击编辑 |
| 强推哪几个品 | 改 `recommended` 数组 |
| 礼包话术是否展示 | 改 `showSalesScript` |
| 保存修改 | **Ctrl+Shift+E** 导出 JSON |

## 强推规则

规则 `N选M` → `recommended` 数组写 **M 个主推品名**（销售优先讲这些，标绿色「主推」）。

**页面上展示该档全部赠品**，每个品都有 2 句详细卖点；主推品额外带「主推」标签和绿色边框。

## 图片（本地 → 云端）

1. 图片放到 `assets/2026-06/`，按品名与子目录规范命名
2. JSON 里填 `"image": "assets/2026-06/..."` 路径
3. **上云 = 整个 `sales-gift-strategy` 文件夹一起上传**（含 `assets/`、`data/periods.json`）

图片会随文件夹部署，**不需要单独同步**。  
注意：浏览器里三击编辑的内容存在本机 localStorage，换电脑/清缓存会丢 → 改完务必 **导出 JSON** 再部署。

## 目录

```
sales-gift-strategy/
├── index.html
├── data/periods.json      ← 内容源
├── docs/运营使用说明.md    ← 运营手册
├── ops-pack/              ← 供页面下载 Skill
├── assets/2026-06/        ← 图片放这里
└── styles/main.css
```

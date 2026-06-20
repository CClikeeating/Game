# Baiou 小程序上线同步 PM 报告

更新日期：2026-06-18

## 当前结论

小程序还不能直接提审上线。后端、网页端和正式 HTTPS 域名已具备上线基础，但小程序需要完成微信后台配置、真实微信登录配置、真机回归和隐私材料确认。

当前线上地址：

```text
https://baioulove.xyz
https://baioulove.xyz/app
https://baioulove.xyz/api/v1/health
```

## 本轮同步口径

- 第一版免费使用，不接微信支付。
- 小程序必须使用微信授权登录。
- 每人每日免费额度默认 10。
- 全站每日额度默认 1000。
- 日常接话：`bailian_rag_fast`，扣 1。
- 暧昧推荐：`bailian_rag_strategy_quality`，扣 2。
- 旧模式 `bailian_rag_quality`、`bailian_rag_strategy_fast` 后端继续兜底为日常接话，不对用户展示。
- 文字输入入口强制日常接话，不展示上传截图区域。
- 截图回复入口可选日常接话/暧昧推荐。
- 用户端保留“分析”，不展示截图理解和参考片段。
- dry-run 不在用户端展示。
- 充值付费改为“联系作者获取更多额度”，QQ：`1179123330`。
- 小程序加入兑换码入口；后端已预留兑换码创建和兑换接口，具体兑换规则后续可调整。
- 后台导出新增审核 ZIP，包含 `feedback.csv` 和用户上传截图，供人工审核。

## 已完成的技术同步

- 后端配置默认额度改为每人每日 10、全站每日 1000。
- 模式扣费配置为日常接话 1、暧昧推荐 2。
- 小程序正式环境 API 地址配置为 `https://baioulove.xyz`，开发环境仍可走本地地址。
- 小程序登录去掉无 code 内测回退，正式环境依赖微信 `wx.login`。
- 小程序回复页已改为文字输入/截图回复两个入口。
- 小程序“我的”页已加入联系作者和兑换码入口。
- 后端新增：
  - `POST /api/v1/redeem-codes/redeem`
  - `POST /api/v1/admin/redeem-codes`
  - `GET /api/v1/admin/feedback/export.zip`
- 后台原 CSV 导出保留，ZIP 审核包新增截图附件。

## PM 需要操作

1. 微信公众平台 -> 开发管理 -> 开发设置 -> 服务器域名：
   - request 合法域名填 `https://baioulove.xyz`
   - uploadFile 合法域名填 `https://baioulove.xyz`

2. 微信公众平台 -> 开发管理：
   - 提供小程序 `AppID`
   - 提供小程序 `AppSecret`

3. 服务器环境变量需要配置：

```text
BAIOU_WECHAT_APPID=小程序AppID
BAIOU_WECHAT_SECRET=小程序AppSecret
BAIOU_MINIPROGRAM_DEV_LOGIN=false
BAIOU_ADMIN_PASSWORD_HASH=后台密码哈希
BAIOU_ADMIN_SESSION_DAYS=7
BAIOU_DAILY_REPLY_QUOTA=10
BAIOU_WEB_SITE_DAILY_QUOTA=1000
BAIOU_WEB_IP_DAILY_QUOTA=0
BAIOU_MODE_UNIT_COSTS=bailian_rag_fast=1,bailian_rag_strategy_quality=2
BAIOU_CONTACT_QQ=1179123330
```

4. 提供或确认提审材料：
   - 用户协议链接或正文。
   - 隐私政策链接或正文。
   - 截图上传用途说明。
   - 数据保留周期说明：默认截图和运行明细保留 30 天。
   - 小程序类目、服务说明、审核截图。
   - 草案见 `baiou/product/MINIPROGRAM_SUBMISSION_MATERIALS.md`。

5. 确认后台数据使用边界：
   - 谁可以下载审核 ZIP。
   - 截图人工审核后如何保管、删除或脱敏。
   - 后台密码的保管人和轮换方式；服务器只保存密码 hash。

## 测试计划

- 微信开发者工具：
  - 打开 URL 校验。
  - 确认正式版 API 指向 `https://baioulove.xyz`。
  - 微信登录成功。
  - 文字输入不展示上传截图区域。
  - 文字输入生成回复，扣 1。
  - 截图回复上传图片成功。
  - 日常接话生成回复，扣 1。
  - 暧昧推荐生成回复，扣 2。
  - 反馈成功。
  - 兑换码输入后额度刷新。

- 真机：
  - 登录、上传、生成、反馈完整跑通。
  - request/uploadFile 合法域名不报错。
  - 弱网和大图上传提示正常。

- 后台：
  - stats、users、ip-usage、feedback、reply-runs 可加载。
  - 审核 ZIP 可下载。
  - ZIP 内包含 `feedback.csv` 和截图文件。
  - 后台创建兑换码后，小程序可兑换。

## 风险和建议顺序

P0：
- 配置微信合法域名。
- 配置 `BAIOU_WECHAT_APPID` / `BAIOU_WECHAT_SECRET`。
- 关闭 `BAIOU_MINIPROGRAM_DEV_LOGIN`。
- 真机完整回归。
- 补齐用户协议、隐私政策、截图上传说明。

P1：
- 确认截图审核 ZIP 的权限和保管流程。
- 配置 SQLite、上传目录和后台配置文件备份。
- 确认服务器只暴露 Nginx 80/443，Gunicorn 继续监听 `127.0.0.1:7871`。

P2：
- 后续再细化兑换码规则，例如有效期、可用次数、提升额度策略。
- 后续访问量上来后迁移数据库和对象存储。
- 正式商业化前再接微信支付。

# SocialFlux 受邀标注 demo

独立托管的参与者网站。匿名编号与随机恢复码用于找回一份标注，无需 ChatGPT 登录。只发布 GPT50_001 的 6 道公开文字题，T1/T2/T3 各 2 道；不包含 author、参考答案、oracle、机器建议或研究后台。

## 参与流程

研究者分发完整邀请链接，参与者填写匿名编号、既往参考答案接触情况及参与确认，保存恢复码后开始。切换题目时保存到 D1；当前设备另存未保存草稿，并提示未保存状态。用编号和恢复码可跨设备继续。最终提交要求每题答案、把握程度和独立作答确认。提交后锁定，参与者只能下载自己的记录。

邀请凭据在 URL fragment 中传入，验证后移入 HttpOnly cookie 并从地址栏移除。邀请凭据仅用于领取新任务；已领取者凭个人恢复码访问记录。恢复码含 256 位随机数，服务器只用 SHA-256 摘要查询记录。数据库列 `user_id` 存的是该摘要，与平台账户无关。编号本身不授权访问，编号不要求全局唯一。

## 数据与复现

- `data/questions.json` 是经过 `tasks.offline_choice.public_instance` 白名单导出的冻结公开投影；原始题库留在研究仓库本地，不进入网站源码。
- `dataset_sha256` 标识发布包；每个 item 哈希指向原始完整题目，供研究者本地审计。不要在同一发布版本中重写题目。
- `demo_sessions` 保存匿名编号、既往接触情况、答案、备注、版本、时间戳及题目哈希。无姓名、邮箱或平台用户标识；备注中应避免个人信息。
- 并发修改使用 revision 比较更新，冲突返回 409，保留客户端输入。重复提交返回同一回执。演示结果标记 `formal_ground_truth: false`，不能直接作为正式 GT。
- 网站所有者可使用 Sites 的数据库查看功能读取 `demo_sessions`。没有公开的全量导出接口；参与者导出始终由自己的恢复凭据限定。

## 本地开发

Node >= 22.13。保留 Sites 的 Vinext 构建集成与 `.openai/hosting.json`；生产绑定为 `DB`。先安装依赖，再执行：

```sh
npm run db:generate  # 仅在修改 schema 时生成新的迁移
npm run build
node --import ./scripts/sites-env.mjs ./node_modules/wrangler/bin/wrangler.js d1 execute DB --local --config dist/server/wrangler.json --persist-to .wrangler/state --file drizzle/0000_bright_prism.sql
npm start -- --port 8012
```

本地启动前将 `DEMO_INVITE_SHA256` 放到 `dist/server/.dev.vars`，这是随机邀请字符串的 SHA-256 hex 值；文件必须保持忽略。生产环境通过 Sites runtime secret 配置同名键，不写进 hosting manifest 或源码。邀请链接格式为 `https://<site>/#invite=<random-url-safe-token>`；不要提交真实邀请凭据或恢复码。

## 验证与发布

```sh
node node_modules/typescript/bin/tsc --noEmit --incremental false
node --experimental-strip-types --test tests/protocol.test.mjs
```

`tests/browser.cjs` 通过 stdin 接收 `{url, invite, output}`，需要 Playwright 和已安装 Chromium。仅针对独立本地数据库运行，以免产生正式标注记录。覆盖匿名领取、跨设备恢复、版本冲突、无效输入、不完整提交、提交锁定、幂等重试、下载、公开数据边界及 360/390px 手机布局。

发布使用 Sites skill 的 source helper：检查/构建 → 提交并推送精确源码 → 打包 → save_site_version → deploy_site_version。托管入口允许匿名浏览，应用层仍验证邀请及个人恢复码；机器人索引已关闭。D1 迁移由托管部署应用。`.dev.vars`、`.wrangler`、浏览器 QA 输出及生产凭据都不进入发布包。

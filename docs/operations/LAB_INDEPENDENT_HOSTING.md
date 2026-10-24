# Lab：GitHub Pages 前端 + 现有 AutoDL 后端

## 当前状态（2026-10-24）

用户已明确选择当前 AutoDL 服务器作为后端，取代下文历史 Sites / Render 方案。
6006 的 Lab 与独立标注存储服务已运行，并由 Supervisor 自动重启。
GitHub Pages 已从 `main` 成功发布并核验 HTTPS 页面资源：
[成功的 Actions 运行](https://github.com/diudiu0515/SocialFlux/actions/runs/40087124546)。
仓库的 `github-pages` 环境只允许 `main`；用户合并 Lab 后，发布触发器已对准该分支，
保留原环境保护规则。之后更新 `main` 中的 `pages/` 或发布工作流会自动部署。

- Lab：`https://diudiu0515.github.io/SocialFlux/lab/`
- 标注：`https://diudiu0515.github.io/SocialFlux/annotation/`

前端发布内容为本分支的 `pages/`，不含私有数据库、题库包、标注或视频。
不再要求 Render、ChatGPT 登录或 ChatGPT Sites 域名。
后端读取当前研究数据；AutoDL 必须在线才能读取数据或保存。6006 的同源页面保留为备用入口。

## 标注迁移、汇总与恢复

旧 Lab 的 1 份标注和旧独立站的 4 份标注已导入
`data/sites_annotation/annotation.sqlite3`，逐字段核验原答案、恢复码哈希与材料绑定。
原始云端记录未删除。另备份了服务器原有 2 份标注会话与计划数据库。
5 份云端记录均为未提交记录：4 份研究回执已进入本地回执归档和现有 Lab 汇总，
1 份旧 Demo 单独保留；不得把这些草稿计为正式提交或共识 GT。

新标注按公开背景修订版派发：50 场景 / 400 题的“人物关系”“权力与资源”“目标冲突”
均可在作答前查看。旧标注仍绑定其原材料，不改写既有答案。
已保存记录可凭原编号和恢复码跨设备继续。下载 JSON 另外保留未锁定草稿，
不把草稿混入盲答基线。进度和正式结果沿用 Lab 的人工标注汇总；“人工与 GT”页直接列出各版本的导入数、未提交数和最终提交数。

每次保存采用 SQLite 完整同步提交、版本冲突检查、修改历史、不可变回执和一致快照。
数据库、回执与媒体位于 `data/sites_annotation/`；部署或重建前端不会清空这些目录。
备份包为 `data/migrations/20261024-pages-sites/annotation-backup-20261024.tar.gz`，
校验清单为同目录 `backup-manifest.json`。已通过服务重启和独立副本恢复检查。
快照和备份仍在同一台服务器，应另下载一份；它们不能防止整块磁盘丢失。
具体构建、服务和恢复步骤见 `web/annotation_portable/README.md`。

浏览器已验证 Pages 子路径、Lab 七个视图、移动端、断网草稿恢复、跨设备恢复、
JSON 下载和鉴权视频播放。生产数据库未写入测试标注；公网后端的 HTTPS 和 Pages CORS 已验证。
最终 GitHub Pages 地址与发布资源已核验；生产浏览器验证结果记录在 `reports/experiments/2026-10-24_lab_pages_migration.json`。

## 历史部署记录（以下不再作为当前方案）


2026-10-24 补充：用户明确要求保留并恢复服务器端口 Lab。实时研究入口使用
转发后的 `http://localhost:8000/lab` 或 `http://localhost:6006/lab`，
`socialflux-lab-public` 已恢复为当前研究代码的 6006 服务，并开启自动重启。
下文独立站是并行保留的部署，不替代端口 Lab；此前禁止恢复端口服务的约束已被本次用户指令覆盖。

## 当前生产入口（2026-10-23）

正式站点：https://socialflux-experiment-lab.junqiao24.chatgpt.site

2026-10-23 15:42 UTC 已发布成功。人工标注已集成到同一项目的 `/annotation`：沿用 Lab 登录、原数据库和访问权限，支持自动保存、手动保存、当前账户任务列表恢复、恢复码及 JSON 导出。原实验结果、`/plans` 计划与笔记继续保留。旧独立标注站的历史记录仍在原站，本轮未迁移其数据库；Lab 内保留旧记录恢复链接。发布状态见 `reports/experiments/2026-10-23_lab_annotation_integration.json`。

此前对独立标注网站的要求：不得依赖 AutoDL 开机才能访问；服务器实时 Lab 现按后续指令单独保留。
继续使用已有 Sites 项目 `appgprj_6acdd14e43dc81919897c86163918baf` 和原有私有权限。
首页提供最新发布的实验矩阵、62 张结果表和报告下载；`/plans` 保留原有 D1 云端计划与笔记。
数据随网站版本一起发布，页面标明结果生成时间，不是对研究机器的实时轮询。
汇总接口和下载均在独立站点同源执行，无 AutoDL 网络依赖。

本次站点源码位于 `build/independent-lab-site-20261023`，通过 Sites 源码工作流提交并发布。
后续更新应从该项目源码仓库继续工作，并保留 `.openai/hosting.json` 中的项目 ID、DB 绑定和既有云端记录。
原始研究数据、媒体与计算进程仍属于研究环境；本次未宣称将整个 Python 研究后端和约 15 GB 原始材料迁移。

`socialflux-lab-public` 的停用状态已于 2026-10-24 按用户指令撤销。
6006 与原 8000 均为服务器研究入口；与本文件描述的独立站分别运行。

## 历史备选方案：GitHub Pages + Render（未上线）

目标地址为 `https://diudiu0515.github.io/SocialFlux/lab/`。它是待发布地址，
在 Pages 发布成功并核验前不能作为可用网址交付。

前端使用 `.github/workflows/lab-pages.yml`，后端使用 `render.yaml`。
二者都读取 `lab-independent-hosting-20261022` 分支。后端代码、数据及存储
全部迁到独立托管服务后，网站不再调用 AutoDL，也不要求 AutoDL 保持开机。

## 发布前所需连接

以下连接条件属于历史备选方案，不是当前 Sites 部署的前提。SocialFlux 的 GitHub 应用授权已可用。
仓库 Settings → Pages 的 Source 设为 GitHub Actions，允许本发布分支使用
github-pages environment，并在 Actions variables 设置真实 `LAB_BACKEND_URL`。
这个值只能是独立后端 HTTPS Origin，构建脚本明确拒绝 AutoDL/SeetaCloud 地址。

Render 需要连接用户账户和此仓库。本 Blueprint 使用持久磁盘，适用于付费服务；
当前只是配置准备，不代表已开通或已产生费用。当前 data 目录约 15.05 GB，
配置预留 20 GB，正式迁移前仍需加上相关 build 文件核定容量。
密码由 Render 生成，仅在后端环境变量中保存。

## 数据迁移与保留

`SOCIALFLUX_DATA_ROOT=/var/data/lab` 位于独立持久磁盘。
首次启动只复制仓库里的配置与报告文档，保留目标目录已有内容。
真实数据需要单独迁移，包括实验统计所引用的 data/build 文件、题库、媒体、
人工导出记录、媒体历史版本及计划数据库。不能把本机目录软链接当作迁移。
视频等私有材料不得放进 GitHub Pages artifact。

迁移时对 SQLite 使用 backup API 获取一致备份；逐文件生成 SHA-256 清单，
传输后核验。确认记录数、表格、报告、冻结材料和媒体哈希均与来源一致，
再在持久目录写入 `lab-data-ready.json`，记录清单哈希与核验时间。
没有这个标记时，后端拒绝读写实验 API，避免把空数据库误报为迁移完成。
该备选方案只有在数据迁移后才能提供完整 Python 功能；本次恢复的端口服务直接读取原研究数据，不属于该迁移方案。

## 页面与登录

Pages 只发布 HTML、JS、CSS 和字体。浏览器登录后在内存中保存认证头，
不向 GitHub 提交密码，也不把密码写进 URL、localStorage 或 sessionStorage。
后端只允许明确配置的 Pages Origin，写请求仍需认证与 JSON 格式。
计划编辑、回执导入、裁决、实时读取、报告和 CSV/Markdown/LaTeX 导出使用
相同的 Python 实现。研究工具链接打开独立后端页面，可能再次要求登录。

## 验证与完成条件

Pages 子路径资源正常；错误密码被拒绝；七个 Lab 页面可用；计划写入与跨页面
读取正常；回执流程、表格导出和手机布局通过；未经授权的 Origin 不可读写。
独立后端健康检查 `/healthz` 的 `data_ready` 必须为 true。
最终核验必须在独立托管地址完成，并确认网络请求没有 AutoDL 域名。

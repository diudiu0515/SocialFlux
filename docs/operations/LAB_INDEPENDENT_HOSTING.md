# Lab 独立托管

## 当前生产入口（2026-10-23）

正式站点：https://socialflux-experiment-lab.junqiao24.chatgpt.site

用户明确要求：网站不得托管在 AutoDL，不得依赖 AutoDL 开机才能访问。
继续使用已有 Sites 项目 `appgprj_6acdd14e43dc81919897c86163918baf` 和原有私有权限。
首页提供最新发布的实验矩阵、62 张结果表和报告下载；`/plans` 保留原有 D1 云端计划与笔记。
数据随网站版本一起发布，页面标明结果生成时间，不是对研究机器的实时轮询。
汇总接口和下载均在独立站点同源执行，无 AutoDL 网络依赖。

本次站点源码位于 `build/independent-lab-site-20261023`，通过 Sites 源码工作流提交并发布。
后续更新应从该项目源码仓库继续工作，并保留 `.openai/hosting.json` 中的项目 ID、DB 绑定和既有云端记录。
原始研究数据、媒体与计算进程仍属于研究环境；本次未宣称将整个 Python 研究后端和约 15 GB 原始材料迁移。

旧 AutoDL 公网服务 `socialflux-lab-public` 已停止，`configs/lab.supervisord.conf` 的
`autostart` 与 `autorestart` 均为 false。不得重新启用；原 8000 研究服务不作为网站生产入口。

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
该备选方案只有在数据迁移后才能提供完整 Python 功能；不得以迁移未完成为由重启已停用的 AutoDL 公网服务。

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

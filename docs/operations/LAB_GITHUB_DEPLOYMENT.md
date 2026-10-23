# 已停用：AutoDL 上的 GitHub 联动后端

2026-10-23：用户明确要求网站不得托管在 AutoDL。本方案已停用，不能再作为生产部署说明执行。
`socialflux-lab-public` 已停止，Supervisor 配置已禁用自动启动和自动重启。
后续网站更新应使用已有独立站点 https://socialflux-experiment-lab.junqiao24.chatgpt.site ，
详见 [独立托管说明](LAB_INDEPENDENT_HOSTING.md)。下文仅保留旧实现供追溯。

Lab 保留 Python 后端、实时读取、计划编辑、回执导入、裁决、视频和论文表格导出。
GitHub 分支 `lab-backend-deploy-20261022` 保存旧发布代码；旧 AutoDL 公网后端已停止。
这不是 GitHub Pages 静态快照。服务器关机后网站也会停止。

## 运行与更新

`configs/lab.supervisord.conf` 管理独立的 6006 端口服务，不改变原 8000 服务。
`scripts/run_github_lab.py` 每 60 秒从 GitHub 检查一次指定分支，只接受 fast-forward。
每个提交解包到 `build/lab-deployment/releases/<commit>`；导入检查通过后重启服务，
以已认证 `/api/lab` 响应检查启动。失败时恢复上次健康提交。
部署状态位于 `build/lab-deployment/status.json`，当前健康提交位于 `active.json`。
短暂启动或更新会造成服务中断；不是零停机部署。

`SOCIALFLUX_DATA_ROOT` 指向原始研究项目目录。发布代码中的静态页面仍从本次提交读取，
数据、报告、题库、SQLite 和参与者记录继续保存在原目录，更新代码不会替换这些文件。
`web/runtime_paths.py` 统一解析此设置；不设置时维持原本行为。
更新数据不需要推送 GitHub，网页仍每 30 秒读取服务器上的最新结果。

仅查看已停用服务状态（不要启动）：

```bash
build/web-service/venv/bin/python -m supervisor.supervisorctl -c configs/lab.supervisord.conf status
```

Supervisor 自动启动与自动重启均已禁用；不得因旧脚本或 GitHub 分支有更新而恢复此服务。

## 登录与验证

公网入口使用 AutoDL 的 `AutoDLService6006URL`，页面路径 `/lab`。
用户名 `socialflux`；密码保存在 `.secrets/lab-public-password`，权限必须为 600。
密码与私有研究数据不会提交 GitHub。不要把密码放进 URL 或 GitHub 配置。
所有页面、API 和视频均使用已有 HTTP Basic 登录保护，提交仍要求同源 JSON。
AutoDL 代理可能重写 Host，`--public-origin` 仅允许明确配置的外部 HTTPS Origin，
不信任客户端提供的转发头，也不开放跨站提交。GitHub 同步复用原项目的 SSH 配置。

公网检查应验证：匿名访问返回 401，登录后页面与 `/api/lab` 返回 200，
页面无资源加载错误，矩阵、报告与表格可导出。写入测试必须使用临时数据目录，
不得向生产计划或参与者记录添加测试数据。

回退应通过向发布分支追加 revert 提交，不要强推分支。

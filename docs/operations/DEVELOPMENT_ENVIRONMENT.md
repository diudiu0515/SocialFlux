# Conda 环境与复现

新开发和新部署使用 Conda 管理 Python 环境，不向 `base` 添加项目依赖。
`environment.yml` 是基础 benchmark/client 环境，`environments/qwen.yml` 是独立的
可选 GPU 模型服务环境。Conda 管理 Python 和环境生命周期；仅通过当前环境的
`python -m pip` 安装其中声明的 Python wheel。

## 基础环境

在仓库根目录执行：

```bash
bash scripts/create_conda_env.sh core --dry-run
bash scripts/create_conda_env.sh core
conda activate "$PWD/build/runtime/envs/core"
python -m pipeline --help
python -m unittest tests.test_public_task4_api tests.test_offline_choice tests.test_qwen_task4_policy -v
```

安装器默认将环境、Conda/pip/npm/uv 缓存和临时文件放在 `build/runtime/`。
本服务器的项目目录位于数据盘；其他机器需自行选择容量合适的数据目录：

```bash
export SOCIALFLUX_STORAGE_ROOT=/absolute/path/on/data-disk/socialflux-runtime
bash scripts/create_conda_env.sh core
conda activate "$SOCIALFLUX_STORAGE_ROOT/envs/core"
```

路径变量不能使用 `/root/...` 等开发机固定地址作为公开默认值。环境激活后，
`TMPDIR`、`PIP_CACHE_DIR`、`CONDA_PKGS_DIRS`、`npm_config_cache`、`HF_HOME` 等自动
指向该存储目录。未激活此环境的旧进程不受影响。脚本拒绝覆盖已存在的环境；
升级依赖应使用新的存储目录和运行记录，避免在冻结实验中途更新依赖。

基础环境支持 CLI、公开会话客户端、远程模型 provider 和无模型单元测试，不需要
CUDA 或 GPU。本地推理、视频生成和语音处理是额外能力，不属于最小安装承诺。

## 可选 Qwen 模型服务

仅在需要本地 GPU 推理的机器安装：

```bash
bash scripts/create_conda_env.sh qwen
conda activate "$PWD/build/runtime/envs/qwen"
python scripts/serve_qwen_local.py --runtime-prefix "$CONDA_PREFIX" --print-command
```

检查模型位置、GPU 数量、CUDA/驱动和端口后，去掉 `--print-command` 才会加载模型。
该定义固定项目已部署的 vLLM 版本，不表示所有 GPU/驱动平台都受支持。
模型权重另按[Qwen 部署说明](QWEN_LOCAL_ENVIRONMENT.md)准备，不随代码发布。
Task4 HTTP 服务只需要基础环境和可访问的模型 endpoint，不必再次安装 GPU 包。

历史 `build/qwen_deployment/venv` 是现有冻结实例的运行依赖。启动器不传
`--runtime-prefix` 时保留该历史路径，防止现有 Supervisor 配置重启时隐式换环境。
这不是已完成迁移的声明：下一次新部署须显式选择 Conda prefix，同步修改该实例的
Supervisor 启动命令，完成健康检查和验收后再退役旧环境。不得在活跃批次中途替换。

旧视频依赖与新 vLLM/Transformers 存在版本差异，应放在另一个 Conda 环境，按
[视频依赖](../../requirements-video.txt)及相应任务说明安装，不能叠加到基础环境。

## 可复现记录

环境 YAML 声明依赖范围，不是跨平台锁文件。创建后自动保留本机解析结果：

- `build/runtime/locks/<profile>/conda-explicit.txt`：Conda 包的精确平台构建。
- `build/runtime/locks/<profile>/pip-freeze.txt`：当前 Python 包版本清单。

这两个文件是环境清单，不能替代 wheel 哈希校验、模型 revision、驱动记录或数据
许可。正式运行须将环境清单与代码 commit/工作区差异、schema/prompt 哈希、配置、
模型及数据版本、seed 和实际请求计数一并绑定到 run manifest。
当前冻结机制见[Task4 手册](QWEN_TASK4.md)，公开接口见
[benchmark 接口合同](../protocols/PUBLIC_BENCHMARK_API.md)。

发布前在干净 checkout 和全新 Conda 环境复测；基础接口测试不依赖 `data/`、
私有凭据、GPU 或外部模型。历史集成测试所需的真实数据必须另行提供并注明许可，
不能把合成工程 fixture 当作 benchmark 场景或验收证据。

# 第一阶段：代码、Docker 与实验

固定提交：`3bd152ddbb6df45e0e07d6c9e9eb1573dcfd3dc6`（2026-11-02 main）。构建不会自动升级主线。

## 执行方式

在仓库根目录运行 `./run.sh`，或本目录运行 `./run.sh`。默认 smoke。依赖为 Linux x86-64、Docker、Bash、Python 3；不要求在宿主安装 LLVM、Clang、CMake、perf，也不自动执行系统安装。

默认从本仓库 Release 获取发布镜像，按 `image.json` 核对归档 SHA256、代码指纹、文件系统层和执行入口，载入后运行。已载入的相同代码镜像直接复用。也可将 Release 的 Docker 归档放入 `.build/stage1.docker.tar.gz` 后离线执行。发布镜像复用已验证的固定版本 BOLT，重新编译本仓库的 Clang 18 负载与控制器。

需要独立源码重建时使用 `./run.sh build --source --jobs 2`，自动完成：

1. 下载固定 LLVM 源码并编译原版 BOLT。
2. 对同一提交应用 patch，增量编译修改版。
3. 构建运行镜像，其中包含两版 llvm-bolt、运行库、测试负载、控制器和脚本。
4. 用 Clang 18 正常 O3 编译负载。构建分支内核时使用真实 BOLT candidate 转换，并核查恰好转换一组及公共回退调用点。

构建需要联网，运行容器使用 `--network none`、当前用户 UID/GID，不使用 privileged、LBR 或 PMU。默认编译并发为 2，可用 `--jobs N` 改变。镜像按源码指纹复用，修改执行代码后会重新构建相关层。

源码重建建议至少 8 GB 内存、约 15 GB 可用磁盘，首次耗时较长。本次打包已检查下载、固定提交和 CMake 配置，未重复完成整套 LLVM 编译；发布镜像使用此前已经构建、验证并记录哈希的相同源码工具链。

如果设置了 HTTP(S)_PROXY，启动器将其作为 Docker 构建代理传递；localhost 代理在构建阶段使用 host 网络。需要其他构建网络时可设置 `BOLT_BUILD_NETWORK`。运行阶段仍然禁网。

APT 软件包和 Git 源码下载默认先直连，失败后使用已配置的代理，保持签名/HTTPS 校验；可设置 `BOLT_APT_MODE=direct|proxy`、`BOLT_GIT_MODE=direct|proxy` 固定选择。Git 下载使用超时与有限重试，避免永久等待。

| 模式 | 执行内容 |
| --- | --- |
| `functional` | 原版/关闭版可执行节一致性，静态 Pass 语义与拒绝检查，17 项 ASan/UBSan 控制器检查，468 次控制器功能检查 |
| `smoke`（默认） | functional 加 low95/uniform 的快速采样、校准与执行流程 |
| `full` | functional 加原静态方案正式实验、运行时 52 场景 ×31 块 ABBA/BAAB 实验及 off/off 自对照 |
| `build` | 仅获取发布镜像；加 `--source` 才从 LLVM 源码重建 |
| `evidence` | 无需 Docker，仅从随附压缩原始数据重算历史统计，并核对结果逐字节一致 |

full 可能因真实性能/统计区间未达到门槛而失败。这是保留失败数据的预期行为，不能将 smoke 的成功替代完整验收。性能实验期间避免并行编译或运行其他基准。

输出结构示例：

```text
results/<时间>-smoke/run/
  result.json
  default-off-identity/
  static-functional/
  controller-functional.json
  controller-safety.log
  static-smoke/
```

目录必须不存在，完整日志与原始数据不会覆盖。Docker 构建的源码提交固定，但 apt 软件包可能更新；结果会记录实际编译器、工具和负载 SHA256。

## 已实现的 BOLT 能力

`-cmov-branchify` 默认关闭。只接收相邻同条件、2～4 条 64 位寄存器 CMOV，拒绝内存源、32 位和不支持的控制流结构；要求循环、编码预算、样本与偏置及独立收益校准等条件。

| 选项 | 用途 |
| --- | --- |
| `-cmov-branchify-probe -instrument` | 将站点暴露给 BOLT 插桩运行库，采集谓词方向 |
| `-cmov-branchify-sites=FILE` | 导出站点与来源 |
| `-cmov-branchify-profile=FILE` | 输入谓词计数和校准信息 |
| `-cmov-branchify` | 最终静态转换，默认关闭 |
| `-cmov-branchify-candidate` | 离线候选实验，不能当作已批准的生产优化 |

## 运行时部分的范围

`runtime/` 是合作式批次 ABI 原型：检查工作量和等长批次，三组完整确认后才准入，一次失败后本调用永久回退；连续执行期间复查，回退先撤销观察函数栈帧再从公共调用点进入原路径。状态属于单次调用，时钟失效时返回原路径。

它没有自动从任意 ELF 识别工作量、克隆函数或注入线程状态；当前没有新的 BOLT 自适应选项。原型使用 BOLT 生成的两个真实内核，但**不能将它与静态 Pass 的证据拼成“同一最终产品已满足第四条”**。

## 核查随附数据

`evidence/static/` 保留原静态实验的原始计时、结果、关闭版一致性和输入变化反例；`evidence/conservative/` 保留最新正式协议、全部原始计时、统计结果、安全和容器功能记录。原始计时仅做 gzip 压缩，未删慢样本。

`scripts/analysis.py` 是对应正式统计方法；`scripts/benchmark.py` 可对新构建的 ELF 重做实验，未通过返回 2。历史证据的编译器/CPU/工具哈希可能与新 Docker 不同，这属于独立重建，不能据此直接套用历史收益。

设计、适用负载与未完成项见 [Word](docs/design.docx) 或 [Markdown](docs/design.md)。全仓库普通文件校验见 `SHA256SUMS`；在仓库根目录执行 `sha256sum -c SHA256SUMS`。

# 系统优化大作业 · 第一阶段

基于 **2026-11-02 LLVM main** 的 BOLT CMOV 组反向转换，以及保守运行时准入原型。

**这是阶段性提交，第四条“无收益负载无性能副作用”尚未全部达标。** 已实现的 BOLT 选项是 `-cmov-branchify`；运行时保护仍是合作式批次接口原型，不能当作已经集成的新 BOLT 自适应选项。

## 一键运行

需要原生 Linux x86-64、Bash、Python 3 和可用的 Docker；WSL2 需启用 Docker 集成。在仓库根目录执行：

```bash
./run.sh
```

首次运行自动下载固定提交、编译原版和修改版 BOLT、构建包含工具与负载的 Docker，再执行功能检查和快速流程；需要网络、数 GB 磁盘空间，建议至少 8 GB 内存。默认 2 个编译任务，首次编译可能耗时较长，后续复用缓存。运行测试时容器禁网。

```bash
./run.sh functional                  # 正确性、拒绝、代码一致性、安全检查
./run.sh full                        # 另做完整静态/运行时性能实验
./run.sh build --jobs 2              # 仅构建镜像
./run.sh evidence                    # 无需 Docker，重算随附历史统计
./run.sh smoke --output "$PWD/results/check-01"
```

结果写入 `results/` 下的新目录，已有目录不会覆盖。**smoke 成功只说明流程和功能检查通过，不代表性能验收通过。** full 中性能区间未过会返回非零状态并保留全部数据；详细结果见输出中的 `run/result.json` 和各日志。完整性能实验可能再运行数十分钟，期间请避免其他高负载任务。

`evidence` 成功表示原始数据可以精确重算，不表示历史性能目标通过；重算会明确输出 `historical_performance_gate_passed: false`。

## 第一阶段内容

| 内容 | 位置 |
| --- | --- |
| 构建与运行说明 | [stage_1/README.md](stage_1/README.md) |
| 可应用于固定主线的代码 patch | [cmov-branchify.patch](stage_1/patches/cmov-branchify.patch) |
| 自动构建 Docker | [Dockerfile](stage_1/Dockerfile) |
| BOLT 训练、校准、测试及负载 | [app/](stage_1/app/) |
| 最新保守准入实现 | [runtime/](stage_1/runtime/) |
| Word 设计文档 | [design.docx](stage_1/docs/design.docx) |
| 在线设计说明 | [design.md](stage_1/docs/design.md) |
| 必要的原始数据与验收结果 | [evidence/](stage_1/evidence/) |

仓库不包含 LLVM 整棵源码、构建缓存、工具二进制、历次试验目录或第二阶段项目；这些不影响一键源码构建。GitHub 的 **Code → Download ZIP** 可获取本阶段完整源代码包。

## 当前结果与边界

历史正式运行时实验为 2 尺寸 ×26 场景 ×31 个独立输入块：12,896 次计时结果校验通过；安全检查 17 项、容器功能检查 468 次通过。low95 收益比约 **1.21～1.30**。

最差场景中位耗时增加约 **1%**，紧贴目标；其 95% 区间约为 **0.17%～1.88%**，因此不能宣布回退上界小于 1%。均匀等静态拒绝案例的代码一致性，与运行时保护的整体性能验收，是不同证据。原静态优化在输入分布改变后仍有显著退化反例。

既有证据来自 Clang 24/WSL2；新 Docker 使用 Clang 18 重新构建负载、重新采集 profile。不同机器必须以新跑出的结果为准，不能套用旧 profile 或保证相同加速比。

CMOV 转分支在 LLVM X86 后端已有先例，本项目不主张理论首创。AI 参与了方案讨论、实现草稿、脚本和文档；课程提交者需独立理解、验证并说明自己的贡献。LLVM patch 和第三方代码许可见 [说明](stage_1/licenses/NOTICE.md)。

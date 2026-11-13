# LLVM BOLT 自适应 CMOV 优化

在BOLT中为循环内的CMOV组生成分支实现，根据当前批次的耗时选择执行版本。对能确定结果为0的任务，在入口直接完成。优化由 `-cmov-branchify-runtime` 控制，默认关闭。

基线固定为 **2026-11-02 LLVM main**：`3bd152ddbb6df45e0e07d6c9e9eb1573dcfd3dc6`。支持Linux x86-64和具有明确批次入口的程序。

## 实验数据

测试平台：Ryzen 7 7735H、WSL2，Clang 18正常 `-O3` 编译的批量查找负载。加速比为“关闭选项耗时 / 开启选项耗时”。

| 负载 | 开启优化后的结果 |
|---|---|
| 4K键表、强偏置查找 | 1.349倍加速 |
| 8K键表、强偏置查找 | 1.493倍加速 |
| 空表512/1024批 | 完整调用约4 ns |

![主要正例的开关对照](stage_1/docs/assets/concise/result_speedup.png)

59项负载、31轮正式实验，共14632次计时执行，结果校验全部通过。常规51/52项中位回退低于1%，最差1.10%；7项边界均低于1%。独立长计时中，两项临界场景回退约0.17%和0.21%。完整数据与区间见[实验结果](stage_1/docs/results.md)。

perf已测7项负载、252次计数。另在公开日志数据、合成查询的累计计数原型中，范围前查询的完整进程加速约1.030倍，Docker复现约1.020倍；均匀查询未确认提升。详见[perf与应用实验](stage_1/docs/perf-application.md)及[原型复现说明](stage_1/experiments/log-time-index/README.md)。

## 一键运行

准备Linux x86-64、Bash、Python3和可用Docker，WSL2可用。

```bash
git clone https://github.com/LeeDashuai666/so_homework_1.git
cd so_homework_1
./run.sh
```

首次运行自动下载并校验Docker镜像，随后重新采样、独立校准、检查功能并快速测量。`full` 覆盖52项常规负载和7项边界。

```bash
./run.sh full                   # 完整实验
./run.sh functional             # 功能、安全和准入检查
./run.sh evidence               # 离线复算已保存数据，不重新计时
./run.sh --output 新目录         # 指定输出目录
./run.sh build --source --jobs 2 # 从固定源码构建镜像
```

每台机器重新校准；未通过时保留原实现。可从[Release](https://github.com/LeeDashuai666/so_homework_1/releases/tag/runtime-v3-20261113)手动下载Docker包，将它放在仓库目录或仓库的父目录后运行 `./run.sh`，入口会校验并自动加载。

## 提交内容

- [代码patch](stage_1/patches/cmov-runtime.patch)
- 简洁设计文档：[Word](stage_1/docs/design.docx) · [PDF](stage_1/docs/design.pdf) · [在线阅读](stage_1/docs/design.md)
- [实验数据](stage_1/evidence/final/) · [长计时补测](stage_1/evidence/precision/) · [结果CSV](stage_1/docs/results.csv)
- [Docker及源码包](https://github.com/LeeDashuai666/so_homework_1/releases/tag/runtime-v3-20261113)

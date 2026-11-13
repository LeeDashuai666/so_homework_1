# 最终版perf测量

在能够直接运行目标ELF的Linux宿主机测量，需安装与环境兼容的perf，并允许当前用户采集用户态硬件事件。已验证环境为本项目WSL2。先做已知程序检查，再测最终版，不能仅因perf命令成功就认定计数可靠。

```bash
python3 stage_1/experiments/wsl-perf-check/run.py --output results-perf-validation --perf /usr/bin/perf
./run.sh --output results-perf-build
python3 stage_1/experiments/cmov-final-perf/run.py \
  --build results-perf-build/run/build --output results-perf-final \
  --validation results-perf-validation/summary.json --perf /usr/bin/perf
```

7个场景、9个配对块，四项用户态硬件事件成组计数。事件覆盖整个进程，包括准备和预热；API耗时来自程序JSON，两个统计口径分列。全进程计数不能直接叫作精确热点区间计数。热点采样只作辅助解释，BOLT生成的PIE可能出现符号显示错误，应按映射和ELF范围核查。

本次采集的标签曾被程序JSON中的guarded字段覆盖，已按保存的执行argv恢复；所有计数、时间和样本均保留，原始JSON另存。脚本已修复字段覆盖顺序。

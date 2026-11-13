# 公开日志上的累计计数业务原型

输入Loghub Linux 2k结构化日志与合成时间阈值，读取日志、排序建立时间索引，计算所有阈值之前的事件数量总和。它输出汇总值，不是逐条日志检索工具。年份统一设为2000年UTC；原始数据无年份。查询由固定种子生成，非生产请求回放。

数据来源：https://github.com/logpai/loghub ，固定提交dd61d0952749ee7963bde24220d1be5ede023033。Jieming Zhu等，Loghub: A Large Collection of System Log Datasets for AI-driven Log Analytics，ISSRE 2023。数据使用遵守data/LICENSE.loghub。

## 复现

先在仓库根目录运行 `./run.sh build`，再用已有镜像运行本原型：

```bash
mkdir -p results-log-count
docker run --rm --network none --user "$(id -u):$(id -g)" \
  --entrypoint python3 \
  --mount "type=bind,src=$(pwd)/stage_1/experiments/log-time-index,dst=/opt/homework/experiments/log-time-index,readonly" \
  --mount "type=bind,src=$(pwd)/results-log-count,dst=/results" \
  so-homework-1:runtime-b6201a99e79e751a \
  /opt/homework/experiments/log-time-index/run.py --compiler clang++-18 --output /results/run
```

程序独立生成训练、校准和测试查询，实际校准通过后才批准运行时转换；按Python bisect核对全部结果，分别报告查找、应用主体及完整进程耗时。数据生成不计入应用计时。保存所有原始样本和关闭自对照，已有目录不会覆盖。

原型中范围外查询占95%的假设应在真实请求中进一步验证；应用本身增加范围检查也可能消除对应工作，本实验没有证明BOLT优于该算法改写。

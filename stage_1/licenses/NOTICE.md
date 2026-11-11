# 第三方代码与先例

LLVM/BOLT 基于 LLVM Project，固定提交 `3bd152ddbb6df45e0e07d6c9e9eb1573dcfd3dc6`。

- 上游：https://github.com/llvm/llvm-project
- 许可证：Apache License 2.0 with LLVM Exceptions，原文保留于 [LLVM.txt](LLVM.txt)。patch 保留原 LLVM 文件的许可声明。
- Docker 构建时获取完整上游及其许可，不将完整 LLVM 源码复制进本仓库。

固定主线 BOLT 的 CMOVConversion 处理条件分支转 CMOV；LLVM X86 后端已有相反方向的转换。本项目新增的是固定版本 BOLT 中的反向 Pass、谓词采样及准入工程，不声称发明了 CMOV 转分支理论。

本仓库为课程第一阶段材料。新增脚本、负载和运行时原型的贡献与 AI 使用情况见根目录 README 和设计文档。

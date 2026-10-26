# 已验证接口与排版经验

这些记录来自维护者的实际工程核验，用于说明方法与局限，不包含客户工程或本机私有路径。

## 验证环境

原生验证使用 Altium Designer Enterprise 26.4.1。基础 RC 示例完成创建、保存、编译、逐引脚网表比较和原生导出，8 个物理引脚的同网关系一致；编译为 0 错误、4 条警告。复杂器件、PCB 与其他版本需要分别核验。完整公开说明见仓库 docs/VALIDATION.md。

EXE 的泛化 VersionInfo 与软件实际版本可能不同，运行前核对应用版本、原生接口与库。现有项目只在副本上试验，保留原始资料和未保存会话。

## 排版与连接经验

- 直接平移拼接旧功能区，再扩大画布，容易出现松散、空白和碎片化。应先校准芯片轮廓、字高、外围锚点与功能阅读顺序。
- 字框未重叠仍可能贴线或挨引脚号过近，须看文字、导线、符号和连接点之间的实际留距。
- 显示圆点不能单独证明导通。原生网表曾发现连续交叉线的预期连接被分开；显式分段共享端点后才与独立检查一致。
- 磁盘文件修改后，同名旧文档可能仍在内存。新副本重开，核对完整路径与哈希，再看真实导出。
- 格式、数量或边界检查不能代替实际审图，也不能证明电路设计或 PCB 制造可用。

## 原生与资料来源

- [符号与引脚](https://www.altium.com/documentation/altium-designer/components-libraries/creating-schematic-symbol)。
- [原理图连接与作用域](https://www.altium.com/documentation/altium-designer/schematic/creating-circuit-connectivity)。
- [Workspace Manager API](https://www.altium.com/documentation/altium-dxp-developer/workspace-manager-api)。
- [F28035 数据手册](https://www.ti.com/lit/ds/symlink/tms320f28035.pdf)，仅在选用对应芯片时读取。
- [TPS73 数据手册](https://www.ti.com/lit/ds/symlink/tps73.pdf)，仅在选用对应稳压器时读取。

此前 Context7 检索未得到对应官方符号和 Workspace 库。第三方脚本或格式解析库仅可作线索，接口判断以当前官方文档、本机示例和原生结果为准。

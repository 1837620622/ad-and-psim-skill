# 原生操作与电气检查

## 本机预检

先确认实际进程版本和可执行文件。文件 VersionInfo 可能只写产品代号，必要时查看 AD 的实际关于窗口或可靠运行信息。检查原工程的 SchDoc、SchLib、IntLib、PrjPcb 和引用路径，不自动假定外部库已经嵌入。

先读现有符号，确认引脚号、名字、电气类型、方向、热端、隐藏脚、分部件和显示模式。用户要求完整芯片时把物理引脚完整保留在一个有效符号中，不用多个看似芯片的矩形代替。

## 修改连接与属性

- 位号、Comment、数值使用关联文字；改变参数后重新读取并导出，不能再放一段静态文字盖住旧值。
- 线必须连到引脚热端。标号的电气锚点必须在线或热端上；文字视觉上在线上方不代表锚点可以偏离导线。
- 同页同名标号可建立连接；跨页行为受项目 Net Identifier Scope 控制。不要把全局网络名无条件替代层次端口。
- 区分真正连接、单纯交叉和 NC。不要把所有几何相交都判为导通，也不要给所有未连接脚批量加免责标记。
- 合并连续导线以减小多余折点，但不得抹掉真实分支。对必要的四向连接，在交点处分段让电气端点重合，并在 AD 中复核；也可重排成两个相邻 T 形连接。
- 避免横穿芯片文字、参数、其它引脚或电源符号。移动网络名后，必要时延长它所属的线，并复查是否意外碰到相邻网络。

## 完整芯片的功能检查

逐类检查供电与去耦、内部稳压条件、上电/复位、启动绑带、时钟、调试、ADC 基准、数字/模拟电平和保护输入。芯片型号接近不代表引脚或供电可互换。

F28035 个案中需要分别确认 VDDIO、VDDA、VDD 和 VREGENZ，不能为照抄参考把核心电源接到 3.3V。GPIO34 的启动上拉不能仅依赖运行 LED。复位上拉、稳压器 EN 极性及输出稳定性须查对应器件手册。这些检查项可复用，数值不可无条件复用。

对于驱动与采样，分别检查信号电平、隔离供电、回流、相别、保护极性和同名端。原理图的零错误不能证明选型、隔离距离、功率损耗或 PCB 安全要求已满足。

## API 的使用边界

优先当前版本支持的原生接口、库编辑与 UI。直接读写 SchDoc 二进制格式属于需单独验证的路线；文件头正确不代表所有属性与编译语义正确，不能作为默认批量改图捷径。

本机已验证过的 Workspace 访问方式如下，使用前仍须核对目标版本与对象接口：

```pascal
Workspace := GetWorkspace;
Workspace.DM_OpenProject(Requested, True);
Project.DM_SetAsCurrentProject;
Cancelled := False;
Ok := Project.DM_CompileEx(True, Cancelled);
```

`Project` 必须从 Workspace 返回对象中按完整路径匹配获取，不能假设当前对象就是目标。`DM_CompileEx` 的 All 参数可能涉及其它已打开工程，执行前识别工作区，避免把其它项目消息混入本项目结论。只统计目标工程的 violations，消息面板单独记录。

编译后通过 `IDocument` 的 `DM_NetCount/DM_Nets`，以及 `INet` 的 `DM_PinCount/DM_Pins` 获取原生连接。每个 `INetItem` 读取 `DM_PhysicalPartDesignator` 和 `DM_PinNumber`，不要把它与 `ISch_Pin` 的接口属性混用。

如果接口返回失败、取消或统计像旧缓存，确认目标文档已加载，使用保存后的新副本重新验证。先保留已完成结果，定位同一失败的原因，不无限循环试猜 API。

## 来源

- [官方元件符号创建](https://www.altium.com/documentation/altium-designer/components-libraries/creating-schematic-symbol)：符号、引脚、分部件与显示模式。
- [官方原理图连接](https://www.altium.com/documentation/altium-designer/schematic/creating-circuit-connectivity)：热端、网络标号、作用域和连接点。
- [官方 Workspace Manager API](https://www.altium.com/documentation/altium-dxp-developer/workspace-manager-api)：编译与原生网络对象。

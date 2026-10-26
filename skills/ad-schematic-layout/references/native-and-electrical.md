# 原生操作与电气检查

## 开始前

- 确认 AD 的实际版本：EXE 的文件版本信息可能只写产品代号，以"关于"窗口或 `env` 为准。
- 检查工程引用的 SchDoc、SchLib、IntLib、PrjPcb 路径；外部库不一定已嵌入。
- 先读现有符号的引脚号、名称、电气类型、方向、热端、隐藏脚、多部件和显示模式。要求完整芯片时，全部物理引脚放在一个有效符号里，不用几个方框拼凑。
- 现有工程只在副本上试验，不覆盖用户未保存的会话。

## 改连接与属性

- 位号、注释、数值用关联属性。改值后重新读回和出图，不要另放静态文字盖住旧值。
- 导线连到引脚热端；标号的电气锚点在线上或热端上。
- 同页同名标号相连；跨页按工程的 Net Identifier Scope 决定，不要把全局网络名当成层次端口的替代。
- 分清真正的连接、单纯交叉和 NC。不要把几何相交都当导通，也不要给所有空脚批量加 No ERC。
- 合并连续导线可以，但不能抹掉真实分支。必要的四向连接在交点处分段，让端点重合，再在 AD 里复核；更好的做法是改成两个错开的 T 形。
- 移动网络名后，必要时延长它所在的线，并确认没有碰到相邻网络。

## 完整芯片的功能检查

逐项核对：供电与去耦、内部稳压条件、上电复位、启动绑带、时钟、调试口、ADC 基准、数字/模拟电平、保护输入。型号相近不代表引脚或供电可以互换。

例如 F28035 要分别确认 VDDIO、VDDA、VDD 和 VREGENZ，不能为了照抄参考把核心电源接到 3.3 V；GPIO34 的启动上拉不能只靠运行指示灯；复位上拉、稳压器 EN 极性按对应器件手册确认。这些检查项可以复用，数值不能照搬。

驱动和采样电路分别检查信号电平、隔离供电、回流、相序、保护极性和同名端。原理图 0 error 不能证明选型、隔离距离、损耗或 PCB 安全要求已经满足。

## AD API

优先用当前版本支持的原生接口、库编辑器和界面操作。直接改 SchDoc 二进制只适用于本生成器能表达的基础图元；文件头正确不代表属性和编译语义都正确，不要用它批量改带库图形的原生图纸。

已在本机验证过的工程访问方式（换版本前仍要核对接口）：

```pascal
Workspace := GetWorkspace;
Workspace.DM_OpenProject(Requested, True);
Project.DM_SetAsCurrentProject;
Cancelled := False;
Ok := Project.DM_CompileEx(True, Cancelled);
```

- `Project` 从 Workspace 返回的工程里按完整路径匹配，不假设当前工程就是目标。
- `DM_CompileEx` 的 All 参数可能编译工作区里其他打开的工程；只统计目标工程的 violations。
- 编译后用 `IDocument.DM_NetCount/DM_Nets` 和 `INet.DM_PinCount/DM_Pins` 读连接；每个 `INetItem` 读 `DM_PhysicalPartDesignator` 和 `DM_PinNumber`。不要和 `ISch_Pin` 的属性混用。
- 接口返回失败、取消或像旧缓存时，确认目标文档已加载，用保存后的新副本重试；同一个错误不要无休止地换着 API 猜。

## 来源

- [元件符号创建](https://www.altium.com/documentation/altium-designer/components-libraries/creating-schematic-symbol)：符号、引脚、多部件与显示模式。
- [原理图连接](https://www.altium.com/documentation/altium-designer/schematic/creating-circuit-connectivity)：热端、网络标号、作用域和连接点。
- [Workspace Manager API](https://www.altium.com/documentation/altium-dxp-developer/workspace-manager-api)：编译与网络对象。

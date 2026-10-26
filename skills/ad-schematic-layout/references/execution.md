# 原生执行入口

相对命令从本技能目录运行，实际软件路径由本机预检给出；下面的 AD_EXE 是占位变量，不是可直接执行的安装路径。完整实机例子在 local-evidence.md。

## 自然语言转为可执行任务

先把描述转为范围、器件与真实引脚、预期网络、参考图布局锚点和交付目录。参考优先明确到功能区相对位置、芯片长宽与字号、外围间距、图框和阅读顺序。新建先建立一个代表性局部并原生导出，确认风格再扩展；无需反复重做已核验部分。

| 操作 | 命令 |
|---|---|
| 排版预检与草图 | `python scripts/check_layout.py assets/rc-filter-plan.json --preview work/draft.png --output work/layout.json` |
| 基础原生创建 | `python scripts/native_ad.py create assets/rc-filter-plan.json work` |
| 原生编译与逐引脚检查 | `python scripts/native_ad.py --ad-exe AD_EXE --report verify.json verify work/RC_Filter.PrjPcb verify-out --expected work/expected.json` |
| 原生完整出图 | `python scripts/native_ad.py --ad-exe AD_EXE --report export.json export work/RC_Filter.SchDoc preview` |
| 执行本地原生脚本 | `python scripts/native_ad.py --ad-exe AD_EXE run-script edit.pas Main` |

`--timeout` 是等待 AD 状态的时限。超时先查看原生脚本面板和当前软件状态，不以旧文件当作成功，不反复启动相同任务。

`create` 先在内存中生成图纸并运行与 `check_layout.py` 相同的预检，存在 error 时不写文件，并在输出目录写出 `layout-check.json`。`--allow-layout-errors` 只用于定位问题，不能用于交付。预检、`verify` 与 `export` 的判定顺序见[排版硬规则](drafting-rules.md)。

## 基础计划格式

[可运行 RC 计划](../assets/rc-filter-plan.json)按排版硬规则编排：常规接插件比例、就近地符号、无浮动标题，预检 0 error、0 warning，可作为小电路的起点。

- `units: "10mil"`，`canvas: [width,height]`；坐标向右、向上。可选 `grid`（默认 10）与 `font`（默认 1，即 9 pt Times New Roman，全图器件文字共用）。原生纸张选项以实际导出为准。
- `parts` 中 R/C/L/Y 接受 ref、value、at、vertical；`symbol_scale` 默认 0.5，只调符号几何，热端始终落在栅格上，文字保持完整字高。中心点 at 须在栅格上。
- `kind: "component"` 接受 body 矩形和真实 pins。每脚含 number、name、at、direction（right/up/left/down）和 electrical；at 是符号边界，实际热端由 `pin_length`（默认 20）确定。
- 位号与注释默认放在器件外：两脚件横放时叠放在上方、竖放时在右侧；芯片和接插件的位号在框上方、注释在框下方。需要时用 `designator_at`、`comment_at` 覆盖。
- 通用芯片矩形可用于符合厂商引脚定义的 IC 或连接器，不能把需要专用图形和模型的开关、放大器等都画成方框。
- `wires` 每条是折线路径，点可写 `"R1.1"` 指真实引脚热端，或写坐标。保持正交；多路交点显式分段并原生核对连接。
- `labels` 为 name、at；`power_ports` 为 name、at、ground 和可选 orientation，at 可直接写引脚如 `"C1.2"`，地符号默认朝下。texts 仅用于必要说明，不代替关联位号或参数；标题写进图签。
- `pin_map` 为物理引脚到预期网络的字典，输出 expected.json。它应来自独立设计意图，不根据原生结果反向改写以求通过。

基础生成器写出可编辑 SchDoc 和 PrjPcb；它是基础图元通路，必须原生重开、编译和审图。它不生成 SchLib、封装或 SPICE 模型，也不保证所有 AD 版本或扩展属性保留。

## 复杂电路与已有图整理

复杂器件优先使用本机核实的原生库与 AD API，必要时界面补齐。已有 SchDoc 的移动与属性修改通过原生对象/API处理，保留原有库关联、参数、隐藏引脚和嵌入资源。不要用只覆盖基础图元的写入器把已有工程整份重写。

`run-script` 不限制绘图语言的上游生成方式。执行前检查本地 DelphiScript 的目标文档与修改范围；脚本写出包含 Complete 的状态文件，路径使用字符串占位 `__STATUS__`，启动器替换为隔离临时目录。失败时写出 `Failed=原因` 行，启动器会立即报错而不是等到超时。最小完成协议：

```pascal
Procedure Main;
Var Status : TStringList;
Begin
    { Perform verified native edits before reporting completion. }
    Status := TStringList.Create;
    Status.Add('Complete');
    Status.SaveToFile('__STATUS__');
    Status.Free;
End;
```

该最小示例只说明完成协议，不代表已绘图。中文参数通过 UTF-16 输入文件传递，脚本本体使用 ASCII，避免本机脚本解释器编码差异。

verify 在副本上执行，保留源文档；当前原生 Workspace 编译调用可能触及其他已打开工程，报告按目标文档筛选，不能把它描述成工作区其他工程均通过。脚本和真实原始日志保留在报告中的 job 目录。export 使用原生 RedrawToDC，EMF 只修正容器物理尺寸字段，绘图记录保持；PNG 是完整原生导出的渲染。结果中的 `text_review` 是对原生 EMF 的文字重叠、越界和压线审查。生成预览不等于图面验收，仍须全图和局部实际查看。

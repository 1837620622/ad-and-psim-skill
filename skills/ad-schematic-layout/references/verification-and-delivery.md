# 核验与交付

## 每一层证明什么

| 层面 | 证据 | 不能据此声称 |
| --- | --- | --- |
| 文件 | 原生能打开，引用路径和库可用 | 电路正确 |
| 连接 | 原生编译、逐引脚网表与预期一致 | PCB 或实物合格 |
| 图面 | 原生全图、关键局部、打印尺寸下可读 | 器件额定值或制造检查已完成 |
| 交付 | 清单与 SHA-256 一致，Windows 上能复开 | 其他软件版本也兼容 |

Error、Fatal、Warning 和取消状态分开统计。0 error 不能写成 0 warning，也不能靠关闭报告级别制造"通过"。只做原理图时可以说明封装缺失的边界；有 PCB 制造要求时必须处理封装和焊盘映射。

保存后用新副本重开工程，避免同路径的旧文档还留在内存里；副本要包含工程和全部引用，不只是一个 SchDoc。

## 逐引脚网表比较

原生网表每行三个字段：`网络名|位号|引脚号`。

```text
+3V3|U1|29
+3V3|C1|1
DGND|C1|2
```

预期网表也可以写成 JSON：`{"pin_map": {"U1.29": "+3V3", "C1.1": "+3V3", "C1.2": "DGND"}}`。

```text
python scripts/compare_pin_nets.py expected.json nets.txt --output check.json
```

比较的是每个引脚的同网伙伴，所以自动生成的网名变化不算差异；缺脚、多脚、合网、断网都会失败，同一引脚出现两次直接报错。工具不会判断某个连接本该不该存在，预期网表必须来自设计意图，不能从待检网表复制。

## 出图审查

`export` 的结果里有 `text_review`，内容来自 `review_emf_text.py` 对原生 EMF 的检查：

```text
python scripts/review_emf_text.py drawing.emf --output text-review.json
```

它报告文字重叠、文字越出边界（可用 `--border` 指定 EMF 设备坐标的图框），以及被导线、引脚、器件轮廓或圆形穿过的文字。线条按 EMF 映射模式换算，并用记录自带的范围核对换算是否可靠。圆弧、器件遮挡、参数对错和视觉重心不在检查范围内。

工具通过后仍要人工看图：

1. 全图：阅读顺序、密度、留白、图框边界。
2. 每个功能区：器件、位号、参数、短线。
3. 芯片长引脚名、引脚号和网络名之间的间隔；晶振、复位、电源等局部。
4. 重复通道的对应关系和隔离回流。
5. 图片和工程是不是同一版本，实际打印尺寸下能不能看清。

需要软件截图时用 `screenshot` 截真实窗口，保留原图；不要给导出图或渲染图套假的软件界面。

## 交付

```text
python scripts/native_ad.py deliver work/ delivery/ --name 项目名 --clean
```

`delivery/项目名/` 是给客户的目录，保持原来的相对路径，只放 PrjPcb、SchDoc、库文件和正式图纸（原生导出的 PDF、PNG、SVG、EMF）。`export` 时把图写进工作目录（例如 `work/drawing/`），`deliver work/` 才会带上。

硬性规则：计划和报告 JSON、脚本（`.py`、`.pas` 等）、批处理、日志、压缩包是制作过程中的文件，一律不进客户目录，`--include` 也放不进去；文件名带 `draft`、`.render`、`preview` 的图和 `preflight/` 目录也不交付。结果里的 `delivered` 和 `not_delivered` 分别列出放进去和没放进去的文件；用 `--include` 点名的过程文件也会被拒绝，并在 `warnings` 里说明。

- 工作目录里的文件只复制、不移动；不生成压缩包。AD 自动生成的 `History`、`__Previews`、`*.SchDocPreview` 不复制。
- `--clean`：交付后删除工作目录里的缓存（`__Previews`、`*.SchDocPreview`、`*.PrjPcbStructure`、`__pycache__`、`Thumbs.db` 等，AD 和 Python 会自动重建），不删 History 备份和 `*.bak`。
- `--archive`：需要自己留底时，另写 `delivery/项目名-archive/`，放过程文件和 `manifest.json`（每个文件的 SHA-256）。
- `--include`：额外要交付的文件（如说明文档）；`--dry-run` 先看会交付哪些文件。

交付前在 Windows 上从客户目录重新打开工程，确认引用都在。

最终说明写清：实际验证的软件版本、error 与 warning 数、未完成的范围。没有用户同意不要清理历史交付。

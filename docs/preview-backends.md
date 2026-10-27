# Mac 预览后端 / Mac preview backends

## 选择依据 / Choice

| 包 / Package | 作用与平台 / Scope and platforms | 本项目处理 / Integration |
| --- | --- | --- |
| [resvg-py](https://pypi.org/project/resvg-py/) | SVG → PNG；Python 3.10+；macOS Intel、Apple Silicon；MIT | 已加入可选依赖并实测，安装后自动用于便携 PNG；不解析 SchDoc/psimsch，不求解电路 |
| [altium-monkey](https://pypi.org/project/altium-monkey/) | 专用 Altium 解析与预览；`native_altium()` 样式；Python 3.12–3.14；AGPL-3.0-or-later | 已隔离评测，未并入商业项目依赖；当前完整依赖支持 Apple Silicon Mac，Intel Mac 受 [wn-geometer](https://pypi.org/project/wn-geometer/) 的平台轮子限制 |
| [skia-python](https://pypi.org/project/skia-python/) | 通用绘图引擎，有 macOS 两架构轮子 | 不提供原生 AD/PSIM 的符号、字体规则或求解器，仅更换画笔不能保证原图一致 |
| [CairoSVG](https://cairosvg.org/documentation/) | SVG → PNG/PDF，另需 Cairo 环境 | 本项目没有采用；同样不解析这两种原生工程 |

评测使用本项目自建 RC 图，比较了 `altium-monkey` 默认及 `native_altium()` 样式、本项目 resvg 与 Pillow 输出。统一尺寸后，每种便携输出仍与 Windows 原生图存在像素差异。白色背景占比很大，不把全图平均误差包装成“一致率”。

`resvg-py` 的优点是可固定 SVG 输入和允许加载的字体，减少平台绘图差异；它不会补出生成器尚未支持的原生图元。本项目没有找到经过验证、能在 Mac 上通用复现 PSIM 图纸与求解结果的 pip 包；名称相似的统计包不能当作 Altair PSIM。

The RC evaluation found pixel differences for every portable renderer. `resvg-py` is the optional raster backend, not an Altium/PSIM parser or solver. The AD-specific `altium-monkey` candidate remains separate because its license and full dependency platform support need to be considered before integration.

## 使用 / Usage

```bash
python -m pip install -r requirements-optional.txt
python skills/ad-schematic-layout/scripts/native_ad.py render plan.json preview.png --renderer resvg
python skills/psim-simulation-layout/scripts/native_psim.py render plan.json preview.png --renderer resvg
```

只需 PNG 便携渲染时也可单独安装 `resvg-py==0.5.0`；Windows 原生 EMF 转 PNG 使用 Python 3.11+ 和 Pillow 13。Python 3.10 的可选依赖只安装 resvg，避免选取带已知漏洞的旧 Pillow。`--renderer pillow` 保留旧后端，SVG 输出只用标准库。

两端拥有相同、可合法使用的字体时，可显式指定：

```bash
python skills/ad-schematic-layout/scripts/native_ad.py render plan.json preview.png --renderer resvg --font-dir ./fonts --no-system-fonts
```

`--font-file` 和 `--font-dir` 都可重复。禁用系统字体时必须提供字体；目录中应包含所需的 Times New Roman/Arial 或明确采用的替代字体，以及必要的中文字体。字体文件不随项目分发。结果 JSON 记录后端、是否加载系统字体与显式文件哈希。目录内容和系统字体变化仍会影响输出，提供目录不等于已证明字体完全相同。字体选项仅用于 resvg PNG；SVG 由打开它的查看器加载字体。

Explicit font files/directories and `--no-system-fonts` reduce uncontrolled font fallback. Fonts are not distributed with this project. Hashes cover explicit font files; directory contents and system fonts are not claimed to be identical across computers.

## 原生一致性 / Native identity

新图的离线预览仍是近似。要求看到实际软件图面时，用 [handoff / receive](../skills/ad-schematic-layout/references/mobile-workflow.md)：Windows 原软件出图和求解，Mac 接收相同字节的 PNG、SMV、CSV。接收器不重新画图或模拟另一个求解器。同一图片文件的显示缩放与屏幕色彩管理仍由查看设备决定。

For native results, Windows runs the actual applications. Mac receives the original PNG and simulation data without redrawing or recalculating them. Identical file bytes do not promise identical monitor scaling or color management.

接口依据：[resvg API](https://resvg-py.readthedocs.io/en/latest/api.html)、[resvg 许可](https://github.com/baseplate-admin/resvg-py/blob/master/LICENSE)、[altium-monkey 源码与字体说明](https://github.com/wavenumber-eng/altium_monkey)。

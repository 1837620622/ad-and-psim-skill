# Mac/Linux 准备、Windows 原生执行、再接收回来

Mac/Linux 不用安装 AD 或 PSIM。计划、预检、基础 AD 文件、离线预览、任务交接和结果接收均可在 Mac/Linux 完成；原生编译、图纸和仿真由装有相应软件的 Windows 电脑完成。

## 两种预览

| 文件或字段 | 来源 | 一致性 |
| --- | --- | --- |
| `preview.render.svg/png` | 便携绘图器（任何系统） | 用来检查布局；字体和未标定器件可能与原生软件不同 |
| `receive` 返回的 `png` | Windows 原生导出 | 与 Windows 原图 SHA-256 相同，接收端直接显示，不再渲染 |

需要确认软件实际打开的图面时，查看第二种图。没有经过 Windows 的新计划只能提供近似预览，不能将它宣称为任意原生库元件的精确图像，也不能在 Mac/Linux 上冒充 PSIM 求解结果。

## 准备任务

在所选技能目录运行，对应选择 AD 或 PSIM 的命令：

```text
python scripts/native_ad.py handoff assets/rc-filter-plan.json work/job-ad
python scripts/native_psim.py handoff assets/rc-filter-plan.json work/job-psim --name RC_Filter
```

`--name` 支持英文、中文、数字、下划线和短横线。参数文件、子电路依赖等用 `--include params.txt` 显式列出；文件须位于计划所在目录内，可使用相对的子目录。通过 MCP 提供依赖时，使用真实计划文件路径。

任务目录含有：

```text
job/
├── input/plan.json         # 本次实际执行的计划，含哈希
├── tool/scripts/           # 自带执行工具，不含 AD/PSIM 运行时
├── tool/references/native/ # AD 的原生脚本（PSIM 不需要）
├── prepared/               # 准备端生成的 SchDoc/PrjPcb（仅 AD）
├── preview.render.svg      # 离线近似预览；有 resvg-py 或 Pillow 时另生成 PNG
├── native-request.json     # 输入和工具文件清单
├── README.txt
└── run.bat
```

任务目录需要为空；预检有 error 时不生成任务。原始计划不会被覆盖。AD 带模型关联或基础生成器无法无损表达的图元仍应在 Windows 原生编辑；导入器会报告无法表示的内容。

## Windows 执行

将整个目录复制到 Windows。需要 Python 3.11+、Pillow 13 和相应的已授权软件；不需要克隆仓库。双击 `run.bat`，也可运行：

```text
python tool/scripts/native_job.py run . --timeout 600
```

安装位置支持 Windows 卸载注册表和常见目录自动查找。找不到时，通过 `AD_EXE` 指定 X2.EXE 或通过 `PSIM_DIR` 指定 PSIM 安装目录，也可传 `--ad-exe` / `--psim-dir`。这些配置只用于执行端，准备端不需要。

- AD：生成新副本，核对与准备端生成的 SchDoc 字节相同，原生编译；给定 `pin_map` 时比较逐引脚同网关系，再原生导出并检查文字。
- PSIM：用实际 API 建模，原生求解，保留 SMV 与 CSV，再原生导出并检查文字。
- 任何原生阶段失败都返回非零状态；`text_review.passed=false` 也算失败。失败结果留在原目录供诊断，不能作为已通过结果接收。
- 原生执行写入新的 `native-results/`，已有非空目录不会被覆盖。修改计划后准备新任务目录，避免混入旧结果。

## 接收原图与原始结果

将 Windows 的 `native-results/` 目录传回准备任务的电脑，运行：

```text
python scripts/native_ad.py receive work/job-ad work/returned-ad work/final-ad
python scripts/native_psim.py receive work/job-psim work/returned-psim work/final-psim
```

第一项是准备端保留的原任务，第二项是返回的结果目录，第三项是新的接收目录。接收器验证请求、计划与每个文件的 SHA-256，拒绝不匹配的任务、修改过的文件、失败结果和越界路径。

返回 `native_verified=true`、`preview_bytes_identical=true` 与图片路径 `png`。原生 PNG、工程、SMV/CSV 都按字节复制；不换字体，不缩放重绘，不插值原始波形。清单证明对应关系和传输完整性，工程与物理结论仍按实际模型和软件版本核对。

## 比较结果

两项技能都可运行 `compare`，无需厂商软件：

```text
python scripts/native_ad.py compare reference.SchDoc received.SchDoc
python scripts/native_psim.py compare reference.csv candidate.csv --waveforms
python scripts/native_psim.py compare reference.csv candidate.csv --waveforms --atol 1e-8 --rtol 1e-6
```

| `equivalence` | 含义 |
| --- | --- |
| `byte_identical` | 文件 SHA-256 相同 |
| `numeric_equal` | 文本序列化不同，所比较的时间与信号数值完全相等 |
| `within_tolerance` | 在显式给定的容差内相符，仍有数值差异 |
| `different` | 时间网格、样本数量或信号不相符 |

默认比较完整列集合，容差为零，不插值或平滑；独立设置 `--time-atol` 才允许时间舍入差异。用 `--signal` 限定列时，结果会注明只比较了部分信号。比较器不运行求解器，也不证明没有提供的工况。

MCP 对应工具为 `ad_handoff` / `psim_handoff`、`ad_receive` / `psim_receive` 和 `ad_compare` / `psim_compare`。

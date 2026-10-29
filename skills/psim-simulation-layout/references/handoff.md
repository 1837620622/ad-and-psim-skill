# Mac/Linux 准备、Windows 原生执行、再接收回来

Mac/Linux 不用安装 AD 或 PSIM。计划、预检、基础 AD 文件、离线预览、任务交接和结果接收均可在 Mac/Linux 完成；原生编译、图纸和仿真由装有相应软件的 Windows 电脑完成。

## 两种预览

| 文件或字段 | 来源 | 一致性 |
| --- | --- | --- |
| `preview.render.svg/png` | 仿原生渲染（任何系统） | PNG 按原生导出标定：RC 示例与原生图尺寸相同，线条和文字像素 97% 以上在 1 像素内对齐；未标定的 PSIM 元件画成方框 |
| `receive` 返回的 `png` | Windows 原生导出 | 与 Windows 原图 SHA-256 相同，接收端直接显示，不再渲染 |

需要确认软件实际打开的图面时，查看第二种图。没有经过 Windows 的新计划只有预测图，不能宣称为任意原生库元件的精确图像，也不能在 Mac/Linux 上冒充 PSIM 求解结果。

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
├── preview.render.svg      # 离线预览；有 Pillow 时另生成仿原生 PNG
├── preflight/              # 离线预测：预检报告、仿原生预览、PSIM 离线预仿真 presim.csv
├── reference/              # 仅 PSIM 且给了 --reference：用来对照的原始文件
├── native-request.json     # 输入和工具文件清单
├── README.txt
└── run.bat
```

任务目录需要为空；预检有 error 时不生成任务。原始计划不会被覆盖。AD 带模型关联或基础生成器无法无损表达的图元仍应在 Windows 原生编辑；导入器会报告无法表示的内容。

## Windows 执行

将整个目录复制到 Windows。需要 64 位 Python 3.11+、Pillow 13（`py -3 -m pip install Pillow==13.0.0`）和相应的已授权软件；不需要克隆仓库。缺少 Pillow 时 `run` 在启动软件之前就停下。双击 `run.bat`，也可运行：

```text
python tool/scripts/native_job.py run . --timeout 600
```

安装位置支持 Windows 卸载注册表和常见目录自动查找。找不到时，通过 `AD_EXE` 指定 X2.EXE 或通过 `PSIM_DIR` 指定 PSIM 安装目录，也可传 `--ad-exe` / `--psim-dir`。这些配置只用于执行端，准备端不需要。

- AD：生成新副本，核对与准备端生成的 SchDoc 字节相同，原生编译；给定 `pin_map` 时比较逐引脚同网关系，再原生导出并检查文字。
- PSIM：用实际 API 建模，原生求解，保留 SMV 与 CSV，再原生导出并检查文字。
- 任何原生阶段失败都返回非零状态；`text_review.passed=false` 也算失败。失败结果留在原目录供诊断，不能作为已通过结果接收。
- 原生执行写入 `native-results/`。失败时窗口停住显示原因（设置 `NATIVE_NO_PAUSE` 不停）；改好原因后直接再双击 `run.bat`，上次未通过或中途停下的结果改名为 `native-results.failed-N` 保留。已通过的结果不会被覆盖。修改计划后准备新任务目录，避免混入旧结果。

## 与原始文件对照（PSIM）

要求仿真结果和用户的原始模型或原始结果一模一样时，准备任务或构建包时用 `--reference` 带上原始文件：

```text
python scripts/native_psim.py handoff plan.json work/job-psim --name RC_Filter --reference 原始模型.psimsch
python scripts/native_psim.py package plan.json work/kit --name RC_Filter --reference 原始结果.csv
python scripts/native_psim.py simulate 新模型.psimsch work/result --reference 原始模型.psimsch
```

- 给 psimsch：在 Windows 上用同样的参数另行求解原始模型（放在临时目录，用完删除），再与新模型的 `native.csv` 对照。
- 给 CSV：直接与它对照，不重新求解。
- 对照规则与下面的 `compare --waveforms` 相同：零容差，比较全部列，时间网格和样本数量都要相同；SIMVIEW 按固定位数导出的 CSV 按它写出的位数逐位比较（`printed_digits_equal`）。
- 结果写在 `reference`：`passed`、`equivalence`，数值不同时 `first_mismatches` 列出最先几处差异，列不一致等无法逐点比较时 `reason` 说明原因。不一致时 `simulate` 返回 1，`build` 和 `run` 都算失败，`receive` 也不接收。
- 原始文件只用来对照：不进 `input/`、不随结果返回、不进客户交付目录。

## 接收原图与原始结果

将 Windows 的 `native-results/` 目录传回准备任务的电脑，运行：

```text
python scripts/native_ad.py receive work/job-ad work/returned-ad work/final-ad
python scripts/native_psim.py receive work/job-psim work/returned-psim work/final-psim
```

第一项是准备端保留的原任务，第二项是返回的结果目录，第三项是新的接收目录。接收器验证请求、计划与每个文件的 SHA-256，拒绝不匹配的任务、修改过的文件、失败结果和越界路径。

返回 `native_verified=true`、`preview_bytes_identical=true` 与图片路径 `png`。返回清单的 `forecast` 记录离线预测和原生结果的对照：AD 是预计与实际的编译 warning 数（`match`），PSIM 是离线预仿真与 PSIM 波形在同一时间点上的最大偏差（容差 1e-3）；对照只作记录，不影响原生结果是否通过。原生 PNG、工程、SMV/CSV 都按字节复制；不换字体，不缩放重绘，不插值原始波形。清单证明对应关系和传输完整性，工程与物理结论仍按实际模型和软件版本核对。

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
| `printed_digits_equal` | 参考 CSV 每个数都按同样的有效位数写成科学计数（SIMVIEW 导出的样式），候选数值按这个位数写出后与参考逐位相同；其他写法的 CSV 不放宽 |
| `within_tolerance` | 在显式给定的容差内相符，仍有数值差异 |
| `different` | 时间网格、样本数量或信号不相符 |

默认比较完整列集合，容差为零，不插值或平滑；独立设置 `--time-atol` 才允许时间舍入差异。用 `--signal` 限定列时，结果会注明只比较了部分信号。比较器不运行求解器，也不证明没有提供的工况。

MCP 对应工具为 `ad_handoff` / `psim_handoff`、`ad_receive` / `psim_receive` 和 `ad_compare` / `psim_compare`。

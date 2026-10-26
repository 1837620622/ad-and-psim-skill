# 物理参数、损耗与测量口径

## 参数表的四种身份

分别列明设计值、工程假设、原生模型输入和实际仿真测量；硬件实测另列。输入电压范围、寄生、器件压降和 ESR 若是工程假设，不写成任务书要求或器件实测。

对于开关与磁性元件，至少核对本次指标涉及的导通电阻、二极管压降/电阻、绕组铜阻、漏感、励磁电感、饱和和电容 ESR。具体需要哪些取决于模型层级，不能为效率好看而隐藏已知损耗。

## 变压器折算

先读所选原生模型对每个 R、L 字段的定义。字段名写 secondary 并不保证它接受实际副边值。对于规定折算到原边的阻抗，定义 `n=Np/Ns` 后：

```text
R_secondary_referred_primary = n² × R_secondary_physical
L_secondary_referred_primary = n² × L_secondary_physical
```

例如 90:9 匝比、实际副边铜阻 0.035Ω，折算到原边为 3.5Ω。若字段本来接受实际副边值，则直接输入 0.035Ω；不能再折算一次。多绕组模型还要确认是参考第一个原边还是其它绕组。

本机 `TF_1F_1` 所在模型说明采用原边参照；随附手册的多绕组章节也要求检查参照侧。新模型、新版本先在简单原生对照电路中用解析关系确认。不能把这一结论扩展到所有 PSIM 变压器。

铜损核对必须使用同一参照侧的电流与电阻。物理副边电流配物理副边电阻；折算电流配折算电阻。漏感能量同样遵循同一口径，避免再乘一次匝比平方。

## 功率和效率

先明确输入与输出测量边界、功率方向和正负号。正向输入取向系统供能为正，输出取向负载供能为正。对 AC 输入，使用瞬时 `v(t)i(t)` 的周期平均，不用电压电流均值相乘。

```text
P_in = ∫v_in(t)i_in(t)dt / Δt
P_out = ∫v_out(t)i_out(t)dt / Δt
ΔE_C = C(V_end² − V_start²)/2
ΔE_L = L(I_end² − I_start²)/2
P_residual = P_in − P_out − ΔE_known/Δt
```

只有稳态、方向一致、边界与损耗模型适用时，才把 `100×P_out/P_in` 称作效率。储能项不完整时，残余功率不能直接全部称为器件损耗；磁化能量、其它储能和未测端口可能仍有贡献。

效率大于 100%、残余功率符号异常或输入功率很小，应先核对方向、窗口、储能、变比和数据分辨率，不能直接截断到 100% 或删除异常点。反向功率和再生工况单独说明。

理想模型接近 100% 不代表实物效率；功能级模型不能证明宽带噪声、全温度、EMI 或样机热性能。热模块参数也要对应器件、工作点和模型限制。

## 波形测量与辅助工具

CSV 必须由原生 Graph/SMV 或受控的 Simview 导出产生。先看表头、单位、编码和 Time 列，确认波形不是独立数值预验证或重绘后的采样数据。

`scripts/analyze_waveform.py` 支持以下输入方式：

```text
python scripts/analyze_waveform.py native.csv --pin Pin --pout Pout --signal Vout --signal Vbus --start 0.3 --end 0.4 --output metrics.json
python scripts/analyze_waveform.py native.csv --vin Vin --iin Iin --vout Vout --iout Iout --fundamental-hz 50 --cycles 5 --end 0.5 --gate Gate --threshold 0.5 --output metrics.json
```

`--time` 默认 Time；列名按真实表头传入。可选 `--capacitor Vbus=0.002` 与 `--inductor IL=0.001` 加入已确认参照侧的已知储能项。SI 单位分别为 F、H、V、A、s；不要直接传带工程后缀的字符串。使用原生功率列时选择 `--pin/--pout`；使用 V/I 列时选择完整四列，不能混合两种口径。

默认只报告功率比；`--steady` 表示调用者已通过相邻周期和储能等检查确认适用稳态效率，不是工具自动认证。门极不足三个上升沿时只报告数据不足。采样间隔输出明确标为输出间隔，不伪装成求解步长。

工具对线性插值段精确计算均值和 RMS；V/I 模式在同段计算乘积积分，避免用均值相乘。它无法恢复稀疏采样漏掉的尖峰或开关事件，测量仍需步长与采样敏感性验证。

## PF、谐波与动态

总功率因数使用 `P_in/(V_rms I_rms)`，不能只把基波相位余弦称为总 PF。辅助工具只有 V/I 模式显式给出 `--ac-input`、`--fundamental-hz` 并使用整周期窗口时才报告 input_total_power_factor；普通 DC 或启动窗口只输出数学功率比，不命名为交流功率因数。THD 说明基波、谐波阶数、去直流、窗口和频谱分辨率。FFT 的时间区间、输出间隔和 Nyquist 范围要与测量带宽相符。

阶跃说明变化时刻、幅度、初态、观察窗口与测量定义。纹波取稳态，瞬态峰值与开关尖峰分别观察；长时间包络不能替代开关细节。

来源：[Altair LLC 损耗应用说明](https://2023.help.altair.com/psim-tut/tutorials/AN007-Power%20Loss%20and%20Efficiency%20Calculation%20of%20Resonant%20LLC%20Converter.pdf) 提供相应损耗建模背景；模型具体字段以当前本机帮助为准。

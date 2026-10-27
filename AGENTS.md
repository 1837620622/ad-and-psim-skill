# AD and PSIM Skill

把自然语言需求做成可编辑的 AD 原理图和 PSIM 仿真模型。处理 AD 任务先读 `skills/ad-schematic-layout/SKILL.md`，PSIM 任务先读 `skills/psim-simulation-layout/SKILL.md`，两者都要读各自的 `references/drafting-rules.md`。任务范围以当前用户要求为准。

## 维护约定

- 每个技能目录自成一体：脚本只引用同目录的模块，复制到任何 Agent 的技能目录都能运行。
- 两项技能共用的 `canvas.py`、`capture.py`、`deliver.py`、`mcp_server.py`、`review_emf_text.py`、`compare_results.py`、`native_job.py`、`native_discovery.py` 各放一份相同的副本，改一处就同步另一处；测试会检查两份一致。
- 脚本核心只用 Python 3.10+ 标准库；Pillow 与 resvg-py 为可选图像后端。代码风格按 `ruff.toml`，提交前运行：

```bash
ruff format skills scripts tests && ruff check skills scripts tests
python -m unittest discover -s tests -v
npx markdownlint-cli2 "**/*.md"
```

- 示例计划必须保持预检 0 error、0 warning；改了示例或生成器，在 Windows 上重新原生验证并更新 `docs/VALIDATION.md` 和 `docs/images`。
- `README.md` 与 `README.en.md` 的功能、命令、授权和验证范围保持一致。文档用 UTF-8，不写日期，不夸大自动化程度，不暗示厂商背书。

## 原生工程与图面

只改排版时保留器件参数和逐端口连接。先看客户或官方参考，再定比例、分区和局部接线；看完整导出和关键区域，不能用自动检查代替看图。仿真结果必须来自实际求解器。

Mac/Linux 上用 `handoff` 准备任务，由 Windows 的 `run.bat` 原生执行，再通过 `receive` 验证接收。原生预览按字节复制，不在 Mac/Linux 重绘。离线便携预览仍是近似图，不声明为原生图或 PSIM 求解。

## 发布与资料

用户的原始工程和本机参考副本不删除。`_核验/`、客户材料、`references/images` 与 `references/professional` 下的本机副本不进 Git。公开参考只放官方链接，示例图片只用自建电路。

推送到 GitHub 须有用户明确指示；推送前检查提交身份、授权声明、链接、语法和待提交文件。本项目为专有商业授权，见 LICENSE；微信 1837620622。不要把第三方内容改称自有或开源授权，不修改全局记忆。

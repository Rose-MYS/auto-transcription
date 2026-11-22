# TASK-002 真人录音的节拍与小节线

- 发布：Claude（cowork-piano-pipeline），2026-11-22
- 验收：Claude 检查结果后向 Rose 汇报
- 状态：待领取（领取后在本文件末尾“领取记录”写上 agent 名和日期）

## 0 规则（必读）

1. 所有文件只放在 `Z:\claude-share\projects\20261120-全自动扒谱\` 下（代码、数据、运行输出、笔记），不要只留在你自己的云端或临时目录。
2. 这是一个独立 git 仓库。从 `claude/cowork-piano-pipeline` 切出自己的分支 `<agent名>/beats-v2`（例如 `antigravity/beats-v2`），只在自己的分支提交。每完成一个阶段 commit 一次。>20MB 的文件不进 git。
   - 如果 git 报 dubious ownership：`git -c safe.directory=* <命令>`，或执行 `git config --global --add safe.directory "%(prefix)///vmware-host/Shared Folders/claude-share/projects/20261120-全自动扒谱"`。
3. 每次修改都生成新文件，不覆盖旧输出：每次运行用新的 `工作文件\runs\<新名字>\`；最终成品放 `最终成品\v2-<日期>\`。
4. 笔记写在 `工作记录\<agent名>-beats-v2.md`（自己的文件，不要改别人的）。
5. 机器很弱：Windows，2 核，4GB 内存，无 NVIDIA GPU，无 ffmpeg。**一次只跑一个重模型**（Transkun 和 beat_this 不要同时跑），长任务放后台并写日志，否则设备会断线。
6. 非商用项目，非商用许可的模型可以用。先查 GitHub 有无现成方案。

## 1 背景

目标：任意钢琴曲 / 单旋律录音 → 干净可用的五线谱（MusicXML）+ 简谱。v1 已跑通（见 `最终成品\v1-20261122\测评报告.md`）：

- 合成音频（L1/L2）：调号、拍号、小节线全对。
- 真人演奏（L3，自由速度）：音符准（F1≈0.99），但**拍号和小节线不准**。原因：v1 只靠音符起音做节拍跟踪。

已验证：CPJKU **beat_this**（final0 检查点）在真人录音上效果很好，但在合成曲上会半速、强拍过密。本任务就是把它正式接入流水线并自动选择节拍来源。

## 2 代码和数据位置

| 内容 | 位置 |
|---|---|
| 流水线代码 | `工作文件\bapu\`（入口 `run_all.py`，核心 `midi2score.py`，节拍 `beats.py`，测评 `evaluate.py`） |
| 测试曲 L1–L3 | `工作文件\test-songs\L1-*`…`L3-*`（audio + answer.mid/musicxml） |
| 测试曲 L4（新） | `工作文件\test-songs\L4-01`…`L4-05`：MAESTRO 真人录音前 90 秒 + ASAP 人工节拍/强拍标注 `beats.json`。由 `bapu\build_asap_set.py` 生成 |
| 运行输出 | `工作文件\runs\<名>\`（report.md、results.json、每首歌的 xml/mid/svg） |
| L3 转写缓存 | `工作文件\runs\dev-02-L3\`（可用 `--midi-cache` 复用，省掉 Transkun 时间） |
| L4 已有运行 | `runs\l4-a-notes`（音符节拍）、`runs\l4-a-bt`（beat_this） |
| v1 成品 | `最终成品\v1-20261122\` |
| Claude 笔记 | `工作记录\cowork-piano-pipeline.md` |

L4 曲目：01 巴赫 C 大调前奏曲 BWV846（4/4）、02 舒伯特音乐瞬间 3（2/4）、03 舒伯特即兴曲 Op.90-2（3/4）、04 莫扎特 K332-1（3/4）、05 肖邦摇篮曲 Op.57（6/8）。

## 3 环境

- 已有 venv：`C:\Users\ClaudeVM2\venvs\bapu`（Python 3.13，CPU）。venv 放 C 盘，因为网络盘导入太慢。
- 重建：在 PowerShell 运行 `工作文件\bapu\setup_env.ps1`（含 torch CPU、transkun `--no-deps`、torchaudio、librosa、music21、mir_eval、verovio、onnxruntime、beat_this）。
- beat_this 检查点 final0（77MB）首次运行自动下载到 `%USERPROFILE%\.cache\torch\hub\checkpoints`。下载不完整会报错，删掉重下。
- 运行（在 `工作文件` 目录下）：

```powershell
$py = "C:\Users\ClaudeVM2\venvs\bapu\Scripts\python.exe"
# L4，用 beat_this 节拍
& $py -m bapu.run_all --songs L4 --out runs\<新名> --mode piano --beats final0
# L3，复用转写缓存，只调谱面
& $py -m bapu.run_all --songs L3 --out runs\<新名> --midi-cache runs\dev-02-L3 --beats final0
# 全量回归
& $py -m bapu.run_all --out runs\<新名> --beats auto   # auto 需你实现
```

`--beats none` 为 v1 行为（从音符推节拍）。节拍结果缓存在每首歌目录的 `beats_audio.json`。

## 4 当前进度（Claude 已完成）

L4 小节线 F-measure（强拍对比 ASAP 标注）：

| 曲目 | 从音符推（v1） | beat_this final0 |
|---|---|---|
| L4-01 巴赫 4/4 | 0.03 | **0.98**（拍 F 0.974） |
| L4-02 舒伯特 2/4 | 0.35 | **1.00**（拍 F 1.00） |
| L4-03/04/05 | 未跑 | 未跑 |

注意：beat_this 训练集可能包含 ASAP/MAESTRO，L4 分数可能偏乐观；Transkun 也是 MAESTRO 训练的。结论要再用 L3（非 MAESTRO）目测验证。

`midi2score.transcribe_to_score(midi, title, triplets, beats_ext, downbeats_ext)` 已支持外部节拍/强拍；`meter_from_downbeats` 由强拍间拍数推拍号。

## 5 要做的事

1. 用 final0 跑完 L4-03/04/05 和 L3 全部，记录拍 F、小节 F、拍号。
2. **自动选择节拍来源**（`--beats auto`）：合成/机械速度的曲子用音符节拍（v1），真人录音用 beat_this。可参考的判据：音符起音的速度规整度、两种来源的一致性、beat_this 速度与音符速度是否成 2 倍关系。不要按文件名或测试集等级判断。
3. 修正 beat_this 的拍级倍频问题（半速/倍速），同时保留它的强拍位置。
4. 复合拍子（6/8 等）：beat_this 可能把 6/8 输出为 2 拍或 6 拍，需要映射到正确拍号和三连/八分网格。
5. L1/L2 不能退步。

## 6 完成标准

- L4 五首平均小节 F ≥ 0.85；拍号至少 4/5 正确。
- L1/L2 调号、拍号、小节线仍然全对，音符/声部指标不低于 v1.1（见 `runs\v1.1-20261122\report.md`）。
- L3 拍号至少 4/5 正确，并目测检查 Grieg 一首的谱面（附 SVG/PNG 截图）。
- 用 `--beats auto` 完整跑一次全部测试曲，输出到 `runs\v2-<日期>\`，无报错。

## 7 交付物

1. 代码改动在你的分支上 commit（说明改了什么）。
2. `runs\v2-<日期>\report.md` + `results.json`。
3. `最终成品\v2-<日期>\`：每首歌 .musicxml / .mid / _简谱.txt / .svg + `测评报告.md`（与 v1 对比表）。
4. `工作记录\<agent名>-beats-v2.md`：做了什么、遇到的问题、没解决的问题。
5. 在本文件末尾“完成记录”写一行：分支名、最后 commit、报告路径。

## 领取记录

Antigravity / 2026-11-22

## 完成记录

（分支 / commit / 报告路径）

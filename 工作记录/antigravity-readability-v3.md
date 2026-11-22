# Antigravity 工作记录：TASK-003 真人录音谱面可读性（readability-v3）

- 分支：`antigravity/readability-v3`（切自 `claude/review-task-002` commit `3326d14`）
- 日期：2026-11-22

## 阶段 0：分支与目录说明
- 已切出分支 `antigravity/readability-v3`，并在 `任务\TASK-003-真人录音谱面可读性.md` 登记领取记录。
- 关于工作区中遗留的 7 个未追踪 `runs\v2-dev-*` / `v2-base-*` 目录：它们是 TASK-002 开发过程产物，保留原样未删未提交；本任务（v3）未新增任何临时 runs 目录，仅输出并提交最终 `runs\v3-20261122\`。

## 阶段 1：可读性指标（`evaluate.py` + `run_all.py`）
- 新增 `readability_metrics`：`rests_per_bar`、`tuplet_ratio`、`short16_ratio`、`has_pickup`，并在 `report.md` 末尾新增 `## C. 谱面可读性` 对比表，不改动已有表 A/B 与指标含义。

## 阶段 2：谱面可读性优化（`midi2score.py`）
- `load_notes_with_pedal`：真人演奏路径读取 MIDI CC64 延音踏板，延长踏板内音符时值（受限于同音高下一次起音）。
- `quantize_onsets` / `quantize_dur`：速度自适应网格 + 严格三连音条件（需 3 个起音簇覆盖 `{0,1,2}` 且 `e3 < 0.45*e4`、`e3 < 0.055`）。
- `hand_to_events`：吸收小于 1 拍的碎休止；真休止前音符末端对齐拍边界。
- `build_part`：支持 `pickup_ql > 0` 时输出 MusicXML `<measure implicit="yes" number="0">` 真弱起小节。
- `_detect_compound`：新增快速一拍一小节 `3/8` 识别，修复 `L3-03` 斯卡拉蒂。

## 阶段 3：全量验证（`runs\v3-20261122`）与成品整理
- 命令：`& $py -m bapu.run_all --out runs\v3-20261122 --midi-cache runs\v2-20261122 --beats auto`，全部 16 首无报错完成。
- **L1/L2**：所有已有指标与 `v2-20261122` 100% 一致，`L2-03` 新增真弱起且休止符/小节 `0.80 → 0.60`。
- **L4**：平均小节 F **0.997**，拍号 **5/5**；休止符/小节均值 `0.94 → 0.15`（-84%），连音占比均值 `0.30% → 0.14%`（-53%），≤16 分占比均值 `56.2% → 45.4%`。
- **L3**：拍号 **5/5**（`L3-03` 修复为 `3/8`）；休止符/小节均值 `1.24 → 0.11`（-91%），连音占比均值 `12.3% → 0.4%`（-96%）。
- 已渲染并目测核查 `L3-02`（Grieg）与 `L4-05`（Chopin）的 v3 及 v2/v3 前后对比 PNG。
- 遗留小问题：`L3-03` 音频路径因 CC64 延音影响 `detect_key` 权重导致调号偏移（`oracle` 仍为 F 大调 ✓）。

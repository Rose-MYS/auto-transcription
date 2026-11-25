# 工作记录：TASK-007 新曲验证（v4 防过拟合）

- **任务**：`任务/TASK-007-新曲验证.md`
- **分支**：`antigravity/validate-v4`（从 `claude/review-task-006` `fdb6453` 切出）
- **日期**：2026-11-25
- **约束遵守**：本任务**未修改任何 `bapu/` 算法代码**，原样使用 `claude/review-task-006` 的 v4 代码运行。

## 1. 验证集 L6 构建

从 `工作文件/test-songs/L5-rose/钢琴翻弹合集/` 中选取此前未使用的全部 8 首，截取 75 秒主旋律片段（44.1kHz mono WAV），建立 `工作文件/test-songs/L6-01` 至 `L6-08`：

- `L6-01_qifengle`（15–90s，起风了）
- `L6-02_castle_in_the_sky`（15–90s，天空之城·伴随着你）
- `L6-03_big_fish`（20–95s，大鱼，跳过前 20s 极轻引子）
- `L6-04_summer`（15–90s，Summer·菊次郎的夏天）
- `L6-05_canon`（15–90s，卡农）
- `L6-06_lemon`（20–95s，Lemon）
- `L6-07_guyongzhe`（15–90s，孤勇者）
- `L6-08_truth_that_you_leave`（15–90s，The Truth That You Leave）

### 参考调号核实（以录音为准）
对照 `L5-rose审核记录.md` 提示的 3 首“乐谱与录音不同调”曲目，使用 Transkun 转写 MIDI 的时值加权音级直方图、低音音级分布及 Krumhansl-Schmuckler / Temperley-Kostka-Payne 双算法交叉核实：
- `L6-02 天空之城`：高占比音级 G/C/Eb/D/Bb/F/Ab，低音 G/C/Bb/F → 确认为 **c 小调（-3）**（乐谱为 E 大调）。
- `L6-03 大鱼`：高占比音级 Bb/F/Eb/Db/Ab/C/Gb，低音 Bb(36%)/Gb(24%)/F(17%)/Ab(16%) → 确认为 **降 b 小调（-5）**（乐谱为 5♯）。
- `L6-06 Lemon`：高占比音级 B/D#/F#/G#/C#/E/A#，低音 B/G#/F#/D# → 确认为 **B 大调（5♯）**（乐谱为 E 大调）。
- 其余 5 首均与乐谱 PDF 及审核记录一致。所有依据均写入各曲 `meta.json` 的 `ref_basis` 字段。

## 2. 运行与回归验证

1. **L6 全量运行**：`python -m bapu.run_all --songs L6 --out runs\v4-val-20261125 --beats auto`，8 首全部跑通无报错。
   - 严格拍号 `meter_exact`：**8 / 8 (100%)**
   - 宽松拍号 `meter_ok`：**8 / 8 (100%)**
   - 调号 `key_ok`：**8 / 8 (100%)**
   - 节拍来源 `beat_this`：**8 / 8 (100%)**
   - 可读性均值：休止符 `0.12 / 小节`（L5 为 `0.27`）、连音占比 `0.000`（L5 为 `0.000`）、≤16 分占比 `0.376`（L5 为 `0.222`）。
2. **L1–L5 回归**：使用 `--midi-cache runs\v4-test-20261123 --beats auto` 全量重跑 L1–L5（31 首），与 `runs\v4-20261123\results.json` 逐字段比对 **0 差异**。

## 3. 过拟合结论与目测发现

- **结论：保持（无过拟合）**。v4 新增的 3 类核心规则（力度判别机械速度、强拍纯度回退 `detect_meter`、`2/4 → 4/4` 升格）均在未见新曲 L6 上直接触发并发挥正向作用（尤其是 `L6-02`、`L6-07` 被力度判别救回 `beat_this`）。
- **目测发现的 2 个真实边界**（记录供后续迭代，本任务未改算法）：
  1. `L6-03 大鱼` 出现半速拍级（`bpm=34.7`，因 `M_ext is None` 跳过了 Step 5 倍频修正）。
  2. `L6-06 Lemon`、`L6-08 The Truth That You Leave` 因强拍纯度低回退 `notes`，拍数正确（`4/4`）但局部乐段强拍相位偏 1 拍。

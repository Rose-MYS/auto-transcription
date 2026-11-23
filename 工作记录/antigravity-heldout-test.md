# Antigravity 工作记录：TASK-005 训练集外真人录音测试（heldout-test）

- 分支：`antigravity/heldout-test`（切自 `claude/review-task-004` commit `3a0d618`）
- 日期：2026-11-23

## 1. 环境与测试集构建（`bapu\build_l5_set.py`）
- 在 `C:\Users\Rose_MYS\venvs\bapu` 安装 `av==19.0.2`（PyAV），并同步写入 `工作文件\bapu\setup_env.ps1`。
- 更新 `.gitignore` 排除 `L5-C*/audio.*`、`*_原声.*`、`*_回放.*` 版权音频。
- 构建 15 首训练集外测试集 `L5`（均核对不在 MAESTRO v3.0.0 CSV 中，每首截取 75 秒、22050Hz）：
  - **A 类（4 首，Saarland Music Data v2，Zenodo 10847280，CC BY-NC-SA 3.0）**：`L5-A01` Brahms Op.10-1、`L5-A02` Mozart KV 265、`L5-A03` Haydn Hob.XVII:4、`L5-A04` Brahms Op.10-2（含对齐 `answer.mid` 与 CC64）。
  - **B 类（4 首，Internet Archive 公版/历史录音）**：`L5-B01` Satie Gymnopédie No.1、`L5-B02` Beethoven Für Elise、`L5-B03` Schumann Träumerei (Schnabel 1947 历史录音)、`L5-B04` Chopin Waltz Op.64 No.2 (José Iturbi 78rpm 历史录音)。（注：Wikimedia Commons 初试返回 429 限流，改用 Archive.org 直链。）
  - **C 类（7 首，Rose 提供的 B 站钢琴翻弹合集）**：`L5-C01` 永远同在、`L5-C02` Sparkle、`L5-C03` 夜的钢琴曲五、`L5-C04` River Flows in You、`L5-C05` 克罗地亚狂想曲、`L5-C06` Merry Christmas Mr. Lawrence、`L5-C07` Flower Dance。

## 2. 最小测评接入（不改算法）
- 仅修改 `工作文件\bapu\evaluate.py`（`meta_metrics` 支持读取 `meta.json`）与 `工作文件\bapu\run_all.py`（支持 `.ogg/.oga/.m4a`、`answer.mid` 可选、跳过无音频的 `L5-rose` 容器目录）。
- **零改动** `midi2score.py`、`beats.py`、`audio2midi.py`。

## 3. 全量回归与 L5 实测（`runs\v4-test-20261123`）
- **L1–L4 回归**：16 首全部指标与 `runs\v3.1-20261122\results.json` **0 差异**。
- **L5 汇总**：
  - A 类转写音符 F1：`0.993` / `0.999` / `1.000` / `0.994`（均值 **0.997**）；
  - 节拍来源正确率：**14/15**（仅 `L5-B01` 萨蒂极平稳慢板误走 `notes`）；
  - 调号正确率：**13/15**（`L5-A03` 判为 g 小调、`L5-C07` 判为 g# 小调）；
  - 拍号正确率：**11/15**（`L5-A04` 4/4→3/4、`L5-B03` 4/4→6/8、`L5-B04` 3/4→2/4、`L5-C06` 12/8→6/8）。
- 已为全部 15 首渲染前 1–2 页 PNG 并逐首目测打分，为 7 首 C 类曲目并排生成 `_原声.flac` 与 `_回放.flac`（均已 gitignore），诊断报告见 `最终成品\v4-test-20261123\诊断报告.md`。

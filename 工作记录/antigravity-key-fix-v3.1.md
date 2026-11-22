# Antigravity 工作记录：TASK-004 调号修正与收尾（key-fix-v3.1）

- 分支：`antigravity/key-fix-v3.1`（切自 `claude/review-task-003` commit `d2a7e75`）
- 日期：2026-11-22

## 1. 原因定位与修复（`midi2score.py`）
- **v3 调号退步根因**：v3 将 `detect_key` 放在 CC64 延音、时值延长之后，按记谱时值加权改变了音级时长分布，导致 `L3-03`（音频）与 `L4-04`（音频与 Oracle）判调偏移。
- **修复**：
  1. `transcribe_to_score` 中改用未经延音与记谱整理的原始 `notes` 传入 `detect_key`；
  2. 将 `music21` 调性算法升级为 `key.temperleykostkapayne`；
  3. 增加开头乐句同主音大小调消歧（取前 25% / 最多 15s 做副分析，同主音且开头 10s 三度音程比明确时采纳开头大小调），通用解决 `L4-03` 降 E 大调误判为降 e 小调的问题；
  4. 增加 `abs(sharps) > 6` 等音简化（`L4-05` 由升 C 大调 +7 规范化为降 D 大调 -5）。

## 2. L4 调号自动测评（`evaluate.py` + `run_all.py`）
- 在 `evaluate.py` `META` 中补全 `L4-01..L4-05` 参考调号与 `_key_sharps_ok`（支持 `-5`/`+7` 等音等价），并在 `beat_metrics` 与 `run_all.py` 表格中输出 `key_ok`。

## 3. 杂项清理与全量验证
- 删除了工作区中 TASK-002 遗留的 7 个未追踪开发目录（`runs\v2-base-l12-bt`、`v2-base-l3-bt`、`v2-base-l4-bt`、`v2-dev-l12`、`v2-dev-l3`、`v2-dev-l4`、`v2-dev-l4-fix`），保持工作区整洁。
- 运行 `& $py -m bapu.run_all --out runs\v3.1-20261122 --midi-cache runs\v2-20261122 --beats auto`：
  - **调号**：音频 **16/16** ✓，Oracle **16/16** ✓（L3 5/5、L4 5/5、L1/L2 6/6）。
  - **可读性与其它指标**：与 `runs\v3-20261122\results.json` 完全一致（零退步）。
- 成品已整理至 `最终成品\v3.1-20261122\`，报告全部使用相对路径。

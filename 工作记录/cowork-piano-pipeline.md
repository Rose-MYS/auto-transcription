# cowork（线程“搭建钢琴曲扒谱流程并测评”）笔记

- 2026-11-22：搭好 v1 流水线（工作文件/bapu/），测试曲同步到 工作文件/test-songs/，最终成品在 最终成品/v1-20261122/（含测评报告.md）。
- 分支：claude/cowork-piano-pipeline。
- 环境：venv 在 C:\Users\ClaudeVM2\venvs\bapu（网络盘上导入库很慢）；transkun 用 --no-deps 装（ncls 需要 VC++ 编译器，推理用不到）；还需要 torchaudio、onnxruntime、verovio。
- 机器只有 2 核 / 4GB：Transkun 约 1.5× 实时；同时跑两个重模型会让远程连接断开，长任务放后台（Start-Process + 日志）。
- 开发循环：`python -m bapu.run_all --songs L2 --midi-cache runs\<上次>` 复用转写结果，只调“MIDI→谱子”，几秒一轮；`python -m bapu.dev_diff <answer.musicxml> <est.musicxml>` 看错在哪。
- 试过但没采用：Basic Pitch（单旋律不如 pYIN）；beat_this small0（合成曲上节拍/强拍明显不对，final0 没测完）。
- 下一步：真人演奏的强拍跟踪（L3 拍号/小节线）、单谱表双声部、真正的弱起小节、简谱出图。


## 2026-11-22 下午：真人录音节拍（beat_this）

- 新建 L4 测试集（MAESTRO 真人录音前 90 秒 + ASAP 节拍/强拍标注），脚本 `bapu\build_asap_set.py`，5 首已生成，音频与标注对齐已核对。
- 接入 beat_this final0（`bapu\beats.py`，`run_all --beats final0`）。L4 小节 F：巴赫 0.03→0.98，舒伯特 2/4 0.35→1.00。合成曲 L1/L2 上 beat_this 会半速、强拍过密，需自动选择来源。
- 注意 beat_this 训练集可能含 ASAP，L4 分数偏乐观。
- Rose 决定：重活交给其他 agent，Claude 写任务文件并验收。后续工作已写成 `任务\TASK-002-真人录音节拍与小节线.md`。
- 中转目录 C:\Users\ClaudeVM2\bapu-staging 已清理（内容在工作目录里都有）。

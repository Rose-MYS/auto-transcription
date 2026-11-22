# cowork（线程“搭建钢琴曲扒谱流程并测评”）笔记

- 2026-11-22：搭好 v1 流水线（工作文件/bapu/），测试曲同步到 工作文件/test-songs/，最终成品在 最终成品/v1-20261122/（含测评报告.md）。
- 分支：claude/cowork-piano-pipeline。
- 环境：venv 在 C:\Users\ClaudeVM2\venvs\bapu（网络盘上导入库很慢）；transkun 用 --no-deps 装（ncls 需要 VC++ 编译器，推理用不到）；还需要 torchaudio、onnxruntime、verovio。
- 机器只有 2 核 / 4GB：Transkun 约 1.5× 实时；同时跑两个重模型会让远程连接断开，长任务放后台（Start-Process + 日志）。
- 开发循环：`python -m bapu.run_all --songs L2 --midi-cache runs\<上次>` 复用转写结果，只调“MIDI→谱子”，几秒一轮；`python -m bapu.dev_diff <answer.musicxml> <est.musicxml>` 看错在哪。
- 试过但没采用：Basic Pitch（单旋律不如 pYIN）；beat_this small0（合成曲上节拍/强拍明显不对，final0 没测完）。
- 下一步：真人演奏的强拍跟踪（L3 拍号/小节线）、单谱表双声部、真正的弱起小节、简谱出图。

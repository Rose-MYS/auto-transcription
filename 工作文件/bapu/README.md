# bapu：音频 → 五线谱（MusicXML）+ 简谱

第一版流水线（2026-11-22）。定位：钢琴曲和单旋律 → 排版干净、能直接导入 MuseScore / Sibelius / Finale / Dorico 的谱子。全部在 CPU 上跑。

## 流程

```
audio.mp3
  │  audio2midi.py   自动判断：钢琴 → Transkun v2；单旋律（长笛/小提琴/人声）→ pYIN 音高跟踪
  ▼
transcribed.mid      （音符事件：起止时间、音高、力度，没有小节和拍子）
  │  midi2score.py   节拍跟踪 → 量化（16 分/三连音）→ 拍号与强拍 → 调号与升降号拼写 → 左右手分配
  ▼
audio_score.musicxml 钢琴大谱表（或单行旋律谱）   ← 主要成品
audio_score.mid      量化后的 MIDI（给编曲软件）
audio_jianpu.txt     简谱（主旋律，jianpu-ly 语法）
audio_score-p1.svg   谱面预览（verovio 渲染）
```

## 用法

```powershell
# 首次：建环境（venv 在 C 盘，网络盘上太慢）
powershell -ExecutionPolicy Bypass -File 工作文件\bapu\setup_env.ps1

cd 工作文件
C:\Users\<你>\venvs\bapu\Scripts\python.exe -m bapu.run_all                 # 全部测试曲 + 测评
C:\Users\<你>\venvs\bapu\Scripts\python.exe -m bapu.run_all --songs L2      # 只跑 L2
C:\Users\<你>\venvs\bapu\Scripts\python.exe -m bapu.run_all --mode melody   # 强制单旋律路线
```

每次运行输出到 `工作文件/runs/<时间戳>/`，不会覆盖旧结果；`report.md` 是测评表。

## 文件

| 文件 | 作用 |
|---|---|
| audio2midi.py | 音频→MIDI：Transkun（钢琴）、pYIN（单旋律）、自动选择 |
| midi2score.py | MIDI→MusicXML：本项目的核心 |
| jianpu.py | MusicXML→简谱文本 |
| render.py | MusicXML→SVG 预览 |
| evaluate.py | 测评（音符级 mir_eval；谱面级对比 answer.musicxml） |
| run_all.py | 一键跑全部 + 写报告 |
| dev_diff.py | 开发用：列出与答案不一致的音 |

## 依赖与许可

Transkun（MIT）、librosa（ISC）、music21（BSD）、mir_eval（MIT）、verovio（LGPL）。测试集 L3 来自 MAESTRO（CC BY-NC-SA，仅非商用）。

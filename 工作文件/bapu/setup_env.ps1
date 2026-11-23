# 一键重建 Python 环境（Windows，CPU）。venv 放在 C 盘：放在网络盘 Z: 上导入库会非常慢。
# 用法：powershell -ExecutionPolicy Bypass -File setup_env.ps1
$venv = "$env:USERPROFILE\venvs\bapu"
python -m venv $venv
& "$venv\Scripts\python.exe" -m pip install --upgrade pip
& "$venv\Scripts\python.exe" -m pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu
& "$venv\Scripts\python.exe" -m pip install -r "$PSScriptRoot\requirements.txt"
# transkun 的 ncls 依赖需要 C++ 编译器，只有训练/评测才用到，推理不需要 → 跳过依赖安装
& "$venv\Scripts\python.exe" -m pip install --no-deps transkun==2.0.1
# 单旋律备用模型、谱面预览、节拍/强拍模型、m4a 解码
& "$venv\Scripts\python.exe" -m pip install onnxruntime verovio requests av https://github.com/CPJKU/beat_this/archive/main.zip
Write-Host "完成。运行：cd 工作文件; $venv\Scripts\python.exe -m bapu.run_all"

# Demucs 服务 { #demucs-service }

本文介绍如何安装 Demucs 服务。该服务使用 AI 处理卡拉 OK 音频，分离人声并生成带时间轴的歌词，让你可以将歌曲制作成卡拉 OK。

Demucs 服务可以与主应用运行在同一台电脑上，也可以部署到另一台配备更强 GPU 的电脑上。

!!! Warning
    该服务需要支持 CUDA 的 NVIDIA GPU。AMD 和 Intel GPU 可能可以与 PyTorch 配合使用，但目前未经测试。没有 GPU 也可以运行，不过处理会完全使用 CPU，速度会更慢。

下面是处理一首典型的 3 分钟歌曲所需时间的大致参考。

测试环境：Windows 11，CPU：Intel i7-12700K，GPU：NVIDIA RTX 4070 SUPER 12 GB。

| 后端 | 使用 GPU | 仅使用 CPU |
|---|---|---|
| Demucs `htdemucs` | 约 10 秒 | 约 1 分 20 秒 |
| SherpaONNX Spleeter | 不适用 | 约 20 秒 |
| WhisperX | 约 15 秒 | 约 1 分 20 秒 |

### 1. 安装 [Python 3.10](https://www.python.org/downloads/release/python-3100/) { #1-install-python-310 }

- 目前只有 Python 3.10 与全部机器学习依赖一起经过测试。更新的 Python 版本可能无法正常工作。
- 你也可以尝试使用 `uv` 或 `conda` 管理环境，只要创建出的虚拟环境能够正常运行 `whisperx` 和 `demucs`。

### 2. 下载代码和依赖 { #2-download-the-code-and-dependencies }
#### 应用程序 { #application }
```powershell
git clone https://github.com/vttc08/demucs-karaoke-app
```

- 如果无法使用 Git，可以从 GitHub 下载代码库的 ZIP 文件并解压，然后在 PowerShell 中打开解压后的目录。


```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

#### 下载 [PyTorch](https://pytorch.org/get-started/locally/) { #download-pytorch }

```powershell
pip install torch==2.8.0+cu126 torchaudio==2.8.0+cu126 torchvision==0.23.0+cu126 --index-url https://download.pytorch.org/whl/cu126
```

- 如果你的 GPU 不支持 CUDA，请选择 CPU 版本。

#### 安装项目依赖 { #project-dependencies }

```powershell
cd demucs-karaoke-app # the location where you downloaded the code
cd demucs_svc
pip install -r requirements.txt
```

### 3. 准备 Hugging Face token { #3-prepare-a-hugging-face-token }

部分 WhisperX 模型需要验证。请先接受以下模型的许可协议：

- [pyannote/speaker-diarization](https://huggingface.co/pyannote/speaker-diarization)
- [pyannote/segmentation](https://huggingface.co/pyannote/segmentation)

在 [Hugging Face](https://huggingface.co/settings/tokens) 创建个人访问 token，并将其保存到文件中。

```powershell
New-Item -ItemType Directory -Force -Path $env:HF_HOME | Out-Null
$env:HF_TOKEN_PATH="$env:HF_HOME\token"
Set-Content -Path $env:HF_TOKEN_PATH -Value "<your_huggingface_token>"
```

如果未设置 `HF_HOME`，请检查系统环境变量或用户环境变量。

### 4. 运行应用程序 { #4-run-the-application }

   ```powershell
   uvicorn.exe app:app --host 0.0.0.0 --port 8001
   ```

### 5. 检查应用健康状况 { #5-verify-application-health }

**PyTorch：**

   ```powershell
   python -c "import torch, torchaudio; print(torch.__version__); print(torchaudio.__version__); print(torch.cuda.is_available())"
   ```

**Web 应用：**

   ```powershell
   (curl.exe -fsSL http://localhost:8001/health | ConvertFrom-Json).status # ok
   (curl.exe -fsSL http://localhost:8001/health | ConvertFrom-Json).supported_backends # demucs sherpa_spleeter
   ```

### Conda 快速设置（可选） { #conda-quick-setup-optional }

如果你更喜欢使用 Conda，可以创建环境并安装 Demucs 服务依赖：

```powershell
conda create --name demucs-karaoke python=3.10
conda activate demucs-karaoke
cd demucs-karaoke-app\demucs_svc
python -m pip install -r requirements.txt
```

使用上面的命令安装与你的 CUDA 或 CPU 配置匹配的 PyTorch 版本，然后继续完成 Hugging Face token、启动服务和健康检查步骤。

## 下一步 { #next-steps }

- [配置 Demucs 服务](../configuration/karaoke-processing.md#demucs-service)

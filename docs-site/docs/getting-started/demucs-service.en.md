# Demucs Service

This doc outlines the installation of Demucs service, which runs AI-powered karaoke processing to remove vocals and generate timed lyrics, creating karaoke from any song.

The service can run on the same machine as the main application, or on a separate machine with more GPU processing.

!!! Warning
    The service requires a CUDA-enabled Nvidia GPU, AMD and Intel GPUs may or may not work with PyTorch and is untested. Without GPU, processing will be CPU-only and it's slower.

Table here is the approximate processing time for a typical 3-minute song

Tested on Windows 11, CPU: Intel i7-12700K, GPU: Nvidia RTX 4070 Super 12GB

| Backends | GPU | CPU-Only |
|---|---|---|
| Demucs htdemucs | 10s | 1m 20s |
| SherpaONNX Spleeter | N/A | 20s |
| WhisperX | 15s | 1m20s |

### 1. Install [Python 3.10](https://www.python.org/downloads/release/python-3100/).

- Only Python 3.10 has been tested with all ML dependencies. Newer Python versions may not work.
- You can also try using `uv` or `conda`, as long as you have a working virtual environment that can run `whisperx` and `demucs`.

### 2. Download the code and dependencies.
#### Application
```powershell
git clone https://github.com/vttc08/demucs-karaoke-app
```

- If Git is not available, you can download and extract the repository as a ZIP file, then open the resulting folder in PowerShell.


```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

#### Download [PyTorch](https://pytorch.org/get-started/locally/):

```powershell
pip install torch==2.8.0+cu126 torchaudio==2.8.0+cu126 torchvision==0.23.0+cu126 --index-url https://download.pytorch.org/whl/cu126
```

- Choose CPU if your GPU doesn't support CUDA.

#### Project dependencies:

```powershell
cd demucs-karaoke-app # the location where you downloaded the code
cd demucs_svc
pip install -r requirements.txt
```

### 3. Prepare a Hugging Face token. 

Some WhisperX models require authentication. Accept the license agreement for the following models:

- [pyannote/speaker-diarization](https://huggingface.co/pyannote/speaker-diarization)
- [pyannote/segmentation](https://huggingface.co/pyannote/segmentation)

Generate a personal access token from [Hugging Face](https://huggingface.co/settings/tokens) and save it to a file.

```powershell
New-Item -ItemType Directory -Force -Path $env:HF_HOME | Out-Null
$env:HF_TOKEN_PATH="$env:HF_HOME\token"
Set-Content -Path $env:HF_TOKEN_PATH -Value "<your_huggingface_token>"
```

If `HF_HOME` is not set, check your system or user environment variables.

### 4. Run the application.

   ```powershell
   uvicorn.exe app:app --host 0.0.0.0 --port 8001
   ```

### 5. Verify application health.

**PyTorch:**

   ```powershell
   python -c "import torch, torchaudio; print(torch.__version__); print(torchaudio.__version__); print(torch.cuda.is_available())"
   ```

**Web app:**

   ```powershell
   (curl.exe -fsSL http://localhost:8001/health | ConvertFrom-Json).status # ok
   (curl.exe -fsSL http://localhost:8001/health | ConvertFrom-Json).supported_backends # demucs sherpa_spleeter
   ```

### Conda quick setup (optional)

If you prefer Conda, create an environment and install the Demucs service dependencies with:

```powershell
conda create --name demucs-karaoke python=3.10
conda activate demucs-karaoke
cd demucs-karaoke-app\demucs_svc
python -m pip install -r requirements.txt
```

Install the matching PyTorch build using the command above, adjusted for your CUDA or CPU setup. Then continue with the Hugging Face token, service startup, and health-check steps.

## Next Steps

- [Configuring Demucs](../configuration/index.md#demucs-service)

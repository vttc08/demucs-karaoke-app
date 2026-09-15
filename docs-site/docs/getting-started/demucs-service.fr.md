# Service Démucs { #demucs-service }

Ce document décrit l'installation du service Demucs, qui exécute le traitement de karaoké sous l'IA pour supprimer les voix et générer des paroles chronométrées, créant du karaoké de n'importe quelle chanson.

Le service peut fonctionner sur la même machine que l'application principale, ou sur une machine séparée avec plus de traitement GPU.

!!! Warning
    Le service nécessite un GPU Nvidia, AMD et Intel compatible avec CUDA peut ou non fonctionner avec PyTorch et n'est pas testé. Sans GPU, le traitement sera uniquement CPU et il est plus lent.

    Tableau ici est le temps de traitement approximatif pour une chanson typique de 3 minutes

    Testé sur Windows 11, CPU: Intel i7-12700K, GPU: Nvidia RTX 4070 Super 12 Go

    | Backends | GPU | CPU-Only |
    |---|---|---|
    | Demucs htdemucs | 10s | 1m 20s |
    | SherpaONNX Spleeter | N/A | 20s |
    | WhisperX | 15s | 1m20s |

### 1. Install [Python 3.10](https://www.python.org/downloads/release/python-3100/). { #1-install-python-310httpswwwpythonorgdownloadsreleasepython-3100 }

- Seul Python 3.10 a été testé avec toutes les dépendances ML. Les versions plus récentes de Python peuvent ne pas fonctionner.
- You can also try using `uv` or `conda`, as long as you have a working virtual environment that can run `whisperx` and `demucs`.

### 2. Télécharger le code et les dépendances. { #2-download-the-code-and-dependencies }
#### Demande { #application }
```powershell
git clone https://github.com/vttc08/demucs-karaoke-app
```

- Si Git n'est pas disponible, vous pouvez télécharger et extraire le dépôt en tant que fichier ZIP, puis ouvrir le dossier résultant dans PowerShell.


```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

#### Download [PyTorch](https://pytorch.org/get-started/locally/): { #download-pytorchhttpspytorchorgget-startedlocally }

```powershell
pip install torch==2.8.0+cu126 torchaudio==2.8.0+cu126 torchvision==0.23.0+cu126 --index-url https://download.pytorch.org/whl/cu126
```

- Choisissez CPU si votre GPU ne supporte pas CUDA.

#### Dépendances du projet : { #project-dependencies }

```powershell
cd demucs-karaoke-app # the location where you downloaded the code
cd demucs_svc
pip install -r requirements.txt
```

### 3. Préparez un jeton Hugging Face. { #3-prepare-a-hugging-face-token }

Certains modèles WhisperX nécessitent une authentification. Acceptez le contrat de licence pour les modèles suivants :

- [pyannote/speaker-diarization](https://huggingface.co/pyannote/speaker-diarization)
- [pyannote/segmentation](https://huggingface.co/pyannote/segmentation)

Generate a personal access token from [Hugging Face](https://huggingface.co/settings/tokens) and save it to a file.

```powershell
New-Item -ItemType Directory -Force -Path $env:HF_HOME | Out-Null
$env:HF_TOKEN_PATH="$env:HF_HOME\token"
Set-Content -Path $env:HF_TOKEN_PATH -Value "<your_huggingface_token>"
```

If `HF_HOME` is not set, check your system or user environment variables.

### 4. Exécutez l'application. { #4-run-the-application }

   ```powershell
   uvicorn.exe app:app --host 0.0.0.0 --port 8001
   ```

### 5. Vérifier la santé de l'application. { #5-verify-application-health }

**PyTorche:**

   ```powershell
   python -c "import torch, torchaudio; print(torch.__version__); print(torchaudio.__version__); print(torch.cuda.is_available())"
   ```

**Application Web:**

   ```powershell
   (curl.exe -fsSL http://localhost:8001/health | ConvertFrom-Json).status # ok
   (curl.exe -fsSL http://localhost:8001/health | ConvertFrom-Json).supported_backends # demucs sherpa_spleeter
   ```

### Conda configuration rapide (facultatif) { #conda-quick-setup-optional }

Si vous préférez Conde, créez un environnement et installez les dépendances du service Demucs avec :

```powershell
conda create --name demucs-karaoke python=3.10
conda activate demucs-karaoke
cd demucs-karaoke-app\demucs_svc
python -m pip install -r requirements.txt
```

Installez la compilation PyTorch correspondante en utilisant la commande ci-dessus, ajustée pour votre configuration CUDA ou CPU. Continuez ensuite avec le jeton Hugging Face, le démarrage de service et les étapes de contrôle de santé.

## Prochaines étapes { #next-steps }

- [Configure the Demucs service](../configuration/karaoke-processing.md#demucs-service)

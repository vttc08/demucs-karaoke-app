# Servizio Demucs {#demucs-service}

Questa guida spiega come installare il servizio Demucs, che usa l'IA per rimuovere la voce e sincronizzare i testi, così da creare karaoke a partire da qualsiasi brano.

Il servizio può essere eseguito sullo stesso computer dell'applicazione principale oppure su un computer separato dotato di una GPU più potente.

!!! warning "Attenzione"
    Il servizio richiede una GPU NVIDIA compatibile con CUDA. Le GPU AMD e Intel non sono state testate e potrebbero non funzionare con PyTorch. Senza una GPU, l'elaborazione viene eseguita solo sulla CPU ed è più lenta.

La tabella mostra i tempi di elaborazione approssimativi per un brano tipico di tre minuti.

Testato su Windows 11, CPU: Intel i7-12700K, GPU: Nvidia RTX 4070 Super 12GB

| Backend | GPU | Solo CPU |
|---|---|---|
| Demucs htdemucs | 10s | 1m 20s |
| SherpaONNX Spleeter | N/A | 20s |
| WhisperX | 15s | 1m20s |

### 1. Installare [Python 3.10](https://www.python.org/downloads/release/python-3100/). {#1-install-python-310httpswwwpythonorgdownloadsreleasepython-3100}

- Solo Python 3.10 è stato testato con tutte le dipendenze ML. Le versioni più recenti di Python potrebbero non funzionare.
- Puoi anche usare `uv` o `conda`, purché l'ambiente virtuale riesca a eseguire `whisperx` e `demucs`.

### 2. Scaricare il codice e le dipendenze {#2-download-the-code-and-dependencies}
#### Applicazione {#application}
```powershell
git clone https://github.com/vttc08/demucs-karaoke-app
```

- Se Git non è disponibile, puoi scaricare il repository come file ZIP, estrarlo e aprire la cartella risultante in PowerShell.


```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

#### Scarica [PyTorch](https://pytorch.org/get-started/locally/): {#download-pytorchhttpspytorchorgget-startedlocally}

```powershell
pip install torch==2.8.0+cu126 torchaudio==2.8.0+cu126 torchvision==0.23.0+cu126 --index-url https://download.pytorch.org/whl/cu126
```

- Se la tua GPU non supporta CUDA, scegli la versione per CPU.

#### Dipendenze del progetto: {#project-dependencies}

```powershell
cd demucs-karaoke-app # the location where you downloaded the code
cd demucs_svc
pip install -r requirements.txt
```

Per installare usando solo la CPU, esegui:

```powershell
uv pip install --index-strategy unsafe-first-match -r requirements-cpu.txt
```

!!! warning "Attenzione"
    Per usare solo la CPU, aggiungi esplicitamente `DEMUCS_DEVICE=cpu` al file `.env` in `demucs_svc`.

### 3. Preparare un token Hugging Face {#3-prepare-a-hugging-face-token}

Alcuni modelli WhisperX richiedono l'autenticazione. Accetta i termini di licenza dei seguenti modelli:

- [pyannote/speaker-diarization](https://huggingface.co/pyannote/speaker-diarization)
- [pyannote/segmentation](https://huggingface.co/pyannote/segmentation)

Genera un token di accesso personale da [Hugging Face](https://huggingface.co/settings/tokens) e salvalo in un file.

```powershell
New-Item -ItemType Directory -Force -Path $env:HF_HOME | Out-Null
$env:HF_TOKEN_PATH="$env:HF_HOME\token"
Set-Content -Path $env:HF_TOKEN_PATH -Value "<your_huggingface_token>"
```

Se `HF_HOME` non è impostata, controlla le variabili d'ambiente di sistema o dell'utente.

### 4. Avviare l'applicazione {#4-run-the-application}

   ```powershell
   uvicorn.exe app:app --host 0.0.0.0 --port 8001
   ```

### 5. Verificare lo stato dell'applicazione {#5-verify-application-health}

**PyTorch:**

   ```powershell
   python -c "import torch, torchaudio; print(torch.__version__); print(torchaudio.__version__); print(torch.cuda.is_available())"
   ```

**Web app:**

   ```powershell
   (curl.exe -fsSL http://localhost:8001/health | ConvertFrom-Json).status # ok
   (curl.exe -fsSL http://localhost:8001/health | ConvertFrom-Json).supported_backends # demucs sherpa_spleeter
   ```

### Configurazione rapida con Conda (facoltativa) {#conda-quick-setup-optional}

Se preferisci Conda, crea un ambiente e installa le dipendenze del servizio Demucs con:

```powershell
conda create --name demucs-karaoke python=3.10
conda activate demucs-karaoke
cd demucs-karaoke-app\demucs_svc
python -m pip install -r requirements.txt
```

Installa la versione di PyTorch corrispondente usando il comando riportato sopra e adattandolo alla configurazione CUDA o CPU. Poi segui i passaggi per configurare il token Hugging Face, avviare il servizio e verificarne lo stato.

## Passaggi successivi {#next-steps}

- [Configurare il servizio Demucs](../configuration/karaoke-processing.md#demucs-service)

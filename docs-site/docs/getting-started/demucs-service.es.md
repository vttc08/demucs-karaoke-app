# Servicio Demucs

Este documento describe la instalación del servicio Demucs, que ejecuta el procesamiento de karaoke con IA para eliminar las voces y generar letras sincronizadas, creando karaoke a partir de cualquier canción.

El servicio puede ejecutarse en la misma máquina que la aplicación principal o en otra máquina con mayor capacidad de procesamiento de GPU.

!!! warning "Advertencia"
    El servicio requiere una GPU Nvidia compatible con CUDA. Las GPU AMD e Intel pueden funcionar o no con PyTorch y no se han probado. Sin GPU, el procesamiento se realizará solo con CPU y será más lento.

La siguiente tabla muestra el tiempo de procesamiento aproximado para una canción típica de 3 minutos.

Probado en Windows 11; CPU: Intel i7-12700K; GPU: Nvidia RTX 4070 Super 12GB.

| Backends | GPU | Solo CPU |
|---|---|---|
| Demucs htdemucs | 10 s | 1 min 20 s |
| SherpaONNX Spleeter | N/D | 20 s |
| WhisperX | 15 s | 1 min 20 s |

### 1. Instala [Python 3.10](https://www.python.org/downloads/release/python-3100/).

- Solo se ha probado Python 3.10 con todas las dependencias de ML. Es posible que las versiones más recientes de Python no funcionen.
- También puedes probar a usar `uv` o `conda`, siempre que tengas un entorno virtual funcional que pueda ejecutar `whisperx` y `demucs`.

### 2. Descarga el código y las dependencias.
#### Aplicación
```powershell
git clone https://github.com/vttc08/demucs-karaoke-app
```

- Si Git no está disponible, puedes descargar y extraer el repositorio como archivo ZIP y abrir después la carpeta resultante en PowerShell.


```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

#### Descarga [PyTorch](https://pytorch.org/get-started/locally/):

```powershell
pip install torch==2.8.0+cu126 torchaudio==2.8.0+cu126 torchvision==0.23.0+cu126 --index-url https://download.pytorch.org/whl/cu126
```

- Elige CPU si tu GPU no es compatible con CUDA.

#### Dependencias del proyecto:

```powershell
cd demucs-karaoke-app # the location where you downloaded the code
cd demucs_svc
pip install -r requirements.txt
```

### 3. Prepara un token de Hugging Face.

Algunos modelos de WhisperX requieren autenticación. Acepta el acuerdo de licencia de los siguientes modelos:

- [pyannote/speaker-diarization](https://huggingface.co/pyannote/speaker-diarization)
- [pyannote/segmentation](https://huggingface.co/pyannote/segmentation)

Genera un token de acceso personal en [Hugging Face](https://huggingface.co/settings/tokens) y guárdalo en un archivo.

```powershell
New-Item -ItemType Directory -Force -Path $env:HF_HOME | Out-Null
$env:HF_TOKEN_PATH="$env:HF_HOME\token"
Set-Content -Path $env:HF_TOKEN_PATH -Value "<your_huggingface_token>"
```

Si `HF_HOME` no está configurado, revisa las variables de entorno del sistema o del usuario.

### 4. Ejecuta la aplicación.

   ```powershell
   uvicorn.exe app:app --host 0.0.0.0 --port 8001
   ```

### 5. Verifica el estado de la aplicación. { #5-verify-application-health }

**PyTorch:**

   ```powershell
   python -c "import torch, torchaudio; print(torch.__version__); print(torchaudio.__version__); print(torch.cuda.is_available())"
   ```

**Aplicación web:**

   ```powershell
   (curl.exe -fsSL http://localhost:8001/health | ConvertFrom-Json).status # ok
   (curl.exe -fsSL http://localhost:8001/health | ConvertFrom-Json).supported_backends # demucs sherpa_spleeter
   ```

### Configuración rápida con Conda (opcional)

Si prefieres Conda, crea un entorno e instala las dependencias del servicio Demucs con:

```powershell
conda create --name demucs-karaoke python=3.10
conda activate demucs-karaoke
cd demucs-karaoke-app\demucs_svc
python -m pip install -r requirements.txt
```

Instala la compilación de PyTorch correspondiente mediante el comando anterior, ajustado a tu configuración de CUDA o CPU. A continuación, continúa con los pasos del token de Hugging Face, inicio del servicio y comprobación de estado.

## Próximos pasos

- [Configurar el servicio Demucs](../configuration/karaoke-processing.md#demucs-service)

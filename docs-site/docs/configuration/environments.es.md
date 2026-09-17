# Variables de entorno

DMKaraoke lee las variables de entorno desde un archivo `.env`, el entorno del sistema operativo o un bloque `environment:` de Docker. Use variables de entorno para valores específicos de la implementación, como rutas, URL de servicios, rutas de ejecutables y secretos.

El punto de partida completo es el [archivo `.env.example`](https://raw.githubusercontent.com/vttc08/demucs-karaoke-app/main/.env.example).

!!! warning "Proteja los secretos"

    No confirme tokens de API ni claves de servicio en un repositorio público. Guarde los secretos en un archivo `.env` protegido, un archivo de entorno de systemd con permisos restringidos o el sistema de gestión de secretos de su contenedor.

## Cómo funciona la configuración

La aplicación principal carga valores en este orden:

1. Variables de entorno proporcionadas por el proceso, Docker o systemd.
2. Valores del archivo `.env` local.
3. Valores guardados en la base de datos de ajustes de ejecución de la aplicación.
4. Valores predeterminados integrados en la aplicación.

Una variable de entorno proporcionada explícitamente tiene prioridad sobre un valor guardado desde la página de ajustes tras reiniciar. Esto es útil cuando una implementación debe mantener fija una ruta, URL de servicio, ejecutable u otro valor. Deje una variable sin establecer si desea que la página de ajustes y el valor de base de datos la controlen.

La mayoría de variables booleanas aceptan valores como `true`, `false`, `1`, `0`, `yes` o `no`. Las rutas pueden ser absolutas o relativas al directorio de la aplicación, salvo que se indique lo contrario. Los límites de bytes usan bytes, mientras que los tiempos de espera e intervalos usan segundos.

El archivo Docker Compose proporciona algunos valores predeterminados de la aplicación directamente mediante su sección `environment:`. Para instalaciones Linux o Windows, quite el comentario de las variables correspondientes en `.env` cuando necesite establecerlas antes del inicio.

## Aplicación principal

Las siguientes variables configuran la aplicación principal de FastAPI.

### Servidor y enrutamiento { #server-and-routing }

| Variable | Predeterminado | Descripción |
| --- | --- | --- |
| `HOST` | `0.0.0.0` | Dirección de red en la que escucha la aplicación. `0.0.0.0` escucha en todas las interfaces, lo que normalmente se requiere para Docker y acceso LAN. |
| `PORT` | `8000` | Puerto en el que escucha la aplicación. |
| `KARAOKE_BASE_PATH` | vacío | Prefijo de URL opcional para un proxy inverso, como `/karaoke`. Déjelo vacío si la aplicación se sirve en `/`. El proxy debe conservar el prefijo al reenviar solicitudes. |
| `ENABLED_LOCALES` | `en` | Códigos de configuración regional disponibles en la interfaz, separados por comas, como `en,zh-CN`. Use `zh-CN` para chino simplificado; `zh` por sí solo no es suficiente. |

### Base de datos y almacenamiento

| Variable | Predeterminado | Descripción |
| --- | --- | --- |
| `DATABASE_URL` | `sqlite:///./karaoke.db` | URL de base de datos SQLAlchemy. El valor predeterminado guarda la base SQLite en el directorio de la aplicación. Docker normalmente la establece en una ruta bajo `/data`. |
| `MEDIA_PATH` | `/tmp/karaoke_media` | Directorio para medios descargados, cargados y procesados. La aplicación lo crea cuando es necesario y el usuario en ejecución debe poder leerlo y escribir en él. |
| `CACHE_PATH` | `/tmp/karaoke_cache` | Directorio para descargas temporales, resultados de procesamiento, miniaturas y otros archivos de caché. |
| `KARAOKE_PROCESSING_MAX_WORKERS` | `2` | Número máximo de tareas de procesamiento de la aplicación principal que pueden ejecutarse a la vez. |
| `KARAOKE_MAX_UPLOAD_BYTES` | `2147483648` (2 GiB) | Tamaño máximo de un archivo cargado o importación ZIP expandida. |
| `KARAOKE_UPLOAD_MIN_FREE_BYTES` | `1073741824` (1 GiB) | Espacio libre mínimo requerido antes de aceptar una carga. |

### Proveedores de letras e idiomas

| Variable | Predeterminado | Descripción |
| --- | --- | --- |
| `MUSIXMATCH_TOKEN` | vacío | Token de Musixmatch usado por el proveedor de letras. |
| `LASTFM_API_KEY` | vacío | Clave de API de Last.fm usada para mejorar la inferencia de metadatos de título y artista. |
| `LRCLIB_API_URL` | `https://lrclib.net` | URL base del proveedor de letras LRCLIB. |
| `LYRICS_TTML_STORAGE_URL` | `https://lyrics-storage.binimum.org` | URL del servicio usado para actualizaciones TTML opcionales de letras sincronizadas compatibles. |
| `LYRICS_TTML_UPGRADE_TIMEOUT_SECONDS` | `3.0` | Tiempo máximo de espera para una actualización TTML. El resultado de letras original sigue disponible si vence el tiempo de espera. |
| `LYRICS_PROVIDER_CUSTOM_PATHS` | vacío | Lista opcional, separada por comas, de archivos Python o directorios con módulos de proveedores de letras personalizados. Los directorios se exploran buscando archivos `.py` de nivel superior. |
| `LYRICS_PROVIDER_NETEASE_ENABLED` | `true` | Activa el proveedor de letras NetEase. |
| `LYRICS_PROVIDER_LRCLIB_ENABLED` | `true` | Activa el proveedor de letras LRCLIB. |

### Demucs y procesamiento de karaoke

Estas variables controlan cómo se conecta la aplicación principal al servicio Demucs independiente y cómo le solicita trabajo. El propio servicio tiene variables adicionales documentadas más abajo.

| Variable | Predeterminado | Descripción |
| --- | --- | --- |
| `DEMUCS_API_URL` | `http://localhost:8001` | URL del servicio Demucs. En Docker Compose normalmente es `http://demucs:8001`; para un servicio remoto, use su URL HTTP accesible. |
| `DEMUCS_API_KEY` | vacío | Clave de API compartida opcional. Establezca el mismo valor en la aplicación principal y el servicio Demucs cuando el servicio se exponga fuera de una red de confianza. |
| `DEMUCS_MODEL` | `htdemucs` | Modelo Demucs solicitado para la separación vocal. |
| `DEMUCS_DEVICE` | `cuda` | Dispositivo de procesamiento solicitado a Demucs. Use `cpu` cuando CUDA no esté disponible. |
| `DEMUCS_OUTPUT_FORMAT` | `mp3` | Formato de salida solicitado a Demucs. Los valores admitidos son `mp3` y `wav`. |
| `DEMUCS_MP3_BITRATE` | `320` | Tasa de bits MP3 en kbps cuando el formato seleccionado es MP3. |
| `SEPARATION_BACKEND` | `demucs` | Backend de separación solicitado a Demucs. Los valores admitidos son `demucs` y `sherpa_spleeter`. |
| `SHERPA_SPLEETER_MODEL` | `fp16` | Variante del modelo Sherpa+Spleeter cuando `SEPARATION_BACKEND=sherpa_spleeter`. Los valores admitidos son `fp16`, `int8` y `fp32`. |
| `DEMUCS_DIRECT_MEDIA_MAX_MB` | `500` | Tamaño máximo de medios, en MB, para procesamiento directo sin copiar primero los medios al flujo de trabajo normal. |
| `DEMUCS_POLL_INTERVAL_SECONDS` | `1.0` | Intervalo entre sondeos mientras se espera una tarea Demucs remota. |
| `WHISPERX_TRANSCRIPTION_MODEL` | `tiny` | Modelo de transcripción WhisperX solicitado para alinear letras. |
| `WHISPERX_ALIGN_LANGUAGE` | `en` | Idioma pasado a la alineación WhisperX. |
| `WHISPERX_DETECT_LANGUAGE` | `false` | Permite que WhisperX detecte el idioma de transcripción en lugar de usar el idioma configurado. |
| `WHISPERX_USE_SYNCED_LYRICS` | `false` | Solicita letras sincronizadas como parte del procesamiento WhisperX cuando el flujo de trabajo las admite. |
| `WHISPERX_PRELOAD_MODELS` | `transcription=tiny,align=en` | Especificación, separada por comas, de precarga de modelos WhisperX enviada al servicio Demucs. |

### Descargas y herramientas externas

| Variable | Predeterminado | Descripción |
| --- | --- | --- |
| `YTDLP_PATH` | `yt-dlp` | Ruta o nombre ejecutable para yt-dlp. La aplicación comprueba primero el entorno virtual activo y luego el `PATH` del sistema. |
| `YTDLP_DENO_PATH` | vacío | Ruta opcional a Deno para ejecución de JavaScript externo de yt-dlp. Déjela vacía salvo que un vídeo lo requiera. |
| `YTDLP_PROXY_URL` | vacío | URL de proxy HTTP, HTTPS, SOCKS4 o SOCKS5 opcional para yt-dlp y solicitudes salientes relacionadas. |
| `YTDLP_VIDEO_RESOLUTION` | `default` | Resolución de vídeo preferida. Los valores admitidos son `default`, `360`, `480`, `720`, `1080` y `2160`. |
| `YTDLP_VIDEO_CODEC` | vacío | Preferencia opcional de códec de vídeo. Déjela vacía para la selección predeterminada; se admite `avc` cuando se necesita una preferencia de códec. |
| `CONCURRENT_YTDLP_SEARCH_ENABLED` | `false` | Activa búsquedas simultáneas de yt-dlp. Esto puede aumentar las solicitudes salientes y el uso de recursos. |
| `FFMPEG_PATH` | `ffmpeg` | Ruta o nombre ejecutable para FFmpeg. |
| `FFMPEG_AUDIO_CODEC` | vacío | Preferencia opcional de códec de audio. Déjela vacía para la selección predeterminada; se admite `aac` cuando se necesita una preferencia de códec. |

### Registro

| Variable | Predeterminado | Descripción |
| --- | --- | --- |
| `LOG_LEVEL` | `INFO` | Nivel raíz de registro, como `DEBUG`, `INFO`, `WARNING` o `ERROR`. |
| `LOG_DIR` | `./logs` | Directorio del archivo de registro de la aplicación. |
| `LOG_FILE_NAME` | `karaoke.log` | Nombre de archivo de registro dentro de `LOG_DIR`. |
| `LOG_MAX_BYTES` | `5242880` (5 MB) | Tamaño máximo de un archivo de registro antes de la rotación. |
| `LOG_BACKUP_COUNT` | `5` | Número de archivos de registro rotados que se conservan. |
| `LOG_FORMAT` | <code>%(asctime)s &#124; %(levelname)s &#124; %(name)s &#124; %(message)s</code> | Cadena de formato de registro de Python. |
| `LOG_TO_FILE_IN_RELOAD` | `false` | Activa el registro en archivo al ejecutarse en modo de recarga. Déjelo desactivado durante el desarrollo normal para evitar bucles de recarga causados por escrituras de registro. |

### Comportamiento de escenario y WebSocket

| Variable | Predeterminado | Descripción |
| --- | --- | --- |
| `STAGE_QR_URL` | vacío | URL codificada en la superposición QR mostrada en el escenario. |
| `STAGE_LOBBY_MEDIA_PATH` | vacío | Ruta opcional `/media/...` o `/cache/...` usada para el bucle de espera cuando la cola está vacía. |
| `STAGE_VOCALS_VOLUME_DEFAULT` | `1.0` | Volumen predeterminado de voces aplicado cuando se carga la página de escenario o cola. Use un valor de `0.0` a `1.0`. |
| `WS_HEARTBEAT_INTERVAL` | `30` | Intervalo de latido WebSocket en segundos. El servidor lo usa para detectar conexiones de navegador obsoletas. |

## Servicio Demucs { #demucs-service }

El servicio Demucs lee su propio archivo de entorno. De forma predeterminada busca `.env` dentro de `demucs_svc/`. Establezca `DEMUCS_ENV_FILE` cuando la configuración del servicio deba residir en otra ruta.

Estas variables configuran el servicio independiente de procesamiento con GPU o CPU. Las variables compartidas con la aplicación principal deben usar normalmente valores coincidentes.

### Rutas y acceso del servicio { #service-paths-and-access }

| Variable | Predeterminado | Descripción |
| --- | --- | --- |
| `DEMUCS_ENV_FILE` | `demucs_svc/.env` | Ruta al archivo de entorno del servicio Demucs. Esta variable se lee antes de que el servicio cargue sus ajustes. |
| `DEMUCS_IO_ROOT` | `demucs_svc/io` | Directorio raíz para trabajos entrantes y resultados procesados. Las rutas relativas se resuelven desde el directorio `demucs_svc`. |
| `DEMUCS_API_KEY` | vacío | Clave de API compartida opcional requerida por la aplicación principal. Use el mismo valor que `DEMUCS_API_KEY` de la aplicación principal. |

### Ajustes de procesamiento y modelos { #processing-and-model-settings }

| Variable | Predeterminado | Descripción |
| --- | --- | --- |
| `DEMUCS_MODEL` | `htdemucs` | Modelo Demucs cargado por el servicio. |
| `DEMUCS_DEVICE` | `cuda` | Dispositivo usado por el servicio. Use `cpu` para procesamiento solo con CPU. |
| `DEMUCS_OUTPUT_FORMAT` | `wav` | Formato de salida predeterminado producido por el servicio. |
| `DEMUCS_MP3_BITRATE` | `320` | Tasa de bits MP3 en kbps cuando se selecciona salida MP3. |
| `SEPARATION_BACKEND` | `demucs` | Backend de separación predeterminado. Los valores admitidos son `demucs` y `sherpa_spleeter`. |
| `SHERPA_SPLEETER_MODEL` | `fp16` | Variante de modelo Sherpa+Spleeter. Los valores admitidos son `fp16`, `int8` y `fp32`. |
| `SHERPA_SPLEETER_MODEL_ROOT` | `demucs_svc/model_data/sherpa_spleeter` | Directorio donde se almacenan los modelos Sherpa+Spleeter. Las rutas relativas se resuelven desde `demucs_svc`. |
| `SHERPA_SPLEETER_NUM_THREADS` | hasta `8` | Número de hilos de CPU utilizados por Sherpa+Spleeter. El valor predeterminado está limitado por el número de CPU del host. |
| `SHERPA_SPLEETER_FFMPEG_PATH` | `ffmpeg` | Ruta o nombre ejecutable para FFmpeg usado por Sherpa+Spleeter. |
| `WHISPERX_TRANSCRIPTION_MODEL` | `tiny` | Modelo de transcripción WhisperX utilizado por el servicio. |
| `WHISPERX_ALIGN_LANGUAGE` | `en` | Idioma predeterminado usado para alineación WhisperX. |
| `WHISPERX_DETECT_LANGUAGE` | `false` | Activa la detección de idioma para transcripción WhisperX. |
| `WHISPERX_USE_SYNCED_LYRICS` | `false` | Usa letras sincronizadas proporcionadas al ejecutar el flujo de trabajo de alineación. |
| `WHISPERX_PRELOAD_MODELS` | `transcription=tiny,align=en` | Modelos solicitados durante la precarga de inicio del servicio. |

### Límites de recursos y limpieza

| Variable | Predeterminado | Descripción |
| --- | --- | --- |
| `DEMUCS_MAX_CONCURRENT_JOBS` | `1` | Número máximo de trabajos de separación procesados al mismo tiempo. Mantenerlo en `1` ayuda a evitar contención de memoria de GPU. |
| `DEMUCS_MAX_UPLOAD_BYTES` | `2147483648` (2 GiB) | Tamaño máximo de carga entrante aceptado por el servicio. |
| `DEMUCS_MIN_FREE_BYTES` | `1073741824` (1 GiB) | Espacio libre mínimo requerido antes de aceptar otra carga. |
| `DEMUCS_GC_INTERVAL_SECONDS` | `600` | Intervalo entre comprobaciones programadas de limpieza de memoria GPU. |
| `DEMUCS_GC_LOW_FREE_VRAM_BYTES` | `2147483648` (2 GiB) | Umbral de VRAM libre que activa limpieza adicional. |

## Configuraciones de ejemplo

### Aplicación local mínima

```dotenv
HOST=0.0.0.0
PORT=8000
MEDIA_PATH=/srv/karaoke/media
CACHE_PATH=/srv/karaoke/cache
DATABASE_URL=sqlite:////srv/karaoke/karaoke.db
```

### Aplicación principal conectada a un servicio Demucs remoto

```dotenv
DEMUCS_API_URL=http://demucs-host:8001
DEMUCS_API_KEY=replace-with-a-shared-secret
DEMUCS_DEVICE=cuda
YTDLP_DENO_PATH=/usr/local/bin/deno
```

### Almacenamiento y registro de Docker Compose

```dotenv
PUID=1000
PGID=1000
```

El archivo Compose incluido asigna el directorio `data` del host a `/data` en el contenedor y define allí las rutas de la aplicación. `PUID` y `PGID` controlan el usuario y grupo numéricos que utiliza el contenedor para la propiedad de montajes vinculados; son variables de Compose, no ajustes de la aplicación.

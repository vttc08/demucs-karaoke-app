# Variabili d'ambiente {#environment-variables}

DMKaraoke legge le variabili d'ambiente da un file `.env`, dall'ambiente del sistema operativo o da un blocco Docker `environment:`. Utilizza le variabili d'ambiente per valori specifici della distribuzione come percorsi, servizio URLs, percorsi eseguibili e segreti.

Il punto di partenza completo è [`.env.example` file](https://raw.githubusercontent.com/vttc08/demucs-karaoke-app/main/.env.example).

!!! warning "Proteggere i segreti"

    Non commettere token API o chiavi di servizio in un repository pubblico. Mantieni i segreti in un file `.env` protetto, in un file di ambiente di sistema con autorizzazioni limitate o nel tuo sistema di gestione segreta dei container.

## Come funziona la configurazione {#how-configuration-works}

Le principali applicazioni caricano i valori in questo ordine:

1. Variabili ambientali fornite dal processo, Docker, o systemd.
2. Valori dal file `.env` locale.
3. Valori salvati nel database delle impostazioni di runtime dell'applicazione.
4. Predefiniti dell'applicazione integrata.

Una variabile di ambiente esplicitamente fornita ha la precedenza su un valore salvato dalla pagina Impostazioni dopo un riavvio. Ciò è utile quando una distribuzione deve mantenere un percorso, un servizio URL, eseguibile o un altro valore fisso. Lasciare un'impostazione della variabile quando si desidera che la pagina Impostazioni e il valore del database lo controllino.

La maggior parte delle variabili booleane accetta valori come `true`, `false`, `1`, `0`, `yes` o `no`. I percorsi possono essere assoluti o relativi alla directory dell'applicazione, a meno che non sia diversamente specificato. I limiti di byte utilizzano byte, mentre i timeout e gli intervalli utilizzano secondi.

Il file Docker Compose fornisce alcune impostazioni predefinite dell'applicazione direttamente attraverso la sua sezione `environment:`. Per un'installazione Linux o Windows, decommentare le variabili corrispondenti in `.env` quando è necessario impostarle prima dell'avvio.

## Applicazione principale {#main-application}

Le seguenti variabili configurano l'applicazione principale FastAPI.

### Server e instradamento {#server-and-routing}

| Variabile | Default | Descrizione |
| --- | --- | --- |
| `HOST` | `0.0.0.0` | `0.0.0.0` mette il servizio in ascolto su tutte le interfacce; in genere è necessario per l'accesso da Docker e dalla rete locale. |
| `PORT` | `8000` | Porta su cui l'applicazione ascolta. |
| `KARAOKE_BASE_PATH` | vuoto | Prefisso URL opzionale per un proxy inverso, ad esempio `/karaoke`. Lasciare vuoto quando l'app viene servita in `/`. Il proxy deve preservare il prefisso durante l'inoltro delle richieste. |
| `FORWARDED_ALLOW_IPS` | `127.0.0.1` | Indirizzi IP separati da virgola o intervalli CIDR di proxy inversi attendibili. Questa impostazione di Uvicorn controlla se `X-Forwarded-For` e `X-Forwarded-Proto` sono accettati. Vedi indirizzo [Indirizzo client dietro un proxy inverso](../tasks/server-administration.md#client-address-behind-a-reverse-proxy). |
| `ENABLED_LOCALES` | `en` | Codici locali separati da virgole disponibili nell'interfaccia utente, come `en,zh-CN`. Utilizzare `zh-CN` per il cinese semplificato; `zh` da solo non è sufficiente. |

### Database e archiviazione {#database-and-storage}

| Variabile | Default | Descrizione |
| --- | --- | --- |
| `DATABASE_URL` | `sqlite:///./karaoke.db` | Database SQLAlchemy URL. Il database SQLite predefinito viene memorizzato nella directory dell'applicazione. Docker normalmente imposta questo percorso in `/data`. |
| `MEDIA_PATH` | `/tmp/karaoke_media` | Directory per i supporti scaricati, caricati ed elaborati. L'applicazione lo crea quando necessario e l'utente in esecuzione deve essere in grado di leggerlo e scriverlo. |
| `CACHE_PATH` | `/tmp/karaoke_cache` | Directory per download temporanei, output di elaborazione, miniature e altri file di cache. |
| `KARAOKE_PROCESSING_MAX_WORKERS` | `2` | Numero massimo di attività di elaborazione delle applicazioni principali che possono essere eseguite contemporaneamente. |
| `KARAOKE_MAX_UPLOAD_BYTES` | `2147483648` (2 GiB) | Dimensione massima di un file caricato o importazione ZIP ampliata. |
| `KARAOKE_UPLOAD_MIN_FREE_BYTES` | `1073741824` (1 GiB) | Spazio minimo libero richiesto prima di accettare un upload. |

### Provider di testi e lingue {#lyrics-providers-and-languages}

| Variabile | Default | Descrizione |
| --- | --- | --- |
| `MUSIXMATCH_TOKEN` | vuoto | token Musixmatch utilizzato dal provider di testi. |
| `LASTFM_API_KEY` | vuoto | Last.fm API chiave utilizzata per migliorare il titolo e l'inferenza dei metadati dell'artista. |
| `LRCLIB_API_URL` | `https://lrclib.net` | Base URL per il provider di testi LRCLIB. |
| `LYRICS_TTML_STORAGE_URL` | `https://lyrics-storage.binimum.org` | Servizio URL utilizzato per gli aggiornamenti TTML opzionali ai testi sincronizzati supportati. |
| `LYRICS_TTML_UPGRADE_TIMEOUT_SECONDS` | `3.0` | Tempo massimo di attesa per un aggiornamento TTML. Il risultato del testo originale rimane disponibile se l'aggiornamento scade. |
| `LYRICS_PROVIDER_CUSTOM_PATHS` | vuoto | Elenco opzionale separato da virgole di file o directory Python contenenti moduli di testo-provider personalizzati. Le directory vengono scansionate per i file `.py` di primo livello. |
| `LYRICS_PROVIDER_NETEASE_ENABLED` | `true` | Abilita il provider di testi NetEase. |
| `LYRICS_PROVIDER_LRCLIB_ENABLED` | `true` | Abilita il provider di testi LRCLIB. |

### Demucs ed elaborazione karaoke {#demucs-and-karaoke-processing}

Queste variabili controllano il modo in cui l'applicazione principale si connette e richiedono il lavoro dal servizio Demucs separato. Il servizio stesso ha variabili aggiuntive documentate di seguito.

| Variabile | Default | Descrizione |
| --- | --- | --- |
| `DEMUCS_API_URL` | `http://localhost:8001` | URL del servizio Demucs. In Docker Compose questo è comunemente `http://demucs:8001`; per un servizio remoto, utilizzare il suo HTTP URL raggiungibile. |
| `DEMUCS_API_KEY` | vuoto | Chiave API condivisa, facoltativa. Se il servizio è esposto al di fuori di una rete attendibile, imposta lo stesso valore nell'applicazione principale e nel servizio Demucs. |
| `DEMUCS_MODEL` | `htdemucs` | Modello Demucs richiesto per la separazione vocale. |
| `DEMUCS_DEVICE` | `cuda` | Utilizzare `cpu` quando CUDA non è disponibile. |
| `DEMUCS_OUTPUT_FORMAT` | `mp3` | I valori supportati sono `mp3` e `wav`. |
| `DEMUCS_MP3_BITRATE` | `320` | Bitrate MP3 in kbps quando il formato di output selezionato è MP3. |
| `SEPARATION_BACKEND` | `demucs` | I valori supportati sono `demucs` e `sherpa_spleeter`. |
| `SHERPA_SPLEETER_MODEL` | `fp16` | Variante del modello Sherpa+Spleeter quando `SEPARATION_BACKEND=sherpa_spleeter`. I valori supportati sono `fp16`, `int8` e `fp32`. |
| `DEMUCS_DIRECT_MEDIA_MAX_MB` | `500` | Dimensioni massime dei supporti, in MB, per l'elaborazione diretta senza prima copiare i supporti nel normale flusso di lavoro. |
| `DEMUCS_POLL_INTERVAL_SECONDS` | `1.0` | Intervallo tra i sondaggi in attesa di un'attività remota di Demucs. |
| `WHISPERX_TRANSCRIPTION_MODEL` | `tiny` | Modello di trascrizione WhisperX richiesto per l'allineamento lirico. |
| `WHISPERX_ALIGN_LANGUAGE` | `en` | Lingua passata all'allineamento WhisperX. |
| `WHISPERX_DETECT_LANGUAGE` | `false` | Consente a WhisperX di rilevare il linguaggio di trascrizione invece di utilizzare il linguaggio configurato. |
| `WHISPERX_USE_SYNCED_LYRICS` | `false` | Richiede testi sincronizzati come parte dell'elaborazione WhisperX quando supportato dal flusso di lavoro. |
| `WHISPERX_PRELOAD_MODELS` | `transcription=tiny,align=en` | Specifiche di precarico del modello WhisperX separate da virgole inviate al servizio Demucs. |

### Download e strumenti esterni {#downloads-and-external-tools}

| Variabile | Default | Descrizione |
| --- | --- | --- |
| `YTDLP_PATH` | `yt-dlp` | Percorso o nome eseguibile per yt-dlp. L'applicazione controlla prima l'ambiente virtuale attivo e poi il `PATH` di sistema. In Docker, usa `/data/tools/yt-dlp` e mantieni `/data` su uno storage persistente per aggiornare yt-dlp dalle impostazioni senza ricreare l'immagine. |
| `YTDLP_DENO_PATH` | vuoto | Percorso opzionale a Deno per l'esecuzione JavaScript esterna di yt-dlp. Lasciare vuoto a meno che un video non lo richieda. |
| `YTDLP_PROXY_URL` | vuoto | Opzionale HTTP, HTTPS, SOCKS4 o SOCKS5 proxy URL per yt-dlp e relative richieste in uscita. |
| `YTDLP_VIDEO_RESOLUTION` | `default` | I valori supportati sono `default`, `360`, `480`, `720`, `1080` e `2160`. |
| `YTDLP_VIDEO_CODEC` | vuoto | Preferenza codec video opzionale. Lasciare vuoto per la selezione predefinita; `avc` è supportato quando è necessaria una preferenza codec. |
| `CONCURRENT_YTDLP_SEARCH_ENABLED` | `false` | Consente ricerche yt-dlp simultanee. Ciò può aumentare le richieste in uscita e l'uso delle risorse. |
| `FFMPEG_PATH` | `ffmpeg` | Percorso o nome eseguibile per FFmpeg. |
| `FFMPEG_AUDIO_CODEC` | vuoto | Preferenza codec audio opzionale. Lasciare vuoto per la selezione predefinita; `aac` è supportato quando è necessaria una preferenza codec. |

### Registrazione dei log {#logging}

| Variabile | Default | Descrizione |
| --- | --- | --- |
| `LOG_LEVEL` | `INFO` | Livello di registrazione radice, come `DEBUG`, `INFO`, `WARNING` o `ERROR`. |
| `LOG_DIR` | `./logs` | Directory per il file di registro dell'applicazione. |
| `LOG_FILE_NAME` | `karaoke.log` | Log nome file all'interno di `LOG_DIR`. |
| `LOG_MAX_BYTES` | `5242880` (5 MB) | Dimensione massima di un file di registro prima della rotazione. |
| `LOG_BACKUP_COUNT` | `5` | Numero di file di registro ruotati da conservare. |
| `LOG_FORMAT` | <code>%(asctime)s &#124; %(levelname)s &#124; %(name)s &#124; %(message)s</code> | Stringa di formato di registrazione Python. |
| `LOG_TO_FILE_IN_RELOAD` | `false` | Abilita la registrazione dei file durante l'esecuzione in modalità di ricarica. Lasciare disabilitato durante lo sviluppo normale per evitare di ricaricare i loop causati dalle scritture di registro. |

### Comportamento del palco e dei WebSocket {#stage-and-websocket-behavior}

| Variabile | Default | Descrizione |
| --- | --- | --- |
| `STAGE_QR_URL` | vuoto | URL codificato nella sovrapposizione QR visualizzata sul palco. |
| `STAGE_LOBBY_MEDIA_PATH` | vuoto | Percorso opzionale `/media/...` o `/cache/...` utilizzato per il loop della lobby quando la coda è vuota. |
| `STAGE_VOCALS_VOLUME_DEFAULT` | `1.0` | Volume vocale predefinito applicato quando viene caricata la pagina del palco o della coda. Usare un valore da `0.0` a `1.0`. |
| `WS_HEARTBEAT_INTERVAL` | `30` | Intervallo del battito cardiaco WebSocket in pochi secondi. Il server utilizza questo per rilevare connessioni del browser stantie. |

## Servizio Demucs {#demucs-service}

Il servizio Demucs legge il proprio file di ambiente. Per impostazione predefinita cerca `.env` all'interno di `demucs_svc/`. Imposta `DEMUCS_ENV_FILE` quando la configurazione del servizio dovrebbe vivere in un altro percorso.

Queste variabili configurano il servizio di elaborazione GPU o CPU separato. Le variabili condivise con l'applicazione principale dovrebbero normalmente utilizzare valori corrispondenti.

### Percorsi e accesso al servizio {#service-paths-and-access}

| Variabile | Default | Descrizione |
| --- | --- | --- |
| `DEMUCS_ENV_FILE` | `demucs_svc/.env` | Percorso del file di ambiente di servizio Demucs. Questa variabile viene letta prima che il servizio carichi le sue impostazioni. |
| `DEMUCS_IO_ROOT` | `demucs_svc/io` | Directory radice per i lavori in entrata e l'output elaborato. I percorsi relativi vengono risolti dalla directory `demucs_svc`. |
| `DEMUCS_API_KEY` | vuoto | Chiave API condivisa opzionale richiesta dall'applicazione principale. Utilizzare lo stesso valore dell'`DEMUCS_API_KEY` dell'applicazione principale. |

### Impostazioni di elaborazione e dei modelli {#processing-and-model-settings}

| Variabile | Default | Descrizione |
| --- | --- | --- |
| `DEMUCS_MODEL` | `htdemucs` | Modello Demucs caricato dal servizio. |
| `DEMUCS_DEVICE` | `cuda` | Dispositivo utilizzato dal servizio. Utilizzare `cpu` per l'elaborazione solo CPU. |
| `DEMUCS_OUTPUT_FORMAT` | `wav` | Formato di output predefinito prodotto dal servizio. |
| `DEMUCS_MP3_BITRATE` | `320` | Bitrate MP3 in kbps quando si seleziona l'output MP3. |
| `SEPARATION_BACKEND` | `demucs` | I valori supportati sono `demucs` e `sherpa_spleeter`. |
| `SHERPA_SPLEETER_MODEL` | `fp16` | I valori supportati sono `fp16`, `int8` e `fp32`. |
| `SHERPA_SPLEETER_MODEL_ROOT` | `demucs_svc/model_data/sherpa_spleeter` | Directory in cui sono memorizzati i modelli Sherpa+Spleeter. I percorsi relativi vengono risolti da `demucs_svc`. |
| `SHERPA_SPLEETER_NUM_THREADS` | fino a `8` | Numero di thread CPU utilizzati da Sherpa+Spleeter. Il valore predefinito è limitato dal numero di host CPU. |
| `SHERPA_SPLEETER_FFMPEG_PATH` | `ffmpeg` | Percorso o nome eseguibile per FFmpeg utilizzato da Sherpa+Spleeter. |
| `WHISPERX_TRANSCRIPTION_MODEL` | `tiny` | Modello di trascrizione WhisperX utilizzato dal servizio. |
| `WHISPERX_ALIGN_LANGUAGE` | `en` | Linguaggio predefinito utilizzato per l'allineamento WhisperX. |
| `WHISPERX_DETECT_LANGUAGE` | `false` | Consente il rilevamento del linguaggio per la trascrizione WhisperX. |
| `WHISPERX_USE_SYNCED_LYRICS` | `false` | Utilizza i testi sincronizzati forniti durante l'esecuzione del flusso di lavoro di allineamento. |
| `WHISPERX_PRELOAD_MODELS` | `transcription=tiny,align=en` | Modelli richiesti durante il precarico di avvio del servizio. |

### Limiti delle risorse e pulizia {#resource-limits-and-cleanup}

| Variabile | Default | Descrizione |
| --- | --- | --- |
| `DEMUCS_MAX_CONCURRENT_JOBS` | `1` | Il numero massimo di processi di separazione elaborati contemporaneamente. Mantenere questo a `1` aiuta a evitare la contesa della memoria GPU. |
| `DEMUCS_MAX_UPLOAD_BYTES` | `2147483648` (2 GiB) | Dimensione massima di caricamento in entrata accettata dal servizio. |
| `DEMUCS_MIN_FREE_BYTES` | `1073741824` (1 GiB) | Minimo spazio libero richiesto prima di accettare un altro upload. |
| `DEMUCS_GC_INTERVAL_SECONDS` | `600` | Intervallo tra i controlli di pulizia programmati GPU-memory. |
| `DEMUCS_GC_LOW_FREE_VRAM_BYTES` | `2147483648` (2 GiB) | Soglia Free-VRAM che attiva una pulizia aggiuntiva. |

## Esempi di configurazione {#example-configurations}

### Applicazione locale minima {#minimal-local-application}

```dotenv
HOST=0.0.0.0
PORT=8000
MEDIA_PATH=/srv/karaoke/media
CACHE_PATH=/srv/karaoke/cache
DATABASE_URL=sqlite:////srv/karaoke/karaoke.db
```

### Applicazione principale collegata a un servizio Demucs remoto {#main-application-connected-to-a-remote-demucs-service}

```dotenv
DEMUCS_API_URL=http://demucs-host:8001
DEMUCS_API_KEY=replace-with-a-shared-secret
DEMUCS_DEVICE=cuda
YTDLP_DENO_PATH=/usr/local/bin/deno
```

### Archiviazione e log con Docker Compose {#docker-compose-storage-and-logging}

```dotenv
PUID=1000
PGID=1000
```

Il file Compose incluso mappa la directory host `data` in `/data` nel contenitore e definisce i percorsi dell'applicazione. `PUID` e `PGID` controllano l'utente numerico e il gruppo utilizzati dal contenitore per la proprietà bind-mount; sono variabili Compose piuttosto che le impostazioni dell'applicazione.

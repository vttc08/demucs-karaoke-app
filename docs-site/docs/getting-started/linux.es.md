# Linux

El despliegue en Linux usa systemd para gestionar la aplicación principal. Esta configuración es adecuada para instalaciones bare-metal y LXC.

## Instalación

### 1. Prepara la aplicación y las dependencias { #1-prepare-the-application-and-dependencies }

Clona la aplicación:

```bash
git clone https://github.com/vttc08/demucs-karaoke-app.git /opt/karaoke/app
```

Instala [uv](https://docs.astral.sh/uv/getting-started/installation/) y, después, instala las dependencias del sistema y de la aplicación:

```bash
sudo apt-get install ffmpeg
cd /opt/karaoke/app
uv venv
uv pip install -e .
```

!!! note

    La instalación predeterminada no incluye `numpy` ni `scipy`, necesarios para la [sincronización de voces](../tasks/create-ai-karaoke.md). Si necesitas la sincronización de voces, instala el extra `vocal-sync`:

```bash
uv pip install -e ".[vocal-sync]"
```

### 2. Instala Deno si lo necesitas

Algunos vídeos requieren la compatibilidad de yt-dlp con la ejecución de JavaScript externo. Instala [Deno](https://docs.deno.com/runtime/getting_started/installation/) solo si lo necesitas. El paquete npm es válido en hosts que ya disponen de npm:

```bash
npm install -g deno
which deno
```

### 3. Compila la documentación

En una configuración sin Docker, la documentación estática no se incluye de forma predeterminada en la aplicación. Puedes ejecutar la aplicación sin ella y usar la [documentación en línea](https://vttc08.github.io/demucs-karaoke-app/). Para compilar la documentación localmente, instala las dependencias de documentación y ejecuta el script de compilación:

```bash
uv pip install mkdocs mkdocs-material mkdocs-minify-plugin mkdocs-static-i18n pymdown-extensions
uv run scripts/build_docs.py
```

### 4. Configura el entorno

Guarda el entorno en `/etc/karaoke.env`:

La siguiente configuración debería funcionar en la mayoría de los casos. Sustituye las rutas de ejemplo y la URL del servicio por los valores de tu host. Puedes consultar la configuración detallada en la [sección de configuración](../configuration/settings.md).

```env
HOST=0.0.0.0
PORT=8000
DATABASE_URL=sqlite:////opt/karaoke/data/karaoke.db
MEDIA_PATH=/your/media/path
CACHE_PATH=/opt/karaoke/data/cache
LOG_DIR=/opt/karaoke/data/logs
YTDLP_PATH=yt-dlp
YTDLP_DENO_PATH=/usr/local/bin/deno
DEMUCS_API_URL=http://demucs-host:8001
```

!!! note

    `MEDIA_PATH` debe poder escribirse por el usuario que ejecuta la aplicación y tener espacio suficiente para tus archivos multimedia. Se admiten recursos compartidos SMB/NFS.

### 5. Crea el servicio systemd

Crea `/etc/systemd/system/karaoke.service` con el siguiente contenido:

```ini
[Unit]
Description=Karaoke main app
After=network-online.target
Wants=network-online.target

[Service]
User=<your-user>
Group=<your-group>
WorkingDirectory=/opt/karaoke/app
EnvironmentFile=/etc/karaoke.env
ExecStart=/usr/bin/env uv run uvicorn main:app --host 0.0.0.0 --port 8000
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### 6. Habilita e inicia el servicio

```bash
sudo systemctl daemon-reload
sudo systemctl enable karaoke.service
sudo systemctl start karaoke.service
sudo systemctl status karaoke.service
```

Después de cambiar las rutas de herramientas o almacenamiento en `/settings`, reinicia el servicio si el ajuste afecta a los montajes de inicio o al entorno del proceso.

### 7. Configura el usuario administrador y los ajustes predefinidos predeterminados

Desde el directorio de la aplicación, crea el primer usuario administrador e instala los ajustes predefinidos del escenario:

```bash
cd /opt/karaoke/app
uv run python scripts/admin_user.py create --username admin
uv run python scripts/default_presets.py
```

Cuando la aplicación esté en ejecución, abre `http://<your-server-ip>:8000/login` e inicia sesión con el usuario administrador que acabas de crear.

## Próximos pasos

- [Copia de seguridad, restauración y actualización](backup-and-restore.md)
- [Desplegar el servicio Demucs (opcional)](demucs-service.md)
- [Conectar clientes](clients.md)
- [Página de cola](../features/queue-page.md)
- [Crear karaoke con IA](../tasks/create-ai-karaoke.md)

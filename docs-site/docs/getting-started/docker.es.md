# Docker

### 1. Descarga el archivo Compose y `.env.example`

```bash
wget https://raw.githubusercontent.com/vttc08/demucs-karaoke-app/refs/heads/main/compose.yml
wget https://raw.githubusercontent.com/vttc08/demucs-karaoke-app/refs/heads/main/.env.example
```

### 2. Prepara el entorno y las carpetas

```bash
mkdir -p data
mv .env.example .env
```

- La aplicación se ejecuta de forma predeterminada como un usuario sin privilegios de root, por lo que la carpeta `data` debe crearse de antemano.
- Puedes cambiar `user: uid:gid` para que coincida con los permisos de tu host.

### 3. Configura el entorno { #3-configure-the-environment }

- Usa un editor de texto como `vim` o `nano` para revisar tanto la sección `environment` de `compose.yml` como `.env`. La configuración predeterminada debería ser suficiente para la mayoría de los casos de uso.

Hay dos imágenes disponibles:

- `vttc08/demucs-karaoke-app` es la imagen predeterminada que usa `compose.yml`.
- `vttc08/demucs-karaoke-app:vocal-sync` es una imagen más grande que incluye `numpy` y `scipy`, necesarios para el flujo de sincronización de voces.

!!! note

    Se requieren tokens de Musixmatch y Last.fm para disfrutar de la mejor experiencia con letras. Sin ellos, la funcionalidad de letras será limitada.

- [Token de Last.fm](https://www.last.fm/api/authentication)
- Token de Musixmatch (se requiere la aplicación de escritorio): [sigue esta guía](https://spicetify.app/docs/faq#sometimes-popup-lyrics-andor-lyrics-plus-seem-to-not-work)

### 4. Inicia la aplicación

```bash
docker compose up -d
docker compose logs -f
```

### 5. Configura el usuario administrador y los ajustes predefinidos predeterminados

```bash
docker compose exec -it karaoke python scripts/admin_user.py create --username admin
docker compose exec -it karaoke python scripts/default_presets.py
```

Cuando la aplicación esté en ejecución, abre `http://<your-server-ip>:8000/login` e inicia sesión con el usuario administrador que acabas de crear.

## Próximos pasos

- [Copia de seguridad, restauración y actualización](backup-and-restore.md)
- [Desplegar el servicio Demucs (opcional)](demucs-service.md)
- [Conectar clientes](clients.md)
- [Página de cola](../features/queue-page.md)
- [Crear karaoke con IA](../tasks/create-ai-karaoke.md)

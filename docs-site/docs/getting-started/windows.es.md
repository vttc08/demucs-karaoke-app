## Windows

Este documento explica cómo instalar la aplicación principal de karaoke en Windows. Para el servicio Demucs, consulta [Servicio Demucs](demucs-service.md).

### 1. Descarga Python/UV y las dependencias

- [Python](https://www.python.org/downloads/windows/) 3.11 o posterior; asegúrate de marcar "Add Python to PATH" durante la instalación.
- [UV](https://docs.astral.sh/uv/getting-started/installation/)
- [ffmpeg](https://ffmpeg.org/download.html) 6.0 o posterior; añádelo a PATH.
- [Deno](https://docs.deno.com/runtime/getting_started/installation/); añádelo a PATH solo si lo necesitas.

### 2. Añade los binarios a PATH

Abre "Edit the system environment variables" y añade lo siguiente a PATH:

- `C:\Tools\ffmpeg\bin` (o la ubicación donde instalaste ffmpeg, ffprobe y ffplay.exe)
- La ruta de Deno si es necesaria, por ejemplo `C:\Tools\deno`

Verifica desde la línea de comandos:

```powershell
ffmpeg -version
uv --version
deno --version  # only if needed
python --version
```

### 3. Descarga y configura la aplicación

```powershell
git clone https://github.com/vttc08/demucs-karaoke-app.git
cd demucs-karaoke-app
uv venv
uv pip install -e .
```

!!! tip
    Si git no está disponible, puedes descargar el ZIP desde GitHub y extraerlo.

!!! note
    La instalación predeterminada no incluye `numpy` ni `scipy`, necesarios para la [sincronización de voces](../tasks/create-ai-karaoke.md). Si necesitas la sincronización de voces, instala el extra `vocal-sync`:

    ```powershell
    uv pip install -e .[vocal-sync]
    ```

### 4. Compila la documentación

En una configuración sin Docker, la documentación estática no se incluye. Puedes ejecutar la aplicación sin ella y usar la [documentación en línea](https://vttc08.github.io/demucs-karaoke-app/). Para compilar la documentación, instala `mkdocs` y `mkdocs-material`:

```bash
uv pip install mkdocs mkdocs-material mkdocs-minify-plugin mkdocs-static-i18n
uv run scripts/build_docs.py
```

### 5. Configura el entorno

```powershell
cp .env.example .env
```

La configuración de entorno predeterminada debería funcionar en la mayoría de los casos. Puedes consultar la configuración detallada en la [página Ajustes](../configuration/settings.md).

### 6. Ejecuta la aplicación

```powershell
uv run uvicorn main:app --host 0.0.0.0 --port 8000
```

Para el inicio sin supervisión, usa el Programador de tareas o un contenedor de servicios como NSSM. Guarda los medios, la caché, los registros y la base de datos SQLite en un directorio que la cuenta de servicio pueda leer y escribir.

### 7. Configura el usuario administrador y los ajustes predefinidos predeterminados

Mientras la aplicación esté en ejecución, abre otra ventana de PowerShell en el directorio de la aplicación. Crea el primer usuario administrador e instala los ajustes predefinidos del escenario:

```powershell
uv run python scripts/admin_user.py create --username admin
uv run python scripts/default_presets.py
```

Cuando la aplicación esté en ejecución, abre `http://<your-server-ip>:8000/login` e inicia sesión con el usuario administrador que acabas de crear.

## Próximos pasos

- [Configurar la aplicación](../configuration/settings.md)
- [Desplegar el servicio Demucs (opcional)](demucs-service.md)
- [Clientes](clients.md)
- [Explorar la página de cola](../features/queue-page.md)

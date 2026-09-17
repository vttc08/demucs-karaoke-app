## Copia de seguridad y restauración

Para la aplicación principal, los únicos datos que deben respaldarse son `karaoke.db` en la carpeta `/data`; la aplicación conservará toda la configuración al trasladarla a otro lugar.
### Docker
Ejecuta el comando de copia de seguridad en la máquina host.
```bash
tar -czvf backup.tar.gz -C /path/to/data/ .
```
> Esto supone que la base de datos, los medios de karaoke y la caché se encuentran en la carpeta `/data`. Si los medios de karaoke están en otra ubicación, respalda también esas carpetas según corresponda.

Copia `compose.yml`, `.env` y `backup.tar.gz` a la nueva máquina host y restaura la copia de seguridad con el siguiente comando.
```bash
tar -xzvf backup.tar.gz -C /path/to/new/data/
docker compose up -d
```

Opcional: vuelve a escanear la biblioteca multimedia.

### Linux/Windows

El procedimiento es el mismo que con Docker: respalda la carpeta `/data` y restáurala en la nueva máquina host. Si la ruta de la carpeta es distinta, asegúrate de cambiar `MEDIA_PATH` y `CACHE_PATH` en el archivo `.env` para que apunten a la nueva ubicación.

En Windows, puedes usar `robocopy`.
```powershell
robocopy C:\path\to\data D:\path\to\new\data /E
```

### Demucs

No es necesario respaldar archivos de base de datos ni de configuración. El servicio puede ejecutarse simplemente modificando el archivo `.env`.

La aplicación descarga modelos. Si deseas respaldarlos, depende de la ubicación de tu caché de Hugging Face:

- SherpaONNX: `<demucs_svc_root>/model_data/sherpa_spleeter`
- Demucs y WhisperX: `$env:HF_HOME` o `%USERPROFILE%\.cache\huggingface` en Windows, `~/.cache/huggingface` en Linux

Los modelos se descargarán de nuevo si no se encuentran, por lo que quizá no sea necesario respaldarlos.

## Actualización { #upgrade }
### Docker
Descarga la imagen más reciente y reinicia el servicio.
```bash
docker compose pull
docker compose up -d
docker image prune -f
```
### Linux/Windows/Demucs
Descarga el código más reciente.
```bash
git pull
uv pip install -e . --upgrade
```
Reinicia el servicio mediante `systemd` o `services.msc` si es necesario.

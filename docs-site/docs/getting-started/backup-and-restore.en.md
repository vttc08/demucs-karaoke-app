## Backup and Restore
For the main application, the only data that needs to be backed up is `karaoke.db` in the `/data` folder and application will keep all configs when moved elsewhere.
### Docker
Execute the backup command on the host machine.
```bash
tar -czvf backup.tar.gz -C /path/to/data/ .
```
> This assume the database, karaoke media and cache is all located in `/data` folder. If your karaoke media is located elsewhere, backup these folders accordingly.

Copy the `compose.yml`, `.env` and `backup.tar.gz` to the new host machine and restore the backup with the following command.
```bash
tar -xzvf backup.tar.gz -C /path/to/new/data/
docker compose up -d
```

Optional: re-scan the media library

### Linux/Windows

Same procedure as Docker, backup the `/data` folder and restore it to the new host machine. If the folder path is different, be sure to change the `MEDIA_PATH` and `CACHE_PATH` in the `.env` file to point to the new location.

On Windows, you can use `robocopy`.
```powershell
robocopy C:\path\to\data D:\path\to\new\data /E
```

### Demucs

No database/config files need to be backed up. The service can run by simply modifying the `.env` file.

The application download models, if you want to backup the models, if depends on your huggingface cache location

- SherpaONNX: `<demucs_svc_root>/model_data/sherpa_spleeter`
- Demucs and WhisperX: `$env:HF_HOME` or `%USERPROFILE%\.cache\huggingface` on Windows, `~/.cache/huggingface` on Linux

The models will be downloaded again if not found, so it might not be necessary to backup.

## Upgrade
### Docker
Pull the latest image and restart the service.
```bash
docker compose pull
docker compose up -d
docker image prune -f
```
### Linux/Windows/Demucs
Download the latest code.
```bash
git pull
uv pip install -e . --upgrade
```
Restart the service, using `systemd` or `services.msc` if needed.
## 备份和恢复 { #backup-and-restore }
对于主应用，需要备份的是 `/data` 文件夹中的 `karaoke.db`。将应用移动到其他位置时，应用会保留所有配置。
### Docker { #docker }
在主机上执行备份命令：
```bash
tar -czvf backup.tar.gz -C /path/to/data/ .
```
> 以下命令假设数据库、卡拉 OK 媒体和缓存都位于 `/data` 文件夹中。如果卡拉 OK 媒体存放在其他位置，请一并备份相应目录。

将 `compose.yml`、`.env` 和 `backup.tar.gz` 复制到新主机，然后使用以下命令恢复备份：
```bash
tar -xzvf backup.tar.gz -C /path/to/new/data/
docker compose up -d
```

可选：重新扫描媒体库

### Linux/Windows { #linuxwindows }

Linux 和 Windows 的备份流程与 Docker 类似：备份 `/data` 文件夹，并将其恢复到新主机。如果目录路径发生变化，请修改 `.env` 中的 `MEDIA_PATH` 和 `CACHE_PATH`，使其指向新位置。

在 Windows 上，可以使用 `robocopy`：
```powershell
robocopy C:\path\to\data D:\path\to\new\data /E
```

### Demucs { #demucs }

Demucs 服务不需要备份数据库或配置文件。只需修改 `.env` 文件，即可在其他位置运行服务。

应用会自动下载所需模型。如果要备份模型，请根据 Hugging Face 缓存位置备份以下目录：

- SherpaONNX：`<demucs_svc_root>/model_data/sherpa_spleeter`
- Demucs 和 WhisperX：Windows 上的 `$env:HF_HOME` 或 `%USERPROFILE%\.cache\huggingface`，Linux 上的 `~/.cache/huggingface`

如果找不到这些模型，应用会重新下载，因此通常不一定需要备份模型文件。

## 升级 { #upgrade }
### Docker { #docker }
拉取最新 Docker 镜像并重启服务：
```bash
docker compose pull
docker compose up -d
docker image prune -f
```
### Linux/Windows/Demucs { #linuxwindowsdemucs }
下载最新代码：
```bash
git pull
uv pip install -e . --upgrade
```
如有需要，使用 `systemd` 或 `services.msc` 重启服务。

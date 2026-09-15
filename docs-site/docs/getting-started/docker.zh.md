# Docker { #docker }

### 1. 下载 Compose 文件和 `.env.example` { #1-download-the-compose-file-and-envexample }

```bash
wget https://raw.githubusercontent.com/vttc08/demucs-karaoke-app/refs/heads/main/compose.yml
wget https://raw.githubusercontent.com/vttc08/demucs-karaoke-app/refs/heads/main/.env.example
```

### 2. 准备环境和目录 { #2-prepare-the-environment-and-folders }

```bash
mkdir -p data
mv .env.example .env
```

- 主应用默认以非 root 用户运行，因此必须提前创建 `data` 目录。
- 你可以修改 `user: uid:gid`，使其与主机上的用户和组权限匹配。

### 3. 配置环境 { #3-configure-the-environment }

- 使用 `vim` 或 `nano` 等文本编辑器，检查 `compose.yml` 中的 `environment` 部分和 `.env` 文件。默认配置通常已经能够满足大多数使用场景。

目前提供两个 Docker 镜像：

- `vttc08/demucs-karaoke-app` 是 `compose.yml` 默认使用的镜像。
- `vttc08/demucs-karaoke-app:vocal-sync` 是较大的镜像，包含人声同步工作流程所需的 `numpy` 和 `scipy`。

!!! note

    要获得完整的歌词功能，需要配置 Musixmatch 和 Last.fm 的 token。未配置 token 时，歌词功能仍可使用，但可用的歌词来源会减少，结果也可能不完整。

- [Last.fm token](https://www.last.fm/api/authentication)
- Musixmatch token（需要桌面应用）：[请参阅此指南](https://spicetify.app/docs/faq#sometimes-popup-lyrics-andor-lyrics-plus-seem-to-not-work)

### 4. 启动应用程序 { #4-start-the-application }

```bash
docker compose up -d
docker compose logs -f
```

### 5. 配置管理员用户和默认预设 { #5-configure-the-admin-user-and-default-presets }

```bash
docker compose exec -it karaoke python scripts/admin_user.py create --username admin
docker compose exec -it karaoke python scripts/default_presets.py
```

应用程序启动后，打开 `http://<your-server-ip>:8000/login`，使用刚创建的管理员用户登录。

## 下一步 { #next-steps }

- [备份、恢复和升级](backup-and-restore.md)
- [部署 Demucs 服务（可选）](demucs-service.md)
- [连接客户端](clients.md)
- [队列页面](../features/queue-page.md)
- [创建 AI 卡拉 OK](../tasks/create-ai-karaoke.md)

# Linux { #linux }

Linux 部署使用 systemd 管理主应用。此方式适用于直接安装在 Linux 主机上，或安装在 LXC 容器中的场景。

## 安装 { #installation }

### 1. 准备主应用和依赖项 { #1-prepare-the-application-and-dependencies }

下载主应用代码：

```bash
git clone https://github.com/vttc08/demucs-karaoke-app.git /opt/karaoke/app
```

安装 [uv](https://docs.astral.sh/uv/getting-started/installation/)，然后安装系统依赖和应用依赖：

```bash
sudo apt-get install ffmpeg
cd /opt/karaoke/app
uv venv
uv pip install -e .
```

!!! note

    默认安装不包括人声同步所需的 `numpy` 和 `scipy`。如果需要使用[人声同步](../tasks/create-ai-karaoke.md)，请安装 `vocal-sync` 额外依赖：

    ```bash
    uv pip install -e ".[vocal-sync]"
    ```

### 2. 根据需要安装 Deno { #2-install-deno-if-needed }

某些视频需要 yt-dlp 提供外部 JavaScript 执行支持。只有在遇到这类视频时，才需要安装 [Deno](https://docs.deno.com/runtime/getting_started/installation/)。如果主机上已经安装了 npm，也可以直接使用 npm 包安装：

```bash
npm install -g deno
which deno
```

### 3. 构建文档 { #3-build-the-documentation }

在不使用 Docker 的部署中，应用默认不会内置静态文档。你可以不安装本地文档，直接运行应用并使用[在线文档](https://vttc08.github.io/demucs-karaoke-app/)。如果需要在本地构建文档，请安装文档依赖并运行构建脚本：

```bash
uv pip install mkdocs mkdocs-material mkdocs-minify-plugin mkdocs-static-i18n pymdown-extensions
uv run scripts/build_docs.py
```

### 4. 环境配置 { #4-configure-the-environment }

将环境变量保存到 `/etc/karaoke.env`：

以下配置通常适用于大多数场景。请将示例路径和服务 URL 替换为适合你主机的值。详细配置说明请参阅[配置部分](../configuration/settings.md)。

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

    运行主应用的用户必须能够写入 `MEDIA_PATH` 指定的目录，并且该目录需要有足够空间存放媒体文件。支持使用 SMB/NFS 共享目录。

### 5. 创建 systemd 服务 { #5-create-the-systemd-service }

创建 `/etc/systemd/system/karaoke.service`，内容如下：

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

### 6. 启用和启动服务 { #6-enable-and-start-the-service }

```bash
sudo systemctl daemon-reload
sudo systemctl enable karaoke.service
sudo systemctl start karaoke.service
sudo systemctl status karaoke.service
```

如果你在 `/settings` 中修改了工具路径或存储路径，并且该设置会影响服务启动时的挂载或进程环境，请重启 systemd 服务。

### 7. 配置管理员用户和默认预设 { #7-configure-the-admin-user-and-default-presets }

在应用程序目录中创建第一个管理员用户，并安装默认舞台预设：

```bash
cd /opt/karaoke/app
uv run python scripts/admin_user.py create --username admin
uv run python scripts/default_presets.py
```

应用程序启动后，打开 `http://<your-server-ip>:8000/login`，使用刚创建的管理员用户登录。

## 下一步 { #next-steps }

- [备份、恢复和升级](backup-and-restore.md)
- [部署 Demucs 服务（可选）](demucs-service.md)
- [连接客户端](clients.md)
- [队列页面](../features/queue-page.md)
- [创建 AI 卡拉 OK](../tasks/create-ai-karaoke.md)

## Windows { #windows }

本文介绍如何在 Windows 上安装主卡拉 OK 应用。有关 Demucs 服务的安装方法，请参阅 [Demucs 服务](demucs-service.md)。

### 1. 下载 Python、uv 和依赖项 { #1-download-pythonuv-and-dependencies }

- [Python](https://www.python.org/downloads/windows/) 3.11 或更高版本。安装时请勾选“Add Python to PATH”。
- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- [ffmpeg](https://ffmpeg.org/download.html) 6.0 或更高版本，并将其添加到 PATH。
- [Deno](https://docs.deno.com/runtime/getting_started/installation/)，仅在需要时安装并添加到 PATH。

### 2. 将可执行文件目录添加到 PATH { #2-add-binary-to-path }

打开“编辑系统环境变量”，将以下目录添加到 PATH：

- `C:\Tools\ffmpeg\bin`（或你安装 ffmpeg、ffprobe 和 ffplay.exe 的其他目录）
- 如果需要，添加 Deno 所在的目录，例如 `C:\Tools\deno`

在命令行中验证安装：

```powershell
ffmpeg -version
uv --version
deno --version  # only if needed
python --version
```

### 3. 下载并设置应用 { #3-download-and-setup-the-application }

```powershell
git clone https://github.com/vttc08/demucs-karaoke-app.git
cd demucs-karaoke-app
uv venv
uv pip install -e .
```

!!! tip
    如果无法使用 Git，可以从 GitHub 下载 ZIP 压缩包并解压。

!!! note
    默认安装不包括人声同步所需的 `numpy` 和 `scipy`。如果需要使用[人声同步](../tasks/create-ai-karaoke.md)，请安装 `vocal-sync` 额外依赖：

    ```powershell
    uv pip install -e .[vocal-sync]
    ```

### 4. 构建文档 { #4-build-documentation }

在不使用 Docker 的部署中，应用默认不会内置静态文档。你可以不安装本地文档，直接运行应用并使用[在线文档](https://vttc08.github.io/demucs-karaoke-app/)。如果需要构建本地文档，请安装 `mkdocs` 和 `mkdocs-material` 等文档依赖：

```bash
uv pip install mkdocs mkdocs-material mkdocs-minify-plugin mkdocs-static-i18n
uv run scripts/build_docs.py
```

### 5. 环境配置 { #5-configure-the-environment }

```powershell
cp .env.example .env
```

默认环境配置通常适用于大多数场景。详细配置说明请参阅[设置页面](../configuration/settings.md)。

### 6. 运行应用程序 { #6-running-the-application }

```powershell
uv run uvicorn main:app --host 0.0.0.0 --port 8000
```

如果需要让应用在无人值守的情况下自动启动，可以使用任务计划程序或 NSSM 等服务包装器。请将媒体文件、缓存、日志和 SQLite 数据库存放在服务账户具有读写权限的目录中。

### 7. 配置管理员用户和默认预设 { #7-configure-the-admin-user-and-default-presets }

应用运行期间，在应用目录中打开另一个 PowerShell 窗口。创建第一个管理员用户，并安装默认舞台预设：

```powershell
uv run python scripts/admin_user.py create --username admin
uv run python scripts/default_presets.py
```

应用启动后，打开 `http://<your-server-ip>:8000/login`，使用刚创建的管理员用户登录。

## 下一步 { #next-steps }

- [配置应用程序](../configuration/settings.md)
- [部署 Demucs 服务（可选）](demucs-service.md)
- [客户端](clients.md)
- [探索队列页面](../features/queue-page.md)

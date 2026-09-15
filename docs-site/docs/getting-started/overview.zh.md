# 开始使用 { #getting-started }

DMKaraoke 由两项服务组成。

- [主应用](#ways-to-deploy)：提供点歌队列、舞台控制和媒体管理功能的 Web 服务器。
- [Demucs 服务](demucs-service.md)：独立运行 WhisperX 和 Demucs，用于分离人声和生成带时间轴的歌词。

这种架构让你可以在性能要求较低的家用服务器上运行主应用，并将卡拉 OK 处理任务交给性能更强的电脑上的 Demucs 服务。Demucs 服务既可以运行在自己的另一台电脑上，也可以通过互联网使用朋友的电脑。两项服务通过 HTTP 通信，因此一项 Demucs 服务可以同时为多台卡拉 OK 服务器提供处理能力。

![DMKaraoke 架构](../assets/images/architecture.webp)

建议在 Linux 服务器上使用 Docker 容器部署 DMKaraoke 主应用。此外也支持不使用 Docker 的安装方式，例如直接安装在 Linux 系统或 LXC 容器中；也可以安装在 Windows 上。

## 部署方式 { #ways-to-deploy }

主应用是一项轻量级的 FastAPI Web 服务，使用 SQLite 数据库。它可以在任何 x64 或 ARM64 Linux 服务器上运行，包括 Raspberry Pi 4 或较旧的办公电脑。

<div class="grid cards" markdown>

-   :material-docker: **Docker**

    Linux 服务器的推荐部署方式。

    [:octicons-arrow-right-24: 查看 Docker 指南](docker.md)

-   :material-linux: **Linux**

    不使用 Docker，直接运行主应用。

    [:octicons-arrow-right-24: 查看 Linux 指南](linux.md)

-   :material-microsoft-windows: **Windows**

    在 Windows 上安装主应用或 Demucs 服务。

    [:octicons-arrow-right-24: 查看 Windows 指南](windows.md)

</div>

### Demucs 服务 { #demucs-service }

使用支持 CUDA 的 NVIDIA GPU 时，Demucs 服务可以获得最佳处理性能。没有此类 GPU 也可以运行，但会改用 CPU 处理，因此速度较慢。你也可以将 Demucs 服务部署在另一台电脑上。

- [Demucs 服务](demucs-service.md)

## 生产环境注意事项 { #production-considerations }

请定期备份应用数据和媒体文件，并在新版本发布后及时升级。有关备份、迁移和升级方法，请参阅[备份、恢复和升级](backup-and-restore.md)。

如果要在生产环境中部署 DMKaraoke，还应规划代理服务器或反向代理、监控和访问控制等配套服务。详情请参阅[服务器管理](../tasks/server-administration.md)。

## 舞台客户端 { #stage-client }
舞台客户端用于向观众显示卡拉 OK 歌词和视频。

建议使用运行 **Windows、Linux 或 macOS 的桌面设备**，例如笔记本电脑或台式机，尤其是在需要连接电视或投影仪时。也可以尝试使用移动设备投屏（AirPlay、Samsung DeX），但此方式尚未经过测试。

支持 Android 设备，但可能需要进一步调整舞台主题，才能在较小的窗口中获得合适的显示效果。

iOS/iPadOS 设备无法使用舞台客户端的全部功能。由于 Apple 浏览器的限制，这些设备不能同时播放两路音频，因此无法启用人声，只会播放伴奏。

此外，部分较旧的 Apple 设备仅支持 H.264 + AAC 媒体。请参阅 [iPhone 和 iPad 舞台显示指南](../tasks/stage-and-branding.md#use-an-iphone-or-ipad-as-a-stage-display)。

## 来宾客户端 { #guest-clients }
任何配有现代网页浏览器的设备都可以搜索歌曲、加入队列并控制卡拉 OK 媒体。

来宾设备必须能够通过本地网络或互联网访问主应用服务器。如果使用 Wi-Fi 客户端隔离或访客网络，请考虑配置反向代理，并在路由器上启用 hairpin NAT（发夹 NAT）。更多网络配置请参阅[服务器管理](../tasks/server-administration.md)。

平板电脑或笔记本电脑适合作为共享设备。可以启用自助终端模式，防止来宾离开应用。

[iPad 自助终端模式](https://support.apple.com/en-us/111795)

[Android 自助终端应用](https://github.com/RushB-fr/freekiosk)

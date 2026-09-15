# 工具 { #tools }

![工具设置](../assets/images/settings/tools.webp){ width="400" }

使用此区域检查网络和存储状态，而不会修改主应用配置。这些操作仅限管理员使用。

### 代理信息 { #proxy-info }

选择**检查代理**，通过 `ipinfo.io/json` 检查当前出站连接。结果会显示检测到的 IP 地址、位置和组织，有助于确认是否正在使用已配置的代理。

### 存储使用情况 { #storage-usage }

选择**检查存储**，估算媒体、缓存文件和 SQLite 数据库占用的空间。结果还会显示合计大小。

### 清理缓存和数据库 { #clean-cache-and-database }

选择**清除缓存和 DB**，删除临时缓存文件和过期的数据库记录。这不会删除已配置媒体路径中的媒体文件，但如果某个媒体项目曾被报告为缺失，请先查看结果，再依赖该项目继续操作。

### 检查 Demucs { #check-demucs }

添加或修改 Demucs URL 或 API key 后，可以使用此选项检查与 Demucs 服务的连接。

### 运行 Demucs GC { #run-demucs-gc }

手动强制 Demucs 服务执行垃圾回收，卸载 Demucs 和 WhisperX 模型，以释放显存。

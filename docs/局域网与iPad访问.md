# 局域网与 iPad 访问

Study Atlas 默认只监听 `127.0.0.1`，手机或 iPad 不能通过它访问 Mac 上的知识库。需要多端时，显式开启局域网模式：

```sh
sh start.sh --lan
```

Windows：

```bat
start.bat --lan
```

也可以直接执行：

```sh
python3 server.py --lan
```

## 连接步骤

1. Mac 与 iPad 连接同一个可信 Wi-Fi；Mac 保持开机并运行终端窗口。
2. 启动后终端会打印 `http://<私网 IP>:8765/`、`http://<电脑名>.local:8765/`，并提示登录码文件 `.local/lan-code.txt`。
3. **推荐使用 `.local` 地址**（例如 `http://zizhifadeMacBook-Pro-2.local:8765/`）：Wi-Fi 重新分配 IP 后它仍不变。若 iPad 解析不了 Bonjour，再改用终端打印的私网 IP。
4. 在 iPad Safari 打开地址，输入 `.local/lan-code.txt` 中的登录码。
5. 登录成功后，使用 Safari 分享菜单的“添加到主屏幕”，以后可像 App 一样打开；会话保留 30 天。
6. 登录码每次服务重启都会更新；需要让新设备登录时，查看当前 `.local/lan-code.txt`。

如果终端没有显示可用地址，可在 Mac 的“系统设置 → Wi-Fi → 详细信息”查看 IP。macOS 防火墙询问时，只允许“专用网络”上的 Python 接入；不要将 8765 端口映射到公网。

## 安全边界

- **默认本机模式不需要登录**；只有加 `--lan` 才监听 `0.0.0.0` 并启用登录。
- Host 只接受回环、RFC1918 私网、`.local` 和 Tailscale 的 `100.64.0.0/10` 地址；公网域名/IP、伪造 Origin 和跨站请求会被拒绝。
- 登录码文件与签名密钥在 `.local/`，权限为 0600；不会进入 GitHub、JSON 备份或导出文件。
- 会话 Cookie 为 `HttpOnly; SameSite=Strict`；写入仍需页面内存令牌，登录只解决“谁可以打开知识库”。
- 局域网模式走 HTTP，**不是加密传输**。只应在自己的可信 Wi-Fi 使用；公共 Wi-Fi、宿舍共享网络或不可信路由器上不要开启。
- 不会修改系统代理、DNS、hosts 或防火墙；不会自动端口转发，也不会把服务变成公网多用户系统。

## 远程使用

离开同一个 Wi-Fi 时，优先使用 **Tailscale** 等私有网络，而不是公网端口转发：

1. Mac 和 iPad 登录同一个 Tailscale 私有网络。
2. 用 `python3 server.py --lan` 启动；程序会接受 Tailscale 的 `100.x` 地址。
3. 在 iPad 打开 Mac 的 Tailscale IP，例如 `http://100.x.y.z:8765/`，输入登录码。

Tailscale 负责链路加密；应用层仍是单用户登录。不要将 8765 直接暴露到公网，也不要依赖“只改监听地址”来实现安全远程访问。

## 和 AirDrop、Handoff 等方式的区别

- **AirDrop** 只能传送文件，不能把 Mac 上正在运行的 Python 服务“投”到 iPad。它适合传送导出的 PDF、JSON 备份或教学讲义，不是实时访问。
- **Safari Handoff / iCloud 标签页** 可以把当前网页交接到 iPad，但前提仍是 iPad 能访问 Mac 的局域网或 Tailscale 地址，并且已经登录；它不替代服务端。
- **iCloud Drive / 网盘同步 `data/library.json`** 不适合实时使用：多端同时写入可能产生冲突或半个文件。要迁移时请用“导出 JSON → 合并导入”。
- **Universal Control / Sidecar** 是把 iPad 当 Mac 的输入或显示设备，不是让 iPad 独立打开网站。
- **在 iPad 上运行 Python 服务**（如 Pythonista/a-Shell）是另一套安装，受 iOS 后台限制，不推荐把当前项目直接搬过去。
- **公网隧道/端口转发**能远程访问，但会扩大攻击面；需要 HTTPS、访问策略和额外审计，不应作为默认方案。Tailscale 是更窄的私有网络方案。

## 多端同时编辑

所有设备共享同一份 `data/library.json`。如果两个设备几乎同时保存，后保存的一方会收到版本冲突提示，需要刷新后重试；不会静默覆盖先保存的内容。它不是在线的多人协作或实时同步系统。

## 退出与排障

- 局域网登录后，左侧栏底部会出现“退出局域网登录”；退出会清除当前浏览器会话，并使其他设备的会话失效。
- iPad 打不开：先确认 Mac 与 iPad 同网、Mac 未休眠、终端仍在运行；再检查 macOS 防火墙是否允许 Python 接收入站连接。
- 输入登录码后一直回到登录页：确认使用的是当前 `.local/lan-code.txt`，并检查 Safari 是否禁用了 Cookie。
- 连接超时：路由器可能启用了客户端隔离；改用同一路由器的另一频段或 Tailscale 私有网络。
- 不要通过公网 IP、端口转发或关闭防火墙来绕过连接问题。

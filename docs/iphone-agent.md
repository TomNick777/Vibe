# iPhone Agent 移植

## 运行关系

iPhone 17 Pro 通过 USB-C 数据线连接 StopWatch；StopWatch 是 USB 鼠标和键盘，使用 Wi-Fi 连接 Windows 电脑的 TCP 7300 端口。iPhone 通过 AirPlay 把屏幕投送给 Windows 上的 UxPlay。Python 服务接收图像、调用视觉模型、校准鼠标和发送操作指令。浏览器操作入口为 `http://127.0.0.1:8890`。

StopWatch 本身不运行投屏接收器或视觉模型。开发和备份时把 USB 接到电脑；使用时把 USB 接到 iPhone，指令经 Wi-Fi 传输。三者需要能在同一局域网通信。

## 代码来源

- [官方固件](https://github.com/m5stack/M5StopWatch-UserDemo)：`6b4aa125288b6fe9dca661f10159f6e1e5ee785c`。
- [移植源](https://github.com/onehumanbeing/esp32-iphone-agent)：`1f6a51aa3d7bdb3f12024693a559cd5b5f2b9c28`。
- 设备协议与 HID 时序移植为 ESP-IDF；电脑端复制自上游 `server` 并增加 Windows 图像传输。
- 保留上游 MIT 许可，见 `third-party/esp32-iphone-agent-LICENSE.txt` 及 `../server/LICENSE`。
- [UxPlay](https://github.com/FDH2/UxPlay)：本机源码 commit `ec203121355220dd90278a369eeabb0b8ba4f14a`，1.74 experimental。其内部 mDNS 实现不要求另外安装 Bonjour。UxPlay 单独编译、运行，保持其 GPL-3.0 许可。

## 已实现范围

- 官方菜单增加 iPhone Agent 图标、Wi-Fi/服务端/USB 状态和指令计数。
- 支持上游 `ping/home/move/press/release/click/scroll/type/key` 命令与 `hello` 握手。
- 支持相对鼠标、双轴滚轮、ASCII 输入、Cmd/Ctrl/Alt/Shift 组合键。
- A 键或屏幕按钮启动/停止；同时长按 A/B 返回菜单，停止 TCP/Wi-Fi，释放输入并卸载 HID。
- USB 操作与网络等待位于独立工作任务；不阻塞官方界面更新。
- 共享 Wi-Fi 栈初始化，避免与徽章 AP 重复初始化；退出后可以再开启徽章编辑。
- 新增输入格式、整数范围与 TCP 分包检查。单条指令最多 1024 字节，移动每轴最多 ±10000，滚轮每轴最多 ±127。超长行会丢弃到下一换行，不执行残留内容。
- Windows 用 GStreamer `tcpclientsink` 将 JPEG 发到 Python 回环监听端口，避免 `pass_fds`；保留 Unix 管道方式。

## 本机配置与构建

ESP-IDF 与工具安装在 `.tools/esp-idf`、`.tools/espressif`；MSYS2 位于 `.tools/msys64`，均只属于这个工作区。官方依赖由 `python fetch_repos.py` 拉取。

复制 `main/apps/app_iphone_agent/config.example.h` 为同目录 `config.local.h`，填写 2.4GHz Wi-Fi 名称、密码、Windows 电脑局域网 IPv4 和 TCP 端口（默认 7300）。这是本地忽略文件。没有配置时，应用显示未配置且不会启动桥接。

复制 `server/.env.example` 为 `server/.env`，设置 `LLM_BASE_URL`、`LLM_MODEL`、`LLM_API_KEY`。所选模型必须支持图片输入；先填入实际模型，模板中的示例不代表已经配置成功。手动控制与投屏检查不需要模型 API。

```powershell
./scripts/build-firmware.ps1
./scripts/build-uxplay.ps1
./scripts/start-agent.ps1
```

Python 环境可用 `uv venv server/.venv`、`uv pip install --python server/.venv/Scripts/python.exe -e 'server[dev]'` 重建。UxPlay 的 Windows 编译依赖按其官方 README，在 MSYS2 UCRT64 下安装 GCC、CMake、Ninja、pkgconf、libplist、GStreamer、gst-plugins-base/good/bad 和 gst-libav。

## 备份与首次真机验证

`scripts/backup-device.ps1` 读取完整 16MB Flash，并保存 SHA256 元数据。烧录使用官方分区布局，包含两个应用分区和 4MB 图片存储；实际设备布局尚需与备份核对。不要用原项目的 Arduino 烧录脚本覆盖官方固件。

配置并编译后，先检查完整备份，再通过 ESP-IDF 烧录。HID 工作时 USB 会重新枚举；需要烧录时按官方方法长按电源键约两秒直到绿灯亮进入下载模式。

真机验证依次检查：原有应用与图片、iPhone Agent 启停、USB 鼠标/键盘枚举、Wi-Fi/TCP 连接、投屏、手动点击/输入/滑动、校准、再运行一个简单 AI 任务。断开 Wi-Fi、锁定手机、退出应用后检查没有按键保持；退出后检查徽章 AP 仍可使用。

## 验证状态

协议 C++ 测试及电脑端 34 项 pytest / Ruff 通过，覆盖命令解析、Windows GStreamer JPEG/TCP 传输及服务启停。设备指针、键盘、AirPlay 发现、投屏、校准、AI 任务、重连与应用切换仍需真实 iPhone 验证；编译和单元测试不替代真机验收。

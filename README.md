# Vibe

<img src="assets/brand/vibe-icon.png" alt="Vibe 圆环眼睛 Logo" width="180">

Vibe 是基于 M5Stack StopWatch 的蓝牙语音输入与 AI 额度面板，目前支持 Codex 与 X 共享周额度，后续计划接入 Grokbot 宠物。

当前版本 **0.2**，专注蓝牙语音输入和 AI 额度显示。

圆屏显示眼睛与额度：左半环带以青色外线表示 Codex 周剩余、橙色内线表示五小时剩余，右半环为紫色 X 共享周剩余。轻触打开整屏额度页，左右滑动切换三项，轻触或十五秒无操作返回；录音开始立即返回。未知值显示 `--`，缓存或过期数据标为 `Cached`。旧版面板与主题已移除。

双线环对齐、菜单图标、蓝牙连接与退出重进已通过真机确认。BLE 语音与 X 共享周额度已通过此前真机验证；0.2 连接修复后的文字转写与长段录音仍待确认。Grokbot 宠物数据和 Codex 桌面实时等待确认状态尚未接通，当前眼睛为本地状态动画。蓝牙名称为 `Vibe-*`，兼容旧 `M5Codex-*`。

## 当前界面

<img src="docs/images/vibe-0.2-home.png" alt="Vibe 0.2 当前界面：左侧青橙双线、右侧紫环与中央眼睛" width="320">

依据当前固件绘制逻辑还原的界面预览截图，使用示例额度，非设备实拍。默认无时间或常驻文字；轻触可查看额度详情。

此前的三套淘汰方案及原始预览保存在 [设计归档](docs/designs/README.md)，仅供查看设计过程。

## 使用与开发

Windows Bridge：`./scripts/start-vibe.ps1 run`。原命令 `start-vibecoding.ps1` 保留为兼容入口。微信输入法选择 `CABLE Output`，按住说话快捷键为 `Ctrl+Win`；Windows 默认播放设备选择实际扬声器或耳机。

```powershell
uv venv --python 3.12 windows_bridge/.venv
uv pip install --python windows_bridge/.venv/Scripts/python.exe -e "windows_bridge[dev]"
./scripts/start-vibe.ps1 init
./scripts/start-vibe.ps1 doctor
./scripts/start-vibe.ps1 run
```

固件构建入口使用本地 `.tools/esp-idf` 与 `.tools/espressif`。安装 ESP-IDF v5.5.4 后，通过 `python fetch_repos.py` 获取项目依赖，再运行：

```powershell
./scripts/build-firmware.ps1 reconfigure
./scripts/build-firmware.ps1 build
windows_bridge/.venv/Scripts/python.exe -m pytest windows_bridge/tests -q
```

使用 ESP-IDF v5.5.4、LVGL v9.5.0；依赖通过 `python fetch_repos.py` 获取。本项目保留官方应用、双 OTA 分区与图片存储布局。烧录须使用验证备份和分区的 `scripts/flash-app.ps1`。

- [当前产品与验收说明](docs/vibe.md)
- [当前 Logo 与资源生成](assets/brand/README.md)
- [Windows Bridge](windows_bridge/README.md)

版本由根目录 `version.txt` 设置，设备版本显示直接读取固件描述；Bridge 版本在 `windows_bridge/m5vibe/__init__.py`，CLI 可用 `--version` 查询。

基础为 [M5Stack 官方出厂固件](https://github.com/m5stack/M5StopWatch-UserDemo)，BLE 语音移植基础源自 [M5stopwatch-vibecoding](https://github.com/liptoxli/M5stopwatch-vibecoding)。来源和版本见项目说明。

第三方版本与许可证见 [来源说明](docs/third-party/README.md)。

# Vibe Windows Bridge

Windows 原生 BLE Bridge，将设备麦克风音频写入 VB-CABLE，并回传 Codex 额度。
当前状态与验收边界见 [Vibe 说明](../docs/vibe.md)。

X 共享周额度通过官方 Grok CLI 使用的账单接口读取；先运行 `grok login --oauth` 登录。
Bridge 默认从 `~/.grok/auth.json` 读取当前登录，仅向官方账单地址发起只读查询。
配置 `grok_usage: false` 可关闭；`grok_auth_file` 可指定官方登录文件位置。
不要把 token 或 refresh token 填进项目配置。每次轮询重新读取 CLI 登录文件；
当前适配器不自行刷新或改写官方凭据。登录失效时运行 `grok login --oauth` 恢复，
同一账户的旧读数会标为过期；跨账户、缺失百分比或周窗口结束则显示未知。
该数据与 Codex 独立轮询和缓存，一方失败不会阻断另一方。

```powershell
uv venv --python 3.12 windows_bridge/.venv
uv pip install --python windows_bridge/.venv/Scripts/python.exe -e "windows_bridge[dev]"
./scripts/start-vibe.ps1 init
./scripts/start-vibe.ps1 doctor
./scripts/start-vibe.ps1 run
```

在设备菜单打开 Vibe；微信输入法使用“按住 Ctrl+Win 说话”和
`CABLE Output (VB-Audio Virtual Cable)`。默认 A 按住/松开控制语音，B 为 Return，
B 长按为 Ctrl+Return。配置保存在忽略的 `config.local.json`。

Windows 默认播放设备选择实际扬声器或耳机；Bridge 会单独向 `CABLE Input` 输出，
不需要将它设为系统默认播放设备。

VB-CABLE 是用户独立安装的 [第三方驱动](https://vb-audio.com/Cable/)，不包含在项目中。
Bridge 只写指定的虚拟输出，不修改默认音频设备，不保存录音，不上传音频。
设备只保留标准键盘 HID，已删除专用 Vendor HID 与三项控制。扫描兼容
`Vibe-*` 和旧 `M5Codex-*`，旧启动脚本仍可用。CLI 版本查询：`windows_bridge/.venv/Scripts/python.exe -m m5vibe --version`。

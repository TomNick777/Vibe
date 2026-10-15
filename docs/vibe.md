# Vibe 当前说明

版本：0.1。Vibe 定位为蓝牙语音输入、AI 额度面板与 Grokbot 宠物载体。

## 新界面：圆屏宠物

用户选择“下弧副表盘＋整屏额度页”。默认保留已验收的整圈周额度轨道：左半为 Codex 周剩余、右半为 X 共享周剩余，两者独立，不相加或平均。眼睛下方增加五小时剩余额度短弧，不显示常驻文字。上方时钟保留。

周环圆心 (233,233)、半径 214、线宽 13，左右各占 180 度，从底向顶镜像填充，上下平端相接。五小时短弧使用同一圆心、半径 137、40..140 度、线宽 9，圆端，独立表示五小时剩余；不再恢复旧左内环布局。

轻触圆屏进入整屏详情，默认显示 Codex 五小时额度。中心大百分比，下方显示 Remaining 和重置倒计时，外围显示该项独立进度，底部三点指示页码。左右滑动循环切换五小时、Codex 周、X 共享周；轻触详情页返回表盘，十五秒无操作自动返回。任何非 Idle 语音状态都会收起详情，并阻止打开或翻页。触摸按一次按下到释放判断，横向滑动至少 50px 且大于纵向位移时才翻页，翻页不同时触发轻触关闭。

无数据为 `--` / `Unavailable`，重置时间缺失显示 `Reset unavailable`；过期、缓存或断开连接的数据以 `Cached` 文字和暗色进度区分。不把百分比转换为虚构的 token/次数余额。设备绘制使用真实 Bridge 数据，设计预览中的示例数值不进入固件。

未连接时半闭眼，连接后正常睁眼并眨眼；录音时绿色、处理时蓝紫色、录音中断时橙色。状态色使用整屏统一的低亮度底色，仅在状态切换时改变，不绘制同心圆背景、不做持续呼吸。额度环颜色独立。录音指示条是状态动画，不代表测得的音量。

动画只使眼睛与录音指示条区域重绘，待机静止时不持续重绘；额度轨道仅在额度或有效性变化时更新，文字内容不变时不重复设置。

红色表示明确的 `needs_confirmation`，Windows 端只把新鲜的 `waitingOnApproval` / `waitingOnUserInput` 标记映射到该字段，未知状态不会触发。当前本机只读 app-server 的 thread/list 返回 `notLoaded`，因此**不能保证桌面 Codex 的等待确认会自动同步到屏幕**；红色显示与协议已实现，桌面实时状态源仍待接入。该限制不影响蓝牙录音与额度。

Codex 五小时与周额度按窗口时长 300 / 10080 分钟识别，不依赖 primary/secondary 的顺序。五小时数据独立缓存、独立判断过期；缺失时不借用周额度。

## 已实现与本轮删减

蓝牙语音链路为：设备 A 键与麦克风 → BLE → Windows Bridge → VB-CABLE → 微信输入法。上一版已由用户确认转写成功。当前保留 Codex / X 额度、缓存、圆屏眼睛、时钟和电量。旧两套主题、热力图、任务列表界面、旧宠物动画及其专用图片资源已按用户要求删除；当前眼睛尚不是 Grokbot 集成。

本轮移除了四个 Agent 的触摸入口及灯效、推理强度滑动与浮层、中央四向手势与浮层。对应槽位事件、Encoder/Radial 事件、Vendor HID 和 RPC 已从设备端删除。圆屏触摸详情页及语音所需的标准键盘保留。BLE 任务字段仍兼容接收，但应用已不订阅或展示旧任务列表。

Grokbot 宠物数据仍属于后续工作。Codex 历史面板字段、内部 `app_codex` 路径、NVS 命名与统计缓存继续兼容，避免仅为改名迁移真实数据。

## X 共享周额度

2026-10-15 已恢复官方 Grok CLI 登录，通过其实际使用的只读账单接口读取共享池，并由用户在 Grok Dashboard 核对一致。官方说明：[新套餐的共享周池](https://cursor.com/help/grok-bot/plans)，接口与字段来源：[官方 Grok Build billing 源码](https://github.com/xai-org/grok-build/blob/main/crates/codegen/xai-grok-shell/src/extensions/billing.rs)。这属于客户端使用的接口，不是承诺稳定的公开第三方配额 API。

`windows_bridge/m5vibe/grok.py` 仅查询 `https://cli-chat-proxy.grok.com/v1/billing?format=credits`，拒绝跳转，不发送模型消息。仅接受 `isUnifiedBillingUser=true`、明确的 `creditUsagePercent` 以及有效的周时间窗口；剩余为 100 减去已用百分比。没有百分比时不推算为 0% 已用；预付余额和按需费用不混入额度环。

数据独立缓存在忽略的 Bridge 状态文件；同账户网络故障时保留旧数据并置为过期，切换账户或周窗口结束后不继续显示旧池。凭据不进入配置、缓存或日志。每次轮询读取 CLI 最新登录文件，适配器不自行刷新凭据；如果官方登录失效，运行 `grok login --oauth` 恢复。默认随额度轮询间隔更新（300 秒），Grok 请求在线程中执行，不阻塞 BLE 录音循环。

沿用现有 `grokbot.weekly` 面板字段回传数据，X 额度首次接入仅更新 Bridge；之后额度卡界面改用 `X shared weekly` 标签，不改变 BLE 协议或 bond marker。Grokbot 独立宠物状态和桌面实时确认仍未接入。

## 日常语音设置

Windows 启动 `./scripts/start-vibe.ps1 run`，设备打开 Vibe。A 按住说话、松开结束；默认快捷键 `Ctrl+Win`，HID modifier 为 `0x09`。微信输入法麦克风选择 `CABLE Output (VB-Audio Virtual Cable)`。Windows 默认播放设备使用实际扬声器或耳机，Bridge 明确写入 `CABLE Input`。

蓝牙名称为 `Vibe-*`，Bridge 也识别旧 `M5Codex-*`。固件使用 static random 地址，Windows 连接必须保留 `winrt.address_type="random"`。固件仅发布标准键盘；初版 bond schema 为 4，电脑忘记设备后的单次恢复修订为 5，只清理蓝牙绑定与订阅记录，保留音频配置与额度缓存。正常重启不会重复清理。

菜单使用新的 Vibe LOGO；默认界面只用睡眼/睁眼和状态颜色表示 BLE 连接及语音状态，不再显示 `Sleeping - offline` / `Ready` 文字。连接不表示 Agent 已就绪。当前仅保留圆屏界面，旧两套主题及 Theme 切换按钮和设置读写逻辑已删除。

## 离线验证与部署边界

```powershell
./scripts/build-firmware.ps1 reconfigure
./scripts/build-firmware.ps1 build
windows_bridge/.venv/Scripts/python.exe -m pytest windows_bridge/tests -q
windows_bridge/.venv/Scripts/python.exe -m ruff check windows_bridge/m5vibe windows_bridge/tests
```

增加、删除源码或资源后需 reconfigure；ESP-IDF 的脚本模式不支持这里的 `CONFIGURE_DEPENDS`。

首轮删减时用户不在设备旁，未烧录。用户现已回到设备旁并启动界面改造与真机部署；当前发布保留构建与离线测试结论，下弧布局与详情页交互仍待真机回归。编译与单元测试不能替代实机验收。

用户回到设备后，先核验完整备份和安装分区表，再通过 `scripts/flash-app.ps1` 仅写应用分区。保留现有配对，检查菜单图标、圆屏、五小时短弧及整屏额度页、A 键长句录音、松开结束与连续重录、B 键、退出重进及官方应用切换。不得直接烧录上游大分区镜像。

版本 0.1 保留标准键盘语音通道，已取消的原生控制不在验收范围。

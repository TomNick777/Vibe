# Vibe LOGO

## 当前设备图标

`vibe-icon.svg` 是根据当前圆屏设计的可编辑图标，`vibe-icon.png` 为大图预览，`vibe-icon-200.png` 为设备原始尺寸预览。左侧青橙双线、右侧紫环与中央眼睛对应实际界面；没有文字和时钟，适合 200×200 菜单尺寸。静态弧长仅为品牌图形，不表示真实额度。

`scripts/build-vibe-icon.py` 直接绘制图形并生成两种源文件及 `main/assets/vibe/icon_vibe.c`。设备资源为 200×200 非压缩 RGB565（80,000 bytes），与官方菜单图标格式一致，不需要透明通道或解压。复现：`uv run --with pillow --python 3.12 python scripts/build-vibe-icon.py`。新增资源后执行固件 reconfigure 再编译。

## 历史品牌字标（v0.1）

设计把 V 字形、声波和小伙伴表情结合在一起，使用青色到紫色的配色。图片由内置 OpenAI 图像生成工具生成（2026-10-15），透明 PNG 原图保持不变。

- `vibe-logo-light.png`：深色字标，适合浅色背景。
- `vibe-logo-dark.png`：浅色字标，适合深色 AMOLED 背景和设备菜单。
- v0.1 菜单图标曾由深色字标缩放并压缩为 RGB565A8/LZ4；当前已由上述图标替代。

历史版本资源转换命令（当前脚本已更新为上面的直接绘制流程）：

```powershell
uv run --with pillow --with lz4 --python windows_bridge/.venv/Scripts/python.exe python scripts/build-vibe-icon.py
./scripts/build-firmware.ps1 reconfigure
./scripts/build-firmware.ps1 build
```

两张原图均为生成结果，并非可编辑矢量文件。设备图标仅做缩放、像素格式和压缩转换。图像生成并不保证逐像素遵守提示词，最终采用的是仓库中的实际图像。

## 原始生成提示词

Tool: built-in `image_gen.imagegen`, transparent_background=true.

```text
Use case: logo-brand. Design one original finished logo for a personal product named exactly "Vibe" (V capital, i b e lowercase). Vibe is a small round AMOLED wearable/desk companion providing Bluetooth voice input, AI quota dashboards, and eventually a virtual pet. Create a distinctive compact symbol where a readable letter V and a flowing voice waveform are fused into one simple, confident silhouette; a subtle friendly companion character is appropriate but keep it abstract and very restrained. Add the exact wordmark "Vibe" underneath the symbol, using elegant rounded geometric lettering and excellent spacing. Composition: one centered logo lockup on a square, genuinely transparent canvas with generous clear margins. The symbol should dominate, with the wordmark clearly readable at small sizes; it must work as an app launcher icon on a dark OLED screen and as a project identity. Style: polished flat graphic logo, crisp clean edges, few solid colors, balanced negative space, strong legibility, warm and approachable but technically precise. Choose a cohesive high-contrast color treatment suitable for the existing dark dashboard. No mockups, no physical devices, no presentation board, no extra variants, no watermark, no slogans, no gradients, no glow, no drop shadow. Do not borrow any OpenAI, Codex, Grok or Bluetooth trademark shapes. Output only the single logo with real alpha transparency.
```

输出原文件：`exec-c5891a96-7f8b-4b31-a221-c477cd767426.png`，保存为 `vibe-logo-light.png`。

## 深色背景版本编辑提示词

Tool: built-in `image_gen.imagegen`, referenced_image_paths=[assets/brand/vibe-logo-light.png], transparent_background=true.

```text
Edit this Vibe logo to create its dark-surface version. Make exactly one change: recolor only the bottom wordmark "Vibe" from dark navy to a near-white light neutral, #EEF2FF, so it reads clearly on a dark AMOLED background. Preserve the icon/symbol above exactly, including its shape, face, V silhouette, cyan/purple coloring, contours, size, position and spacing. Preserve the exact spelling and geometry of the wordmark, the canvas size and overall lockup. Keep the background genuinely transparent and preserve the existing alpha. No additional graphics, no background, no mockup, no shadow, no tagline. Only change the wordmark color.
```

输出原文件：`exec-b1d3485e-9a55-4d50-88fe-9d4a12e06dca.png`，保存为 `vibe-logo-dark.png`。

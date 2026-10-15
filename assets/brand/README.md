# Vibe LOGO

设计把 V 字形、声波和小伙伴表情结合在一起，使用青色到紫色的配色。图片由内置 OpenAI 图像生成工具生成（2026-10-15），透明 PNG 原图保持不变。

- `vibe-logo-light.png`：深色字标，适合浅色背景。
- `vibe-logo-dark.png`：浅色字标，适合深色 AMOLED 背景和设备菜单。
- `main/assets/vibe/icon_vibe.c`：深色背景版本缩放至 200×200 后转换为 RGB565A8，采用 LVGL LZ4 压缩；转换时验证解压数据完全一致。

复现资源转换（从仓库根目录执行）：

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

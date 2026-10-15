"""Capture Vibe UI previews, not device photographs.

Run: uv run --with playwright --python 3.12 python scripts/render-ui-previews.py
Uses an installed Edge browser. Current geometry follows view/vibe.cpp;
archived screenshots are captured from the original design fragments.
"""
import math
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
DESIGNS = ROOT / "docs/designs"
IMAGES = ROOT / "docs/images"


def arc(radius, start, end, color, width):
    def point(angle):
        angle = math.radians(angle)
        return 233 + radius * math.cos(angle), 233 + radius * math.sin(angle)

    x1, y1 = point(start)
    x2, y2 = point(end)
    return (f'<path d="M{x1:.3f},{y1:.3f} A{radius},{radius} 0 '
            f'{int(end-start > 180)},1 {x2:.3f},{y2:.3f}" '
            f'fill="none" stroke="{color}" stroke-width="{width}"/>')


def current_markup():
    # SVG centered strokes correspond to LVGL outer radii 223/213.
    # Example values only: weekly 68%, five-hour 35%, X weekly 90%.
    marks = ['<circle cx="233" cy="233" r="233" fill="#05080d"/>',
             ('<circle cx="233" cy="233" r="214" fill="none" '
              'stroke="#202832" stroke-width="18"/>'),
             arc(219, 90, 90 + 180*0.68, "#74e3f3", 8),
             arc(209, 90, 90 + 180*0.35, "#ffbb68", 8),
             arc(214, 450 - 180*0.90, 450, "#b39aff", 18)]
    for center in (183, 283):
        marks.append(f'<rect x="{center-19}" y="183" width="38" height="64" '
                     'rx="19" fill="#83c9f4"/>')
        marks.append(f'<rect x="{center-9}" y="192" width="8" height="12" '
                     'rx="4" fill="#f0fdff" opacity="0.627"/>')
    return ('<div id="vibe-current" style="width:466px;height:466px">'
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 466 466" '
            'width="466" height="466" role="img" aria-label="Vibe 0.2 界面预览，示例额度">'
            + "".join(marks) + '</svg></div>')


def main():
    IMAGES.mkdir(parents=True, exist_ok=True)
    latest = current_markup()
    (DESIGNS / "current.html").write_text(latest + "\n", encoding="utf-8")
    captures = [
        ("current.html", None, "#vibe-current", "vibe-0.2-home.png"),
        ("round-quota.html", "下弧副表盘", ".dial", "archived-subdial.png"),
        ("round-quota.html", "三段外圈", ".dial", "archived-segments.png"),
        ("shared-ring.html", "宽轨叠线", "svg", "archived-overlay.png"),
    ]
    errors = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page(viewport={"width": 736, "height": 760}, device_scale_factor=2)
        page.on("pageerror", lambda error: errors.append(str(error)))
        for filename, variant, selector, destination in captures:
            fragment = (DESIGNS / filename).read_text(encoding="utf-8")
            page.set_content('<style>body{margin:24px;background:transparent}</style>' + fragment)
            if variant:
                page.locator("section[data-variant]").evaluate_all(
                    "(sections, selected) => sections.forEach(s => "
                    "s.hidden = s.dataset.variant !== selected)", variant)
                target = page.locator(f'section[data-variant="{variant}"] {selector}')
            else:
                target = page.locator(selector)
            target.screenshot(path=str(IMAGES / destination), omit_background=True)
            print(f"Captured {destination}")
        browser.close()
    if errors:
        raise RuntimeError(errors)


if __name__ == "__main__":
    main()

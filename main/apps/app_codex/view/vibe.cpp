// SPDX-License-Identifier: MIT
// Vibe: the round display is the companion's body. All geometry is in 466px coordinates.
#include "view.h"
#include <hal/hal.h>
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstring>

using namespace view;
using namespace uitk::lvgl_cpp;

namespace {
constexpr uint32_t kWeek = 0x74E3F3;
constexpr uint32_t kFive = 0xFFBB68;
constexpr uint32_t kGrok = 0xB39AFF;
constexpr uint32_t kTrack = 0x202832;
constexpr uint32_t kDim = 0x697585;

bool activeUntil(uint32_t deadline, uint32_t now)
{
    return deadline != 0 && static_cast<int32_t>(deadline - now) > 0;
}

void setTextIfChanged(Label& label, const char* text)
{
    if (!label.getText() || std::strcmp(label.getText(), text) != 0) label.setText(text);
}
}

CodexView::QuotaDisplay CodexView::quotaDisplay(uint8_t page) const
{
    const bool cached = _vibe_quota.cached || !_state.bleConnected;
    switch (page) {
    case 0:
        return {"Codex - 5 hours", _vibe_quota.fiveHourLeftPct,
                _vibe_quota.fiveHourStale || cached, kFive, &_vibe_quota.fiveHourReset};
    case 1:
        return {"Codex - Weekly", _vibe_quota.valid ? _vibe_quota.weeklyLeftPct : -1,
                _vibe_quota.stale || cached, kWeek, &_vibe_quota.weeklyUsage};
    default:
        return {"X - Shared weekly", _vibe_quota.grokbotWeeklyLeftPct,
                _vibe_quota.grokbotStale || cached, kGrok, &_vibe_quota.grokbotWeeklyReset};
    }
}

void CodexView::initVibe(lv_obj_t* parent)
{
    lv_obj_remove_flag(parent, LV_OBJ_FLAG_SCROLLABLE);
    _panel = std::make_unique<Container>(parent);
    _panel->setSize(466, 466);
    _panel->align(LV_ALIGN_CENTER, 0, 0);
    _panel->setPaddingAll(0);
    _panel->setBorderWidth(0);
    _panel->setRadius(LV_RADIUS_CIRCLE);
    _panel->setBgColor(lv_color_hex(0x05080D));
    _panel->setBgOpa(LV_OPA_COVER);
    _panel->removeFlag(LV_OBJ_FLAG_SCROLLABLE);

    _vibe_canvas = std::make_unique<Container>(_panel->get());
    _vibe_canvas->setSize(466, 466);
    _vibe_canvas->align(LV_ALIGN_CENTER, 0, 0);
    _vibe_canvas->setBgOpa(LV_OPA_TRANSP);
    _vibe_canvas->setBorderWidth(0);
    _vibe_canvas->setPaddingAll(0);
    _vibe_canvas->removeFlag(LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_add_event_cb(_vibe_canvas->get(), drawVibeEvent, LV_EVENT_DRAW_MAIN_BEGIN, this);
    lv_obj_add_flag(_vibe_canvas->get(), LV_OBJ_FLAG_CLICKABLE);
    // Track one press through release so swipes cannot also trigger a tap.
    for (auto code : {LV_EVENT_PRESSED, LV_EVENT_PRESSING, LV_EVENT_RELEASED, LV_EVENT_PRESS_LOST}) {
        lv_obj_add_event_cb(_vibe_canvas->get(), touchVibeEvent, code, this);
    }

    auto makeLabel = [&](std::unique_ptr<Label>& label, int y, const lv_font_t* font) {
        label = std::make_unique<Label>(_panel->get());
        label->setTextFont(font);
        label->setTextColor(lv_color_hex(0xC4D2DF));
        label->setWidth(300);
        label->setTextAlign(LV_TEXT_ALIGN_CENTER);
        label->setLongMode(LV_LABEL_LONG_MODE_CLIP);
        label->align(LV_ALIGN_TOP_MID, 0, y);
        label->removeFlag(LV_OBJ_FLAG_CLICKABLE);
    };
    makeLabel(_vibe_quota_name, 132, &lv_font_montserrat_20);
    makeLabel(_vibe_quota_value, 186, &lv_font_montserrat_48);
    lv_obj_set_style_transform_pivot_x(_vibe_quota_value->get(), 150, 0);
    lv_obj_set_style_transform_pivot_y(_vibe_quota_value->get(), 24, 0);
    lv_obj_set_style_transform_scale(_vibe_quota_value->get(), 384, 0);
    makeLabel(_vibe_quota_caption, 264, &lv_font_montserrat_18);
    makeLabel(_vibe_quota_reset, 308, &lv_font_montserrat_18);
    for (auto* label : {_vibe_quota_name.get(), _vibe_quota_value.get(),
                        _vibe_quota_caption.get(), _vibe_quota_reset.get()}) {
        label->setHidden(true);
    }
    updateVibe();
}

void CodexView::updateVibe()
{
    const auto now = GetHAL().millis();
    const bool connected = _state.bleConnected;
    const bool recording = _voice_mode == VoiceMode::Recording;
    const bool error = _voice_mode == VoiceMode::Interrupted;
    const bool hostLive = connected && !_vibe_quota.cached && now - _vibe_panel_at < 30000;
    const bool approval = hostLive && _vibe_quota.needsConfirmation;
    const bool busy = connected && (_voice_mode == VoiceMode::Processing ||
                                   (_state.processing && hostLive));
    const uint32_t background = !connected ? 0x050608 : error ? 0x1C1105 : recording ? 0x04180D :
                                approval ? 0x1C070B : busy ? 0x10091B : 0x05080D;
    const bool colorChanged = background != _vibe_background;
    if (colorChanged) {
        _panel->setBgColor(lv_color_hex(background));
        _vibe_background = background;
    }
    if (_voice_mode != VoiceMode::Idle) {
        _vibe_details_until = 0;
        _vibe_touch_tracking = false;
    }
    const bool details = activeUntil(_vibe_details_until, now);
    if (details != _vibe_details_visible) {
        _vibe_details_visible = details;
        _vibe_details_dirty = true;
        for (auto* label : {_vibe_quota_name.get(), _vibe_quota_value.get(),
                            _vibe_quota_caption.get(), _vibe_quota_reset.get()}) {
            label->setHidden(!details);
        }
        _vibe_full_redraw = true;
    }
    if (details && _vibe_details_dirty) {
        const auto reading = quotaDisplay(_vibe_details_page);
        char value[16] = "--";
        if (reading.remaining >= 0) std::snprintf(value, sizeof(value), "%d%%", reading.remaining);
        setTextIfChanged(*_vibe_quota_name, reading.name);
        setTextIfChanged(*_vibe_quota_value, value);
        setTextIfChanged(*_vibe_quota_caption, reading.remaining < 0 ? "Unavailable" :
                         reading.stale ? "Remaining - Cached" : "Remaining");
        const std::string reset = reading.remaining < 0 || *reading.reset == "--" ? "Reset unavailable" :
                                  "Resets in " + *reading.reset;
        setTextIfChanged(*_vibe_quota_reset, reset.c_str());
        _vibe_details_dirty = false;
    }
    const bool animating = !connected || recording || busy || now % 4700 < 200 ||
                           activeUntil(_vibe_touch_until, now);
    if (_vibe_full_redraw) {
        lv_obj_invalidate(_vibe_canvas->get());
        _vibe_full_redraw = false;
    } else if (!details && (animating || _vibe_was_animating || colorChanged)) {
        // Include both eyes' complete motion envelope and the recording bars.
        // Stable quota rings and labels no longer repaint at the animation rate.
        lv_area_t area;
        lv_obj_get_coords(_vibe_canvas->get(), &area);
        area.x2 = area.x1 + 320;
        area.y2 = area.y1 + 275;
        area.x1 += 145;
        area.y1 += 174;
        lv_obj_invalidate_area(_vibe_canvas->get(), &area);
    }
    _vibe_was_animating = animating;
}

void CodexView::touchVibeEvent(lv_event_t* event)
{
    auto* self = static_cast<CodexView*>(lv_event_get_user_data(event));
    const auto code = lv_event_get_code(event);
    if (self->_voice_mode != VoiceMode::Idle || code == LV_EVENT_PRESS_LOST) {
        self->_vibe_touch_tracking = false;
        return;
    }
    auto* indev = lv_event_get_indev(event);
    if (!indev) return;
    lv_point_t point;
    lv_indev_get_point(indev, &point);
    if (code == LV_EVENT_PRESSED) {
        self->_vibe_touch_start = point;
        self->_vibe_touch_tracking = true;
        if (self->_vibe_details_visible) self->_vibe_details_until = GetHAL().millis() + 15000;
        return;
    }
    if (!self->_vibe_touch_tracking) return;
    if (code != LV_EVENT_RELEASED) {
        if (self->_vibe_details_visible) self->_vibe_details_until = GetHAL().millis() + 15000;
        return;
    }
    self->_vibe_touch_tracking = false;
    const int dx = point.x - self->_vibe_touch_start.x;
    const int dy = point.y - self->_vibe_touch_start.y;
    const auto now = GetHAL().millis();
    const bool details = activeUntil(self->_vibe_details_until, now);
    if (std::abs(dx) >= 50 && std::abs(dx) > std::abs(dy)) {
        if (!details) return;
        self->_vibe_details_page = (self->_vibe_details_page + (dx < 0 ? 1 : 2)) % 3;
        self->_vibe_details_dirty = true;
        self->_vibe_details_until = now + 15000;
        self->_vibe_full_redraw = true;
    } else if (std::abs(dx) < 20 && std::abs(dy) < 20) {
        if (details) {
            self->_vibe_details_until = 0;
        } else {
            self->_vibe_details_page = 0;
            self->_vibe_details_until = now + 15000;
        }
        self->_vibe_touch_until = now + 700;
    }
}

void CodexView::drawVibeEvent(lv_event_t* event)
{
    auto* self = static_cast<CodexView*>(lv_event_get_user_data(event));
    lv_area_t area;
    lv_obj_get_coords(self->_vibe_canvas->get(), &area);
    self->drawVibe(lv_event_get_layer(event), area.x1, area.y1);
}

void CodexView::drawVibe(lv_layer_t* layer, int x, int y)
{
    const uint32_t now = GetHAL().millis();
    const float t = static_cast<float>(now % 60000) / 1000.0f;
    const bool connected = _state.bleConnected;
    const bool recording = connected && _voice_mode == VoiceMode::Recording;
    const bool error = connected && _voice_mode == VoiceMode::Interrupted;
    const bool hostLive = connected && !_vibe_quota.cached && now - _vibe_panel_at < 30000;
    const bool approval = hostLive && _vibe_quota.needsConfirmation;
    const bool busy = connected && (_voice_mode == VoiceMode::Processing || (_state.processing && hostLive));
    const uint32_t color = !connected ? 0x768193 : error ? 0xFFBC63 : recording ? 0x6CEAA4 :
                           approval ? 0xFF7185 : busy ? 0xB6A0FF : 0x83C9F4;
    auto rect = [&](int left, int top, int w, int h, int radius, uint32_t fill, lv_opa_t opa) {
        lv_draw_rect_dsc_t d;
        lv_draw_rect_dsc_init(&d);
        d.bg_color = lv_color_hex(fill);
        d.bg_opa = opa;
        d.radius = radius;
        lv_area_t a = {x + left, y + top, x + left + w - 1, y + top + h - 1};
        lv_draw_rect(layer, &d, &a);
    };
    auto arc = [&](int radius, int start, int end, uint32_t fill, lv_opa_t opa, int width) {
        if (end <= start) return;
        lv_draw_arc_dsc_t d;
        lv_draw_arc_dsc_init(&d);
        d.center = {x + 233, y + 233};
        d.radius = radius;
        d.start_angle = start % 360;
        d.end_angle = end - start >= 360 ? d.start_angle + 360 : end % 360;
        d.width = width;
        d.color = lv_color_hex(fill);
        d.opa = opa;
        d.rounded = width == 15;  // Only the independent detail dial has rounded ends.
        lv_draw_arc(layer, &d);
    };
    auto progress = [&](int radius, int start, int sweep, int pct, bool stale,
                        uint32_t fill, int width, bool reverse = false) {
        if (pct < 0) return;
        const int span = sweep * std::clamp(pct, 0, 100) / 100;
        const int from = reverse ? start + sweep - span : start;
        arc(radius, from, from + span, stale ? kDim : fill, stale ? 120 : LV_OPA_COVER, width);
    };
    const auto five = quotaDisplay(0);
    const auto week = quotaDisplay(1);
    const auto shared = quotaDisplay(2);
    if (_vibe_details_visible) {
        const auto reading = quotaDisplay(_vibe_details_page);
        arc(207, 130, 410, kTrack, LV_OPA_COVER, 15);
        progress(207, 130, 280, reading.remaining, reading.stale, reading.color, 15);
        for (int i = 0; i < 3; ++i) {
            rect(215 + i * 15, 376, 6, 6, 3, i == _vibe_details_page ? 0xD5E2EF : kTrack, LV_OPA_COVER);
        }
        return;
    }
    // Two independent Codex readings share one left band without hiding each other.
    // LVGL uses the OUTER radius, while the preview uses a centered stroke.
    // Both halves occupy radii 205..223; left lanes leave a 2px middle gap.
    constexpr int ringOuter = 223;
    constexpr int ringWidth = 18;
    constexpr int laneWidth = 8;
    constexpr int laneGap = 2;
    arc(ringOuter, 0, 360, kTrack, LV_OPA_COVER, ringWidth);
    progress(ringOuter, 90, 180, week.remaining, week.stale, week.color, laneWidth);
    progress(ringOuter - laneWidth - laneGap, 90, 180, five.remaining, five.stale, five.color, laneWidth);
    progress(ringOuter, 270, 180, shared.remaining, shared.stale, shared.color, ringWidth, true);

    const uint32_t blinkPhase = now % 4700;
    float open = !connected ? 0.22f + 0.05f * std::sin(t) : 1.0f;
    if (connected && blinkPhase < 180 && !recording && !approval) {
        open = std::abs(static_cast<float>(blinkPhase) - 90.0f) / 90.0f;
    }
    if (activeUntil(_vibe_touch_until, now)) open = 0.22f;
    int height = std::max(6, static_cast<int>(64 * open));
    int shift = busy ? static_cast<int>(8 * std::sin(t * 2)) : 0;
    int lift = !connected ? static_cast<int>(3 * std::sin(t)) : recording ? static_cast<int>(2 * std::sin(t * 5)) : 0;
    for (int center : {183, 283}) {
        rect(center - 19 + shift, 215 - height / 2 + lift, 38, height, 19, color, connected ? LV_OPA_COVER : 135);
        if (connected && height > 30) rect(center - 9 + shift, 215 - height / 2 + 9 + lift, 8, 12, 4, 0xF0FDFF, 160);
    }
    // A quiet listening indicator rather than an invented audio waveform.
    if (recording) for (int i = 0; i < 5; ++i) {
        const int h = 5 + static_cast<int>(9 * (1 + std::sin(t * 6 + i * 0.8f)));
        rect(209 + i * 10, 257 - h / 2, 5, h, 3, color, 210);
    }
}

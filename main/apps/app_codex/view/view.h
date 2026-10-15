// SPDX-License-Identifier: MIT
#pragma once
#include <smooth_lvgl.hpp>
#include <smooth_ui_toolkit.hpp>
#include <uitk/short_namespace.hpp>
#include <apps/app_codex/codex_quota_client.h>
#include <cstdint>
#include <memory>

namespace view {
class CodexView {
public:
    enum class VoiceMode : uint8_t { Idle, Recording, Processing, Interrupted };
    void init(lv_obj_t* parent);
    void update();
    void applySnapshot(const codex::QuotaSnapshot& snapshot);
    void applyBleState(bool connected);
    void setVoiceMode(VoiceMode mode);
    uint32_t frameIntervalMs() const;

private:
    std::unique_ptr<uitk::lvgl_cpp::Container> _panel;
    struct State {
        bool bleConnected = false;
        bool processing = false;
    } _state;
    struct QuotaDisplay {
        const char* name;
        int remaining;
        bool stale;
        uint32_t color;
        const std::string* reset;
    };
    QuotaDisplay quotaDisplay(uint8_t page) const;
    VoiceMode _voice_mode = VoiceMode::Idle;
    std::unique_ptr<uitk::lvgl_cpp::Container> _vibe_canvas;
    std::unique_ptr<uitk::lvgl_cpp::Label> _vibe_quota_name;
    std::unique_ptr<uitk::lvgl_cpp::Label> _vibe_quota_value;
    std::unique_ptr<uitk::lvgl_cpp::Label> _vibe_quota_caption;
    std::unique_ptr<uitk::lvgl_cpp::Label> _vibe_quota_reset;
    uint8_t _vibe_details_page = 0;  // Five hours, Codex weekly, X shared weekly.
    bool _vibe_touch_tracking = false;
    lv_point_t _vibe_touch_start{};
    static void touchVibeEvent(lv_event_t* event);
    bool _vibe_details_visible = false;
    bool _vibe_details_dirty = true;
    uint32_t _vibe_clock_tick = UINT32_MAX;
    std::unique_ptr<uitk::lvgl_cpp::Label> _vibe_clock;
    codex::QuotaSnapshot _vibe_quota;
    uint32_t _vibe_details_until = 0;
    uint32_t _vibe_touch_until = 0;
    uint32_t _vibe_panel_at = 0;
    uint32_t _vibe_background = UINT32_MAX;
    bool _vibe_full_redraw = true;
    bool _vibe_was_animating = false;
    void initVibe(lv_obj_t* parent);
    void updateVibe();
    void drawVibe(lv_layer_t* layer, int x, int y);
    static void drawVibeEvent(lv_event_t* event);
};
}  // namespace view

// SPDX-License-Identifier: MIT
#include "app_iphone_agent.h"
#include "bridge.h"
#include <hal/hal.h>
#include <array>
#include <algorithm>

namespace {
// Code-drawn phone icon, kept separate from the factory app assets.
const lv_image_dsc_t* phone_icon()
{
    static const auto pixels = [] {
        std::array<uint32_t, 144 * 176> data{};
        for (int y = 0; y < 176; ++y) {
            for (int x = 0; x < 144; ++x) {
                int dx = std::max(28 - x, std::max(x - 115, 0));
                int dy = std::max(28 - y, std::max(y - 147, 0));
                if (dx * dx + dy * dy > 28 * 28) continue;
                uint32_t color = 0xFF55C6E8;
                if (x >= 12 && x <= 131 && y >= 22 && y <= 149) color = 0xFF102A43;
                if (x >= 56 && x <= 87 && y >= 9 && y <= 13) color = 0xFF102A43;
                if (x >= 53 && x <= 90 && y >= 159 && y <= 163) color = 0xFFFFFFFF;
                // A cursor on the phone screen.
                if (y >= 61 && y <= 107 && x >= 56 && x <= 56 + (y - 61) * 3 / 4) color = 0xFFFFFFFF;
                data[y * 144 + x] = color;
            }
        }
        return data;
    }();
    static const auto descriptor = [] {
        lv_image_dsc_t image{};
        image.header.magic = LV_IMAGE_HEADER_MAGIC;
        image.header.cf = LV_COLOR_FORMAT_ARGB8888;
        image.header.w = 144;
        image.header.h = 176;
        image.header.stride = 144 * 4;
        image.data_size = pixels.size() * sizeof(uint32_t);
        image.data = reinterpret_cast<const uint8_t*>(pixels.data());
        return image;
    }();
    return &descriptor;
}
lv_obj_t* label(lv_obj_t* parent, const char* text, int y, uint32_t color, const lv_font_t* font)
{
    auto* object = lv_label_create(parent);
    lv_label_set_text(object, text);
    lv_obj_set_width(object, 310);
    lv_obj_set_style_text_align(object, LV_TEXT_ALIGN_CENTER, 0);
    lv_obj_set_style_text_color(object, lv_color_hex(color), 0);
    lv_obj_set_style_text_font(object, font, 0);
    lv_obj_align(object, LV_ALIGN_CENTER, 0, y);
    return object;
}
}  // namespace

AppIphoneAgent::AppIphoneAgent()
{
    setAppInfo().name = "iPhone Agent";
    setAppInfo().icon = const_cast<lv_image_dsc_t*>(phone_icon());
}
void AppIphoneAgent::onOpen()
{
    _keys = std::make_unique<input::KeyManager>();
    _toggle = false;
    LvglLockGuard lock;
    _panel = lv_obj_create(lv_screen_active());
    lv_obj_set_size(_panel, 466, 466);
    lv_obj_center(_panel);
    lv_obj_remove_flag(_panel, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_set_style_border_width(_panel, 0, 0);
    lv_obj_set_style_radius(_panel, 0, 0);
    lv_obj_set_style_bg_color(_panel, lv_color_hex(0x081624), 0);
    label(_panel, "iPhone Agent", -160, 0x55C6E8, &lv_font_montserrat_28);
    label(_panel, "USB mouse + keyboard", -116, 0xBACBDC, &lv_font_montserrat_16);
    _state = label(_panel, "Stopped", -60, 0xFFFFFF, &lv_font_montserrat_18);
    _links = label(_panel, "", -5, 0xBACBDC, &lv_font_montserrat_16);
    _count = label(_panel, "", 42, 0xBACBDC, &lv_font_montserrat_16);
    _action = lv_button_create(_panel);
    lv_obj_set_size(_action, 210, 55);
    lv_obj_align(_action, LV_ALIGN_CENTER, 0, 110);
    lv_obj_set_style_bg_color(_action, lv_color_hex(0x156582), 0);
    _action_label = lv_label_create(_action);
    lv_obj_center(_action_label);
    lv_obj_set_style_text_font(_action_label, &lv_font_montserrat_18, 0);
    lv_obj_add_event_cb(_action, [](lv_event_t* event) {
        static_cast<AppIphoneAgent*>(lv_event_get_user_data(event))->_toggle = true;
    }, LV_EVENT_CLICKED, this);
    label(_panel, "A: Start / Stop\nHold A + B to exit", 173, 0xBACBDC, &lv_font_montserrat_16);
    update_view();
}
void AppIphoneAgent::toggle()
{
    auto& bridge = iphone_agent::Bridge::instance();
    if (bridge.requested()) bridge.stop();
    else bridge.start();
}
void AppIphoneAgent::onRunning()
{
    auto event = _keys->update();
    if (event == input::KeyEvent::GoHome) { close(); return; }
    bool toggle_requested = _toggle.exchange(false);
    if (event == input::KeyEvent::GoPrevious || toggle_requested) toggle();
    if (GetHAL().millis() - _last_update >= 250) {
        _last_update = GetHAL().millis();
        LvglLockGuard lock;
        update_view();
    }
}
void AppIphoneAgent::update_view()
{
    auto& bridge = iphone_agent::Bridge::instance();
    auto status = bridge.status();
    auto message = bridge.configured() ? status.message.c_str() : "Wi-Fi / server settings needed";
    lv_label_set_text(_state, message);
    lv_label_set_text_fmt(_links, "Wi-Fi: %s   Server: %s\nUSB: %s",
                          status.wifi ? "OK" : "--", status.server ? "OK" : "--", status.usb ? "OK" : "--");
    lv_label_set_text_fmt(_count, "Commands: %lu", static_cast<unsigned long>(status.commands));
    lv_label_set_text(_action_label, status.running ? "Stop" : "Start");
    if (bridge.configured()) lv_obj_remove_state(_action, LV_STATE_DISABLED);
    else lv_obj_add_state(_action, LV_STATE_DISABLED);
}
void AppIphoneAgent::onClose()
{
    iphone_agent::Bridge::instance().stop();
    _keys.reset();
    LvglLockGuard lock;
    lv_obj_delete(_panel);
    _panel = _state = _links = _count = _action = _action_label = nullptr;
}

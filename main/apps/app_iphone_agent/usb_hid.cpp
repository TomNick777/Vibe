// SPDX-FileCopyrightText: 2026 Henry Yuan
// SPDX-License-Identifier: MIT
// Protocol timing adapted from esp32-iphone-agent's MIT-licensed HID bridge.
#include "usb_hid.h"
#include <algorithm>
#include <cstdio>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>
#include <esp_mac.h>
#include <tinyusb.h>
#include <tinyusb_default_config.h>
#include <tusb.h>

namespace {
constexpr uint8_t keyboard_id = 1, mouse_id = 2;
const uint8_t report_descriptor[] = {
    TUD_HID_REPORT_DESC_KEYBOARD(HID_REPORT_ID(keyboard_id)),
    TUD_HID_REPORT_DESC_MOUSE(HID_REPORT_ID(mouse_id))
};
const uint8_t configuration_descriptor[] = {
    TUD_CONFIG_DESCRIPTOR(1, 1, 0, TUD_CONFIG_DESC_LEN + TUD_HID_DESC_LEN,
                          TUSB_DESC_CONFIG_ATT_REMOTE_WAKEUP, 500),
    TUD_HID_DESCRIPTOR(0, 4, HID_ITF_PROTOCOL_NONE, sizeof(report_descriptor), 0x81, 16, 8)
};
char serial_number[13]{};
const char language[] = {0x09, 0x04};
const char* strings[] = {language, "M5Stack", "StopWatch iPhone Agent", serial_number, "Mouse and Keyboard"};
void delay_ms(int ms) { vTaskDelay(pdMS_TO_TICKS(ms)); }
}  // namespace

extern "C" const uint8_t* tud_hid_descriptor_report_cb(uint8_t) { return report_descriptor; }
extern "C" uint16_t tud_hid_get_report_cb(uint8_t, uint8_t, hid_report_type_t, uint8_t*, uint16_t) { return 0; }
extern "C" void tud_hid_set_report_cb(uint8_t, uint8_t, hid_report_type_t, const uint8_t*, uint16_t) {}

namespace iphone_agent {
UsbHid& UsbHid::instance() { static UsbHid hid; return hid; }
bool UsbHid::init()
{
    if (_initialized) return true;
    uint8_t mac[6]{};
    esp_efuse_mac_get_default(mac);
    snprintf(serial_number, sizeof(serial_number), "%02X%02X%02X%02X%02X%02X",
             mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
    tinyusb_config_t config = TINYUSB_DEFAULT_CONFIG();
    config.descriptor.full_speed_config = configuration_descriptor;
    config.descriptor.string = strings;
    config.descriptor.string_count = sizeof(strings) / sizeof(strings[0]);
    _initialized = tinyusb_driver_install(&config) == ESP_OK;
    return _initialized;
}
bool UsbHid::ready() const { return _initialized && tud_mounted() && !tud_suspended(); }
void UsbHid::shutdown()
{
    if (!_initialized) return;
    release_all();
    // Removing the HID device also clears a held button on the host if USB was suspended.
    tud_disconnect();
    tinyusb_driver_uninstall();
    _initialized = false;
    _buttons = 0;
}
bool UsbHid::wake(const std::atomic<bool>& active)
{
    if (!_initialized) return false;
    if (tud_suspended()) {
        tud_remote_wakeup();
        for (int i = 0; i < 50 && tud_suspended() && active; ++i) delay_ms(10);
    }
    return ready();
}
bool UsbHid::wait_report_slot()
{
    if (!ready()) return false;
    for (int i = 0; i < 100; ++i) {
        if (!ready()) return false;
        if (tud_hid_ready()) return true;
        delay_ms(2);
    }
    return false;
}
bool UsbHid::mouse(int x, int y, int vertical, int horizontal)
{
    return wait_report_slot() && tud_hid_mouse_report(mouse_id, _buttons, x, y, vertical, horizontal);
}
bool UsbHid::keyboard(uint8_t modifiers, const uint8_t* keys)
{
    return wait_report_slot() && tud_hid_keyboard_report(keyboard_id, modifiers, keys);
}
bool UsbHid::release_all()
{
    _buttons = 0;
    bool mouse_released = mouse();
    bool keys_released = keyboard(0, nullptr);
    return mouse_released && keys_released;
}
std::string UsbHid::execute(const Command& command, const std::atomic<bool>& active)
{
    if (command.operation == Operation::Ping) return "ok";
    if (!wake(active)) return "err phone usb asleep (unlock the phone)";
    bool success = true;
    switch (command.operation) {
        case Operation::Home:
            for (int i = 0; i < 50 && active && success; ++i) { success = mouse(-127, -127); delay_ms(2); }
            break;
        case Operation::Move: {
            int x = command.x, y = command.y;
            while ((x || y) && active && success) {
                int dx = std::clamp(x, -10, 10), dy = std::clamp(y, -10, 10);
                success = mouse(dx, dy);
                x -= dx; y -= dy;
                delay_ms(8);
            }
            break;
        }
        case Operation::Press: _buttons = MOUSE_BUTTON_LEFT; success = mouse(); break;
        case Operation::Release: _buttons = 0; success = mouse(); break;
        case Operation::Click:
            _buttons = MOUSE_BUTTON_LEFT;
            success = mouse();
            delay_ms(60);
            _buttons = 0;
            success = mouse() && success;
            break;
        case Operation::Scroll: success = mouse(0, 0, command.x, command.y); break;
        case Operation::Type:
            for (unsigned char character : command.text) {
                if (!active || !success) break;
                uint8_t key = 0, modifiers = 0, keys[6]{};
                ascii_key(character, key, modifiers);
                keys[0] = key;
                success = keyboard(modifiers, keys);
                delay_ms(8);
                success = keyboard(0, nullptr) && success;
            }
            break;
        case Operation::Key:
            success = keyboard(command.modifiers, command.keys.data());
            delay_ms(30);
            success = keyboard(0, nullptr) && success;
            break;
        case Operation::Ping: break;
    }
    if (!success || !active) {
        release_all();
        return active ? "err USB report failed" : "err stopped";
    }
    return "ok";
}
}  // namespace iphone_agent

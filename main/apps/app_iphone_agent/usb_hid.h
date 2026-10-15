// SPDX-FileCopyrightText: 2026 Henry Yuan
// SPDX-License-Identifier: MIT
#pragma once
#include "protocol.h"
#include <atomic>

namespace iphone_agent {
class UsbHid {
public:
    static UsbHid& instance();
    bool init();
    void shutdown();
    bool ready() const;
    bool wake(const std::atomic<bool>& active);
    std::string execute(const Command& command, const std::atomic<bool>& active);
    bool release_all();
private:
    bool wait_report_slot();
    bool mouse(int x = 0, int y = 0, int vertical = 0, int horizontal = 0);
    bool keyboard(uint8_t modifiers, const uint8_t* keys);
    bool _initialized = false;
    uint8_t _buttons = 0;
};
}  // namespace iphone_agent

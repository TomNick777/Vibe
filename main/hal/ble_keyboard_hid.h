// SPDX-License-Identifier: MIT
#pragma once

namespace ble_keyboard_hid {
// Voice input shortcuts use a standard HOGP keyboard; no vendor control channel.
bool register_service();
}

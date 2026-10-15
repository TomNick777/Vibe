/*
 * SPDX-FileCopyrightText: 2026 M5Stack Technology CO LTD
 *
 * SPDX-License-Identifier: MIT
 */
#pragma once
#include <string_view>
#include <esp_app_desc.h>

namespace common {

inline const std::string_view FirmwareVersion = esp_app_get_description()->version;

}

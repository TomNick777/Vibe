// SPDX-License-Identifier: MIT
#include "wifi_stack.h"
#include <mutex>
#include <esp_event.h>
#include <esp_netif.h>
#include <esp_wifi.h>

bool wifi_stack::ensure_ready()
{
    static std::mutex mutex;
    static bool initialized = false;
    std::lock_guard<std::mutex> lock(mutex);
    if (initialized) return true;
    auto ret = esp_netif_init();
    if (ret != ESP_OK && ret != ESP_ERR_INVALID_STATE) return false;
    ret = esp_event_loop_create_default();
    if (ret != ESP_OK && ret != ESP_ERR_INVALID_STATE) return false;
    wifi_init_config_t config = WIFI_INIT_CONFIG_DEFAULT();
    config.nvs_enable = false;
    ret = esp_wifi_init(&config);
    if (ret != ESP_OK) return false;
    initialized = true;
    return true;
}

// SPDX-FileCopyrightText: 2026 Henry Yuan
// SPDX-License-Identifier: MIT
#include "bridge.h"
#include "protocol.h"
#include "usb_hid.h"
#if __has_include("config.local.h")
#include "config.local.h"
#else
#include "config.example.h"
#endif
#include <cstring>
#include <cerrno>
#include <fcntl.h>
#include <esp_event.h>
#include <esp_netif.h>
#include <esp_system.h>
#include <esp_timer.h>
#include <esp_wifi.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>
#include <lwip/sockets.h>
#include <hal/utils/wifi_stack/wifi_stack.h>

namespace {
std::atomic<bool> wifi_connected{false};
void wifi_event(void*, esp_event_base_t base, int32_t id, void*)
{
    if (base == IP_EVENT && id == IP_EVENT_STA_GOT_IP) wifi_connected = true;
    if (base == WIFI_EVENT && id == WIFI_EVENT_STA_DISCONNECTED) wifi_connected = false;
}
const char* reset_reason()
{
    switch (esp_reset_reason()) {
        case ESP_RST_POWERON: return "power-on";
        case ESP_RST_BROWNOUT: return "brownout";
        case ESP_RST_TASK_WDT: case ESP_RST_INT_WDT: case ESP_RST_WDT: return "watchdog";
        case ESP_RST_PANIC: return "crash";
        case ESP_RST_SW: return "software";
        case ESP_RST_USB: return "usb";
        default: return "other";
    }
}
bool send_line(int socket, const std::string& text)
{
    auto line = text + "\n";
    std::size_t sent = 0;
    while (sent < line.size()) {
        auto count = send(socket, line.data() + sent, line.size() - sent, 0);
        if (count <= 0) return false;
        sent += count;
    }
    return true;
}
int connect_server(const std::atomic<bool>& active)
{
    int socket_fd = socket(AF_INET, SOCK_STREAM, 0);
    if (socket_fd < 0) return -1;
    sockaddr_in address{};
    address.sin_family = AF_INET;
    address.sin_port = htons(IPHONE_AGENT_SERVER_PORT);
    inet_pton(AF_INET, IPHONE_AGENT_SERVER_IPV4, &address.sin_addr);
    int flags = fcntl(socket_fd, F_GETFL, 0);
    fcntl(socket_fd, F_SETFL, flags | O_NONBLOCK);
    bool connected = connect(socket_fd, reinterpret_cast<sockaddr*>(&address), sizeof(address)) == 0;
    if (!connected && errno == EINPROGRESS) {
        for (int i = 0; i < 20 && active; ++i) {
            fd_set set; FD_ZERO(&set); FD_SET(socket_fd, &set);
            timeval timeout{0, 50000};
            int result = select(socket_fd + 1, nullptr, &set, nullptr, &timeout);
            if (result < 0) break;
            if (result > 0) {
                int error = 0; socklen_t length = sizeof(error);
                connected = getsockopt(socket_fd, SOL_SOCKET, SO_ERROR, &error, &length) == 0 && error == 0;
                break;
            }
        }
    }
    if (!connected || !active) { close(socket_fd); return -1; }
    fcntl(socket_fd, F_SETFL, flags);
    timeval timeout{0, 250000};
    setsockopt(socket_fd, SOL_SOCKET, SO_SNDTIMEO, &timeout, sizeof(timeout));
    setsockopt(socket_fd, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout));
    int enabled = 1;
    setsockopt(socket_fd, IPPROTO_TCP, TCP_NODELAY, &enabled, sizeof(enabled));
    return socket_fd;
}
}  // namespace

namespace iphone_agent {
Bridge& Bridge::instance() { static Bridge bridge; return bridge; }
bool Bridge::configured() const
{
    in_addr address{};
    return strlen(IPHONE_AGENT_WIFI_SSID) > 0 && strlen(IPHONE_AGENT_WIFI_SSID) <= 32 &&
           strlen(IPHONE_AGENT_WIFI_PASSWORD) <= 64 &&
           IPHONE_AGENT_SERVER_PORT > 0 && IPHONE_AGENT_SERVER_PORT <= 65535 &&
           inet_pton(AF_INET, IPHONE_AGENT_SERVER_IPV4, &address) == 1;
}
void Bridge::message(const std::string& text)
{
    std::lock_guard<std::mutex> lock(_mutex);
    _status.message = text;
}
Status Bridge::status()
{
    std::lock_guard<std::mutex> lock(_mutex);
    auto result = _status;
    result.running = _running;
    // USB stack initialization occurs in start() on the app thread.
    result.usb = UsbHid::instance().ready();
    return result;
}
void Bridge::start()
{
    if (_running) return;
    if (!configured()) { message("Wi-Fi / server settings needed"); return; }
    if (!wifi_stack::ensure_ready()) { message("Wi-Fi initialization failed"); return; }
    if (!UsbHid::instance().init()) { message("USB initialization failed"); return; }
    _requested = true;
    _running = true;
    if (xTaskCreate([](void* self) { static_cast<Bridge*>(self)->run(); }, "iphone-agent", 8192, this, 4, nullptr) != pdPASS) {
        _requested = false;
        _running = false;
        UsbHid::instance().shutdown();
        message("Unable to start bridge");
    }
}
void Bridge::stop()
{
    _requested = false;
    // Network and HID waits are bounded; worker owns and releases its resources.
    while (_running) vTaskDelay(pdMS_TO_TICKS(10));
    UsbHid::instance().shutdown();
}
void Bridge::run()
{
    static esp_netif_t* station = nullptr;
    esp_event_handler_instance_t wifi_handler = nullptr, ip_handler = nullptr;
    int socket_fd = -1;
    auto& hid = UsbHid::instance();
    wifi_connected = false;
    bool wifi_started = false;
    bool release_pending = true;
    if (!station) station = esp_netif_create_default_wifi_sta();
    wifi_config_t config{};
    memcpy(config.sta.ssid, IPHONE_AGENT_WIFI_SSID, strlen(IPHONE_AGENT_WIFI_SSID));
    memcpy(config.sta.password, IPHONE_AGENT_WIFI_PASSWORD, strlen(IPHONE_AGENT_WIFI_PASSWORD));
    config.sta.scan_method = WIFI_ALL_CHANNEL_SCAN;
    esp_err_t ret = station ? ESP_OK : ESP_FAIL;
    if (ret == ESP_OK) ret = esp_event_handler_instance_register(WIFI_EVENT, ESP_EVENT_ANY_ID, wifi_event, nullptr, &wifi_handler);
    if (ret == ESP_OK) ret = esp_event_handler_instance_register(IP_EVENT, IP_EVENT_STA_GOT_IP, wifi_event, nullptr, &ip_handler);
    if (ret == ESP_OK) ret = esp_wifi_set_mode(WIFI_MODE_STA);
    if (ret == ESP_OK) ret = esp_wifi_set_config(WIFI_IF_STA, &config);
    if (ret == ESP_OK) { ret = esp_wifi_start(); wifi_started = ret == ESP_OK; }
    if (ret == ESP_OK) ret = esp_wifi_set_ps(WIFI_PS_NONE);
    if (ret != ESP_OK) {
        message("Wi-Fi start failed");
        _requested = false;
    }
    int64_t retry_at = 0;
    LineReader reader;
    bool server_connected = false;
    while (_requested) {
        if (release_pending && hid.ready()) release_pending = !hid.release_all();
        bool wifi = wifi_connected;
        {
            std::lock_guard<std::mutex> lock(_mutex);
            _status.wifi = wifi;
            _status.server = server_connected && wifi;
        }
        int64_t now = esp_timer_get_time();
        if (!wifi) {
            if (socket_fd >= 0) { close(socket_fd); socket_fd = -1; server_connected = false; reader.reset(); }
            release_pending = !hid.release_all();
            if (now >= retry_at) {
                message("Connecting to Wi-Fi...");
                esp_wifi_connect();
                retry_at = now + 5000000;
            }
            vTaskDelay(pdMS_TO_TICKS(100));
            continue;
        }
        if (socket_fd < 0) {
            message("Connecting to server...");
            socket_fd = connect_server(_requested);
            if (socket_fd < 0) { vTaskDelay(pdMS_TO_TICKS(200)); continue; }
            release_pending = !hid.release_all();
            std::string hello = std::string("hello ") + reset_reason() + " " + std::to_string(esp_timer_get_time() / 1000);
            server_connected = send_line(socket_fd, hello);
            if (!server_connected) { close(socket_fd); socket_fd = -1; continue; }
            message("Bridge connected");
        }
        char buffer[256];
        int count = recv(socket_fd, buffer, sizeof(buffer), 0);
        if (count < 0 && (errno == EAGAIN || errno == EWOULDBLOCK)) continue;
        if (count <= 0) {
            close(socket_fd); socket_fd = -1; server_connected = false; reader.reset();
            release_pending = !hid.release_all();
            continue;
        }
        for (int i = 0; i < count && _requested; ++i) {
            std::string line;
            auto result = reader.push(buffer[i], line);
            if (result == LineReader::Result::Pending) continue;
            std::string reply;
            Command command;
            if (result == LineReader::Result::Overflow) reply = "err command too long";
            else if (line.empty() || line == "\r") continue;
            else if (parse_command(line, command, reply)) {
                if (command.operation != Operation::Ping && release_pending) {
                    if (hid.wake(_requested)) release_pending = !hid.release_all();
                }
                if (command.operation != Operation::Ping && release_pending) reply = "err phone usb asleep (unlock the phone)";
                else reply = hid.execute(command, _requested);
                if (reply != "ok") release_pending = !hid.release_all();
                std::lock_guard<std::mutex> lock(_mutex);
                ++_status.commands;
            }
            if (!send_line(socket_fd, reply)) {
                close(socket_fd); socket_fd = -1; server_connected = false; reader.reset();
                release_pending = !hid.release_all();
                break;
            }
        }
    }
    if (socket_fd >= 0) close(socket_fd);
    hid.release_all();
    if (wifi_started) { esp_wifi_disconnect(); esp_wifi_stop(); }
    if (wifi_handler) esp_event_handler_instance_unregister(WIFI_EVENT, ESP_EVENT_ANY_ID, wifi_handler);
    if (ip_handler) esp_event_handler_instance_unregister(IP_EVENT, IP_EVENT_STA_GOT_IP, ip_handler);
    wifi_connected = false;
    {
        std::lock_guard<std::mutex> lock(_mutex);
        _status.wifi = false;
        _status.server = false;
        if (ret == ESP_OK) _status.message = "Stopped";
    }
    _running = false;
    vTaskDelete(nullptr);
}
}  // namespace iphone_agent

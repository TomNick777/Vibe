// SPDX-License-Identifier: MIT
#pragma once
#include <atomic>
#include <cstdint>
#include <mutex>
#include <string>

namespace iphone_agent {
struct Status {
    bool running = false;
    bool wifi = false;
    bool server = false;
    bool usb = false;
    uint32_t commands = 0;
    std::string message = "Stopped";
};
class Bridge {
public:
    static Bridge& instance();
    bool configured() const;
    void start();
    void stop();
    Status status();
    bool requested() const { return _requested.load(); }
private:
    void run();
    void message(const std::string& text);
    std::mutex _mutex;
    Status _status;
    std::atomic<bool> _requested{false};
    std::atomic<bool> _running{false};
};
}  // namespace iphone_agent

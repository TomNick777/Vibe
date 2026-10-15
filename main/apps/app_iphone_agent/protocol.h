// SPDX-FileCopyrightText: 2026 Henry Yuan
// SPDX-License-Identifier: MIT
// ESP-IDF adaptation of esp32-iphone-agent/hardware/hid_bridge.
#pragma once
#include <array>
#include <cstdint>
#include <string>
#include <string_view>

namespace iphone_agent {
constexpr std::size_t max_line_length = 1024;
enum class Operation { Ping, Home, Move, Press, Release, Click, Scroll, Type, Key };
struct Command {
    Operation operation = Operation::Ping;
    int x = 0;
    int y = 0;
    std::string text;
    uint8_t modifiers = 0;
    std::array<uint8_t, 6> keys{};
};
bool ascii_key(unsigned char character, uint8_t& key, uint8_t& modifiers);
bool parse_command(std::string_view line, Command& command, std::string& error);

// TCP packets can split or combine lines. Oversize lines produce one error,
// then are discarded through the next newline instead of executing a suffix.
class LineReader {
public:
    enum class Result { Pending, Line, Overflow };
    Result push(char byte, std::string& line);
    void reset();
private:
    std::string _buffer;
    bool _discard = false;
};
}  // namespace iphone_agent

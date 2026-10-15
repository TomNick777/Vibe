// SPDX-FileCopyrightText: 2026 Henry Yuan
// SPDX-License-Identifier: MIT
#include "protocol.h"
#include <charconv>

namespace iphone_agent {
bool ascii_key(unsigned char character, uint8_t& key, uint8_t& modifiers)
{
    modifiers = 0;
    if (character >= 'a' && character <= 'z') { key = 4 + character - 'a'; return true; }
    if (character >= 'A' && character <= 'Z') { key = 4 + character - 'A'; modifiers = 2; return true; }
    if (character >= '1' && character <= '9') { key = 30 + character - '1'; return true; }
    if (character == '0') { key = 39; return true; }
    if (character == '\t') { key = 43; return true; }
    if (character == ' ') { key = 44; return true; }
    constexpr std::string_view plain = "-=[]\\;'`,./";
    constexpr std::string_view shifted = "_+{}|:\"~<>?";
    constexpr uint8_t codes[] = {45, 46, 47, 48, 49, 51, 52, 53, 54, 55, 56};
    auto index = plain.find(character);
    if (index != std::string_view::npos) { key = codes[index]; return true; }
    index = shifted.find(character);
    if (index != std::string_view::npos) { key = codes[index]; modifiers = 2; return true; }
    index = std::string_view("!@#$%^&*()").find(character);
    if (index != std::string_view::npos) { key = 30 + index; modifiers = 2; return true; }
    return false;
}

namespace {
bool integer(std::string_view token, int& value)
{
    if (token.empty()) return false;
    auto result = std::from_chars(token.data(), token.data() + token.size(), value);
    return result.ec == std::errc() && result.ptr == token.data() + token.size();
}
bool pair(std::string_view arg, int& x, int& y)
{
    auto separator = arg.find(' ');
    if (separator == std::string_view::npos) return false;
    auto second = arg.substr(separator + 1);
    while (!second.empty() && second.front() == ' ') second.remove_prefix(1);
    return integer(arg.substr(0, separator), x) && integer(second, y);
}
bool combo(std::string_view arg, Command& command)
{
    std::size_t count = 0;
    while (!arg.empty()) {
        auto separator = arg.find('+');
        auto token = arg.substr(0, separator);
        uint8_t key = 0, modifier = 0;
        if (token == "cmd") modifier = 8;
        else if (token == "ctrl") modifier = 1;
        else if (token == "alt") modifier = 4;
        else if (token == "shift") modifier = 2;
        else if (token == "enter") key = 40;
        else if (token == "esc") key = 41;
        else if (token == "backspace") key = 42;
        else if (token == "tab") key = 43;
        else if (token == "space") key = 44;
        else if (token == "right") key = 79;
        else if (token == "left") key = 80;
        else if (token == "down") key = 81;
        else if (token == "up") key = 82;
        else if (token.size() == 1) { if (!ascii_key(token.front(), key, modifier)) return false; }
        else return false;
        command.modifiers |= modifier;
        if (key) {
            bool duplicate = false;
            for (auto existing : command.keys) duplicate |= existing == key;
            if (!duplicate) {
                if (count == command.keys.size()) return false;
                command.keys[count++] = key;
            }
        }
        if (separator == std::string_view::npos) return true;
        arg.remove_prefix(separator + 1);
        if (arg.empty()) return false;
    }
    return false;
}
}  // namespace

bool parse_command(std::string_view line, Command& command, std::string& error)
{
    command = {};
    error = "err invalid arguments";
    if (line.size() > max_line_length) { error = "err command too long"; return false; }
    if (!line.empty() && line.back() == '\r') line.remove_suffix(1);
    for (unsigned char byte : line) {
        if (byte < 32 && byte != '\t') return false;
    }
    auto separator = line.find(' ');
    auto name = line.substr(0, separator);
    auto arg = separator == std::string_view::npos ? std::string_view{} : line.substr(separator + 1);
    if (name == "move" || name == "scroll") {
        if (!pair(arg, command.x, command.y)) return false;
        int limit = name == "move" ? 10000 : 127;
        if (command.x < -limit || command.x > limit || command.y < -limit || command.y > limit) return false;
        command.operation = name == "move" ? Operation::Move : Operation::Scroll;
    } else if (name == "type") {
        for (unsigned char byte : arg) {
            uint8_t key, modifiers;
            if (!ascii_key(byte, key, modifiers)) { error = "err ASCII text only"; return false; }
        }
        command.operation = Operation::Type;
        command.text = std::string(arg);
    } else if (name == "key") {
        if (!combo(arg, command)) { error = "err unknown key"; return false; }
        command.operation = Operation::Key;
    } else {
        if (!arg.empty()) return false;
        if (name == "ping") command.operation = Operation::Ping;
        else if (name == "home") command.operation = Operation::Home;
        else if (name == "press") command.operation = Operation::Press;
        else if (name == "release") command.operation = Operation::Release;
        else if (name == "click") command.operation = Operation::Click;
        else { error = "err unknown command"; return false; }
    }
    error.clear();
    return true;
}

LineReader::Result LineReader::push(char byte, std::string& line)
{
    if (_discard) {
        if (byte == '\n') _discard = false;
        return Result::Pending;
    }
    if (byte == '\n') {
        line.swap(_buffer);
        _buffer.clear();
        return Result::Line;
    }
    if (_buffer.size() == max_line_length) {
        _buffer.clear();
        _discard = true;
        return Result::Overflow;
    }
    _buffer += byte;
    return Result::Pending;
}
void LineReader::reset() { _buffer.clear(); _discard = false; }
}  // namespace iphone_agent

// SPDX-License-Identifier: MIT
#include "protocol.h"
#include <cstdlib>
#include <iostream>
#include <vector>
using namespace iphone_agent;
void check(bool condition, const char* reason)
{
    if (!condition) { std::cerr << reason << '\n'; std::exit(1); }
}
int main()
{
    Command command;
    std::string error;
    for (auto name : {"ping", "home", "press", "release", "click"})
        check(parse_command(name, command, error), "upstream no-argument command");
    check(parse_command("move -120 345\r", command, error) && command.x == -120 && command.y == 345, "signed movement / CRLF");
    check(parse_command("scroll -2 1", command, error), "two-axis scroll");
    check(parse_command("type  leading and trailing ", command, error) && command.text == " leading and trailing ", "preserve typed spaces");
    check(parse_command("key cmd+shift+h", command, error) && command.modifiers == 10 && command.keys[0] == 11, "shortcut report");
    check(parse_command("key cmd+space", command, error) && command.keys[0] == 44, "Spotlight shortcut");
    check(parse_command("key left", command, error) && command.keys[0] == 80, "named key");
    for (int character = 32; character <= 126; ++character) {
        uint8_t key, modifiers;
        check(ascii_key(character, key, modifiers) && key != 0, "all printable ASCII has a HID mapping");
    }
    uint8_t key, modifiers;
    check(ascii_key(')', key, modifiers) && key == 39 && modifiers == 2, "shifted zero");
    check(ascii_key('"', key, modifiers) && key == 52 && modifiers == 2, "shifted quote");
    for (const auto& invalid : std::vector<std::string>{
             "move", "move x 1", "move 1 2 ignored", "move 2147483648 0", "move -10001 0",
             "scroll 128 0", "click extra", "key cmd+unknown", "key cmd+", "key +h", "key a+b+c+d+e+f+g",
             "type \xE4\xB8\xAD", std::string("type a\0b", 8), "type a\nb", std::string(1025, 'x')})
        check(!parse_command(invalid, command, error) && !error.empty(), "reject malformed input before HID output");
    LineReader reader;
    std::string line;
    std::vector<std::string> lines;
    for (char byte : std::string("move 1 2\nping\r\n"))
        if (reader.push(byte, line) == LineReader::Result::Line) lines.push_back(line);
    check(lines.size() == 2 && lines[0] == "move 1 2" && lines[1] == "ping\r", "split / combined TCP frames");
    int overflows = 0;
    lines.clear();
    for (char byte : std::string(1025, 'x') + "click\nping\n") {
        auto result = reader.push(byte, line);
        if (result == LineReader::Result::Overflow) ++overflows;
        if (result == LineReader::Result::Line) lines.push_back(line);
    }
    check(overflows == 1 && lines.size() == 1 && lines[0] == "ping", "overflow suffix never executes");
    reader.push('x', line);
    reader.reset();
    check(reader.push('\n', line) == LineReader::Result::Line && line.empty(), "reconnect drops partial commands");
    std::cout << "iPhone Agent protocol tests passed\n";
}

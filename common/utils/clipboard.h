#pragma once

#include <string>
#include <string_view>

namespace Clipboard {
// Returns the current system clipboard text (UTF-8). Empty string if the
// clipboard is empty or the platform has no implementation yet.
std::string paste();

// Writes the given text to the system clipboard. No-op on platforms
// without an implementation.
void copy(std::string_view text);
}

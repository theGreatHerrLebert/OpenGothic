#include "clipboard.h"

// Apple builds provide the real implementation in clipboard.mm via
// NSPasteboard. For other platforms, stub out so consolewidget's paste/copy
// paths compile and silently do nothing until someone wires up Win32's
// OpenClipboard/SetClipboardData or X11/Wayland equivalents.
#if !defined(__APPLE__)

namespace Clipboard {
std::string paste() { return {}; }
void        copy(std::string_view) {}
}

#endif

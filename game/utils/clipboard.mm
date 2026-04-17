#include "clipboard.h"

#if defined(__APPLE__)

#import <AppKit/AppKit.h>

namespace Clipboard {

std::string paste() {
  NSPasteboard* pb = [NSPasteboard generalPasteboard];
  NSString*     s  = [pb stringForType:NSPasteboardTypeString];
  if(s == nil)
    return {};
  const char* utf8 = [s UTF8String];
  return utf8 ? std::string(utf8) : std::string();
  }

void copy(std::string_view text) {
  NSPasteboard* pb = [NSPasteboard generalPasteboard];
  [pb clearContents];
  NSString* s = [[NSString alloc] initWithBytes:text.data()
                                         length:text.size()
                                       encoding:NSUTF8StringEncoding];
  if(s != nil)
    [pb setString:s forType:NSPasteboardTypeString];
  }

}

#endif

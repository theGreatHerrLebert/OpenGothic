#include "consolewidget.h"

#include <Tempest/Painter>
#include <Tempest/UiOverlay>
#include <Tempest/Application>

#include <cctype>

#include "mainwindow.h"
#include "utils/gthfont.h"
#include "utils/clipboard.h"
#include "resources.h"
#include "gothic.h"
#include "build.h"
#include "script/pythonvm.h"

using namespace Tempest;

namespace {
// Find the trailing Python identifier (letters, digits, `_`, `.`) at the end
// of `line` — that's what rlcompleter should be asked to complete.
std::string_view trailingIdentifier(std::string_view line) {
  size_t i = line.size();
  while(i > 0) {
    unsigned char c = static_cast<unsigned char>(line[i-1]);
    if(std::isalnum(c) || c=='_' || c=='.')
      --i;
    else
      break;
    }
  return line.substr(i);
  }

std::string commonPrefix(const std::vector<std::string>& matches) {
  if(matches.empty())
    return {};
  std::string p = matches[0];
  for(size_t i = 1; i < matches.size(); ++i) {
    size_t k = 0;
    while(k < p.size() && k < matches[i].size() && p[k] == matches[i][k])
      ++k;
    p.resize(k);
    if(p.empty())
      break;
    }
  return p;
  }
} // namespace

struct ConsoleWidget::Overlay : public Tempest::UiOverlay {
  ConsoleWidget& owner;

  Overlay(ConsoleWidget& owner):owner(owner){}

  void mouseDownEvent(MouseEvent& e) override {
    e.accept();
    }

  void mouseMoveEvent(MouseEvent& e) override {
    e.accept();
    }

  void mouseWheelEvent(MouseEvent& e) override {
    e.accept();
    }

  void paintEvent(PaintEvent&) override {
    }

  void keyDownEvent(Tempest::KeyEvent& e) override {
    owner.keyDownEvent(e);
    e.accept();
    }

  void keyRepeatEvent(Tempest::KeyEvent& e) override {
    owner.keyRepeatEvent(e);
    e.accept();
    }

  void keyUpEvent(Tempest::KeyEvent& e) override {
    owner.keyUpEvent(e);
    e.accept();
    }

  void closeEvent(Tempest::CloseEvent& e) override {
    e.ignore();
    }
  };

ConsoleWidget::ConsoleWidget(const MainWindow& owner)
  :mainWindow(owner) {
  updateSizeHint();

  setMargins(Margin(8,8,8,8));
  // Expanding horizontally so the console stretches to the overlay's full
  // width; height stays fixed and is controlled by updateSizeHint().
  setSizePolicy(Expanding, Fixed);

  log.emplace_back(appBuild);
  log.emplace_back("");

  closeSk = Shortcut(*this,Event::M_NoModifier,Event::K_F2);
  closeSk.onActivated.bind(this,&ConsoleWidget::close);

  background = Resources::loadTexture("CONSOLE.TGA");

  marvin.print.bind(this,&ConsoleWidget::printLine);
  }

ConsoleWidget::~ConsoleWidget() {
  close();
  }

void ConsoleWidget::close() {
  if(overlay==nullptr)
    return;
  Tempest::UiOverlay* ov = overlay;
  overlay = nullptr;

  setVisible(false);
  CloseEvent e;
  this->closeEvent(e);

  ov->takeWidget(this);
  delete ov;
  }

int ConsoleWidget::exec() {
  if(overlay==nullptr){
    overlay = new Overlay(*this);

    SystemApi::addOverlay(std::move(overlay));
    overlay->setLayout(Vertical);
    overlay->addWidget(this);
    overlay->addWidget(new Widget());
    }

  updateSizeHint();
  setVisible(true);
  while(overlay && Application::isRunning()) {
    Application::processEvents();
    }
  return 0;
  }

void ConsoleWidget::paintEvent(PaintEvent& e) {
  Painter p(e);
  if(background!=nullptr)
    p.setBrush(*background);
  p.drawRect(0,0,w(),h(),
             0,0,p.brush().w(),p.brush().h());

  const float scale = Gothic::interfaceScale(&mainWindow);
  auto& fnt = Resources::font(scale);
  int   y   = h() - margins().bottom;

  for(size_t i=log.size(); i>0;) {
    --i;
    fnt.drawText(p, margins().left, y, log[i]);
    y-=fnt.pixelSize();
    if(i+1==log.size()) {
      int x = margins().left + fnt.textSize(log[i].data(),log[i].data()+cursPos).w;
      float a = float(Application::tickCount()%2000)/2000.f;
      p.setBrush(Color(1,1,1,a));
      p.drawRect(x,y,1,fnt.pixelSize());
      update();
      }
    if(y<0)
      break;
    }
  }

void ConsoleWidget::keyDownEvent(KeyEvent& e) {
  if(Event::K_F1<=e.key && e.key<=Event::K_F12) {
    e.ignore();
    return;
    }

  if(e.key==Event::K_ESCAPE) {
    close();
    }

  if(e.key==Event::K_Left) {
    if (cursPos>0)
      cursPos--;
    return;
    }
  if(e.key==Event::K_Right) {
    if(cursPos<log.back().size())
      cursPos++;
    return;
    }
  if(e.key==Event::K_Up) {
    histPos++;
    if(histPos<cmdHist.size()) {
      if(histPos==0)
        currCmd = log.back();
      log.back() = cmdHist[cmdHist.size()-1-histPos];
      cursPos    = log.back().size();
      }
    else {
      histPos = size_t(cmdHist.size()-1);
      }
    return;
    }
  if(e.key==Event::K_Down) {
    if(histPos==size_t(-1))
      return;
    histPos--;
    if(histPos<cmdHist.size())
      log.back() = cmdHist[cmdHist.size()-1-histPos];
    else
      log.back() = currCmd;
    cursPos = log.back().size();
    return;
    }

  // Cmd/Ctrl+V — paste clipboard contents at the cursor. Newlines are
  // collapsed to spaces so multi-line pastes flatten into one editable line.
  if(e.key==Event::K_V && (e.modifier&Event::M_Command)==Event::M_Command) {
    std::string pasted = Clipboard::paste();
    if(!pasted.empty()) {
      for(char& c : pasted)
        if(c=='\n' || c=='\r' || c=='\t')
          c = ' ';
      log.back().insert(cursPos, pasted);
      cursPos += pasted.size();
      }
    return;
    }

  // Cmd/Ctrl+C — copy the current input line.
  if(e.key==Event::K_C && (e.modifier&Event::M_Command)==Event::M_Command) {
    if(!log.back().empty())
      Clipboard::copy(log.back());
    return;
    }

  if(e.key==Event::K_Back) {
    if(0<cursPos && cursPos<=log.back().size()) {
      log.back().erase(--cursPos,1);
      }
    return;
    }
  if(e.key==Event::K_Delete) {
    if(log.back().size()>cursPos) {
      log.back().erase(cursPos,1);
      }
    return;
    }
  if(e.key==Event::K_Tab) {
    auto& line = log.back();
    if(line.size() == 0)
      return;

    // Python autocomplete: when the line starts with `py ` route Tab to
    // rlcompleter via PythonVM; otherwise fall back to Marvin's own cmd
    // table completion.
    const bool isPy = line.size() >= 3 &&
                      (line[0]=='p' || line[0]=='P') &&
                      (line[1]=='y' || line[1]=='Y') &&
                       line[2]==' ';
    if(isPy) {
      std::string_view pySrc   = std::string_view(line).substr(3);
      std::string_view fragSv  = trailingIdentifier(pySrc);
      auto             matches = PythonVM::inst().complete(fragSv);
      if(matches.empty())
        return;

      std::string common = commonPrefix(matches);
      if(common.size() > fragSv.size()) {
        line.append(common.substr(fragSv.size()));
        cursPos = line.size();
        }
      if(matches.size() > 1) {
        std::string listed;
        for(size_t i = 0; i < matches.size() && i < 24; ++i) {
          if(i)
            listed += "  ";
          listed += matches[i];
          }
        if(matches.size() > 24)
          listed += "  ...";
        printLine(listed);
        }
      return;
      }

    if(marvin.autoComplete(line))
      cursPos = line.size();
    return;
    }
  if(e.key==Event::K_Return) {
    if(log.back().size()>0) {
      const auto   cmd   = log.back();
      const size_t cmdId = log.size()-1;
      cmdHist.emplace_back(cmd);
      log.push_back("");
      if(!marvin.exec(cmd) && cmdId<log.size()) {
        log[cmdId] = "Unknown command : " + cmd;
        }
      cursPos = 0;
      currCmd = "";
      histPos = size_t(-1);
      }
    return;
    }

  // Accept any printable ASCII so the console can host symbol-heavy input
  // (e.g. the Python REPL via `py ...`). Non-character keys (arrows, F-keys,
  // return, backspace, etc.) are handled above and never reach this point.
  char ch = '\0';
  if(e.code>=0x20 && e.code<0x7F)
    ch = char(e.code);
  if(ch=='\0')
    return;
  log.back().insert(cursPos,1,ch);
  cursPos++;
  }

void ConsoleWidget::keyRepeatEvent(KeyEvent& e) {
  keyDownEvent(e);
  }

void ConsoleWidget::printLine(std::string_view s) {
  auto cmd = std::move(log.back());
  log.back() = s;
  log.emplace_back(std::move(cmd));
  }

void ConsoleWidget::updateSizeHint() {
  const float scale = Gothic::interfaceScale(this);
  // Width is just a fallback — actual width comes from the Expanding policy.
  // Height is the real control: 400px fits ~25 lines of font output, enough
  // to see a Python traceback without scrolling.
  setSizeHint(int(1024*scale), int(400*scale));
  }



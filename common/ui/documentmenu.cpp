#include "documentmenu.h"
#include "safearea.h"

#include "world/objects/interactive.h"
#include "world/objects/npc.h"
#include "utils/gthfont.h"
#include "utils/keycodec.h"
#include "gothic.h"

using namespace Tempest;

DocumentMenu::DocumentMenu(const KeyCodec& key)
  :keycodec(key) {
  setFocusPolicy(NoFocus);
  cursor = Resources::loadTexture("U.TGA");
  }

void DocumentMenu::show(const DocumentMenu::Show &doc) {
  document = doc;
  active   = true;
  first    = 0;
  update();
  }

void DocumentMenu::close() {
  if(!active)
    return;
  active=false;

  if(auto pl = Gothic::inst().player())
    pl->setInteraction(nullptr);
  }

void DocumentMenu::keyDownEvent(KeyEvent &e) {
  if(!active){
    e.ignore();
    return;
    }

  // closing comes first, whatever else a key is bound to
  if(e.key==Event::K_ESCAPE || keycodec.tr(e)==KeyCodec::Inventory) {
    close();
    return;
    }
  // a story book turns: Left/Right (arrows, or the strafe and turn keys), two pages at a time; at its first or last
  // spread the key is still taken, so it never moves the hero or the inventory behind the book
  if(document.spread>0 && document.pages.size()>document.spread) {
    const auto act  = keycodec.tr(e);
    const bool back = e.key==Event::K_Left  || act==KeyCodec::Left  || act==KeyCodec::RotateL;
    const bool next = e.key==Event::K_Right || act==KeyCodec::Right || act==KeyCodec::RotateR;
    if(back || next) {
      const size_t step = document.spread;
      if(next && first+step<document.pages.size())
        first += step;
      if(back && first>=step)
        first -= step;
      update();
      return;
      }
    }
  e.ignore();
  }

void DocumentMenu::keyUpEvent(KeyEvent&) {
  }

void DocumentMenu::paintEvent(PaintEvent &e) {
  if(!active)
    return;

  const float scale = Gothic::interfaceScale(this);
  // the pages shown now: all of them, or the spread a story book is open at
  const size_t pBegin = document.spread>0 ? std::min(first, document.pages.size()) : 0;
  const size_t pEnd   = document.spread>0 ? std::min(first+document.spread, document.pages.size())
                                          : document.pages.size();
  float mw = 0, mh = 0;
  for(size_t pi=pBegin; pi<pEnd; ++pi){
    auto& i = document.pages[pi];
    auto back = Resources::loadTexture((i.flg&F_Backgr) ? i.img : document.img);
    if(!back)
      continue;
    mw += float(back->w())*scale;
    mh = std::max(mh,float(back->h())*scale);
    }

  float k  = std::min(1.f,float(800.f+float(document.margins.xMargin()))*scale/std::max(mw,1.f));

  int   x  = SafeArea::center(w(),int(k*mw),margins().left,margins().right);
  int   y  = SafeArea::center(h(),int(mh),margins().top,margins().bottom);
  auto  pl = Gothic::inst().player();

  Painter p(e);
  const int x0 = x;
  for(size_t pi=pBegin; pi<pEnd; ++pi) {
    auto& i = document.pages[pi];
    const GthFont* fnt = nullptr;
    if(i.flg&F_Font)
      fnt = &Resources::font(i.font, Resources::FontType::Normal, scale); else
      fnt = &Resources::font(document.font, Resources::FontType::Normal, scale);
    if(fnt==nullptr)
      fnt = &Resources::font(scale);
    auto back = Resources::loadTexture((i.flg&F_Backgr) ? i.img : document.img);
    if(!back)
      continue;

    auto mgr = (i.flg&F_Margin) ? i.margins : document.margins;
    mgr.left   = int(float(mgr.left)  *scale);
    mgr.right  = int(float(mgr.right) *scale);
    mgr.top    = int(float(mgr.top)   *scale);
    mgr.bottom = int(float(mgr.bottom)*scale);

    const int w = int(k*scale*float(back->w()));
    const int h = int(  scale*float(back->h()));

    p.setBrush(*back);
    p.drawRect(x,y,w,h,
               0,0,back->w(),back->h());

    p.setBrush(Color(0.04f,0.04f,0.04f,1));

    fnt->drawText(p,x+mgr.left,
                  y+mgr.top+fnt->pixelSize(),
                  w - mgr.xMargin(),
                  h - mgr.yMargin(),
                  i.text, Tempest::AlignLeft);

    if(document.showPlayer && cursor!=nullptr && pl!=nullptr) {
      auto  pos = pl->position();
      float wx  = (pos.x-float(document.wbounds.x))/float(document.wbounds.w);
      float wy  = (pos.z-float(document.wbounds.y))/float(document.wbounds.h);

      p.setBrush(*cursor);
      int cx = x+int(wx*float(w));
      int cy = y+int(wy*float(h));

      p.pushState();
      p.translate(cx,cy);
      p.rotate(-pl->rotation()-90);
      p.drawRect(-cursor->w()/2,-cursor->h()/2, cursor->w(),cursor->h());
      p.popState();
      }
    x+=w;
    }
  if(document.spread>0 && document.pages.size()>document.spread) {
    // where one is in the book, at its foot
    auto& fnt = Resources::font(scale);
    const size_t total = (document.pages.size()+document.spread-1)/document.spread;
    const std::string at = std::to_string(first/document.spread+1) + " / " + std::to_string(total) +
                           (first+document.spread<document.pages.size() ? "  >" : "");
    const std::string txt = (first>0 ? "<  " : "") + at;
    fnt.drawText(p, x0 + (x-x0)/2 - fnt.textSize(txt).w/2, y + int(mh) + fnt.pixelSize() + 4, txt);
    }
  }

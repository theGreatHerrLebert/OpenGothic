#include "dialogmenu.h"
#include "game/constants.h"
#include "safearea.h"

#include <Tempest/Application>
#include <Tempest/Painter>
#include <Tempest/Log>
#include <algorithm>
#include <cassert>

#include "utils/gthfont.h"
#include "utils/string_frm.h"
#include "world/objects/npc.h"
#include "gothic.h"
#include "inventorymenu.h"
#include "resources.h"

using namespace Tempest;

bool DialogMenu::Pipe::output(Npc &npc, std::string_view text) {
  return owner.aiOutput(npc,text);
  }

bool DialogMenu::Pipe::outputSvm(Npc &npc, std::string_view text) {
  return owner.aiOutput(npc,text);
  }

bool DialogMenu::Pipe::outputOv(Npc &npc, std::string_view text) {
  return owner.aiOutput(npc,text);
  }

bool DialogMenu::Pipe::printScr(Npc& npc, int time, std::string_view msg, int x, int y, std::string_view font) {
  return owner.aiPrintScr(npc,time,msg,x,y,font);
  }

bool DialogMenu::Pipe::close() {
  return owner.aiClose();
  }

bool DialogMenu::Pipe::isFinished() {
  return !owner.isNpcInDialog(nullptr);
  }

DialogMenu::DialogMenu(InventoryMenu &trade)
  :trade(trade), pipe(*this) {
  tex     = Resources::loadTexture("DLG_CHOICE.TGA");
  ambient = Resources::loadTexture("DLG_AMBIENT.TGA");

  setCursorShape(CursorShape::Hidden);
  setFocusPolicy(NoFocus);

  Gothic::inst().onSettingsChanged.bind(this,&DialogMenu::setupSettings);
  setupSettings();
  }

DialogMenu::~DialogMenu() {
  Gothic::inst().onSettingsChanged.ubind(this,&DialogMenu::setupSettings);
  }

void DialogMenu::setupSettings() {
  dlgAnimation        = Gothic::settingsGetI("GAME","animatedWindows");
  showSubtitles       = Gothic::settingsGetI("GAME","subTitles");
  showSubtitlesPlayer = Gothic::settingsGetI("GAME","subTitlesPlayer");

  const float volume = Gothic::settingsSoundVolume();
  soundDevice.setGlobalVolume(volume);
  }

void DialogMenu::tick(uint64_t dt) {
  if(state==State::PreStart) {
    except.clear();
    dlgTrade=false;
    trade.close();
    onStart(*this->pl,*this->other);
    return;
    }

  skipBlockedMs = skipBlockedMs>dt ? skipBlockedMs-dt : 0;

  if(remPrint>0 || choiceAnimTime>0 || current.time>0 || pscreen.size()>0)
    update();

  if(remPrint<dt) {
    for(size_t i=1;i<MAX_PRINT;++i)
      printMsg[i-1u]=printMsg[i];
    printMsg[MAX_PRINT-1]=PScreen();
    remPrint=1500;
    } else {
    remPrint-=dt;
    }

  if(isChoiceMenuActive()) {
    if(choiceAnimTime+dt>ANIM_TIME)
      choiceAnimTime = ANIM_TIME; else
      choiceAnimTime+=dt;
    } else {
    if(choiceAnimTime<dt)
      choiceAnimTime = 0; else
      choiceAnimTime-=dt;
    }

  if(current.time<=dt){
    current.time = 0;
    if(dlgTrade && !haveToWaitOutput()) {
      startTrade();
      }
    else if(choice.size()==0 && state!=State::Idle && !agentMode && !haveToWaitOutput()) {
      close();
      }
    } else {
    current.time-=dt;
    }

  for(size_t i=0;i<pscreen.size();){
    auto& p=pscreen[i];
    if(p.time<dt){
      pscreen.erase(pscreen.begin()+int(i));
      } else {
      p.time-=dt;
      ++i;
      }
    }

  // update();
  }

void DialogMenu::drawTextMultiline(Painter &p, int x, int y, int w, int h, std::string_view txt, bool isPl) {
  auto sz = processTextMultiline(nullptr,0,0,w,h,txt,isPl);
  y+=std::max(0, (h-sz.h)/2);
  processTextMultiline(&p,x,y,w,h,txt,isPl);
  }

Size DialogMenu::processTextMultiline(Painter* p, int x, int y, int w, int h, std::string_view txt, bool isPl) {
  const float scale = Gothic::interfaceScale(this);
  const int   pdd   = int(10*scale);

  auto fnt = Resources::font(scale);
  Size ret = {0,0};
  if(!isPl && other!=nullptr) {
    y += fnt.pixelSize();
    auto txt  = other->displayName();
    auto sz   = fnt.textSize(w,txt.data());
    if(p!=nullptr)
      fnt.drawText(*p,x+(w-sz.w)/2,y,txt.data());
    h     -= int(sz.h);
    ret.w  = std::max(ret.w,sz.w);
    ret.h += sz.h;
    }

  fnt = Resources::font(isPl ? Resources::FontType::Normal : Resources::FontType::Yellow, scale);

  y     += fnt.pixelSize();
  ret.h += fnt.pixelSize();
  if(p!=nullptr) {
    // a line longer than the box scrolls with the time it is shown, page by page
    int firstLine = 0;
    const int lineH = fnt.textSize("A").h;
    if(lineH>0 && h>0 && current.msgTime>0) {
      const int total   = fnt.textSize(w-2*pdd,txt).h/lineH;
      const int visible = std::max(1, h/lineH);
      const int maxLine = total-visible;
      if(maxLine>0) {
        const uint64_t da      = dlgAnimation ? ANIM_TIME : 0;
        const uint64_t end     = current.msgTime+da;
        const uint64_t elapsed = current.time<end ? end-current.time : 0;
        const float    k       = std::min(1.f, float(elapsed)/float(current.msgTime));
        firstLine = std::min(maxLine, int(k*float(maxLine+1)));
        }
      }
    fnt.drawText(*p,x+pdd, y,
                 w-2*pdd, h, txt, Tempest::AlignHCenter, firstLine);
    }
  auto sz = fnt.textSize(w,txt);
  ret.w  = std::max(ret.w,sz.w);
  ret.h += sz.h;

  return ret;
  }

void DialogMenu::clear() {
  for(auto& i:printMsg)
    i=PScreen();
  pscreen.clear();
  }

void DialogMenu::onWorldChanged() {
  close();
  clear();
  agentNpcs.clear();
  storyTopics.clear();   // the story sets them again for the new world
  }

void DialogMenu::agentSetTopics(Npc* npc, std::vector<std::pair<std::string,std::string>> keyAndTitle) {
  storyTopics.erase(std::remove_if(storyTopics.begin(),storyTopics.end(),[npc](const StoryTopic& t){ return t.npc==npc; }),
                    storyTopics.end());
  for(auto& [key,title]:keyAndTitle)
    storyTopics.push_back({npc, std::move(key), std::move(title)});

  // The NPC's own menu may be on screen right now: show the topics as they are now, not as they were.
  if(npc!=nullptr && other==npc && state==State::Active && !agentMode && depth==0) {
    choice.erase(std::remove_if(choice.begin(),choice.end(),[](const GameScript::DlgChoice& c){ return !c.storyTopic.empty(); }),
                 choice.end());
    choice = withStoryTopics(std::move(choice),*npc);
    if(dlgSel>=choice.size())
      dlgSel = choice.empty() ? 0 : choice.size()-1;
    update();
    }
  }

std::string DialogMenu::agentTakeTopic() {
  if(agentTopicTaken)
    return "";
  agentTopicTaken = true;
  return agentTopic;
  }

bool DialogMenu::agentEndTopic() {
  if(!agentMode || agentTopic.empty() || pl==nullptr || other==nullptr)
    return false;
  // Back to the NPC's own menu, with his scripted topics as before and the story's that still apply.
  agentMode = false;
  agentTopic.clear();
  onStart(*pl,*other);
  return true;
  }

std::vector<GameScript::DlgChoice> DialogMenu::withStoryTopics(std::vector<GameScript::DlgChoice> choices, Npc& npc) const {
  // Before the farewell (the highest sort, 999 in the game's scripts), so "ENDE" stays last.
  auto at = choices.end();
  if(!choices.empty()) {
    auto last = std::max_element(choices.begin(),choices.end(),[](auto& a, auto& b){ return a.sort<b.sort; });
    if(last->sort>=999)
      at = last;
    }
  std::vector<GameScript::DlgChoice> topics;
  for(auto& t:storyTopics) {
    if(t.npc!=&npc)
      continue;
    GameScript::DlgChoice c;
    c.title      = t.title;
    c.sort       = 998;
    c.storyTopic = t.key;
    topics.push_back(std::move(c));
    }
  choices.insert(at, topics.begin(), topics.end());
  return choices;
  }

void DialogMenu::agentBind(Npc* npc) {
  if(npc!=nullptr && std::find(agentNpcs.begin(),agentNpcs.end(),npc)==agentNpcs.end())
    agentNpcs.push_back(npc);
  }

void DialogMenu::agentUnbind(Npc* npc) {
  if(agentMode && (npc==nullptr || npc==other))
    agentClose();
  if(npc==nullptr)
    agentNpcs.clear();
  else
    agentNpcs.erase(std::remove(agentNpcs.begin(),agentNpcs.end(),npc),agentNpcs.end());
  }

bool DialogMenu::agentTakeOpened() {
  const bool ret = agentOpened;
  agentOpened = false;
  return ret;
  }

bool DialogMenu::agentBusy() const {
  return current.time>0 || haveToWaitOutput();
  }

bool DialogMenu::agentSay(std::string_view text, bool isPlayer, uint64_t timeMs, std::string_view wav) {
  if(!agentMode || agentBusy() || pl==nullptr || other==nullptr)
    return false;

  Npc& speaker = isPlayer ? *pl : *other;
  Npc& hearer  = isPlayer ? *other : *pl;
  hearer.stopDlgAnim();

  // a conversation the NPC started can open mid-action; a stray click must not lose it
  if(agentFirstLine)
    skipBlockedMs = 2500;
  agentFirstLine  = false;

  current.txt     = std::string(text);
  current.msgTime = timeMs;
  current.time    = timeMs + (dlgAnimation ? ANIM_TIME*2 : 0);
  currentSnd      = Tempest::SoundEffect();
  curentIsPl      = isPlayer;
  if(!wav.empty()) {
    try {
      currentSnd = soundDevice.load(std::string(wav).c_str());
      currentSnd.play();
      }
    catch(const std::exception& e) {
      Log::e("unable to play dialogue audio: ", e.what());
      currentSnd = Tempest::SoundEffect();
      }
    }
  speaker.startDlgAnim(timeMs);
  speaker.setAiOutputBarrier(timeMs,false);
  update();
  return true;
  }

void DialogMenu::agentSetChoices(const std::vector<std::string>& titles) {
  if(!agentMode)
    return;
  if(pl!=nullptr)
    pl->stopDlgAnim();
  if(other!=nullptr)
    other->stopDlgAnim();
  choice.clear();
  for(auto& t:titles) {
    GameScript::DlgChoice c;
    c.title = t;
    choice.push_back(std::move(c));
    }
  dlgSel = 0;
  update();
  }

int DialogMenu::agentTakeSelection() {
  const int ret = agentSelected;
  agentSelected = -1;
  return ret;
  }

void DialogMenu::agentClose() {
  if(!agentMode)
    return;
  close();
  }

bool DialogMenu::isMobsiDialog() const {
  return pl!=nullptr && other==pl && pl->interactive()!=nullptr;
  }

void DialogMenu::dialogCamera(Camera& camera) {
  if(pl && other){
    auto p0 = pl   ->cameraBone();
    auto p1 = other->cameraBone();
    camera.setTarget((p0+p1)*0.5f + Vec3(0,50,0));
    p0 -= p1;

    if(pl==other) {
      // float a = pl->rotation();
      // camera.setSpin(PointF(0,a));
      } else {
      float l = p0.length();
      float a = 0;
      if(curentIsPl) {
        a = other->rotation()-45;
        } else {
        a = pl->rotation()+45;
        }

      camera.setDialogDistance(l);
      camera.setSpin(PointF(0,a));
      }
    }
  }

void DialogMenu::openPipe(Npc &player, Npc &npc, AiOuputPipe *&out) {
  stopNarration();
  out    = &pipe;
  pl     = &player;
  other  = &npc;
  state  = State::PreStart;
  }

bool DialogMenu::isNpcInDialog(const Npc* npc) const {
  if(state==State::Idle)
    return false;
  return npc==pl || npc==other || npc==nullptr;
  }

bool DialogMenu::aiOutput(Npc &npc, std::string_view msg) {
  if(&npc!=pl && &npc!=other){
    Log::e("unexpected aiOutput call: ",msg.data());
    return true;
    }

  if(current.time>0)
    return false;

  if(pl==&npc) {
    if(other!=nullptr)
      other->stopDlgAnim();
    } else {
    if(pl!=nullptr)
      pl->stopDlgAnim();
    }

  current.txt     = Gothic::inst().messageByName(msg);
  current.msgTime = Gothic::inst().messageTime(msg);
  current.time    = current.msgTime + (dlgAnimation ? ANIM_TIME*2 : 0);
  currentSnd      = soundDevice.load(Resources::loadSoundBuffer(string_frm(msg,".wav")));
  curentIsPl      = (pl==&npc);

  currentSnd.play();
  npc.setAiOutputBarrier(current.msgTime,false);
  update();
  return true;
  }

bool DialogMenu::aiPrintScr(Npc& npc, int time, std::string_view msg, int x, int y, std::string_view font) {
  if(current.time>0)
    return false;
  auto& f = Resources::font(font, Resources::FontType::Normal, 1.0);
  Gothic::inst().onPrintScreen(msg,x,y,time,f);
  return true;
  }

bool DialogMenu::aiClose() {
  if(current.time>0){
    return false;
    }

  choice.clear();
  close();
  state=State::Idle;
  update();
  return true;
  }

void DialogMenu::stopNarration() {
  // A conversation always wins: the voice from off-screen stops and its subtitle goes with it.
  narratorSnd   = Tempest::SoundEffect();
  narratorUntil = 0;
  pscreen.erase(std::remove_if(pscreen.begin(),pscreen.end(),[this](const PScreen& sc){
    return sc.x<0 && std::find(narratorRows.begin(),narratorRows.end(),sc.y)!=narratorRows.end();
    }),pscreen.end());
  narratorRows.clear();
  }

bool DialogMenu::narrating() const {
  return Tempest::Application::tickCount()<narratorUntil;
  }

bool DialogMenu::narrate(std::string_view text, uint64_t timeMs, std::string_view wav) {
  if(isActive() || narrating() || text.empty())
    return false;
  narratorSnd = Tempest::SoundEffect();
  if(!wav.empty()) {
    try {
      narratorSnd = soundDevice.load(std::string(wav).c_str());
      narratorSnd.play();
      }
    catch(const std::exception& e) {
      Log::e("unable to play narrator audio: ", e.what());
      narratorSnd = Tempest::SoundEffect();
      }
    }
  // The font does not wrap, so long lines are split into rows near the top of the screen.
  const float scale   = Gothic::interfaceScale(this);
  auto&       font    = Resources::font(scale);
  const int   seconds = int((timeMs+999)/1000);
  std::string row;
  int         y = 8;
  narratorRows.clear();
  auto flush = [&]() {
    if(!row.empty()) {
      printScreen(row,-1,y,seconds,font);
      narratorRows.push_back(y);
      }
    row.clear();
    y += 4;
    };
  size_t at = 0;
  while(at<text.size()) {
    size_t end  = text.find(' ',at);
    auto   word = text.substr(at,end==std::string_view::npos ? std::string_view::npos : end-at);
    if(!row.empty() && row.size()+1+word.size()>64)
      flush();
    if(!row.empty())
      row += ' ';
    row += word;
    at = end==std::string_view::npos ? text.size() : end+1;
    }
  flush();
  narratorUntil = Tempest::Application::tickCount()+timeMs;
  update();
  return true;
  }

bool DialogMenu::isActive() const {
  return (state!=State::Idle) || current.time>0;
  }

bool DialogMenu::hasContent() const {
  return (current.time>0 || choice.size()>0);
  }

bool DialogMenu::onStart(Npc &p, Npc &ot) {
  const bool guard    = ot.guild()==GIL_MIL || ot.guild()==GIL_PAL;   // guards keep their own words, trip or not
  // Only a conversation that is just starting: the menu's depth is not reliable here, a script's farewell leaves it set.
  const bool tripTalk = Gothic::inst().dmTripTalk && !guard && state==State::PreStart;
  if(tripTalk || std::find(agentNpcs.begin(),agentNpcs.end(),&ot)!=agentNpcs.end()) {
    agentMode      = true;
    agentOpened    = true;
    agentFirstLine = true;
    agentSelected  = -1;
    choice.clear();
    state          = State::Active;
    depth          = 0;
    curentIsPl     = true;
    choiceAnimTime = 0;
    dlgSel         = 0;
    update();
    return true;
    }

  choice         = ot.dialogChoices(p,except,state==State::PreStart);
  if(choice.empty() || choice[0].title.size()>0)
    choice = withStoryTopics(std::move(choice),ot);   // not while an important line opens the talk
  state          = State::Active;
  depth          = 0;
  curentIsPl     = true;
  choiceAnimTime = 0;

  if(choice.size()>0 && choice[0].title.size()==0){
    // important dialog
    onEntry(choice[0]);
    }

  dlgSel=0;
  update();
  return true;
  }

void DialogMenu::printScreen(std::string_view msg, int x, int y, int time, const GthFont &font) {
  if(x>=0 && y>=0) {
    for(auto& sc:pscreen) {
      if(sc.x==x && sc.y==y) {
        sc.txt  = msg;
        sc.font = &font;
        sc.time = uint32_t(time*1000);
        return;
        }
      }
    }
  PScreen e;
  e.txt  = msg;
  e.font = &font;
  e.time = uint32_t(time*1000);
  e.x    = x;
  e.y    = y;
  pscreen.emplace_back(std::move(e));
  update();
  }

void DialogMenu::drawMsg(Tempest::Painter& p, int offsetY) {
  for(size_t i=0;i<MAX_PRINT;++i){
    auto& sc  = printMsg[i];
    if(sc.font==nullptr)
      continue;

    auto& fnt = *sc.font;
    auto  sz  = fnt.textSize(sc.txt);
    int   x   = SafeArea::center(w(),sz.w,margins().left,margins().right);
    fnt.drawText(p, x, offsetY + int(i*2+1)*sz.h, sc.txt);
    }
  }

void DialogMenu::print(std::string_view msg) {
  if(msg.empty())
    return;

  const float scale = Gothic::interfaceScale(this);
  for(size_t i=1;i<MAX_PRINT;++i)
    printMsg[i-1u]=printMsg[i];

  remPrint=1500;
  PScreen& e=printMsg[MAX_PRINT-1];
  e.txt  = msg;
  e.font = &Resources::font(scale);
  e.time = remPrint;
  e.x    = -1;
  e.y    = -1;
  update();
  }

void DialogMenu::onDoneText() {
  choice = Gothic::inst().updateDialog(selected,*pl,*other);
  dlgSel = 0;
  if(choice.size()==0){
    if(depth>0) {
      onStart(*pl,*other);
      } else {
      close();
      }
    }
  }

void DialogMenu::close() {
  auto prevPl  = pl;
  auto prevNpc = other;

  pl=nullptr;
  other=nullptr;
  depth=0;
  dlgTrade=false;
  agentMode=false;
  agentTopic.clear();
  agentTopicTaken=true;
  agentOpened=false;
  agentSelected=-1;
  current.time=0;
  choice.clear();
  state=State::Idle;
  currentSnd = SoundEffect();
  update();

  if(prevPl!=nullptr && prevPl==prevNpc){
    auto i = prevPl->interactive();
    if(i!=nullptr)
      prevPl->setInteraction(nullptr);
    }
  if(prevPl){
    prevPl->stopDlgAnim();
    }
  if(prevNpc && prevNpc!=prevPl){
    prevNpc->stopDlgAnim();
    }
  }

bool DialogMenu::haveToWaitOutput() const {
  if(pl && pl->haveOutput()){
    return true;
    }
  if(other && other->haveOutput()){
    return true;
    }
  return false;
  }

bool DialogMenu::haveToShowSubtitles(bool isPl) const {
  return showSubtitles && (showSubtitlesPlayer || !isPl);
  }

void DialogMenu::startTrade() {
  if(pl!=nullptr && other!=nullptr)
    trade.trade(*pl,*other);
  dlgTrade=false;
  }

void DialogMenu::skipPhrase() {
  if(skipBlockedMs>0)
    return;
  if(current.time>0) {
    if(pl!=nullptr)
      pl->setAiOutputBarrier(0,false);
    if(other!=nullptr)
      other->setAiOutputBarrier(0,false);
    currentSnd   = SoundEffect();
    current.time = 1;
    }
  }

void DialogMenu::onEntry(const GameScript::DlgChoice &e) {
  if(pl && other && !e.storyTopic.empty()) {
    // A story's topic: this conversation is Python's until it calls agentEndTopic().
    agentMode       = true;
    agentTopic      = e.storyTopic;
    agentTopicTaken = false;
    agentSelected   = -1;
    agentFirstLine  = true;
    choice.clear();
    update();
    return;
    }
  if(pl && other) {
    selected = e;
    depth    = 1;
    dlgTrade = e.isTrade;
    except.push_back(e.scriptFn);
    Gothic::inst().dialogExec(e,*pl,*other);

    onDoneText();
    }
  }

void DialogMenu::paintEvent(Tempest::PaintEvent &e) {
  const float scale = Gothic::interfaceScale(this);
  const auto  area  = clientRect();

  Painter p(e);
  const uint64_t da = dlgAnimation ? ANIM_TIME : 0;
  const int      dw = std::min(area.w,int(600*scale));
  const int      dh = int(100*scale);
  const int      dx = SafeArea::center(w(),dw,margins().left,margins().right);
  const int      dy = std::max(20,margins().top);

  if(current.time>0 && trade.isOpen()==InventoryMenu::State::Closed && haveToShowSubtitles(curentIsPl)) {
    if(ambient!=nullptr) {
      int dlgW = dw;
      int dlgH = dh;

      if(current.time>current.msgTime+da) {
        float k = 1.f-float(current.time-current.msgTime-da)/float(da);
        dlgW = int(float(dlgW)*k);
        dlgH = int(float(dlgH)*k);
        }
      else if(current.time<da) {
        float k = float(current.time)/float(da);
        dlgW = int(float(dlgW)*k);
        dlgH = int(float(dlgH)*k);
        }

      p.setBrush(*ambient);
      p.drawRect(dx+(dw-dlgW)/2, dy+(dh-dlgH)/2, dlgW, dlgH,
                 0,0,ambient->w(),ambient->h());
      }

    if(current.time>da && current.time<current.msgTime+da)
      drawTextMultiline(p,dx,dy,dw,dh,current.txt,curentIsPl);
    }

  paintChoice(e);

  for(size_t i=0;i<pscreen.size();++i){
    auto& sc   = pscreen[i];
    auto  fnt  = *sc.font;
    fnt.setScale(Gothic::interfaceScale(this));

    auto  sz   = fnt.textSize(sc.txt);

    int x = sc.x;
    int y = sc.y;
    if(x<0){
      x = SafeArea::center(w(),sz.w,margins().left,margins().right);
      } else {
      x = area.x+(area.w*x)/100;
      }
    if(y<0){
      const int baseline = fnt.pixelSize();
      y = SafeArea::position((h()-sz.h)/2-baseline,sz.h,margins().top,h()-margins().bottom)+baseline;
      } else {
      y = area.y+((area.h-sz.h)*y)/100+sz.h;
      }
    fnt.drawText(p, x, y, sc.txt);
    }
  }

void DialogMenu::paintChoice(PaintEvent &e) {
  if(choice.size()==0)
    return;

  const float scale    = Gothic::interfaceScale(this);
  const auto  area     = clientRect();
  const int   padd     = int(20*scale);
  const int   dw       = std::min(area.w,int(600*scale));
  const bool  isActive = isChoiceMenuActive();

  int  dh = padd*2;
  for(size_t i=0;i<choice.size();++i){
    auto fnt = Resources::dialogFont(scale);
    Size choiceTextSize = fnt.textSize(dw-padd, choice[i].title);
    dh += choiceTextSize.h;
    }

  const int  x        = SafeArea::center(w(),dw,margins().left,margins().right);
  const int  y        = h()-dh-std::max(int(20*scale),margins().bottom);

  if(tex!=nullptr && (choiceAnimTime>0 || isActive)) {
    float k    = dlgAnimation ? (float(choiceAnimTime)/float(ANIM_TIME)) : 1.f;
    int   dlgW = int(float(dw)*k);
    int   dlgH = int(float(dh)*k);

    Painter p(e);
    p.setBrush(*tex);
    p.drawRect(x+(dw-dlgW)/2,y+(dh-dlgH)/2,dlgW,dlgH,
               0,0,tex->w(),tex->h());
    }

  if(choiceAnimTime<ANIM_TIME && dlgAnimation)
    return;

  if(!isChoiceMenuActive())
    return;

  int textHeightOffset = padd;
  Painter p(e);
  for(size_t i=0;i<choice.size();++i){
    GthFont fnt;
    if(i==dlgSel)
      fnt = Resources::font(Resources::FontType::Hi, scale); else
      fnt = Resources::dialogFont(scale);

    Size choiceTextSize = fnt.textSize(dw-padd, choice[i].title);
    fnt.drawText(p,x+padd,y+padd+textHeightOffset,dw-padd,0,choice[i].title,AlignLeft);
    textHeightOffset += choiceTextSize.h;
    }
  }

bool DialogMenu::isChoiceMenuActive() const {
  return choice.size()!=0 && current.time==0 && !haveToWaitOutput() && trade.isOpen()==InventoryMenu::State::Closed;
  }

void DialogMenu::onSelect() {
  if(current.time>0 || haveToWaitOutput()){
    return;
    }

  if(agentMode) {
    if(dlgSel<choice.size()) {
      agentSelected = int(dlgSel);
      choice.clear();
      choiceAnimTime = dlgAnimation ? ANIM_TIME : 0;
      update();
      }
    return;
    }

  if(dlgSel<choice.size()) {
    onEntry(choice[dlgSel]);
    choiceAnimTime = dlgAnimation ? ANIM_TIME : 0;
    }
  }

void DialogMenu::mouseDownEvent(MouseEvent &event) {
  if(state==State::Idle || trade.isOpen()!=InventoryMenu::State::Closed){
    event.ignore();
    return;
    }

  if(event.button==MouseEvent::ButtonLeft) {
    onSelect();
    }
  if(event.button==MouseEvent::ButtonRight) {
    skipPhrase();
    }
  }

void DialogMenu::mouseWheelEvent(MouseEvent &e) {
  if(state==State::Idle || trade.isOpen()!=InventoryMenu::State::Closed){
    e.ignore();
    return;
    }

  if(e.delta>0)
    dlgSel--;
  if(e.delta<0)
    dlgSel++;
  dlgSel = (dlgSel+choice.size())%std::max<size_t>(choice.size(),1);
  update();
  }

void DialogMenu::keyDownEvent(KeyEvent &e) {
  if(state==State::Idle || trade.isOpen()!=InventoryMenu::State::Closed){
    e.ignore();
    return;
    }

  if(e.key==Event::K_Return){
    onSelect();
    return;
    }
  if(e.key==Event::K_W || e.key==Event::K_S || e.key==Event::K_Up || e.key==Event::K_Down || e.key==Event::K_ESCAPE){
    if(e.key==Event::K_W || e.key==Event::K_Up){
      dlgSel--;
      }
    if(e.key==Event::K_S || e.key==Event::K_Down){
      dlgSel++;
      }
    if(e.key==Event::K_ESCAPE){
      skipPhrase();
      }
    dlgSel = (dlgSel+choice.size())%std::max<size_t>(choice.size(),1);
    update();
    return;
    }
  e.ignore();
  }

void DialogMenu::keyUpEvent(KeyEvent &event) {
  if(state==State::Idle && current.time>0){
    event.ignore();
    return;
    }
  }

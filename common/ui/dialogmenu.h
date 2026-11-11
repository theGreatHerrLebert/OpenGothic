#pragma once

#include <Tempest/Font>
#include <Tempest/Texture2d>
#include <Tempest/Timer>
#include <Tempest/Widget>
#include <Tempest/SoundEffect>
#include <Tempest/SoundDevice>

#include "game/gamescript.h"
#include "camera.h"

class Npc;
class Interactive;
class InventoryMenu;
class GthFont;

class DialogMenu : public Tempest::Widget {
  public:
    DialogMenu(InventoryMenu& trade);
    ~DialogMenu();

    void tick(uint64_t dt);
    void clear();

    void onWorldChanged();

    bool isMobsiDialog() const;
    void dialogCamera(Camera& camera);

    void openPipe(Npc &player, Npc& npc, AiOuputPipe*& out);
    bool isNpcInDialog(const Npc* npc) const;

    bool isActive() const;
    bool hasContent() const;

    // Agent mode: talking to the bound NPC opens an empty dialogue driven from
    // Python instead of the NPC's scripted C_INFO entries.
    void agentBind(Npc* npc);
    void agentUnbind(Npc* npc);
    bool agentActive() const { return agentMode; }
    Npc* partner() const { return (state!=State::Idle && other!=pl) ? other : nullptr; }
    bool agentTakeOpened();

    // Extending an NPC: a story's topics appear in the NPC's own menu beside its scripted ones. Choosing one hands
    // this conversation to Python (agent mode) until agentEndTopic(), which returns to the NPC's own menu.
    void        agentSetTopics(Npc* npc, std::vector<std::pair<std::string,std::string>> keyAndTitle);
    std::string agentTakeTopic();
    bool        agentEndTopic();
    bool agentSay(std::string_view text, bool isPlayer, uint64_t timeMs, std::string_view wav);
    void agentSetChoices(const std::vector<std::string>& titles);
    int  agentTakeSelection();
    bool agentBusy() const;
    void agentClose();
    // A voice from off-screen: plays a line with a subtitle near the top, outside any conversation.
    bool narrate(std::string_view text, uint64_t timeMs, std::string_view wav);
    bool narrating() const;
    void stopNarration();

    void print      (std::string_view msg);
    void printScreen(std::string_view msg, int x, int y, int time, const GthFont &font);
    void drawMsg    (Tempest::Painter& p, int offsetY);

    void keyDownEvent   (Tempest::KeyEvent&   event) override;
    void keyUpEvent     (Tempest::KeyEvent&   event) override;

  protected:
    void paintEvent (Tempest::PaintEvent& e) override;
    void paintChoice(Tempest::PaintEvent& e);

    void mouseDownEvent (Tempest::MouseEvent& event) override;
    void mouseWheelEvent(Tempest::MouseEvent& event) override;

    void onSelect();
    void setupSettings();
    bool isChoiceMenuActive() const;

  private:
    const Tempest::Texture2d* tex    =nullptr;
    const Tempest::Texture2d* ambient=nullptr;

    struct Pipe : AiOuputPipe {
      Pipe(DialogMenu& owner):owner(owner){}

      bool output   (Npc& npc, std::string_view text) override;
      bool outputSvm(Npc& npc, std::string_view text) override;
      bool outputOv (Npc& npc, std::string_view text) override;
      bool printScr (Npc& npc, int time, std::string_view msg, int x, int y, std::string_view font) override;

      bool close() override;
      bool isFinished() override;

      DialogMenu& owner;
      };

    enum {
      MAX_PRINT = 3,
      ANIM_TIME = 200,
      };

    enum class State : uint8_t {
      Idle    =0,
      PreStart=1,
      Active  =2
      };

    struct Entry {
      std::string txt;
      uint64_t    msgTime = 0;
      uint64_t    time    = 0;
      };

    struct Forward {
      std::string txt;
      Npc*        npc=nullptr;
      };

    struct PScreen {
      std::string    txt;
      const GthFont* font=nullptr;
      uint64_t       time=0;
      int            x=-1;
      int            y=-1;
      };

    bool onStart(Npc& pl,Npc& other);
    void onEntry(const GameScript::DlgChoice& e);
    void onDoneText();
    void close();
    bool aiOutput  (Npc& npc, std::string_view msg);
    bool aiPrintScr(Npc& npc, int time, std::string_view msg, int x, int y, std::string_view font);
    bool aiClose();

    bool haveToWaitOutput() const;
    bool hasPrintMsg() const;
    bool haveToShowSubtitles(bool isPl) const;

    void drawTextMultiline(Tempest::Painter& p, int x, int y, int w, int h, std::string_view txt, bool isPl);
    Tempest::Size processTextMultiline(Tempest::Painter* p, int x, int y, int w, int h, std::string_view txt, bool isPl);

    void startTrade();
    void skipPhrase();

    InventoryMenu&                      trade;
    Pipe                                pipe;

    Tempest::SoundDevice                soundDevice;

    std::vector<GameScript::DlgChoice>  choice;
    GameScript::DlgChoice               selected;
    Npc*                                pl   =nullptr;
    Npc*                                other=nullptr;
    size_t                              dlgSel=0;
    uint32_t                            depth=0;
    std::vector<uint32_t>               except;

    State                               state=State::Idle;
    Entry                               current;
    Tempest::SoundEffect                currentSnd;
    Tempest::SoundEffect                narratorSnd;
    uint64_t                            narratorUntil = 0;
    std::vector<int>                    narratorRows;
    bool                                curentIsPl=false;
    bool                                dlgTrade=false;
    int32_t                             mobsiState=-1;

    std::vector<PScreen>                pscreen;
    PScreen                             printMsg[MAX_PRINT];
    uint64_t                            remPrint=0;

    std::vector<Npc*>                   agentNpcs;
    struct StoryTopic {
      Npc*        npc = nullptr;
      std::string key, title;
      };
    std::vector<StoryTopic>             storyTopics;
    std::string                         agentTopic;      // the story topic being played, empty if none
    bool                                agentTopicTaken = true;

    std::vector<GameScript::DlgChoice> withStoryTopics(std::vector<GameScript::DlgChoice> choices, Npc& npc) const;
    bool                                agentMode     = false;
    bool                                agentOpened   = false;
    int                                 agentSelected = -1;
    bool                                agentFirstLine = false;
    uint64_t                            skipBlockedMs  = 0;

    bool                                dlgAnimation        = true;
    bool                                showSubtitles       = true;
    bool                                showSubtitlesPlayer = true;
    uint64_t                            choiceAnimTime      = 0;
  };

#pragma once

#include <Tempest/Widget>
#include <Tempest/Texture2d>
#include <Tempest/Timer>

class KeyCodec;

class DocumentMenu : public Tempest::Widget {
  public:
    DocumentMenu(const KeyCodec& key);

    enum Flags : uint8_t {
      F_None,
      F_Margin=1,
      F_Backgr=2,
      F_Font  =4
      };

    struct Page {
      std::string     img;
      std::string     text;
      std::string     font;
      Tempest::Margin margins;
      Flags           flg=F_None;
      };

    // TODO: set default values for these
    struct Show {
      std::vector<Page> pages;
      std::string       font;
      Tempest::Margin   margins;
      std::string       img;
      // map
      bool              showPlayer=false;
      // pages shown at once: 0 all (the game's own documents), 2 a story book's spread, 1 a letter's sheet; with
      // more pages than that, Left/Right turn them (docs/plan-story-books.md)
      uint8_t           spread=0;
      Tempest::Rect     wbounds;
      };

    void show(const Show& doc);
    bool isActive() const { return active; }
    void close();
    void tick(uint64_t dt);

    void keyDownEvent(Tempest::KeyEvent &e);
    void keyUpEvent  (Tempest::KeyEvent &e);

  protected:
    void paintEvent(Tempest::PaintEvent& e);

  private:
    DocumentMenu::Show        document;
    const KeyCodec&           keycodec;
    const Tempest::Texture2d* cursor = nullptr;
    bool                      active = false;
    size_t                    first  = 0;    // the first page shown, when the document turns
  };


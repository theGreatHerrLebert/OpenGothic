#pragma once

#include <zenkit/addon/daedalus.hh>

#include <Tempest/SoundDevice>
#include <Tempest/SoundEffect>

class GameMusic final {
  public:
    GameMusic();
    GameMusic(const GameMusic&)=delete;
    ~GameMusic();

    static GameMusic& inst();

    enum Music : uint8_t {
      SysLoading
      };

    enum Tags : uint8_t {
      Day = 0,
      Ngt = 1<<0,

      Std = 0,
      Fgt = 1<<1,
      Thr = 1<<2
      };

    static Tags mkTags(Tags daytime,Tags mode);

    void      setEnabled(bool e);
    bool      isEnabled() const;
    void      setMusic(Music m);
    void      setMusic(const zenkit::IMusicTheme &theme, Tags t);
    void      stopMusic();

    // A second track (WAV or OGG) beside the game's music, for a story's own music. Both start and stay where the
    // caller puts them: mix() sets the track's volume and scales the game's music, so a crossfade is the caller's.
    bool      playTrack(const std::string& path);
    void      stopTrack();
    void      mix(float trackVolume, float themeScale);
    bool      isTrackPlaying() const;
    // Called every frame, also while paused or in a menu: once the track has ended or is gone, the game's music
    // comes back on its own, so it can never stay muted however the story's side stopped.
    void      tickTrack(uint64_t now);

  private:
    struct MusicProvider;
    struct OpenGothicMusicProvider;
    struct GothicKitMusicProvider;

    void      setupSettings();

    static GameMusic* instance;

    struct {
      zenkit::IMusicTheme theme = {};
      Tags                tags  = Tags::Std;
      } currentMusic;

    int                  provider = -1;
    Tempest::SoundDevice device;
    Tempest::SoundEffect sound;
    MusicProvider*       impl = nullptr;
    Tempest::SoundEffect track;
    float                trackVolume = 0.f;
    float                themeScale  = 1.f;
    uint64_t             lastTrackTick = 0;
  };

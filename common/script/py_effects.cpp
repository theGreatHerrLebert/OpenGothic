#include "pybindings_common.h"
#include "graphics/worldview.h"

#include <algorithm>

#include "gamemusic.h"
#include "game/globaleffects.h"
#include "graphics/sky/galaxy.h"
#include "resources.h"

namespace py = pybind11;

namespace PyBindings {

void bindOverlay(py::module_& m) {
  py::module_ overlay = m.def_submodule("overlay", "The small DM status panel in the corner of the screen.");
  overlay.def("set",
              [](const std::string& text, float progress, float strength) {
                Gothic::inst().dmStatus = {toEngine(text), progress, std::clamp(strength, 0.f, 1.f)};
                },
              py::arg("text"), py::arg("progress") = -1.f, py::arg("strength") = 1.f,
              "Show text, with progress from 0 to 1, or below zero if the length is unknown. strength (0 to 1) "
              "is how strongly the panel shows; it fades towards it.");
  overlay.def("clear", []() { Gothic::inst().dmStatus = {}; });
  overlay.def("menu",
              [](const std::string& text) { Gothic::inst().dmMenu = toEngine(text); },
              py::arg("text"),
              "Show a menu panel below the status, one line per row, even while the status is hidden. "
              "An empty text closes it.");

  m.def("print_screen",
        [](const std::string& text, int x, int y, const std::string& font, int seconds) {
          // What Gothic::printscreen (the PrintScreen extern) does, which is private.
          Gothic::inst().onPrintScreen(toEngine(text), x, y, seconds,
                                       Resources::font(font, Resources::FontType::Normal, 1));
          },
        py::arg("text"), py::arg("x") = -1, py::arg("y") = -1, py::arg("font") = "FONT_OLD_10_WHITE.TGA",
        py::arg("seconds") = 2,
        "Show a line on screen like the PrintScreen extern: x and y in percent of the screen, -1 centres.");

  m.def("play_sound",
        [](const std::string& name) { Gothic::inst().emitGlobalSound(upper(name)); },
        py::arg("name"), "Play one of the game's sound effects (an SFX instance or WAV name), as Snd_Play does.");
  m.def("play_sound_file",
        [](const std::string& path) {
          Tempest::Sound snd(path);
          Gothic::inst().emitGlobalSound(snd);
          },
        py::arg("path"), "Play a WAV file of our own from disk, heard everywhere.");

  m.def("take_keys",
        []() { return Gothic::inst().takeDmKeys(); },
        "DM hotkeys pressed since the last call, oldest first: 'feedback' for Alt+F, '1' to '5' for Alt+1 to Alt+5.");
  }

void bindTrip(py::module_& m) {
  py::module_ trip = m.def_submodule("trip", "A trip set live every tick: the view breathes, colour washes over "
                                              "the screen, the world slows and the camera trembles.");
  trip.def("set",
           [](float fov, float speed, std::tuple<float,float,float,float> tint, float time, float shake,
              float post, float edges, float tracers, std::tuple<float,float,float> bands, float zoom, int look,
              float eye, float afterglow) {
             GlobalEffects::Trip t;
             t.eye     = std::clamp(eye,   0.f, 1.f);
             t.afterglow = std::clamp(afterglow, 0.f, 1.f);
             t.look    = std::clamp(look, 0, 2);   // 0 Mindcap, 1 Emberheart, 2 the Invocation
             t.zoom    = std::clamp(zoom, 0.f, 0.3f);
             t.post    = std::clamp(post, 0.f, 1.f);
             t.edges   = std::clamp(edges, 0.f, 1.f);
             t.tracers = std::clamp(tracers, 0.f, 1.f);
             t.bass    = std::max(std::get<0>(bands), 0.f);
             t.mid     = std::max(std::get<1>(bands), 0.f);
             t.treble  = std::max(std::get<2>(bands), 0.f);
             t.fov   = std::max(fov, 0.f);
             t.speed = std::max(speed, 0.05f);
             t.tint  = Tempest::Color(std::get<0>(tint), std::get<1>(tint), std::get<2>(tint),
                                      std::clamp(std::get<3>(tint), 0.f, 1.f));
             t.time  = std::clamp(time, 0.05f, 1.f);
             t.shake = std::max(shake, 0.f);
             requireWorld()->globalFx()->setTrip(t);
             },
           py::arg("fov") = 0.f, py::arg("speed") = 1.f, py::arg("tint") = std::make_tuple(0.f,0.f,0.f,0.f),
           py::arg("time") = 1.f, py::arg("shake") = 0.f, py::arg("post") = 0.f, py::arg("edges") = 1.f,
           py::arg("tracers") = 1.f, py::arg("bands") = std::make_tuple(0.f,0.f,0.f), py::arg("zoom") = 0.f,
           py::arg("look") = 0, py::arg("eye") = 0.f, py::arg("afterglow") = 0.f,
           "post (0..1) runs the trip shader over the finished frame: glowing edges, tracers, colour; "
           "bands are the music's bass, mid and treble, smoothed.");
  trip.def("clear", []() { requireWorld()->globalFx()->setTrip(GlobalEffects::Trip()); });
  trip.def("take_escapes", []() { auto n = Gothic::inst().dmEscapeRefused; Gothic::inst().dmEscapeRefused = 0; return n; },
           "How often Escape was held back since the last call (while saving is refused).");
  trip.def("block_save", [](bool on) { Gothic::inst().dmBlockSave = on; }, py::arg("on"),
           "While on, saving is refused as it is during a conversation, quick save included.");

  py::module_ weather = m.def_submodule("weather", "Weather the story lays over the world.");
  weather.def("snow", [](float density) { requireWorld()->globalFx()->setSnow(std::clamp(density, 0.f, 1.f)); },
              py::arg("density"), "Falling snow over the frame (the trip lens), 0 none .. 1 a blizzard.");
  weather.def("set",
              [](const std::string& kind, float intensity, float fade, std::tuple<float,float> wind) {
                using P = GlobalEffects::Precipitation;
                P k = kind=="snow" ? P::Snow : kind=="rain" ? P::Rain : kind=="clear" ? P::None
                    : throw std::invalid_argument("weather kind is snow, rain or clear: " + kind);
                requireWorld()->globalFx()->setWeather(k, intensity, fade, std::get<0>(wind), std::get<1>(wind));
                },
              py::arg("kind"), py::arg("intensity") = 1.f, py::arg("fade") = 10.f,
              py::arg("wind") = std::make_tuple(0.f, 0.f),
              "Weather in the world: snow, rain or clear, intensity 0..1, reached over fade seconds of game time; "
              "wind (x, z) in metres per second. A change of kind lets the old one stop first.");
  weather.def("cover", [](float target, float seconds) { requireWorld()->globalFx()->setCover(target, seconds); },
              py::arg("target"), py::arg("seconds") = 600.f, "Snow lying on the ground, 0..1, reached over seconds.");
  weather.def("lightning", [](float delay) { requireWorld()->globalFx()->lightning(delay); }, py::arg("delay") = 2.f,
              "A lightning flash now and its thunder after delay seconds (3 s is about a kilometre away).");
  weather.def("roof_at",
              [](float x, float z) {
                auto* view = requireWorld()->view();
                return view==nullptr ? -1.0e9f : view->weatherRoofAt(x, z);
                },
              py::arg("x"), py::arg("z"), "The roof map's height over a point (cm): the highest static surface there.");
  weather.def("state",
              []() {
                auto& w = requireWorld()->globalFx()->weatherState();
                const char* kinds[] = {"clear", "snow", "rain"};
                py::dict d;
                d["kind"] = kinds[int(w.kind)]; d["intensity"] = w.intensity; d["target"] = w.target;
                d["wind"] = std::make_tuple(w.windX, w.windZ); d["cover"] = w.cover; d["wet"] = w.wet; d["overcast"] = w.overcast;
                d["raining"] = requireWorld()->globalFx()->isRaining();
                return d;
                },
              "What the weather is now.");
  }

void bindSky(py::module_& m) {
  py::module_ sky = m.def_submodule("sky", "A galaxy in place of the sky: images loaded once, shown as strongly as set.");
  sky.def("load", [](int slot, const std::string& path) { return ::Galaxy::inst().load(size_t(std::max(slot, 0)), path); },
          py::arg("slot"), py::arg("path"),
          "Load an image: slot 0 a 360-degree panorama (equirectangular), 1 and 2 nebulae placed on the sky.");
  sky.def("galaxy",
          [](float amount, float gain, std::tuple<float,float,float> tint, float grade, float spin, float glow,
             std::vector<std::tuple<float,float,float,float>> nebulae, float aurora, float time, float moon) {
            GlobalEffects::Galaxy g;
            g.amount = std::clamp(amount, 0.f, 1.f);
            g.gain   = std::max(gain, 0.f);
            g.tint   = Tempest::Vec3(std::get<0>(tint), std::get<1>(tint), std::get<2>(tint));
            g.grade  = std::clamp(grade, 0.f, 1.f);
            g.spin   = spin;
            g.glow   = std::clamp(glow, 0.f, 1.f);
            for(size_t i=0; i<nebulae.size() && i<2; ++i) {
              auto& n = nebulae[i];
              g.nebula[i] = Tempest::Vec4(std::get<0>(n), std::get<1>(n), std::get<2>(n), std::get<3>(n));
              }
            g.aurora = std::clamp(aurora, 0.f, 1.f);
            g.time   = time;
            g.moon   = std::clamp(moon, 0.f, 1.f);
            requireWorld()->globalFx()->setGalaxy(g);
            },
          py::arg("amount"), py::arg("gain") = 1.f, py::arg("tint") = std::make_tuple(1.f,1.f,1.f),
          py::arg("grade") = 0.f, py::arg("spin") = 0.f, py::arg("glow") = 0.f,
          py::arg("nebulae") = std::vector<std::tuple<float,float,float,float>>{},
          py::arg("aurora") = 0.f, py::arg("time") = 0.f, py::arg("moon") = 0.f,
          "amount 0 is the game's sky, 1 the galaxy instead; nebulae are (yaw, pitch, size, strength) in radians; "
          "aurora (0..1) lays northern lights over it, drifting with time (seconds) and flaring with glow; "
          "moon (0..1) raises a blood-red moon.");
  sky.def("clear", []() { requireWorld()->globalFx()->setGalaxy(GlobalEffects::Galaxy()); });
  }

void bindMusic(py::module_& m) {
  py::module_ music = m.def_submodule("music", "A story's own track beside the game's music; mix() crossfades.");
  music.def("play_track", [](const std::string& path) { return GameMusic::inst().playTrack(path); },
            py::arg("path"), "Start a WAV or OGG track at volume 0. Returns False if it cannot be loaded.");
  music.def("stop_track", []() { GameMusic::inst().stopTrack(); });
  music.def("mix", [](float track, float theme) { GameMusic::inst().mix(track, theme); },
            py::arg("track"), py::arg("theme"),
            "Track volume and the game's music volume, each 0 to 1, relative to the music volume setting.");
  music.def("track_playing", []() { return GameMusic::inst().isTrackPlaying(); });
  }

} // namespace PyBindings

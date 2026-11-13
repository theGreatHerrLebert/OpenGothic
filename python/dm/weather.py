"""Snow over the world, set every tick: a fall that starts with a few flakes, thickens to a blizzard and clears again.

    from dm import weather
    weather.snow(rise=60, hold=90, fall=40)      # seconds: a minute to a blizzard, a minute and a half of it, then gone
    weather.stop()                               # eases off

It falls in the world (gothic.weather.set, docs/plan-weather.md), with wind, settling as it falls, and the world's own
roof map keeps it off the hero indoors; afterwards it melts and the weather from before returns (a story's, or the
climate's). On an engine without world weather it falls over the frame instead, fading out indoors.
"""

import sys
import time

INDOORS_FADE = 1.5   # seconds to fade the snow out or in at a door (the lens fallback)
WIND = (2.5, 0.8)    # metres per second: a northern wind


def density_at(seconds, rise, hold, fall, peak=1.0):
    """The planned snow at a moment: a slow start that thickens (eased), the peak held, then clearing."""
    if seconds < 0:
        return 0.0
    if seconds < rise:
        x = seconds / rise
        return peak * x * x * (3 - 2 * x)
    if seconds < rise + hold:
        return peak
    if seconds < rise + hold + fall:
        x = 1 - (seconds - rise - hold) / fall
        return peak * x * x * (3 - 2 * x)
    return 0.0


class Snowfall:
    def __init__(self, rise, hold, fall, peak):
        self.rise, self.hold, self.fall, self.peak = rise, hold, fall, peak
        self.started = None
        self.outside = 1.0
        self.last = None
        self.ending = None   # (when the stop began, the density then)

    def tick(self, gothic, now):
        if self.started is None:
            self.started = now
        dt = now - self.last if self.last is not None else 0.0
        self.last = now
        planned = density_at(now - self.started, self.rise, self.hold, self.fall, self.peak)
        if self.ending is not None:
            when, level = self.ending
            planned = min(planned, level * max(0.0, 1 - (now - when) / 4.0))
        if hasattr(gothic.weather, "set"):
            level = round(planned, 2)
            if level != getattr(self, "set_level", None):   # only when it changes, with a short ease
                gothic.weather.set("snow", level, 1.0, WIND)
                gothic.weather.cover(min(1.0, level * 0.7), 90.0)
                self.set_level = level
        else:
            target = 0.0 if gothic.player.room else 1.0
            step = dt / INDOORS_FADE   # evenly, so indoors it is gone within INDOORS_FADE seconds
            self.outside = min(target, self.outside + step) if target > self.outside else max(target, self.outside - step)
            gothic.weather.snow(planned * self.outside)
        over = now - self.started >= self.rise + self.hold + self.fall
        return not (over or (self.ending is not None and now - self.ending[0] >= 4.0))


_current = None


def snow(rise=60.0, hold=90.0, fall=40.0, peak=1.0):
    """Begin a snowfall; replaces one that is falling."""
    global _current
    _current = Snowfall(rise, hold, fall, peak)


def stop():
    if _current is not None and _current.started is not None:
        now = time.monotonic()
        level = density_at(now - _current.started, _current.rise, _current.hold, _current.fall, _current.peak)
        _current.ending = (now, level)


def _tick(_dt):
    global _current
    import gothic
    if _current is None:
        return
    try:
        if not _current.tick(gothic, time.monotonic()):
            _current = None
            gothic.weather.snow(0.0)
            _restore(gothic)
    except RuntimeError:
        _current = None     # no world while loading; the new world starts without snow


def _restore(gothic):
    """After a snowfall in the world: it melts, and the weather from before comes back."""
    if not hasattr(gothic.weather, "set"):
        return
    from dm import climate, story
    gothic.weather.cover(0.0, 900.0)
    owned = story.state().get("weather")
    hour, minute = gothic.world.time
    if owned and climate.story_weather(story.state(), gothic.world.day * 24 + hour + minute / 60.0):
        gothic.weather.set(owned["kind"], owned.get("intensity", 1.0), 20.0, tuple(owned.get("wind", (0, 0))))
    else:
        gothic.weather.set("clear", 0.0, 20.0, (0, 0))
    climate.forget()   # the climate sets its front again on its next look


def start_ticking():
    """Safe to call repeatedly."""
    import gothic
    if getattr(gothic, "_dm_weather_registered", False):
        return
    gothic.on_tick(lambda dt: sys.modules["dm.weather"]._tick(dt))
    gothic._dm_weather_registered = True

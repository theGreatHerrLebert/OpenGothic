"""Seeking shelter (docs/plan-weather.md): in heavy rain, or under a fire rain, people near the hero leave the open for
the nearest roof, wait there, and go back to what they did once it has passed. Guards stay at their posts.

Nothing to call: it looks every two seconds. It never touches anyone's routine: it queues a run to a covered waypoint
and some waiting there (npc.shelter_at), and more waiting while it rains. A fight, a talk or any perception clears the
queue as it always does; when the waiting runs out, his own routine walks him back. A save keeps the queue: after a
load he waits out what is left and goes home.
"""

import math
import sys

LOOK = 2.0
NEAR = 4000.0          # cm: people this close to the hero take shelter
DROP = 6000.0          # cm: further than this, he is left to finish his waiting alone
SEARCH = 2000.0        # cm: how far one looks for a roof
RAIN_FROM, FIRE_FROM, DRY_UNDER = 0.5, 0.3, 0.15
DRY_FOR = 30.0         # seconds it must have stopped before nobody is sent any more and nobody waits longer
NOTICE = (0.0, 20.0)   # seconds before each one notices
WAIT = 25.0            # seconds of waiting queued at a time
SEARCHES = 3           # per look, at most
RETRY = 30.0           # seconds before one who found no roof looks again
MAX_SHELTER = 900.0    # seconds: after a quarter hour he gives up and goes back
GIL_SEPERATOR_HUM = 16
HARDY = ("BAU", "SLD")  # one in five of these does not bother
# What people do when they may be sent: standing about, talking, eating, sweeping, practising. Not guards, not anyone
# working at something, sitting, walking somewhere, fighting or talking with the hero.
# (The names are the game's own ZS_ states, checked against its scripts.)
STATES = {"ZS_STAND_ARMSCROSSED", "ZS_STAND_WP", "ZS_STAND_EATING", "ZS_STAND_DRINKING", "ZS_SMALLTALK",
          "ZS_SWEEP_FP", "ZS_STAND_SWEEPING", "ZS_PRACTICE_SWORD", "ZS_PRACTICE_MAGIC", "ZS_PICK_FP", "ZS_PEE",
          "ZS_WATCHFIGHT", "ZS_STOMP_HERB", "ZS_WASH_FP", "ZS_SMOKE_JOINT"}

_state = {"world": None, "dry_since": None, "storm": False}
_noticed = {}     # key -> when he goes
_failed = {}      # key -> when he may look again
_sheltered = {}   # key -> {"npc", "wp", "pos", "since"}


def _reset():
    _noticed.clear()
    _failed.clear()
    _sheltered.clear()
    _state["dry_since"] = None
    _state["storm"] = False


def wetness(state):
    """How much it comes down that people flee: rain or a fire rain, 0 when it does not count."""
    kind, falling = state.get("kind"), state.get("falling", 0.0)
    if kind == "rain" and falling > RAIN_FROM:
        return falling
    if kind == "fire" and falling > FIRE_FROM:
        return falling
    return 0.0


def _cast():
    """Who an active story uses: they are left alone."""
    story = sys.modules.get("dm.story")
    if story is None or getattr(story, "_story", None) is None:
        return set()
    out = set()
    for s in story._story.state.get("stories", {}).values():
        if s.get("ended") is None:
            out.update(c.upper() for c in s.get("cast", []))
    return out


def _free(gothic, npc, cast):
    """Not taken by anything else: his ordinary state, no talk with the hero, no story holding or using him."""
    instance = (getattr(npc, "instance", "") or "").upper()
    if instance in cast or getattr(npc, "routine_held", False) or getattr(npc, "state", None) not in STATES:
        return False
    partner = gothic.dialog.partner()
    return partner is None or getattr(partner, "key", None) != npc.key


ON_DUTY = ("MIL", "PAL")   # they leave their post only when off duty
OFF_DUTY = {"ZS_STAND_DRINKING", "ZS_STAND_EATING", "ZS_SMALLTALK", "ZS_WATCHFIGHT", "ZS_PEE"}


def eligible(gothic, npc, cast):
    instance = (getattr(npc, "instance", "") or "").upper()
    if instance.split("_")[0] in ON_DUTY and getattr(npc, "state", None) not in OFF_DUTY:
        return False
    if not instance or instance.startswith("PC_") or instance in cast:
        return False
    if getattr(npc, "guild", 0) > GIL_SEPERATOR_HUM or not getattr(npc, "alive", True):
        return False
    if getattr(npc, "routine_held", False) or getattr(npc, "ai_queue", 0) != 0:
        return False   # a story holds him, or he is on his way somewhere or doing something
    if not _free(gothic, npc, cast):
        return False
    x, y, z = npc.position
    if gothic.weather.roof_at(x, z) > y + 250.0:
        return False   # under a roof already
    if instance.split("_")[0] in HARDY and npc.key % 5 == 0:
        return False
    return True


def tick(gothic, now, rng):
    if not hasattr(gothic.world, "shelter_points"):
        return None
    world = getattr(gothic.world, "generation", None)
    if world != _state["world"]:   # a load or a new world: what was queued there runs out by itself
        _state["world"] = world
        _reset()
    state = gothic.weather.state()
    wet = wetness(state)
    # it starts when it pours, and lasts until it has hardly fallen for half a minute: lighter rain keeps them in
    still = state.get("kind") in ("rain", "fire") and state.get("falling", 0.0) > DRY_UNDER
    if wet > 0.0 or (still and _state.get("storm")):
        _state["dry_since"] = None
        _state["storm"] = True
    elif _state["dry_since"] is None:
        _state["dry_since"] = now
    raining = _state.get("storm", False) and (_state["dry_since"] is None or now - _state["dry_since"] < DRY_FOR)
    if not raining:
        _state["storm"] = False
    hx, hy, hz = gothic.player.position
    sent = []

    # those under cover: more waiting while it rains, else let them go
    cast = _cast()
    for nid, s in list(_sheltered.items()):
        npc = s["npc"]
        try:
            pos, queue, alive = npc.position, npc.ai_queue, npc.alive
        except (RuntimeError, AttributeError):
            del _sheltered[nid]
            continue
        far = math.dist(pos, (hx, hy, hz)) > DROP
        there = math.dist(pos, s["pos"]) < 300.0
        if not alive or far:
            del _sheltered[nid]
            continue
        if queue == 0 and not there:
            del _sheltered[nid]                 # something else took him: a fight, a talk; leave him be a while
            _failed[nid] = now + 120.0
            continue
        if not _free(gothic, npc, cast):
            del _sheltered[nid]                 # a talk, a fight, a story took him: never hold that up
            _failed[nid] = now + 120.0
            continue
        if raining and now - s["since"] < MAX_SHELTER and queue <= 1 and there:
            npc.wait_more(WAIT)
        elif queue == 0:
            del _sheltered[nid]                 # done waiting: his routine has him again
            _failed[nid] = now + 60.0

    if not raining or wet <= 0.0:
        _noticed.clear()
        return sent

    taken = [s["wp"] for s in _sheltered.values()]
    searches = 0
    for npc in gothic.world.npcs_near(NEAR):
        nid = npc.key
        if nid in _sheltered or _failed.get(nid, 0.0) > now or not eligible(gothic, npc, cast):
            continue
        if nid not in _noticed:
            _noticed[nid] = now + rng.uniform(*NOTICE)
            continue
        if now < _noticed[nid] or searches >= SEARCHES:
            continue
        searches += 1
        x, y, z = npc.position
        for name, px, py, pz in gothic.world.shelter_points(x, y, z, SEARCH, taken)[:3]:
            if npc.can_reach(name) and npc.shelter_at(name, WAIT, True):
                _sheltered[nid] = {"npc": npc, "wp": name, "pos": (px, py, pz), "since": now}
                taken.append(name)
                sent.append((npc.instance, name))
                break
        else:
            _failed[nid] = now + RETRY
        _noticed.pop(nid, None)
    return sent


_next_look = 0.0


def _tick(_dt):
    global _next_look
    import random
    import time
    import gothic
    now = time.monotonic()
    if now < _next_look:
        return
    _next_look = now + LOOK
    try:
        gothic.world.day
        gothic.player.position
    except (RuntimeError, AttributeError):
        return
    tick(gothic, now, random)


def start():
    import gothic
    if getattr(gothic, "_dm_shelter_registered", False):
        return
    gothic.on_tick(lambda dt: sys.modules["dm.shelter"]._tick(dt))
    gothic._dm_shelter_registered = True

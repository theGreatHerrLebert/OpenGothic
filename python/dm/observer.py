"""Turns polled game state into a stream of discrete story-relevant events.

Polling compares snapshots once a second, so only changes are recorded. The
baseline is rebuilt after every world load: a loaded save is a new starting
point, not something the player just did.

    import dm.observer as obs
    obs.start()
    obs.recent(20)

Events are appended to python/dm_runtime/events.jsonl.

Timelines: loading an older save throws away what happened since, but the log keeps it. So every event carries the
timeline it happened in ("tl"). A save remembers its timeline and how far it had got; loading it starts a new
timeline branching off there. recent() and branch_filter() give only what happened on the way to the game being
played now, so an author never builds on a deed the player has undone.
"""

import collections
import json
import pathlib
import uuid

import gothic

POLL_MS = 1000
SETTLE_POLLS = 3    # polls at one waypoint before counting as having arrived
NEAR_RADIUS = 1500  # world units; 100 units is about one metre
ITEM_QUIET_POLLS = 5      # item changes merge until this many quiet polls pass
NEAR_COOLDOWN_POLLS = 300 # an NPC must be out of range this long to count again

RUNTIME_DIR = pathlib.Path(__file__).resolve().parent.parent / "dm_runtime"
LOG_PATH = RUNTIME_DIR / "events.jsonl"
TIMELINES_PATH = RUNTIME_DIR / "timelines.json"   # {timeline: {"parent": timeline or None, "at": seq or None}}
SAVES_DIR = RUNTIME_DIR / "saves"                 # <slot>.timeline.json: the timeline a save belongs to, and where


def _read_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(value), encoding="utf-8")
    tmp.replace(path)


def place_of(waypoint):
    """Group a waypoint name into a place, e.g. NW_XARDAS_TOWER_IN1_02 -> XARDAS_TOWER."""
    tokens = waypoint.split("_")
    if tokens and tokens[0] in ("NW", "OW", "ADW", "DRAGON"):
        tokens = tokens[1:]
    kept = []
    for token in tokens:
        if len(kept) == 2 or any(c.isdigit() for c in token):
            break
        kept.append(token)
    return "_".join(kept) or waypoint


def _item_counts():
    counts = collections.Counter()
    for it in gothic.player.items:
        counts[it["instance"]] += it["count"]
    return counts


def _npc_ref(npc):
    return {"instance": npc.instance, "name": npc.name}


class Observer:
    def __init__(self):
        self.events = collections.deque(maxlen=2000)
        self.seq = 0
        self.elapsed = 0
        self.generation = None
        self.base = None
        self.timeline = None

    # ---- timelines ----

    def _begin_timeline(self, parent=None, at=None):
        """A new timeline, branching off parent after event seq at, or a fresh one (a new game, an unknown save)."""
        self.timeline = uuid.uuid4().hex[:12]
        known = _read_json(TIMELINES_PATH, {})
        known[self.timeline] = {"parent": parent, "at": at}
        _write_json(TIMELINES_PATH, known)

    def on_save(self, slot):
        if self.timeline is None:
            self._begin_timeline()
        self._flush_items()
        _write_json(SAVES_DIR / f"{slot}.timeline.json", {"timeline": self.timeline, "seq": self.seq})

    def on_load(self, slot):
        """The game goes back to a save: what happened after it, in any timeline, is no longer this game's past."""
        mark = _read_json(SAVES_DIR / f"{slot}.timeline.json", None)
        if mark is None:
            self._begin_timeline()          # a save from before timelines: its past is unknown, not wrong
        else:
            self._begin_timeline(mark["timeline"], mark["seq"])

    def on_new_game(self):
        self._begin_timeline()

    def branch(self):
        """{timeline: the last seq of it that leads here (None: all of it)} for the game played now."""
        if self.timeline is None:
            return {}
        known = _read_json(TIMELINES_PATH, {})
        chain, current, limit = {}, self.timeline, None
        while current is not None and current not in chain:
            chain[current] = limit
            entry = known.get(current) or {}
            current, limit = entry.get("parent"), entry.get("at")
        return chain

    def on_branch(self, event, chain=None):
        chain = self.branch() if chain is None else chain
        tl = event.get("tl")
        if tl not in chain:
            return False   # another timeline, or an event from before timelines were kept
        limit = chain[tl]
        return limit is None or event.get("seq", 0) <= limit

    def _emit(self, kind, **data):
        if self.timeline is None:
            self._begin_timeline()
        self.seq += 1
        hour, minute = gothic.world.time
        event = {"seq": self.seq, "tl": self.timeline, "day": gothic.world.day, "hour": hour,
                 "minute": minute, "type": kind, **data}
        self.events.append(event)
        RUNTIME_DIR.mkdir(exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")

    def _snapshot(self):
        near = {}
        for npc in gothic.world.npcs_near(NEAR_RADIUS):
            near[npc.instance] = npc
        partner = gothic.dialog.partner()
        return {
            "day": gothic.world.day,
            "room": gothic.player.room,
            "waypoint": gothic.player.waypoint,
            "items": _item_counts(),
            "near": near,
            "alive": {k for k, n in near.items() if n.alive},
            "partner": partner,
            "partner_key": partner.instance if partner else None,
            "down": not gothic.player.alive,
        }

    def _reset(self, snap):
        self.base = snap
        self.place = place_of(snap["waypoint"])
        self.settling = self.place
        self.settle_count = 0
        self.polls = 0
        self.item_delta = collections.Counter()
        self.item_quiet = 0
        self.last_near = {key: 0 for key in snap["near"]}

    def poll(self):
        generation = gothic.world.generation
        snap = self._snapshot()
        if generation != self.generation or self.base is None:
            self.generation = generation
            if self.base is not None:
                self._flush_items()
            self._reset(snap)
            self._emit("world_loaded", waypoint=snap["waypoint"])
            return
        self.polls += 1
        self._diff(self.base, snap)
        self.base = snap

    def _diff(self, old, new):
        if new["day"] != old["day"]:
            self._emit("day_changed", day=new["day"])

        if new["room"] != old["room"]:
            if old["room"]:
                self._emit("room_left", room=old["room"])
            if new["room"]:
                self._emit("room_entered", room=new["room"])

        self._track_place(place_of(new["waypoint"]))
        self._track_items(old, new)

        if new["partner_key"] != old["partner_key"]:
            self._flush_items()
            if old["partner_key"]:
                self._emit("talk_ended", instance=old["partner_key"])
            if new["partner"]:
                self._emit("talk_started", **_npc_ref(new["partner"]))

        self._track_near(new)

        for instance in old["alive"] - new["alive"]:
            if instance in new["near"]:
                self._emit("npc_down", **_npc_ref(new["near"][instance]))

        if new["down"] and not old["down"]:
            self._emit("player_down")

    def _track_place(self, place):
        if place != self.settling:
            self.settling = place
            self.settle_count = 0
            return
        self.settle_count += 1
        if self.settle_count >= SETTLE_POLLS and place != self.place:
            self.place = place
            self._emit("place_entered", place=place)

    def _track_items(self, old, new):
        changed = False
        for instance in set(old["items"]) | set(new["items"]):
            delta = new["items"][instance] - old["items"][instance]
            if delta:
                self.item_delta[instance] += delta
                changed = True
        self.item_quiet = 0 if changed else self.item_quiet + 1
        if self.item_quiet >= ITEM_QUIET_POLLS:
            self._flush_items()

    def _flush_items(self):
        gained = {k: v for k, v in self.item_delta.items() if v > 0}
        lost = {k: -v for k, v in self.item_delta.items() if v < 0}
        self.item_delta.clear()
        if gained:
            self._emit("items_gained", items=gained)
        if lost:
            self._emit("items_lost", items=lost)

    def _track_near(self, new):
        for instance, npc in new["near"].items():
            last = self.last_near.get(instance)
            if npc.alive and (last is None or self.polls - last >= NEAR_COOLDOWN_POLLS):
                self._emit("npc_near", **_npc_ref(npc))
            self.last_near[instance] = self.polls

    def on_tick(self, dt):
        self.elapsed += dt
        if self.elapsed < POLL_MS:
            return
        self.elapsed = 0
        try:
            self.poll()
        except RuntimeError:
            # no active world or player while loading
            self.base = None


_observer = Observer()


def _dispatch(dt):
    _observer.on_tick(dt)


def _module():
    return __import__("dm.observer").observer


def start():
    """Begin observing. Safe to call repeatedly and after gothic.reload."""
    if not getattr(gothic, "_dm_observer_registered", False):
        gothic.on_tick(lambda dt: _module()._dispatch(dt))
        gothic._save_callbacks.append(lambda slot: _module()._observer.on_save(slot))
        gothic._load_callbacks.append(lambda slot: _module()._observer.on_load(slot))
        gothic._new_game_callbacks.append(lambda world: _module()._observer.on_new_game())
        gothic._dm_observer_registered = True


def recent(n=20):
    """The last n events of the game played now: none from a timeline a load has left behind."""
    chain = _observer.branch()
    return [e for e in _observer.events if _observer.on_branch(e, chain)][-n:]


def branch_filter():
    """A test for events read from the log: True for those on the way to the game played now."""
    chain = _observer.branch()
    return lambda event: _observer.on_branch(event, chain)

"""Turns polled game state into a stream of discrete story-relevant events.

Polling compares snapshots once a second, so only changes are recorded. The
baseline is rebuilt after every world load: a loaded save is a new starting
point, not something the player just did.

    import dm.observer as obs
    obs.start()
    obs.recent(20)

Events are appended to python/dm_runtime/events.jsonl.
"""

import collections
import json
import pathlib

import gothic

POLL_MS = 1000
SETTLE_POLLS = 3    # polls at one waypoint before counting as having arrived
NEAR_RADIUS = 1500  # world units; 100 units is about one metre

RUNTIME_DIR = pathlib.Path(__file__).resolve().parent.parent / "dm_runtime"
LOG_PATH = RUNTIME_DIR / "events.jsonl"


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

    def _emit(self, kind, **data):
        self.seq += 1
        hour, minute = gothic.world.time
        event = {"seq": self.seq, "day": gothic.world.day, "hour": hour,
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
        self.arrived = snap["waypoint"]
        self.settling = snap["waypoint"]
        self.settle_count = 0

    def poll(self):
        generation = gothic.world.generation
        snap = self._snapshot()
        if generation != self.generation or self.base is None:
            self.generation = generation
            self._reset(snap)
            self._emit("world_loaded", waypoint=snap["waypoint"])
            return
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

        self._track_arrival(new["waypoint"])

        if new["partner_key"] != old["partner_key"]:
            if old["partner_key"]:
                self._emit("talk_ended", instance=old["partner_key"])
            if new["partner"]:
                self._emit("talk_started", **_npc_ref(new["partner"]))

        for instance in set(old["items"]) | set(new["items"]):
            delta = new["items"][instance] - old["items"][instance]
            if delta > 0:
                self._emit("item_gained", instance=instance, count=delta)
            elif delta < 0:
                self._emit("item_lost", instance=instance, count=-delta)

        for instance in new["alive"] - old["alive"]:
            if instance not in old["near"]:
                self._emit("npc_near", **_npc_ref(new["near"][instance]))

        for instance in old["alive"] - new["alive"]:
            if instance in new["near"]:
                self._emit("npc_down", **_npc_ref(new["near"][instance]))

        if new["down"] and not old["down"]:
            self._emit("player_down")

    def _track_arrival(self, waypoint):
        if waypoint != self.settling:
            self.settling = waypoint
            self.settle_count = 0
            return
        self.settle_count += 1
        if self.settle_count >= SETTLE_POLLS and waypoint != self.arrived:
            self.arrived = waypoint
            self._emit("arrived", waypoint=waypoint)

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


def start():
    """Begin observing. Safe to call repeatedly and after gothic.reload."""
    if not getattr(gothic, "_dm_observer_registered", False):
        gothic.on_tick(lambda dt: __import__("dm.observer").observer._dispatch(dt))
        gothic._dm_observer_registered = True


def recent(n=20):
    return list(_observer.events)[-n:]

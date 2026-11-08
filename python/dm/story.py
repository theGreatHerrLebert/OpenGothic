"""Typed story operations, all-or-nothing plans, and the persistent story log.

A plan is a list of operations. It is validated as a whole against a copy of the
story state, then applied at a safe point in the game loop. If anything fails,
nothing is kept.

The savegame already stores world changes, such as placed items and removed
NPCs. Loading therefore rebuilds only story state from the log and never
re-applies world effects.

    import dm.story as story
    story.start()
    story.submit("Der Novize verschwindet", [
        {"op": "commit_fact", "id": "culprit", "text": "...", "known_by": []},
        {"op": "do_nothing", "reason": "wait until nightfall"},
    ])
"""

import copy
import json
import os
import pathlib

import gothic

from dm import graph as graphs

RUNTIME_DIR = pathlib.Path(__file__).resolve().parent.parent / "dm_runtime"
SAVES_DIR = RUNTIME_DIR / "saves"

# NPCs the original scripts do not depend on. Filled from the dependency map;
# an NPC outside this set cannot be removed by a story.
SAFE_TO_REMOVE = set()


class PlanError(Exception):
    pass


def empty_state():
    return {"facts": {}, "flags": {}, "removed": [], "graphs": {}}


def _require(args, *keys):
    for key in keys:
        if key not in args:
            raise PlanError(f"missing field: {key}")


def _npc_instance(name):
    if gothic.world.instance_kind(name) != "npc":
        raise PlanError(f"not an NPC instance: {name}")
    return name.upper()


def _live_npc(name):
    npc = gothic.world.find_npc(name)
    if npc is None:
        raise PlanError(f"NPC is not in this world: {name}")
    return npc


# Each operation has:
#   check(args, state)  raises PlanError if the operation is not allowed
#   fold(args, state)   the pure change to story state
#   world(args)         optional side effect, returning an undo function or None

def _check_fact(args, state):
    _require(args, "id", "text")
    if args["id"] in state["facts"]:
        raise PlanError(f"fact already committed: {args['id']}")
    for name in args.get("known_by", []):
        _npc_instance(name)


def _fold_fact(args, state):
    state["facts"][args["id"]] = {
        "text": args["text"],
        "known_by": [n.upper() for n in args.get("known_by", [])],
    }


def _check_remove(args, state):
    _require(args, "instance")
    name = _npc_instance(args["instance"])
    if name not in SAFE_TO_REMOVE:
        raise PlanError(f"NPC is not on the safe list: {name}")
    if name in state["removed"]:
        raise PlanError(f"NPC already removed: {name}")
    _live_npc(name)


def _fold_remove(args, state):
    state["removed"].append(args["instance"].upper())


def _world_remove(args):
    gothic.world.remove_npc(_live_npc(args["instance"]))
    return None


def _check_place(args, state):
    _require(args, "instance", "waypoint")
    if gothic.world.instance_kind(args["instance"]) != "item":
        raise PlanError(f"not an item instance: {args['instance']}")
    if not gothic.world.has_waypoint(args["waypoint"]):
        raise PlanError(f"no such waypoint: {args['waypoint']}")


def _world_place(args):
    return gothic.world.place_item(args["instance"], args["waypoint"]).remove


def _check_graph(args, state):
    _require(args, "npc", "graph")
    name = _npc_instance(args["npc"])
    _live_npc(name)
    if name in state["removed"]:
        raise PlanError(f"NPC has been removed: {name}")
    problem = graphs.validate(args["graph"])
    if problem:
        raise PlanError(f"bad dialogue graph: {problem}")


def _fold_graph(args, state):
    state["graphs"][args["npc"].upper()] = args["graph"]


def _world_graph(args):
    npc = _live_npc(args["npc"])
    gothic.dialog.bind(npc)
    return lambda: gothic.dialog.unbind(npc)


def _check_flag(args, state):
    _require(args, "name", "value")


def _fold_flag(args, state):
    state["flags"][args["name"]] = args["value"]


def _check_nothing(args, state):
    _require(args, "reason")


def _noop(args, state):
    pass


OPS = {
    "commit_fact": (_check_fact, _fold_fact, None),
    "remove_npc": (_check_remove, _fold_remove, _world_remove),
    "place_item": (_check_place, _noop, _world_place),
    "attach_dialogue_graph": (_check_graph, _fold_graph, _world_graph),
    "set_flag": (_check_flag, _fold_flag, None),
    "do_nothing": (_check_nothing, _noop, None),
}

# Removal cannot be undone, so it runs after everything that can.
_LAST = {"remove_npc"}


class Story:
    def __init__(self):
        self.state = empty_state()
        self.log = []
        self.queue = []
        self.results = []
        self.generation = None

    def validate(self, ops):
        """Raise PlanError unless the whole plan is acceptable."""
        if not ops:
            raise PlanError("empty plan")
        scratch = copy.deepcopy(self.state)
        for op in ops:
            name = op.get("op")
            if name not in OPS:
                raise PlanError(f"unknown operation: {name}")
            check, fold, _ = OPS[name]
            check(op, scratch)
            fold(op, scratch)

    def submit(self, reason, ops):
        """Validate now and queue for the next safe point."""
        self.validate(ops)
        self.queue.append({"reason": reason, "ops": ops})

    def apply_plan(self, plan):
        # State may have moved on since the plan was queued.
        self.validate(plan["ops"])
        ordered = sorted(plan["ops"], key=lambda op: op["op"] in _LAST)
        undo = []
        try:
            for op in ordered:
                effect = OPS[op["op"]][2]
                if effect is not None:
                    revert = effect(op)
                    if revert is not None:
                        undo.append(revert)
        except Exception:
            for revert in reversed(undo):
                revert()
            raise

        hour, minute = gothic.world.time
        entry = {"seq": len(self.log) + 1, "day": gothic.world.day, "hour": hour,
                 "minute": minute, "reason": plan["reason"], "ops": plan["ops"]}
        self.log.append(entry)
        self._fold(entry)

    def _fold(self, entry):
        for op in entry["ops"]:
            OPS[op["op"]][1](op, self.state)

    def player_flag(self, name, value=True):
        """Record a flag set by play, such as a dialogue node being reached."""
        hour, minute = gothic.world.time
        entry = {"seq": len(self.log) + 1, "day": gothic.world.day, "hour": hour,
                 "minute": minute, "reason": "player",
                 "ops": [{"op": "set_flag", "name": name, "value": value}]}
        self.log.append(entry)
        self._fold(entry)

    # ---- persistence ----

    def reset(self):
        self.__init__()

    def save(self, slot):
        SAVES_DIR.mkdir(parents=True, exist_ok=True)
        path = SAVES_DIR / f"{slot}.story.jsonl"
        tmp = path.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            for entry in self.log:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        os.replace(tmp, path)

    def load(self, slot):
        self.reset()
        path = SAVES_DIR / f"{slot}.story.jsonl"
        if not path.exists():
            return
        with path.open(encoding="utf-8") as f:
            for line in f:
                entry = json.loads(line)
                self.log.append(entry)
                self._fold(entry)

    # ---- game loop ----

    def rebind(self):
        """NPC handles do not survive a world load; attach graphs again."""
        for instance in self.state["graphs"]:
            npc = gothic.world.find_npc(instance)
            if npc is not None:
                gothic.dialog.bind(npc)

    def on_tick(self):
        generation = gothic.world.generation
        if generation != self.generation:
            self.generation = generation
            self.rebind()

        if gothic.dialog.partner() is None and self.queue:
            plan = self.queue.pop(0)
            try:
                self.apply_plan(plan)
                self.results.append({"reason": plan["reason"], "ok": True})
            except (PlanError, RuntimeError, ValueError) as err:
                self.results.append({"reason": plan["reason"], "ok": False,
                                     "error": str(err)})


_story = Story()
_player = graphs.Player(lambda: _story.state["graphs"],
                        lambda name: _story.player_flag(name))


def _tick(dt):
    try:
        _story.on_tick()
        _player.on_tick()
    except RuntimeError:
        pass  # no active world while loading


def start():
    """Safe to call repeatedly."""
    if getattr(gothic, "_dm_story_registered", False):
        return
    module = "dm.story"
    gothic.on_tick(lambda dt: _module(module)._tick(dt))
    gothic._save_callbacks.append(lambda slot: _module(module)._story.save(slot))
    gothic._load_callbacks.append(lambda slot: _module(module)._story.load(slot))
    gothic._new_game_callbacks.append(lambda world: _module(module)._story.reset())
    gothic._dm_story_registered = True


def _module(name):
    import sys
    return sys.modules[name]


def submit(reason, ops):
    _story.submit(reason, ops)


def state():
    return _story.state


def results():
    return list(_story.results)

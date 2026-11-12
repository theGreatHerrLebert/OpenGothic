"""The playability audit itself: one story checked against the game, and the search for its reachable endings."""

import json
import math
import re

from playability_game import (ASLEEP, CHAPTER, FALSE, MAYBE, QUEST_STATE, STATE_ACTIVITY, TRUE, WORLD, hour_window,
                              minutes, spans, t_or)
from playability_story import _checks_with_polarity, _choices, _list, _unique, describe


class Audit:
    def __init__(self, story, game, others=()):
        self.story, self.game, self.others = story, game, list(others)
        self.blockers, self.caveats = [], []
        self._sources = {}

    def sources(self, item):
        if item not in self._sources:
            rank = {TRUE: 0, MAYBE: 1, FALSE: 2}
            self._sources[item] = sorted(self.game.item_sources(item), key=lambda x: rank[x["reach"]])
        return self._sources[item]

    def made_by_story(self, item):
        out = []
        for name, waypoint, parent in self.story.placed:
            if name == item:
                out.append(f"placed by the story at {waypoint}" + (f" ({describe(parent)})" if parent else ""))
        for name, count, parent in self.story.given:
            if name == item:
                out.append(f"given by the story ({count}x, {describe(parent) if parent else 'at start'})")
        return out

    def run(self):
        s = self.story
        report = {"story": s.name, "title": s.title}
        report["items"] = self.items()
        self.waiting_rules()
        report["quests"] = self.quests()
        report["heard"] = self.heard()
        report["people"] = self.people()
        report["objects"] = self.objects()
        report["placed"] = self.placed()
        report["renamed"] = [{"npc": n, "name": name, "was": (self.game.people.get(n) or {}).get("name")}
                             for n, name in s.renamed]
        # attached conversations hide the NPC's own
        report["attached"] = self.attached(report["quests"], report["heard"])
        report["endings"] = self.endings(report["quests"], report["heard"])
        report["shared"] = self.shared()
        report["blockers"], report["caveats"] = _unique(self.blockers), _unique(self.caveats)
        report["verdict"] = ("blocked" if report["blockers"] else "playable with caveats" if report["caveats"]
                             else "playable end to end")
        return report

    # -------------------------------------------------------- 1. items

    def items(self):
        """Every item the story needs, with every source the game or the story itself has for it."""
        g, out = self.game, []
        for item, uses in sorted(self.story.item_needs().items()):
            sources = self.sources(item)
            story_made = self.made_by_story(item)
            reach = t_or([x["reach"] for x in sources] + ([TRUE] if story_made else []))
            entry = {"item": item, "name": g.items.get(item, {}).get("name"), "known": item in g.items or not g.items,
                     "uses": uses, "sources": sources, "story": story_made, "reach": reach}
            out.append(entry)
            if not entry["known"]:
                self.blockers.append(f"item {item} does not exist in the game")
            elif reach == FALSE or not (sources or story_made):
                self.blockers.append(f"item {item} has no source a guildless hero can reach in chapter 1 "
                                     f"({'; '.join(uses[:2])})")
            elif reach == MAYBE and not any(x["reach"] == TRUE for x in sources) and not story_made:
                self.caveats.append(f"item {item}: only conditional sources ({sources[0]['text']})")
        return out

    def waiting_rules(self):
        """A rule that waits for a story's own item also fires on every other copy."""
        s, waiting = self.story, {}
        for c in s.containers:
            on = c.get("on") or {}
            item = (on.get("item") or "").upper()
            if on.get("event") == "took_item" and any(name == item for name, _, _ in s.placed):
                waiting.setdefault(item, []).append(c["id"])
        for item, rules in waiting.items():
            elsewhere = [x for x in self.sources(item) if x["reach"] != FALSE]
            if elsewhere:
                self.caveats.append(f"rule(s) {', '.join(rules)} wait for taking {item}, which the game also has "
                                    f"elsewhere ({elsewhere[0]['text'][:90]}); taking any copy fires them")

    # -------------------------------------------------------- 2. quests

    def quests(self):
        out, by_key = [], {}
        for check, positive, where, _, _ in self.story.checks_of("quest"):
            key = (check["quest"].upper(), check["state"], positive)
            if key in by_key:
                if where not in by_key[key]["where"]:
                    by_key[key]["where"].append(where)
                continue
            by_key[key] = entry = self._quest(*key, where)
            out.append(entry)
        return out

    def _quest(self, var, state, positive, where):
        g = self.game
        constant = QUEST_STATE.get(state)
        if constant is None:
            reach, setters = TRUE, []
        else:
            reach, setters = g.quest_reachable(var, constant)
        started, starters = g.quest_reachable(var, "LOG_RUNNING")
        exists = any(var in q.get("variables", []) for q in g.quests.values()) or bool(setters or starters)
        entry = {"quest": var, "state": state, "positive": positive, "where": [where], "reach": reach,
                 "exists": exists, "setters": _dedupe(setters), "starters": _dedupe(starters), "started": started}
        if not exists:
            self.blockers.append(f"quest variable {var} does not exist")
        elif positive and reach == FALSE:
            self.caveats.append(f"quest {var} can never be {state} in chapter {CHAPTER} without a guild; "
                                f"the check on {where} is a dead option")
        return entry

    # -------------------------------------------------------- 3. topics heard

    def heard(self):
        out, by_info = [], {}
        for check, positive, where, _, _ in self.story.checks_of("heard"):
            key = (check["info"].upper(), positive)
            if key in by_info:
                if where not in by_info[key]["where"]:
                    by_info[key]["where"].append(where)
                continue
            by_info[key] = entry = self._topic(*key, where)
            out.append(entry)
        return out

    def _topic(self, did, positive, where):
        g = self.game
        d = g.dialogues.get(did)
        reach, why = g.dialogue_reachable(did)
        entry = {"info": did, "where": [where], "positive": positive, "exists": d is not None, "reach": reach,
                 "why": why}
        if d:
            entry["npc"] = d.get("npc")
            entry["important"] = not d.get("description")
            entry["condition"] = [e.get("if", []) for e in (d.get("condition") or {}).get("effects", [])
                                  if e.get("return") not in ("FALSE", "0")]
            entry["needs"] = sorted(set(re.findall(r'NPC_KNOWSINFO\(\w+, (\w+)\)', json.dumps(entry["condition"]))))
        if positive and d is None:
            self.blockers.append(f"topic {did} does not exist ({where})")
        elif positive and reach == FALSE:
            self.blockers.append(f"topic {did} cannot be heard in chapter 1 without a guild: {why}")
        return entry

    # -------------------------------------------------------- 4. people and hours

    def windows(self):
        """npc -> [(minutes, why)] the story needs him awake and around."""
        out = {}
        for c in self.story.containers:
            npc = c.get("npc")
            for check, positive in _checks_with_polarity(c["checks"]):
                if check["type"] == "hour" and positive and npc:
                    why = f"{describe(c)} {check['from']}-{check['to']}h"
                    out.setdefault(npc, []).append((hour_window(check), why))
            for key, node, choice in _choices(c):
                for check, positive in _checks_with_polarity(choice.get("checks")):
                    if check["type"] == "hour" and positive and npc:
                        out.setdefault(npc, []).append(
                            (hour_window(check), f"choice in {describe(c)} (node {key}) {check['from']}-{check['to']}h"))
        return out

    def availability(self, npc, window):
        entries = self.game.schedule(self.game.routine_of(npc))
        if not entries:
            return None
        awake, asleep, doing = set(), set(), []
        for start, end, activity, wp in entries:
            overlap = minutes(start, end) & window
            if not overlap:
                continue
            (asleep if activity in ASLEEP else awake).update(overlap)
            doing.append(f"{activity} at {wp} {spans(overlap)}")
        return {"awake": awake, "asleep": asleep, "doing": doing}

    def people(self):
        windows = self.windows()
        return [self._person(npc, roles, windows.get(npc, [])) for npc, roles in sorted(self.story.npcs.items())]

    def _person(self, npc, roles, windows):
        g = self.game
        present, where = g.presence(npc)
        entry = {"npc": npc, "label": g.label(npc), "roles": sorted(roles), "present": present, "where": where,
                 "routine": g.routine_of(npc), "day": g.places(npc), "windows": [],
                 "swaps": sorted({f"{r} via {d}" for r, d in g.swaps.get(g.instance(npc), [])})[:6]}
        if present == FALSE and roles - {"watcher"}:
            self.blockers.append(f"{g.label(npc)} is not in Khorinis in chapter 1 ({where})")
        for window, why in windows:
            entry["windows"].append(self._hour_window(npc, window, why))
        for check, positive, where_, c, _ in self.story.checks_of("npc_state"):
            if check["npc"].upper() != npc or not positive:
                continue
            activity = STATE_ACTIVITY.get(check["state"])
            if activity is None:
                continue          # a spell, a blow: the hero causes it himself
            entry["windows"].append(self._state_window(npc, check, activity, where_))
        return entry

    def _hour_window(self, npc, window, why):
        """Whether an NPC is awake through the hours the story needs him."""
        g = self.game
        found = self.availability(npc, window)
        if found is None:
            return {"why": why, "status": "unknown routine"}
        status = ("never awake then" if not found["awake"] else
                  "asleep part of the time" if found["asleep"] else "awake")
        if status == "never awake then":
            self.blockers.append(f"{g.label(npc)} sleeps through {why}")
        elif status != "awake":
            self.caveats.append(f"{g.label(npc)} sleeps {spans(found['asleep'])} inside {why}; "
                                f"usable only {spans(found['awake'])}")
        return {"why": why, "status": status, "awake": spans(found["awake"]), "asleep": spans(found["asleep"]),
                "doing": found["doing"]}

    def _state_window(self, npc, check, activity, where):
        """Whether an NPC's own routine ever puts him into the state a story's npc_state check waits for."""
        g = self.game
        hours = set()
        for start, end, act, wp in g.schedule(g.routine_of(npc)):
            if act == activity:
                hours |= minutes(start, end)
        others = [r for r in g.other_routines(npc) if any(a == activity for a, *_ in g.routines.get(r, []))]
        if not hours:
            self.blockers.append(f"{g.label(npc)} is never {check['state']} by his chapter-1 routine "
                                 f"({where})" + (f"; only in {', '.join(others)}" if others else ""))
        return {"why": f"{check['state']} on {where}", "status":
                "in his routine" if hours else "not in his chapter-1 routine",
                "awake": spans(hours), "doing": [f"only in {', '.join(others)}"] if others and not hours else []}

    # -------------------------------------------------------- 5. objects

    def objects(self):
        """Every object a rule waits for the hero to use, with the NPCs whose routines sit there."""
        out = []
        for c in self.story.containers:
            on = c.get("on") or {}
            if on.get("event") == "used_object" and on.get("near"):
                out.append(self._object(c, on))
        return out

    def _object(self, c, on):
        x, z, metres = on["near"]
        scheme = (on.get("object") or "").upper()
        target = self._nearest_object(x, z, metres, scheme)
        window = set(range(1440))
        for ch in _hour_checks(c["checks"]):
            window &= hour_window(ch)
        entry = {"rule": c["id"], "near": on["near"], "scheme": scheme or "any", "object": target,
                 "window": spans(window), "users": []}
        fills = [f for f in c["requires"] if self.story.setters_of(f)]
        entry["filled_by"] = sorted({describe(x) for f in fills for x in self.story.setters_of(f)})
        fill_hours = self._fill_hours(fills)
        entry["fill_hours"] = spans(fill_hours) if fill_hours else None
        if target is None:
            self.caveats.append(f"used_object {c['id']}: no known object within {metres} m of ({x}, {z})")
            return entry
        entry["users"] = self._object_users(target, window)
        self._judge_users(c, entry)
        return entry

    def _nearest_object(self, x, z, metres, scheme):
        """The known object of this scheme nearest (x, z), if it lies within the given metres."""
        candidates = [o for o in self.game.mobs if scheme in o[0]]
        if candidates:
            best = min(candidates, key=lambda o: (o[1] - x) ** 2 + (o[2] - z) ** 2)
            if math.hypot(best[1] - x, best[2] - z) <= metres * 100:
                return best
        return None

    def _fill_hours(self, fills):
        """The hours the conversations that set these flags can be held."""
        hours = set()
        for f in fills:
            for x in self.story.setters_of(f):
                found = _hour_checks(x["checks"])
                found += [ch for _, _, choice in _choices(x) for ch in _hour_checks(choice.get("checks"))]
                for ch in found:
                    hours |= hour_window(ch)
        return hours

    def _object_users(self, target, window):
        """NPCs whose routine, in this chapter or a later swap, puts them at this object."""
        g, out = self.game, []
        for npc in g.people:
            if g.presence(npc)[0] == FALSE:
                continue
            seen = set()
            for routine in [g.routine_of(npc)] + g.other_routines(npc):
                for start, end, activity, wp in g.schedule(routine):
                    if g.object_of(activity, wp) != target or (wp, start, end) in seen:
                        continue
                    seen.add((wp, start, end))     # another routine with the same hours adds nothing
                    chapter1 = routine == g.routine_of(npc)
                    via = [d for r, d in g.swaps.get(npc, []) if f"RTN_{r.upper()}_{g.npc_id(npc)}" == routine]
                    out.append({
                        "npc": npc, "label": g.label(npc), "routine": routine, "waypoint": wp,
                        "hours": spans(minutes(start, end)), "overlap": spans(minutes(start, end) & window),
                        "chapter1": chapter1,
                        "how": "chapter-1 routine" if chapter1 else
                        f"only in {routine}" + (f", set by {', '.join(sorted(set(via)))}" if via else "")})
        return out

    def _judge_users(self, c, entry):
        for user in entry["users"]:
            if user["overlap"] == "never":
                user["status"] = "no clash"
                continue
            if entry["filled_by"]:
                user["status"] = "resolved by reservation"
                self.caveats.append(f"{user['label']} smokes at the object of {c['id']} {user['overlap']} "
                                    f"({user['how']}); resolved by reservation once the story fills it")
            else:
                user["status"] = "conflict"
                self.caveats.append(f"{user['label']} occupies the object of {c['id']} {user['overlap']} "
                                    f"({user['how']}); the story never fills it, so nothing makes him get up")

    # -------------------------------------------------------- 6. made by the story

    def placed(self):
        g = self.game
        out = [{"item": i, "waypoint": w, "exists": (w or "").upper() in g.waypoints or not g.waypoints,
                "by": describe(p) if p else "at start"} for i, w, p in self.story.placed]
        for p in out:
            if not p["exists"]:
                self.blockers.append(f"place_item {p['item']}: no waypoint {p['waypoint']} in {WORLD}")
        return out

    # -------------------------------------------------------- attached conversations

    def attached(self, quests, heard):
        g = self.game
        needed = {}
        for h in heard:
            if h.get("npc"):
                needed.setdefault(h["npc"].upper(), []).append(h["info"])
        for q in quests:
            for setter in q["setters"] + q["starters"]:
                if setter.get("npc"):
                    needed.setdefault(setter["npc"].upper(), []).append(setter["by"])
        out, done = [], set()
        for c in self.story.containers:
            if c["kind"] != "graph" or c["npc"] in done:
                continue
            npc = c["npc"]
            done.add(npc)
            own = [d for d in g.npc_dialogues.get(g.instance(npc), []) if not d.endswith("_EXIT")
                   and "PICKPOCKET" not in d]
            clash = sorted(set(needed.get(npc, [])))
            out.append({"npc": npc, "own": len(own), "needed": clash})
            if clash:
                self.blockers.append(f"the story replaces {g.label(npc)}'s conversations, but needs his own "
                                     f"{', '.join(clash)}")
        return out

    # -------------------------------------------------------- endings

    def gate(self, check, npc, items):
        """(ok, why not) for one story check against the game, optimistic where the hero decides."""
        g, kind = self.game, check["type"]
        if kind in ("has_item", "wears"):
            item = check["item"].upper()
            ok = item in items or t_or(s["reach"] for s in self.sources(item)) != FALSE and bool(self.sources(item))
            return ok, None if ok else f"no source for {item}"
        if kind == "quest":
            constant = QUEST_STATE.get(check["state"])
            ok = constant is None or g.quest_reachable(check["quest"], constant)[0] != FALSE
            return ok, None if ok else f"{check['quest']} cannot reach {check['state']}"
        if kind == "heard":
            ok = g.dialogue_reachable(check["info"])[0] != FALSE
            return ok, None if ok else f"{check['info']} cannot be heard"
        if kind in ("npc_dead", "npc_state"):
            ok = g.presence(check["npc"])[0] != FALSE
            if ok and kind == "npc_state" and check["state"] in STATE_ACTIVITY:
                activity = STATE_ACTIVITY[check["state"]]
                ok = any(a == activity for _, _, a, _ in g.schedule(g.routine_of(check["npc"])))
            return ok, None if ok else f"{check['npc']} never {check.get('state', 'dies')}"
        if kind == "hour":
            if not npc:
                return True, None
            found = self.availability(npc, hour_window(check))
            ok = found is None or bool(found["awake"])
            return ok, None if ok else f"{npc} asleep {check['from']}-{check['to']}h"
        if kind == "any":
            results = [self.gate(c, npc, items) for c in check["checks"]]
            ok = any(r[0] for r in results)
            return ok, None if ok else "none of: " + "; ".join(r[1] for r in results if r[1])
        return True, None   # "not", guild, obsessed: the hero decides

    def endings(self, quests, heard):
        """Which of the story's promised endings the hero can reach, first in the story alone, then in the game."""
        _, ideal_active, _ = _Reach(self, real=False).run()
        real_flags, real_active, failing = _Reach(self, real=True).run()
        out = []
        for c, kind in self.story.endings():
            if id(c) in real_active:
                status = "reachable"
            elif id(c) in ideal_active:
                status = "blocked by the game"
            else:
                status = "unreachable in the story itself"
            missing = [f for f in c["requires"] if f not in real_flags]
            out.append({"rule": c["id"], "kind": kind, "status": status, "missing": missing})
        reasons = sorted({r for rs in failing.values() for r in rs})
        self._judge_endings(out, reasons)
        return {"endings": out, "game_gates_failing": reasons}

    def _judge_endings(self, endings, reasons):
        reachable = [e for e in endings if e["status"] == "reachable"]
        lost = [e for e in endings if e["status"] != "reachable"]
        if endings and not reachable:
            self.blockers.append("no ending can be reached in the game" + (f": {'; '.join(reasons[:4])}" if reasons else ""))
        for e in lost:
            if e["status"] == "blocked by the game":
                self.caveats.append(f"ending {e['rule']} ({e['kind']}) cannot be reached in the game"
                                    + (f": {'; '.join(reasons[:3])}" if reasons else ""))
            else:
                self.caveats.append(f"ending {e['rule']} ({e['kind']}) is unreachable even ignoring the game "
                                    f"(missing {', '.join(e['missing'])}); see check_story.py")

    # -------------------------------------------------------- other stories in the same game

    def shared(self):
        """What collides when other stories run in the same game."""
        out = []
        my_npcs = {c["npc"] for c in self.story.containers if c["kind"] == "graph"}
        my_objects = self._objects_of(self.story)
        my_states = {(ch["npc"].upper(), ch["state"]) for ch, pos, *_ in self.story.checks_of("npc_state") if pos}
        for other in self.others:
            for flag in sorted(other.flags_set() & self.story.flags_read()):
                readers = self.story.readers_of(flag)
                out.append(f"flag {flag} is also set by {other.name} (play_story.py namespaces ids, not flags); "
                           f"here it gates {', '.join(readers[:4])}" + (" ..." if len(readers) > 4 else ""))
            both = sorted(my_npcs & {c["npc"] for c in other.containers if c["kind"] == "graph"})
            if both:
                out.append(f"{other.name} also replaces the conversations of {', '.join(both)}; the later one wins")
            same = sorted(my_objects & self._objects_of(other))
            if same:
                out.append(f"{other.name} waits at the same object(s) {same}")
            for npc, state in my_states:
                for start, end, activity, wp in self.game.schedule(self.game.routine_of(npc)):
                    if activity != STATE_ACTIVITY.get(state):
                        continue
                    target = self.game.object_of(activity, wp)
                    if target and (round(target[1]), round(target[2])) in self._objects_of(other):
                        out.append(f"{self.game.label(npc)} must be {state} here, but {other.name} reserves his object "
                                   f"({round(target[1])}, {round(target[2])}) once it fills it, which makes him get up")
        for line in out:
            self.caveats.append(line)
        return out

    def _objects_of(self, story):
        found = set()
        for c in story.containers:
            on = c.get("on") or {}
            if on.get("event") == "used_object" and on.get("near"):
                x, z, metres = on["near"]
                best = self._nearest_object(x, z, metres, (on.get("object") or "").upper())
                found.add((round(best[1]), round(best[2])) if best else (round(x), round(z)))
        return found


def _dedupe(setters):
    out, seen = [], set()
    for x in setters:
        if x["by"] not in seen:
            seen.add(x["by"])
            out.append(x)
    return out


def _hour_checks(checks):
    """The positive hour checks among these."""
    return [ch for ch, pos in _checks_with_polarity(checks) if ch["type"] == "hour" and pos]


class _Reach:
    """What a story can bring about, run to a fixpoint: the containers that open, the flags and items they yield.

    With real=False only the story's own logic counts; with real=True every check must also pass against the game
    (Audit.gate), and the ones that fail are collected by container or choice.
    """

    def __init__(self, audit, real):
        s = audit.story
        self.audit, self.story, self.real = audit, s, real
        self.flags, self.active, self.failing = set(s.initial_flags), set(), {}
        self.items = {name for name, _, parent in s.placed + s.given if parent is None}
        self.changed = False

    def run(self):
        self.changed = True
        while self.changed:
            self.changed = False
            for c in self.story.containers:
                self._visit(c)
        return self.flags, self.active, self.failing

    def _add(self, found, value):
        if value not in found:
            found.add(value)
            self.changed = True

    def _visit(self, c):
        s = self.story
        parent = c.get("parent")
        if parent is not None and id(parent) not in self.active:
            return
        if not all(f in self.flags for f in c["requires"]):
            return
        # "unless" can only be ordered in time by playing; what the runtime provably never allows is
        # excluded: a guard on its own requirement, or on a flag set from the start.
        if any(u in c["requires"] or u in s.initial_flags for u in c["unless"]):
            return
        reasons = self._game_reasons(c) if self.real else []
        if reasons:
            self.failing[c["id"]] = reasons
            return
        self.failing.pop(c["id"], None)
        self._add(self.active, id(c))
        for op in c.get("ops") or []:
            if op.get("op") == "set_flag" and op.get("value"):
                self._add(self.flags, op["name"])
            if op.get("op") in ("give_item", "place_item") and op.get("instance", "").upper() not in self.items:
                self._add(self.items, op["instance"].upper())
        graph = c.get("graph") if isinstance(c.get("graph"), dict) else None
        if graph:
            self._walk(c, graph)

    def _game_reasons(self, c):
        """Why the game keeps this container from ever firing, if it does."""
        reasons = []
        for check in c["checks"]:
            ok, why = self.audit.gate(check, c.get("npc"), self.items)
            if not ok:
                reasons.append(why)
        on = c.get("on") or {}
        if on.get("event") in ("took_item", "read_item") and on.get("item"):
            item = on["item"].upper()
            placed = any(name == item for name, _, _ in self.story.placed)
            ok = placed or item in self.items or bool(self.audit.sources(item))
            if not ok:
                reasons.append(f"{item} is nowhere to take")
        for field in ("target", "seen_by"):
            if on.get(field) and on[field] != "PLAYER" and self.audit.game.presence(on[field])[0] == FALSE:
                reasons.append(f"{on[field]} is not in Khorinis")
        return reasons

    def _walk(self, c, graph):
        """Every node of a conversation the hero can get to, and what its nodes and choices set and give."""
        seen, todo = set(), [graph.get("start")]
        while todo:
            key = todo.pop()
            node = graph["nodes"].get(key)
            if key in seen or node is None:
                continue
            seen.add(key)
            for flag in _list(node.get("sets")):
                self._add(self.flags, flag)
            if node.get("returns"):
                todo.append(node["returns"])
            node_sets = set(_list(node.get("sets")))
            for choice in node.get("choices", []):
                if not self._choice_open(c, key, choice, node_sets):
                    continue
                if choice.get("gives"):
                    self._add(self.items, choice["gives"]["item"].upper())
                if choice.get("goto"):
                    todo.append(choice["goto"])

    def _choice_open(self, c, key, choice, node_sets):
        required = choice.get("requires")
        if required and not any(f in self.flags for f in required):
            return False
        # The node's own flags are set before its choices show, so a choice barred by one of
        # them never appears; nor one barred by its own requirement or a flag set from the start.
        barred = _list(choice.get("unless"))
        if any(u in (required or []) or u in node_sets or u in self.story.initial_flags for u in barred):
            return False
        if not self.real:
            return True
        bad = [self.audit.gate(ch, c.get("npc"), self.items) for ch in choice.get("checks") or []]
        bad = [why for ok, why in bad if not ok]
        if choice.get("takes"):
            ok, why = self.audit.gate({"type": "has_item", "item": choice["takes"]["item"]}, c.get("npc"), self.items)
            if not ok:
                bad.append(why)
        if bad:
            self.failing[f"{c['id']}:{key}:{choice.get('text', '')[:20]}"] = bad
            return False
        return True

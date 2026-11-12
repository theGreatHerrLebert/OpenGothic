"""Can a story be played to the end in the real game? A playability audit against the game's own data.

    python3 python/dm/playability.py <story.json> [...] [--json] [--game <Gothic install>]

check_story.py proves a story is sound in itself. This asks the game: can the hero, in chapter 1 and without a guild,
get every item the story wants, start and finish every quest it checks, hear every topic it waits for, find every
person it needs at the hours it needs them, and sit at every object it waits for while no one else sits there?

It reads what quest_mine.py, map_data.py and tools/world_dump.cpp extracted, all in the gitignored dm_runtime folder:
mechanics/{items,dialogues,functions,quests}.json, mechanics/world.jsonl and map/map_data.json. When the game is
installed (--game, or dm_runtime/settings.json), the NPCs' own starting inventories come from its GOTHIC.DAT.
Nothing here is specific to one story. The report names items and people but never quotes the game's dialogue.

What the hero has is judged by a three-valued reading of the game's own conditions: chapter 1 and no guild are
certain, every other script variable is taken as something the hero could still bring about. "Blocked" means the
game's own rules rule it out; everything else is reachable as far as the data can tell.
"""

import argparse
import json
import math
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
RUNTIME = HERE.parent / "dm_runtime"
MECHANICS = RUNTIME / "mechanics"
MAP_DATA = RUNTIME / "map" / "map_data.json"
WORLD = "NEWWORLD.ZEN"
CHAPTER = 1
HERO_GUILD = "GIL_NONE"

# Interactive objects are not in world.jsonl yet (world_dump.cpp writes items, containers, doors and waypoints).
# Until it does, the water pipes measured in the running game stand in, as (world, scheme, x, z). A "mob" record in
# world.jsonl ({"kind": "mob", "scheme": ..., "x": ..., "z": ...}) takes over as soon as there is one.
KNOWN_OBJECTS = [(WORLD, "SMOKE", 6787, 3160), (WORLD, "SMOKE", 6741, 2972), (WORLD, "SMOKE", 6898, 2711)]
# An NPC at one of these activities takes the free object of this scheme nearest his waypoint.
ACTIVITY_OBJECT = {"SMOKE_WATERPIPE": "SMOKE"}
# A story's npc_state check, as the routine activity that puts an NPC into that state by himself.
STATE_ACTIVITY = {"ZS_SMOKE_WATERPIPE": "SMOKE_WATERPIPE", "ZS_STAND_DRINKING": "STAND_DRINKING", "ZS_SLEEP": "SLEEP",
                  "ZS_PRAY_INNOS": "PRAY_INNOS", "ZS_DANCE": "DANCE", "ZS_STAND_DEMENTOR": "STAND_DEMENTOR"}
ASLEEP = {"SLEEP"}
LOG = {"LOG_RUNNING": 1, "LOG_SUCCESS": 2, "LOG_FAILED": 3, "LOG_OBSOLETE": 4}
QUEST_STATE = {"open": None, "running": "LOG_RUNNING", "success": "LOG_SUCCESS", "failed": "LOG_FAILED",
               "obsolete": "LOG_OBSOLETE"}
TA = re.compile(r'^TA_([A-Z0-9_]+)\((\d+), (\d+), (\d+), (\d+), "([^"]+)"\)$')
GIVE = re.compile(r'B_GIVEINVITEMS\((\w+), (\w+), (\w+), (\w+)\)')
CREATE = re.compile(r'CREATEINVITEMS?\((\w+(?:\.\w+)?), (\w+)(?:, (\w+))?\)')
FIND = re.compile(r'B_PLAYERFINDITEM\((\w+), (\w+)\)')
INSERT_ITEM = re.compile(r'WLD_INSERTITEM\((\w+), "([^"]+)"\)')
HASITEMS = re.compile(r'NPC_HASITEMS\((HERO|SELF|OTHER), (\w+)\)(?:\s*(>=|>)\s*(\d+))?')
MOBSI = re.compile(r'PLAYER_MOBSI_PRODUCTION == (MOBSI_\w+)')
TALENT = re.compile(r'(PLAYER_TALENT_\w+\[\d+\]) == TRUE')
SET_QUEST = re.compile(r'^(MIS_\w+) = (LOG_\w+)$')
ROUTINE_SWAP = re.compile(r'(?:NPC_EXCHANGEROUTINE|B_STARTOTHERROUTINE)\((\w+), "(\w+)"\)')
ADDCHOICE = re.compile(r'INFO_ADDCHOICE\(\w+, .*, (\w+)\)$')

TRUE, FALSE, MAYBE = "yes", "no", "maybe"


def t_and(values):
    values = list(values)
    if FALSE in values:
        return FALSE
    return TRUE if all(v == TRUE for v in values) else MAYBE


def t_or(values):
    values = list(values)
    if TRUE in values:
        return TRUE
    return FALSE if values and all(v == FALSE for v in values) else MAYBE


def t_not(value):
    return {TRUE: FALSE, FALSE: TRUE}.get(value, MAYBE)


# ---------------------------------------------------------------- reading the game's conditions

_TOKEN = re.compile(r'\s*(?:("(?:[^"\\]|\\.)*")|(\d+)|([A-Za-z_\u0178][\w.\u0178]*)'
                    r'|(&&|\|\||==|!=|>=|<=|<<|>>|[<>!~+\-*/%&|()\[\],]))')


def tokenize(text):
    pos, out = 0, []
    while pos < len(text):
        m = _TOKEN.match(text, pos)
        if not m or m.end() == pos:
            if text[pos:].strip() == "":
                break
            raise ValueError(f"cannot read {text[pos:pos + 20]!r}")
        pos = m.end()
        string, number, name, op = m.groups()
        out.append(("str", string) if string else ("num", int(number)) if number else
                   ("name", name) if name else ("op", op))
    return out


class Expr:
    """A recursive-descent reader for the decompiled guards, evaluated as it parses."""

    LEVELS = [("||",), ("&&",), ("|",), ("&",), ("==", "!="), ("<", ">", "<=", ">="), ("<<", ">>"), ("+", "-"),
              ("*", "/", "%")]

    def __init__(self, text, world):
        self.tokens, self.i, self.world = tokenize(text), 0, world

    def peek(self):
        return self.tokens[self.i] if self.i < len(self.tokens) else (None, None)

    def take(self):
        token = self.peek()
        self.i += 1
        return token

    def evaluate(self):
        value = self.level(0)
        return truth(value)

    def level(self, depth):
        if depth == len(self.LEVELS):
            return self.unary()
        left = self.level(depth + 1)
        while self.peek()[0] == "op" and self.peek()[1] in self.LEVELS[depth]:
            op = self.take()[1]
            right = self.level(depth + 1)
            left = self.world.binary(op, left, right)
        return left

    def unary(self):
        kind, text = self.peek()
        if kind == "op" and text in ("!", "-", "+", "~"):
            self.take()
            value = self.unary()
            if text == "!":
                return ("truth", t_not(truth(value)))
            if text == "-" and value[0] == "num":
                return ("num", -value[1])
            return value if text == "+" else ("unk", None)
        return self.postfix()

    def postfix(self):
        kind, text = self.take()
        if kind == "op" and text == "(":
            value = self.level(0)
            self.take()
            return value
        if kind == "num":
            return ("num", text)
        if kind == "str":
            return ("str", text)
        if kind != "name":
            return ("unk", None)
        if self.peek() == ("op", "("):
            self.take()
            args = []
            while self.peek() != ("op", ")") and self.peek()[0] is not None:
                start = self.i
                args.append((self.level(0), self.tokens[start:self.i]))
                if self.peek() == ("op", ","):
                    self.take()
            self.take()
            return self.world.call(text, args)
        if self.peek() == ("op", "["):
            self.take()
            self.level(0)
            self.take()
            return ("unk", None)
        return self.world.name(text)


def truth(value):
    kind, v = value
    if kind == "truth":
        return v
    if kind == "num":
        return TRUE if v else FALSE
    return MAYBE


def _arg_name(arg):
    tokens = arg[1]
    return tokens[0][1] if len(tokens) == 1 and tokens[0][0] == "name" else None


# ---------------------------------------------------------------- the game

class Game:
    """Everything the audit knows about the game, built from plain dicts so tests can make a small one."""

    def __init__(self, items=None, dialogues=None, functions=None, quests=None, world=None, people=None,
                 inventories=None, objects=None):
        self.items = {k.upper(): v for k, v in (items or {}).items()}
        self.dialogues = {d["id"].upper(): d for d in (dialogues or [])}
        self.functions = functions or {}
        self.quests = quests or {}
        self.inventories = inventories          # instance -> {item: count}; None when GOTHIC.DAT was not read
        self.waypoints, self.placed, self.containers, self.mobs = {}, [], [], []
        for r in world or []:
            if r.get("world") != WORLD:
                continue
            kind = r.get("kind")
            if kind == "waypoint":
                self.waypoints[r["name"].upper()] = (r["x"], r["z"])
            elif kind == "item":
                self.placed.append(r)
            elif kind == "container":
                self.containers.append(r)
            elif kind == "mob":
                self.mobs.append((r.get("scheme", "").upper(), r["x"], r["z"]))
        if objects is not None:
            self.mobs = [(s, x, z) for _, s, x, z in objects]
        elif not self.mobs:
            self.mobs = [(s, x, z) for w, s, x, z in KNOWN_OBJECTS if w == WORLD]
        self.people = {}                        # instance -> {"name", "id", "worlds": {world: spawn}, "routine"}
        for world_name, entries in (people or {}).items():
            for p in entries:
                entry = self.people.setdefault(p["instance"].upper(), {"name": p.get("name"), "id": p.get("id"),
                                                                      "worlds": {}, "routine": None})
                entry["worlds"][world_name] = p.get("spawn") or {}
                if world_name == WORLD:
                    entry["routine"] = (p.get("routines") or {}).get(str(CHAPTER))
        self.has_people = bool(self.people)
        self.routines = {}
        for name, body in self.functions.items():
            if name.startswith("RTN_"):
                self.routines[name] = [m.groups() for m in (TA.match(r.get("do", "")) for r in body) if m]
        self.aliases = {}
        for body in self.functions.values():
            for r in body:
                m = re.match(r'^(\w+) = HLP_GETNPC\((\w+)\)$', r.get("set", ""))
                if m:
                    self.aliases[m[1]] = m[2]
        self._dialogue_memo, self._quest_memo = {}, {}
        self._index()

    # ------------------------------------------------------------ indexes

    def _walk_info(self, node, path, guards, out):
        """Every effect of a dialogue, with the choices that lead to it and the guards that enclose it."""
        effects = node.get("effects", []) if node else []
        choice_guard = {}
        for e in effects:
            m = ADDCHOICE.match(e.get("do", ""))
            if m:
                choice_guard[m[1]] = e.get("if", [])
        for e in effects:
            out.append((path, guards + e.get("if", []), e))
        for name, sub in (node or {}).get("choices", {}).items():
            self._walk_info(sub, path + [name], guards + choice_guard.get(name, []), out)

    def _index(self):
        self.effects = {}               # dialogue id -> [(path, guards, effect)]
        self.quest_setters = {}         # (MIS_X, LOG_Y) -> [(kind, name, guards)]
        self.gifts = {}                 # item -> [(dialogue id, guards, count)]
        self.recipes = {}               # item -> [recipe]
        self.npc_dialogues = {}
        self.swaps = {}                 # instance -> [(routine, dialogue id)]
        for did, d in self.dialogues.items():
            out = []
            self._walk_info(d.get("information"), [], [], out)
            self.effects[did] = out
            npc = (d.get("npc") or "").upper()
            self.npc_dialogues.setdefault(npc, []).append(did)
            for path, guards, e in out:
                text = e.get("set") or e.get("do") or ""
                m = SET_QUEST.match(e.get("set", ""))
                if m:
                    self.quest_setters.setdefault((m[1], m[2]), []).append(("dialogue", did, guards))
                for clause in [text] + guards:
                    for giver, receiver, item, count in GIVE.findall(clause):
                        if receiver in ("OTHER", "HERO") and giver != receiver:
                            self.gifts.setdefault(item, []).append((did, guards, count))
                for target, item, count in CREATE.findall(text):
                    if npc == "PC_HERO" and target in ("HERO", "SELF"):
                        self._recipe(did, d, path, guards, item, count)
                    elif target in ("OTHER", "HERO"):
                        self.gifts.setdefault(item, []).append((did, guards, count or "1"))
                for who, routine in ROUTINE_SWAP.findall(text):
                    target = npc if who == "SELF" else self.aliases.get(who, who)
                    self.swaps.setdefault(target, []).append((routine, did))
        self.function_gifts = {}        # item -> [(function, guards)]
        self.trade = {}                 # trader instance -> {item: count} in this chapter
        self.inserted = {}              # item -> [spot] put into the world by script in this chapter
        trader_of = {}
        for r in self.functions.get("B_GIVETRADEINV", []):
            m = re.match(r'^B_GIVETRADEINV\.TRD_(\w+) = HLP_GETNPC\((\w+)\)$', r.get("set", ""))
            if m:
                trader_of[m[1]] = m[2]
        for name, body in self.functions.items():
            for r in body:
                text = r.get("set") or r.get("do") or ""
                m = SET_QUEST.match(r.get("set", ""))
                if m:
                    self.quest_setters.setdefault((m[1], m[2]), []).append(("function", name, r.get("if", [])))
            if name.startswith("B_GIVETRADEINV_"):
                inst = trader_of.get(name[len("B_GIVETRADEINV_"):])
                if inst:
                    stock = self.trade.setdefault(inst, {})
                    for r in body:
                        m = CREATE.search(r.get("do", ""))
                        guard = " ".join(r.get("if", []))
                        chapter = re.search(r'KAPITEL >= (\d+)', guard)
                        if m and (not chapter or int(chapter[1]) <= CHAPTER) and "KAPITEL ==" not in guard:
                            stock[m[2]] = stock.get(m[2], 0) + _int(m[3], 1)
                continue
            if name.startswith(("STARTUP_NEWWORLD", f"B_ENTER_NEWWORLD_KAPITEL_{CHAPTER}")):
                for r in body:
                    m = INSERT_ITEM.search(r.get("do", ""))
                    if m:
                        self.inserted.setdefault(m[1], []).append(m[2])
                continue
            if name.startswith(("B_GIVETRADEINV", "B_CREATEAMBIENTINV", "B_CLEAR", "STARTUP_", "INIT_", "B_ENTER_")):
                continue
            for r in body:
                text = r.get("do", "")
                found = [(item, None) for _, item in FIND.findall(text)]
                found += [(item, None) for target, item, _ in CREATE.findall(text) if target in ("HERO", "OTHER")]
                for item, _ in found:
                    self.function_gifts.setdefault(item, []).append((name, r.get("if", [])))

    def _recipe(self, did, d, path, guards, item, count):
        conditions = []
        for entry in d.get("condition", {}).get("effects", []):
            if entry.get("return") == "TRUE":
                conditions += entry.get("if", [])
        text = " ".join(conditions + guards)
        ingredients = {}
        for _, name, op, amount in HASITEMS.findall(text):
            need = int(amount) + (1 if op == ">" else 0) if amount else 1
            ingredients[name] = max(ingredients.get(name, 0), need, 1)
        self.recipes.setdefault(item, []).append({
            "dialogue": did, "choice": path[-1] if path else None, "ingredients": ingredients,
            "bench": sorted(set(MOBSI.findall(text))), "talents": sorted(set(TALENT.findall(text))),
            "count": _int(count, 1)})

    # ------------------------------------------------------------ the expression world

    def name(self, text):
        if text == "KAPITEL":
            return ("num", CHAPTER)
        if text in ("TRUE", "FALSE"):
            return ("num", int(text == "TRUE"))
        if text in LOG:
            return ("num", LOG[text])
        if text in ("OTHER.GUILD", "HERO.GUILD"):
            return ("guild", HERO_GUILD)
        if text.startswith("GIL_"):
            return ("guild", text)
        if text.startswith("MIS_"):
            return ("quest", text)
        return ("unk", None)

    def call(self, name, args):
        if name == "NPC_KNOWSINFO" and len(args) == 2 and _arg_name(args[0]) in ("OTHER", "HERO"):
            info = _arg_name(args[1])
            return ("truth", self.dialogue_reachable(info)[0] if info else MAYBE)
        if name == "NPC_GETTRUEGUILD" and args and _arg_name(args[0]) in ("OTHER", "HERO"):
            return ("guild", HERO_GUILD)
        return ("unk", None)

    def binary(self, op, left, right):
        if op in ("&&", "||"):
            values = [truth(left), truth(right)]
            return ("truth", t_and(values) if op == "&&" else t_or(values))
        if op in ("==", "!=") and "quest" in (left[0], right[0]):
            quest, other = (left, right) if left[0] == "quest" else (right, left)
            if other[0] != "num":
                return ("unk", None)
            state = {v: k for k, v in LOG.items()}.get(other[1])
            if state is None:                       # == FALSE: not begun yet, which any new game is
                result = MAYBE
            else:
                result = MAYBE if self.quest_reachable(quest[1], state)[0] != FALSE else FALSE
            return ("truth", result if op == "==" else (TRUE if result == FALSE else MAYBE))
        if left[0] == right[0] and left[0] in ("num", "guild") and op in ("==", "!=", "<", ">", "<=", ">="):
            a, b = left[1], right[1]
            if left[0] == "guild" and op not in ("==", "!="):
                return ("unk", None)
            result = {"==": a == b, "!=": a != b, "<": a < b, ">": a > b, "<=": a <= b, ">=": a >= b}[op]
            return ("truth", TRUE if result else FALSE)
        if left[0] == right[0] == "num" and op in ("+", "-", "*"):
            return ("num", {"+": left[1] + right[1], "-": left[1] - right[1], "*": left[1] * right[1]}[op])
        return ("unk", None)

    def guard(self, text):
        try:
            return Expr(text, self).evaluate()
        except (ValueError, IndexError, TypeError, KeyError):
            return MAYBE

    def guards(self, texts):
        return t_and(self.guard(t) for t in texts)

    def condition(self, did):
        """Whether a dialogue's condition function can return TRUE: the first matching return wins."""
        cond = self.dialogues[did].get("condition") or {}
        options, earlier_false = [], []
        for entry in cond.get("effects", []):
            if "return" not in entry:
                continue
            guards = entry.get("if", [])
            here = self.guards(guards)
            ruled_out = t_and(t_not(g) for g in earlier_false)
            value = entry["return"]
            if value == "FALSE" or value == "0":
                earlier_false.append(here)
                continue
            returned = TRUE if value in ("TRUE", "1") else self.guard(value)
            options.append(t_and([here, ruled_out, returned]))
        return t_or(options) if options else MAYBE

    # ------------------------------------------------------------ people

    def instance(self, name):
        name = (name or "").upper()
        return self.aliases.get(name, name)

    def presence(self, npc):
        """yes/no/maybe the NPC is in Khorinis in this chapter, with where he starts."""
        npc = self.instance(npc)
        if npc == "PC_HERO":
            return TRUE, "the hero"
        if not self.has_people:
            return MAYBE, "no map data"
        person = self.people.get(npc)
        if not person:
            return FALSE, "not placed in any world"
        here = person["worlds"].get(WORLD)
        if here and here.get("chapter", 1) <= CHAPTER:
            return (MAYBE if here.get("conditions") else TRUE), f"{WORLD} from chapter {here.get('chapter', 1)}"
        if here:
            return FALSE, f"{WORLD} only from chapter {here.get('chapter')}"
        world = ", ".join(sorted(person["worlds"]))
        if "ADDONWORLD.ZEN" in person["worlds"]:
            return MAYBE, f"only in {world} (Jharkendar)"
        return FALSE, f"only in {world}"

    def schedule(self, routine):
        """[(from minute, to minute, activity, waypoint)] of a routine function."""
        out = []
        for activity, h1, m1, h2, m2, wp in self.routines.get(routine or "", []):
            out.append((int(h1) * 60 + int(m1), int(h2) * 60 + int(m2), activity, wp.upper()))
        return out

    def routine_of(self, npc):
        npc = self.instance(npc)
        person = self.people.get(npc)
        if person and person["routine"]:
            return person["routine"]
        m = re.search(r'_(\d+)(?:_|$)', npc)
        return f"RTN_START_{m[1]}" if m else None

    def npc_id(self, npc):
        person = self.people.get(self.instance(npc))
        if person and person.get("id"):
            return str(person["id"])
        m = re.search(r'_(\d+)(?:_|$)', self.instance(npc))
        return m[1] if m else None

    def other_routines(self, npc):
        nid, start = self.npc_id(npc), self.routine_of(npc)
        return sorted(r for r in self.routines if nid and r.endswith(f"_{nid}") and r != start)

    def object_of(self, activity, wp):
        """The object an NPC at this activity and waypoint takes: the nearest of its scheme."""
        scheme = ACTIVITY_OBJECT.get(activity)
        if not scheme or wp not in self.waypoints:
            return None
        wx, wz = self.waypoints[wp]
        pool = [o for o in self.mobs if scheme in o[0]]
        return min(pool, key=lambda o: (o[1] - wx) ** 2 + (o[2] - wz) ** 2) if pool else None

    def nearest_waypoint(self, x, z):
        best, dist = None, None
        for name, (wx, wz) in self.waypoints.items():
            d = (wx - x) ** 2 + (wz - z) ** 2
            if dist is None or d < dist:
                best, dist = name, d
        return best, (round(math.sqrt(dist) / 100, 1) if dist is not None else None)

    # ------------------------------------------------------------ reachability

    def dialogue_reachable(self, did):
        """(yes/no/maybe, why) the hero can hear this dialogue in this chapter without a guild."""
        did = (did or "").upper()
        if did in self._dialogue_memo:
            return self._dialogue_memo[did]
        if did not in self.dialogues:
            return FALSE, "no such dialogue"
        self._dialogue_memo[did] = (MAYBE, "depends on itself")
        npc = self.dialogues[did].get("npc")
        present, where = self.presence(npc) if npc else (MAYBE, "no speaker")
        cond = self.condition(did)
        result = t_and([present, cond])
        guards = [" && ".join(e.get("if", [])) or e.get("return") for e in
                  (self.dialogues[did].get("condition") or {}).get("effects", [])
                  if "return" in e and e["return"] not in ("FALSE", "0")]
        why = where if present == FALSE else (f"its condition rules it out in chapter {CHAPTER} without a guild: "
                                              + " || ".join(guards)[:200] if cond == FALSE else where)
        self._dialogue_memo[did] = (result, why)
        return result, why

    def quest_reachable(self, var, state):
        """(yes/no/maybe, [setters]) a quest variable can reach LOG_<state> in this chapter without a guild."""
        key = (var.upper(), state)
        if key in self._quest_memo:
            return self._quest_memo[key]
        self._quest_memo[key] = (MAYBE, [])
        found = []
        for kind, name, guards in self.quest_setters.get(key, []):
            if kind == "dialogue":
                reach = t_and([self.dialogue_reachable(name)[0], self.guards(guards)])
                found.append({"by": name, "npc": self.dialogues[name].get("npc"), "reach": reach})
            else:
                callers = self.callers(name)
                reach = t_or(self.dialogue_reachable(c)[0] for c in callers) if callers else MAYBE
                found.append({"by": name, "npc": None, "reach": t_and([reach, self.guards(guards)]),
                              "via": callers[:4]})
        result = (t_or(f["reach"] for f in found) if found else FALSE, found)
        self._quest_memo[key] = result
        return result

    def callers(self, function):
        pattern = function + "("
        return sorted({did for did, effects in self.effects.items()
                       for _, guards, e in effects
                       if pattern in (e.get("do") or "") or any(pattern in g for g in guards)})

    def trade_dialogues(self, npc):
        npc = self.instance(npc)
        return [did for did in self.npc_dialogues.get(npc, [])
                if any("B_GIVETRADEINV(SELF)" in (e.get("do") or "") for _, _, e in self.effects.get(did, []))]

    def item_sources(self, item, depth=0):
        """Every way the game itself hands this item to a guildless hero in this chapter."""
        item = item.upper()
        out = []
        spots = [r for r in self.placed if r.get("instance", "").upper() == item]
        if spots:
            where = []
            for r in spots[:4]:
                wp, metres = self.nearest_waypoint(r["x"], r["z"])
                where.append(f"{wp} ({metres} m)")
            out.append({"kind": "placed", "reach": TRUE, "count": len(spots),
                        "text": f"lies in Khorinis {len(spots)}x, e.g. near " + ", ".join(where)})
        for spot in self.inserted.get(item, []):
            out.append({"kind": "placed", "reach": TRUE, "text": f"put into the world by script at {spot}"})
        for c in self.containers:
            names = [p.split(":")[0].upper() for p in (c.get("contents") or "").split(",") if p]
            if item not in names:
                continue
            wp, metres = self.nearest_waypoint(c["x"], c["z"])
            label = f"container {c.get('name') or ''} near {wp} ({metres} m)".replace("container  ", "container ")
            if not c.get("locked"):
                out.append({"kind": "container", "reach": TRUE, "text": label + ", unlocked"})
            elif c.get("pick"):
                out.append({"kind": "container", "reach": MAYBE,
                            "text": label + f", locked: needs a lockpick and the lock-picking talent"})
            elif c.get("key"):
                out.append({"kind": "container", "reach": MAYBE, "text": label + f", locked: needs key {c['key']}"})
            else:
                out.append({"kind": "container", "reach": FALSE, "text": label + ", locked with no pick or key"})
        for trader, stock in sorted(self.trade.items()):
            if item not in stock:
                continue
            present, where = self.presence(trader)
            if present == FALSE:
                continue
            deals = self.trade_dialogues(trader)
            open_ = t_or(self.dialogue_reachable(d)[0] for d in deals) if deals else MAYBE
            reach = t_and([present, open_])
            places = self.places(trader, awake_only=True)
            gate = "" if open_ == TRUE else (" (trade opens only " + ("never in chapter 1" if open_ == FALSE
                                                                       else "after " + ", ".join(deals)) + ")")
            out.append({"kind": "trader", "reach": reach, "npc": trader,
                        "text": f"sold by {self.label(trader)}: {stock[item]} in stock{gate}; found at {places}"})
        for did, guards, count in self.gifts.get(item, []):
            if self.dialogues[did].get("npc") == "PC_HERO" or self.presence(self.dialogues[did].get("npc"))[0] == FALSE:
                continue
            reach = t_and([self.dialogue_reachable(did)[0], self.guards(guards)])
            npc = self.dialogues[did].get("npc")
            out.append({"kind": "dialogue", "reach": reach, "npc": npc,
                        "text": f"given in {did} by {self.label(npc)}" + ("" if reach != FALSE else
                                                                         " (not reachable in chapter 1)")})
        for recipe in self.recipes.get(item, []):
            parts = []
            reach = TRUE
            for ingredient, count in recipe["ingredients"].items():
                sub = [] if depth > 1 else self.item_sources(ingredient, depth + 1)
                has = t_or(s["reach"] for s in sub) if sub else (MAYBE if depth > 1 else FALSE)
                reach = t_and([reach, has])
                parts.append(f"{count}x {ingredient}" + ("" if has != FALSE else " (no source)"))
            bench = ", ".join(recipe["bench"]) or "no bench"
            users = self.bench_users(recipe["bench"])
            talents = (", needs " + ", ".join(recipe["talents"])) if recipe["talents"] else ""
            out.append({"kind": "made", "reach": reach,
                        "text": f"made by the hero at {bench} ({recipe['dialogue']}) from "
                                + " + ".join(parts) + talents
                                + (f"; NPCs work such a bench at {users}" if users else "")})
        if self.inventories is not None:
            for npc, stock in sorted(self.inventories.items()):
                if item in stock and self.presence(npc)[0] != FALSE:
                    out.append({"kind": "carried", "reach": MAYBE,
                                "text": f"carried by {self.label(npc)} ({stock[item]}x), to steal or loot; "
                                        f"at {self.places(npc)}"})
        for function, guards in self.function_gifts.get(item, []):
            out.append({"kind": "script", "reach": MAYBE, "text": f"handed out by script {function}"})
        return out

    def label(self, npc):
        npc = self.instance(npc)
        person = self.people.get(npc)
        return f"{person['name']} ({npc})" if person and person.get("name") else str(npc)

    def places(self, npc, awake_only=False):
        """Where an NPC spends his day, one line per waypoint."""
        at = {}
        for start, end, activity, wp in self.schedule(self.routine_of(npc)):
            if awake_only and activity in ASLEEP:
                continue
            at.setdefault(wp, set()).update(minutes(start, end))
        seen = [f"{wp} {spans(mins)}" for wp, mins in at.items()]
        return "; ".join(seen[:4]) + (" ..." if len(seen) > 4 else "") if seen else "unknown place"

    def bench_users(self, benches):
        activities = {b.replace("MOBSI_", "").replace("_", "") for b in benches}
        found = []
        for npc in self.people:
            for start, end, activity, wp in self.schedule(self.routine_of(npc)):
                works = any(a in activity.replace("_", "") for a in activities)
                if works and wp not in found and self.presence(npc)[0] != FALSE:
                    found.append(wp)
        return ", ".join(found[:5])


def _int(text, default):
    try:
        return int(text)
    except (TypeError, ValueError):
        return default


def clock(minute):
    return f"{minute // 60 % 24:02d}:{minute % 60:02d}"


def minutes(start, end):
    """The minutes of a day from start up to end, wrapping past midnight; start == end is the whole day."""
    if start == end:
        return set(range(1440))
    if start < end:
        return set(range(start, end))
    return set(range(start, 1440)) | set(range(0, end))


def hour_window(check):
    """The minutes a story's hour check holds: from <= hour < to, wrapping (as checks._holds reads it)."""
    start, end = check["from"] * 60, check["to"] * 60
    if start == end:
        return set()
    return minutes(start, end)


def spans(mins):
    """A set of minutes as readable ranges."""
    if not mins:
        return "never"
    if len(mins) == 1440:
        return "all day"
    out, ordered = [], sorted(mins)
    start = prev = ordered[0]
    for m in ordered[1:] + [None]:
        if m is not None and m == prev + 1:
            prev = m
            continue
        out.append((start, prev + 1))
        if m is not None:
            start = prev = m
    if len(out) > 1 and out[0][0] == 0 and out[-1][1] == 1440:
        out = [(out[-1][0], out[0][1])] + out[1:-1]
    return ", ".join(f"{clock(a)}-{clock(b)}" for a, b in out)


def load_game(mechanics=MECHANICS, map_data=MAP_DATA, game=None):
    def read(name, default):
        path = pathlib.Path(mechanics) / name
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    world = []
    path = pathlib.Path(mechanics) / "world.jsonl"
    if path.exists():
        world = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    people = {}
    if pathlib.Path(map_data).exists():
        worlds = json.loads(pathlib.Path(map_data).read_text(encoding="utf-8"))["worlds"]
        people = {name: w.get("people", []) for name, w in worlds.items()}
    return Game(read("items.json", {}), read("dialogues.json", []), read("functions.json", {}), read("quests.json", {}),
                world, people, read_inventories(game))


def read_inventories(game):
    """The items each NPC instance creates for itself, read from the game's GOTHIC.DAT; None without the game."""
    if game is None:
        settings = RUNTIME / "settings.json"
        if settings.exists():
            game = json.loads(settings.read_text(encoding="utf-8")).get("game")
    dat = pathlib.Path(game or "") / "_work/Data/Scripts/_compiled/GOTHIC.DAT"
    if not game or not dat.exists():
        return None
    sys.path.insert(0, str(HERE))
    import depmap  # noqa: E402
    import quest_mine  # noqa: E402
    program = quest_mine.Program(dat.read_bytes())
    out = {}
    for s in program.symbols:
        if s["kind"] != depmap.T_INSTANCE or not s["address"] or s["address"] <= 0:
            continue
        if depmap.root_class(program.symbols, s) != "C_NPC":
            continue
        stock = {}
        for r in program.run(s):
            m = CREATE.search(r.get("do", ""))
            if m and m[1] == s["name"]:
                stock[m[2]] = stock.get(m[2], 0) + _int(m[3], 1)
        if stock:
            out[s["name"]] = stock
    return out


# ---------------------------------------------------------------- reading a story

class Story:
    """What one story needs and makes, collected from its plan wherever it sits."""

    def __init__(self, story, name="story"):
        self.name, self.title = name, story.get("title", name)
        self.data = story
        self.containers = []    # dicts: kind, id, npc, requires, unless, checks, on, graph, ops, parent, extra
        self.placed = []        # (item, waypoint, container)
        self.given = []         # (item, count, container)
        self.renamed = []       # (npc, name)
        self.npcs = {}          # npc -> set of roles
        for op in story.get("plan", []):
            self._op(op, None)

    def _role(self, npc, role):
        if npc:
            self.npcs.setdefault(npc.upper(), set()).add(role)

    def _op(self, op, parent):
        kind = op.get("op")
        entry = None
        if kind in ("attach_dialogue_graph", "add_scene", "add_topic"):
            entry = {"kind": {"attach_dialogue_graph": "graph", "add_scene": "scene", "add_topic": "topic"}[kind],
                     "id": op.get("id") or f"{op.get('npc')}", "npc": (op.get("npc") or "").upper(),
                     "requires": list(op.get("requires") or []), "unless": _list(op.get("unless")),
                     "checks": op.get("checks") or [], "graph": op.get("graph"), "parent": parent}
            self._role(op.get("npc"), {"graph": "conversation", "scene": "scene", "topic": "topic"}[entry["kind"]])
        elif kind == "add_rule":
            entry = {"kind": "rule", "id": op.get("id"), "npc": None, "requires": list(op.get("when") or []),
                     "unless": _list(op.get("unless")), "checks": op.get("checks") or [], "on": op.get("on"),
                     "ops": op.get("ops") or [], "parent": parent, "unseen_by_near": op.get("unseen_by_near")}
            on = op.get("on") or {}
            for field in ("target", "seen_by"):
                if on.get(field) and on[field] != "PLAYER":
                    self._role(on[field], "deed")
            if op.get("unseen_by_near"):
                self._role(op["unseen_by_near"], "watcher")
        elif kind == "place_item":
            self.placed.append((op.get("instance", "").upper(), op.get("waypoint"), parent))
        elif kind == "give_item":
            self.given.append((op.get("instance", "").upper(), op.get("count", 1), parent))
        elif kind == "rename_npc":
            self.renamed.append((op.get("instance", "").upper(), op.get("display_name")))
            self._role(op.get("instance"), "renamed")
        elif kind in ("spawn_npc", "relocate_npc", "send_npc", "remove_npc", "return_npc"):
            self._role(op.get("instance"), kind)
        if entry is not None:
            self.containers.append(entry)
            for check in _flat_checks(entry["checks"]):
                if check.get("npc"):
                    self._role(check["npc"], check["type"])
            for node in ((entry.get("graph") or {}).get("nodes") or {}).values():
                for choice in node.get("choices", []):
                    for check in _flat_checks(choice.get("checks")):
                        if check.get("npc"):
                            self._role(check["npc"], check["type"])
                    if choice.get("gives"):
                        self.given.append((choice["gives"]["item"].upper(), choice["gives"].get("count", 1), entry))
            for sub in entry.get("ops") or []:
                self._op(sub, entry)
        for npc in (self.data.get("anchor") or []):
            self._role(npc, "anchor")

    # what the story needs

    def item_needs(self):
        """item -> [where]; polarity-aware: an item the hero must NOT carry is no need."""
        needs = {}
        for c in self.containers:
            label = describe(c)
            for check, positive in _checks_with_polarity(c["checks"]):
                if positive and check["type"] in ("has_item", "wears"):
                    needs.setdefault(check["item"].upper(), []).append(f"{check['type']} on {label}")
            on = c.get("on") or {}
            if on.get("event") in ("took_item", "read_item") and on.get("item"):
                needs.setdefault(on["item"].upper(), []).append(f"{on['event']} on {label}")
            for key, node, choice in _choices(c):
                where = f"choice in {label} (node {key})"
                for check, positive in _checks_with_polarity(choice.get("checks")):
                    if positive and check["type"] in ("has_item", "wears"):
                        needs.setdefault(check["item"].upper(), []).append(f"{check['type']} on {where}")
                if choice.get("takes"):
                    needs.setdefault(choice["takes"]["item"].upper(), []).append(
                        f"takes {choice['takes'].get('count', 1)} in {where}")
        return needs

    def checks_of(self, kind):
        out = []
        for c in self.containers:
            for check, positive in _checks_with_polarity(c["checks"]):
                if check["type"] == kind:
                    out.append((check, positive, describe(c), c, None))
            for key, node, choice in _choices(c):
                for check, positive in _checks_with_polarity(choice.get("checks")):
                    if check["type"] == kind:
                        out.append((check, positive, f"choice in {describe(c)} (node {key})", c, choice))
        return out

    def flags_set(self):
        out = set()
        for c in self.containers:
            for key, node, _ in _nodes(c):
                out |= set(_list(node.get("sets")))
            for op in c.get("ops") or []:
                if op.get("op") == "set_flag" and op.get("value"):
                    out.add(op["name"])
        return out

    def flags_read(self):
        out = set()
        for c in self.containers:
            out |= set(c["requires"]) | set(c["unless"])
            for _, _, choice in _choices(c):
                out |= set(choice.get("requires") or []) | set(_list(choice.get("unless")))
        return out

    def readers_of(self, flag):
        """Where this story tests a flag, as readable labels."""
        out = []
        for c in self.containers:
            if flag in c["requires"]:
                out.append(f"{describe(c)} (requires)")
            if flag in c["unless"]:
                out.append(f"{describe(c)} (unless)")
            for key, _, choice in _choices(c):
                if flag in (choice.get("requires") or []) or flag in _list(choice.get("unless")):
                    out.append(f"a choice in {describe(c)}")
        return _unique(out)

    def setters_of(self, flag):
        """Containers that set this flag through a conversation."""
        return [c for c in self.containers if c["kind"] in ("graph", "scene", "topic")
                and any(flag in _list(node.get("sets")) for _, node, _ in _nodes(c))]

    def endings(self):
        out = []
        for c in self.containers:
            if c["kind"] != "rule":
                continue
            for op in c.get("ops") or []:
                if op.get("op") == "journal" and op.get("status") in (2, 3):
                    out.append((c, "success" if op["status"] == 2 else "failure"))
                    break
        if not out:
            out = [(c, "reward") for c in self.containers if c["kind"] == "rule"
                   and any(op.get("op") == "give_item" for op in c.get("ops") or [])]
        return out


def _list(value):
    if value is None:
        return []
    return [value] if isinstance(value, str) else list(value)


def _flat_checks(checks):
    for check in checks or []:
        yield check
        if check.get("type") == "not":
            yield from _flat_checks([check["check"]])
        elif check.get("type") == "any":
            yield from _flat_checks(check.get("checks"))


def _checks_with_polarity(checks, positive=True):
    for check in checks or []:
        if check.get("type") == "not":
            yield from _checks_with_polarity([check["check"]], not positive)
        elif check.get("type") == "any":
            yield from _checks_with_polarity(check.get("checks"), positive)
        else:
            yield check, positive


def _nodes(c):
    graph = c.get("graph") if isinstance(c.get("graph"), dict) else {}
    for key, node in (graph.get("nodes") or {}).items():
        yield key, node, None


def _choices(c):
    for key, node, _ in _nodes(c):
        for choice in node.get("choices", []):
            yield key, node, choice


def describe(c):
    who = f" with {c['npc']}" if c.get("npc") else ""
    return f"{c['kind']} {c['id']}{who}" if c["kind"] != "graph" else f"conversation{who}"


# ---------------------------------------------------------------- the audit

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
        g, s = self.game, self.story
        report = {"story": s.name, "title": s.title}
        # 1. items
        items = []
        for item, uses in sorted(s.item_needs().items()):
            sources = self.sources(item)
            story_made = self.made_by_story(item)
            reach = t_or([x["reach"] for x in sources] + ([TRUE] if story_made else []))
            entry = {"item": item, "name": g.items.get(item, {}).get("name"), "known": item in g.items or not g.items,
                     "uses": uses, "sources": sources, "story": story_made, "reach": reach}
            items.append(entry)
            if not entry["known"]:
                self.blockers.append(f"item {item} does not exist in the game")
            elif reach == FALSE or not (sources or story_made):
                self.blockers.append(f"item {item} has no source a guildless hero can reach in chapter 1 "
                                     f"({'; '.join(uses[:2])})")
            elif reach == MAYBE and not any(x["reach"] == TRUE for x in sources) and not story_made:
                self.caveats.append(f"item {item}: only conditional sources ({sources[0]['text']})")
        report["items"] = items
        waiting = {}                # a rule that waits for a story's own item also fires on every other copy
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
        # 2. quests
        quests, by_key = [], {}
        for check, positive, where, _, _ in s.checks_of("quest"):
            var, state = check["quest"].upper(), check["state"]
            if (var, state, positive) in by_key:
                if where not in by_key[(var, state, positive)]["where"]:
                    by_key[(var, state, positive)]["where"].append(where)
                continue
            constant = QUEST_STATE.get(state)
            if constant is None:
                reach, setters = TRUE, []
            else:
                reach, setters = g.quest_reachable(var, constant)
            started, starters = g.quest_reachable(var, "LOG_RUNNING")
            exists = any(var in q.get("variables", []) for q in g.quests.values()) or bool(setters or starters)
            entry = {"quest": var, "state": state, "positive": positive, "where": [where], "reach": reach,
                     "exists": exists, "setters": _dedupe(setters), "starters": _dedupe(starters), "started": started}
            by_key[(var, state, positive)] = entry
            quests.append(entry)
            if not exists:
                self.blockers.append(f"quest variable {var} does not exist")
            elif positive and reach == FALSE:
                self.caveats.append(f"quest {var} can never be {state} in chapter {CHAPTER} without a guild; "
                                    f"the check on {where} is a dead option")
        report["quests"] = quests
        # 3. topics heard
        heard, by_info = [], {}
        for check, positive, where, _, _ in s.checks_of("heard"):
            did = check["info"].upper()
            if (did, positive) in by_info:
                if where not in by_info[(did, positive)]["where"]:
                    by_info[(did, positive)]["where"].append(where)
                continue
            d = g.dialogues.get(did)
            reach, why = g.dialogue_reachable(did)
            entry = {"info": did, "where": [where], "positive": positive, "exists": d is not None, "reach": reach,
                     "why": why}
            by_info[(did, positive)] = entry
            if d:
                entry["npc"] = d.get("npc")
                entry["important"] = not d.get("description")
                entry["condition"] = [e.get("if", []) for e in (d.get("condition") or {}).get("effects", [])
                                      if e.get("return") not in ("FALSE", "0")]
                entry["needs"] = sorted(set(re.findall(r'NPC_KNOWSINFO\(\w+, (\w+)\)', json.dumps(entry["condition"]))))
            heard.append(entry)
            if positive and d is None:
                self.blockers.append(f"topic {did} does not exist ({where})")
            elif positive and reach == FALSE:
                self.blockers.append(f"topic {did} cannot be heard in chapter 1 without a guild: {why}")
        report["heard"] = heard
        # 4. people and hours
        report["people"] = self.people()
        # 5. objects
        report["objects"] = self.objects()
        # 6. made by the story
        report["placed"] = [{"item": i, "waypoint": w, "exists": (w or "").upper() in g.waypoints or not g.waypoints,
                             "by": describe(p) if p else "at start"} for i, w, p in s.placed]
        for p in report["placed"]:
            if not p["exists"]:
                self.blockers.append(f"place_item {p['item']}: no waypoint {p['waypoint']} in {WORLD}")
        report["renamed"] = [{"npc": n, "name": name, "was": (g.people.get(n) or {}).get("name")}
                             for n, name in s.renamed]
        # attached conversations hide the NPC's own
        report["attached"] = self.attached(quests, heard)
        # endings
        report["endings"] = self.endings(quests, heard)
        # other stories
        report["shared"] = self.shared()
        report["blockers"], report["caveats"] = _unique(self.blockers), _unique(self.caveats)
        report["verdict"] = ("blocked" if report["blockers"] else "playable with caveats" if report["caveats"]
                             else "playable end to end")
        return report

    # -------------------------------------------------------- people

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
        g = self.game
        windows = self.windows()
        out = []
        for npc, roles in sorted(self.story.npcs.items()):
            present, where = g.presence(npc)
            entry = {"npc": npc, "label": g.label(npc), "roles": sorted(roles), "present": present, "where": where,
                     "routine": g.routine_of(npc), "day": g.places(npc), "windows": [],
                     "swaps": sorted({f"{r} via {d}" for r, d in g.swaps.get(g.instance(npc), [])})[:6]}
            if present == FALSE and roles - {"watcher"}:
                self.blockers.append(f"{g.label(npc)} is not in Khorinis in chapter 1 ({where})")
            for window, why in windows.get(npc, []):
                found = self.availability(npc, window)
                if found is None:
                    entry["windows"].append({"why": why, "status": "unknown routine"})
                    continue
                status = ("never awake then" if not found["awake"] else
                          "asleep part of the time" if found["asleep"] else "awake")
                entry["windows"].append({"why": why, "status": status, "awake": spans(found["awake"]),
                                         "asleep": spans(found["asleep"]), "doing": found["doing"]})
                if status == "never awake then":
                    self.blockers.append(f"{g.label(npc)} sleeps through {why}")
                elif status != "awake":
                    self.caveats.append(f"{g.label(npc)} sleeps {spans(found['asleep'])} inside {why}; "
                                        f"usable only {spans(found['awake'])}")
            for check, positive, where_, c, _ in self.story.checks_of("npc_state"):
                if (check["npc"].upper() != npc or not positive):
                    continue
                activity = STATE_ACTIVITY.get(check["state"])
                if activity is None:
                    continue          # a spell, a blow: the hero causes it himself
                hours = set()
                for start, end, act, wp in g.schedule(g.routine_of(npc)):
                    if act == activity:
                        hours |= minutes(start, end)
                others = [r for r in g.other_routines(npc) if any(a == activity for a, *_ in g.routines.get(r, []))]
                entry["windows"].append({"why": f"{check['state']} on {where_}", "status":
                                         "in his routine" if hours else "not in his chapter-1 routine",
                                         "awake": spans(hours),
                                         "doing": [f"only in {', '.join(others)}"] if others and not hours else []})
                if not hours:
                    self.blockers.append(f"{g.label(npc)} is never {check['state']} by his chapter-1 routine "
                                         f"({where_})" + (f"; only in {', '.join(others)}" if others else ""))
            out.append(entry)
        return out

    # -------------------------------------------------------- objects

    def objects(self):
        g = self.game
        out = []
        known = list(g.mobs)
        for c in self.story.containers:
            on = c.get("on") or {}
            if on.get("event") != "used_object" or not on.get("near"):
                continue
            x, z, metres = on["near"]
            scheme = (on.get("object") or "").upper()
            candidates = [(s, ox, oz) for s, ox, oz in known if not scheme or scheme in s]
            target = None
            if candidates:
                best = min(candidates, key=lambda o: (o[1] - x) ** 2 + (o[2] - z) ** 2)
                if math.hypot(best[1] - x, best[2] - z) <= metres * 100:
                    target = best
            window = set(range(1440))
            hour_checks = [ch for ch, pos in _checks_with_polarity(c["checks"]) if ch["type"] == "hour" and pos]
            for ch in hour_checks:
                window &= hour_window(ch)
            entry = {"rule": c["id"], "near": on["near"], "scheme": scheme or "any", "object": target,
                     "window": spans(window), "users": []}
            fills = [f for f in c["requires"] if self.story.setters_of(f)]
            entry["filled_by"] = sorted({describe(x) for f in fills for x in self.story.setters_of(f)})
            fill_hours = set()
            for f in fills:
                for x in self.story.setters_of(f):
                    found = [ch for ch, pos in _checks_with_polarity(x["checks"]) if ch["type"] == "hour" and pos]
                    found += [ch for _, _, choice in _choices(x)
                              for ch, pos in _checks_with_polarity(choice.get("checks"))
                              if ch["type"] == "hour" and pos]
                    for ch in found:
                        fill_hours |= hour_window(ch)
            entry["fill_hours"] = spans(fill_hours) if fill_hours else None
            if target is None:
                self.caveats.append(f"used_object {c['id']}: no known object within {metres} m of ({x}, {z})")
                out.append(entry)
                continue
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
                        entry["users"].append({
                            "npc": npc, "label": g.label(npc), "routine": routine, "waypoint": wp,
                            "hours": spans(minutes(start, end)), "overlap": spans(minutes(start, end) & window),
                            "chapter1": chapter1,
                            "how": "chapter-1 routine" if chapter1 else
                            f"only in {routine}" + (f", set by {', '.join(sorted(set(via)))}" if via else "")})
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
            out.append(entry)
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
        s = self.story
        promised = s.endings()

        def fixpoint(real):
            flags, active, failing = set(), set(), {}
            items = {name for name, _, parent in s.placed + s.given if parent is None}
            changed = True
            while changed:
                changed = False
                for i, c in enumerate(s.containers):
                    parent = c.get("parent")
                    if parent is not None and id(parent) not in active:
                        continue
                    if not all(f in flags for f in c["requires"]):
                        continue
                    reasons = []
                    if real:
                        for check in c["checks"]:
                            ok, why = self.gate(check, c.get("npc"), items)
                            if not ok:
                                reasons.append(why)
                        on = c.get("on") or {}
                        if on.get("event") in ("took_item", "read_item") and on.get("item"):
                            item = on["item"].upper()
                            placed = any(name == item for name, _, _ in s.placed)
                            ok = placed or item in items or bool(self.sources(item))
                            if not ok:
                                reasons.append(f"{item} is nowhere to take")
                        for field in ("target", "seen_by"):
                            if on.get(field) and on[field] != "PLAYER" and self.game.presence(on[field])[0] == FALSE:
                                reasons.append(f"{on[field]} is not in Khorinis")
                    if reasons:
                        failing[c["id"]] = reasons
                        continue
                    failing.pop(c["id"], None)
                    if id(c) not in active:
                        active.add(id(c))
                        changed = True
                    for op in c.get("ops") or []:
                        if op.get("op") == "set_flag" and op.get("value") and op["name"] not in flags:
                            flags.add(op["name"])
                            changed = True
                        if op.get("op") in ("give_item", "place_item") and op.get("instance", "").upper() not in items:
                            items.add(op["instance"].upper())
                            changed = True
                    graph = c.get("graph") if isinstance(c.get("graph"), dict) else None
                    if not graph:
                        continue
                    seen, todo = set(), [graph.get("start")]
                    while todo:
                        key = todo.pop()
                        node = graph["nodes"].get(key)
                        if key in seen or node is None:
                            continue
                        seen.add(key)
                        for flag in _list(node.get("sets")):
                            if flag not in flags:
                                flags.add(flag)
                                changed = True
                        if node.get("returns"):
                            todo.append(node["returns"])
                        for choice in node.get("choices", []):
                            required = choice.get("requires")
                            if required and not any(f in flags for f in required):
                                continue
                            if real:
                                bad = [self.gate(ch, c.get("npc"), items) for ch in choice.get("checks") or []]
                                bad = [why for ok, why in bad if not ok]
                                if choice.get("takes"):
                                    ok, why = self.gate({"type": "has_item", "item": choice["takes"]["item"]},
                                                        c.get("npc"), items)
                                    if not ok:
                                        bad.append(why)
                                if bad:
                                    failing[f"{c['id']}:{key}:{choice.get('text', '')[:20]}"] = bad
                                    continue
                            if choice.get("gives") and choice["gives"]["item"].upper() not in items:
                                items.add(choice["gives"]["item"].upper())
                                changed = True
                            if choice.get("goto"):
                                todo.append(choice["goto"])
            return flags, active, failing

        ideal_flags, ideal_active, _ = fixpoint(False)
        real_flags, real_active, failing = fixpoint(True)
        out = []
        for c, kind in promised:
            if id(c) in real_active:
                status = "reachable"
            elif id(c) in ideal_active:
                status = "blocked by the game"
            else:
                status = "unreachable in the story itself"
            missing = [f for f in c["requires"] if f not in real_flags]
            out.append({"rule": c["id"], "kind": kind, "status": status, "missing": missing})
        reachable = [e for e in out if e["status"] == "reachable"]
        lost = [e for e in out if e["status"] != "reachable"]
        reasons = sorted({r for rs in failing.values() for r in rs})
        if promised and not reachable:
            self.blockers.append("no ending can be reached in the game" + (f": {'; '.join(reasons[:4])}" if reasons else ""))
        for e in lost:
            if e["status"] == "blocked by the game":
                self.caveats.append(f"ending {e['rule']} ({e['kind']}) cannot be reached in the game"
                                    + (f": {'; '.join(reasons[:3])}" if reasons else ""))
            else:
                self.caveats.append(f"ending {e['rule']} ({e['kind']}) is unreachable even ignoring the game "
                                    f"(missing {', '.join(e['missing'])}); see check_story.py")
        return {"endings": out, "game_gates_failing": reasons}

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
                pool = [o for o in self.game.mobs if (on.get("object") or "").upper() in o[0]]
                if pool:
                    best = min(pool, key=lambda o: (o[1] - x) ** 2 + (o[2] - z) ** 2)
                    if math.hypot(best[1] - x, best[2] - z) <= metres * 100:
                        found.add((round(best[1]), round(best[2])))
                        continue
                found.add((round(x), round(z)))
        return found


def _dedupe(setters):
    out, seen = [], set()
    for x in setters:
        if x["by"] not in seen:
            seen.add(x["by"])
            out.append(x)
    return out


def _unique(values):
    out = []
    for v in values:
        if v not in out:
            out.append(v)
    return out


# ---------------------------------------------------------------- output

def markdown(report):
    lines = [f"## {report['title']} ({report['story']})", "", f"**Verdict: {report['verdict']}**", ""]
    for title, key in (("Blocking", "blockers"), ("Caveats", "caveats")):
        if report[key]:
            lines.append(f"{title}:")
            lines += [f"- {x}" for x in report[key]]
            lines.append("")
    lines.append("### 1. Items")
    if not report["items"]:
        lines.append("The story needs no item.")
    for item in report["items"]:
        name = f" ({item['name']})" if item.get("name") else ""
        lines.append(f"- **{item['item']}**{name}: reachable {item['reach']}. Used by: {'; '.join(item['uses'])}")
        for src in item["story"]:
            lines.append(f"  - story: {src}")
        for src in item["sources"][:8]:
            lines.append(f"  - [{src['reach']}] {src['kind']}: {src['text']}")
        if len(item["sources"]) > 8:
            lines.append(f"  - ... {len(item['sources']) - 8} more sources")
        if not item["sources"] and not item["story"]:
            lines.append("  - no source found")
    lines += ["", "### 2. Quests"]
    if not report["quests"]:
        lines.append("The story checks no quest.")
    for q in report["quests"]:
        sense = "" if q["positive"] else " (inside not: the story also handles the other case)"
        lines.append(f"- **{q['quest']}** = {q['state']}{sense}: reachable {q['reach']}; checked on {'; '.join(q['where'])}"
                     + ("" if q["exists"] else " (no such quest variable)"))
        starters = ", ".join(f"{s['by']} ({s['npc'] or 'script'}, {s['reach']})" for s in q["starters"][:4]) or "nobody"
        lines.append(f"  - started (running) by: {starters}")
        if q["state"] not in ("running", "open"):
            setters = ", ".join(f"{s['by']} ({s['npc'] or 'script'}, {s['reach']})" for s in q["setters"][:4]) or "nobody"
            lines.append(f"  - set to {q['state']} by: {setters}")
    lines += ["", "### 3. Topics heard"]
    if not report["heard"]:
        lines.append("The story waits for no topic of the game's own.")
    for h in report["heard"]:
        if not h["exists"]:
            lines.append(f"- **{h['info']}**: does not exist ({'; '.join(h['where'])})")
            continue
        how = "starts by itself when spoken to" if h.get("important") else "chosen from the menu"
        cond = "; ".join(" and ".join(c) or "always" for c in h["condition"]) or "always"
        lines.append(f"- **{h['info']}** of {h['npc']} ({how}): reachable {h['reach']} ({h['why']}); condition: {cond}; "
                     f"waited for by {'; '.join(h['where'])}")
    lines += ["", "### 4. People and hours"]
    for p in report["people"]:
        lines.append(f"- **{p['label']}** ({', '.join(p['roles'])}): present {p['present']} ({p['where']}); "
                     f"routine {p['routine']}: {p['day']}")
        for w in p["windows"]:
            extra = f"; awake {w.get('awake')}" if w.get("awake") else ""
            asleep = f"; asleep {w['asleep']}" if w.get("asleep") and w["asleep"] != "never" else ""
            lines.append(f"  - needed for {w['why']}: {w['status']}{extra}{asleep}"
                         + (f" ({'; '.join(w['doing'])})" if w.get("doing") else ""))
        if p["swaps"]:
            lines.append(f"  - routine can change: {', '.join(p['swaps'])}")
    lines += ["", "### 5. Objects"]
    if not report["objects"]:
        lines.append("The story waits for no used object.")
    for o in report["objects"]:
        target = f"({o['object'][1]}, {o['object'][2]})" if o["object"] else "no known object"
        filled = (f"; filled through {', '.join(o['filled_by'])}" + (f" at {o['fill_hours']}" if o.get("fill_hours") else "")
                  if o["filled_by"] else "; never filled by a conversation")
        lines.append(f"- rule **{o['rule']}**: {o['scheme']} object {target}, allowed {o['window']}{filled}")
        for u in o["users"]:
            lines.append(f"  - {u['label']} at {u['waypoint']} {u['hours']} ({u['how']}): overlap {u['overlap']}, "
                         f"{u.get('status', '')}")
        if o["object"] and not o["users"]:
            lines.append("  - no NPC routine uses it")
    lines += ["", "### 6. Made by the story"]
    for p in report["placed"]:
        lines.append(f"- places {p['item']} at {p['waypoint']} ({p['by']})" + ("" if p["exists"] else " (no such waypoint)"))
    for r in report["renamed"]:
        lines.append(f"- renames {r['npc']} ({r['was']}) to {r['name']}")
    for a in report["attached"]:
        lines.append(f"- replaces the conversations of {a['npc']} ({a['own']} own topics hidden)"
                     + (f"; needed: {', '.join(a['needed'])}" if a["needed"] else ""))
    lines += ["", "### Endings"]
    for e in report["endings"]["endings"]:
        lines.append(f"- {e['rule']} ({e['kind']}): {e['status']}")
    if report["endings"]["game_gates_failing"]:
        lines.append(f"- game gates that fail: {'; '.join(report['endings']['game_gates_failing'])}")
    if report["shared"]:
        lines += ["", "### Other stories in the same game"]
        lines += [f"- {x}" for x in report["shared"]]
    lines.append("")
    return "\n".join(lines)


def summary(report):
    return {"story": report["story"], "title": report["title"], "verdict": report["verdict"],
            "blockers": report["blockers"], "caveats": report["caveats"],
            "items": {i["item"]: i["reach"] for i in report["items"]},
            "quests": {f"{q['quest']}={q['state']}": q["reach"] for q in report["quests"]},
            "heard": {h["info"]: h["reach"] for h in report["heard"]},
            "endings": {e["rule"]: e["status"] for e in report["endings"]["endings"]}}


LIMITS = """### What the data cannot tell

- Interactive objects (water pipes, alchemy benches) are not in world.jsonl; pipe positions come from KNOWN_OBJECTS
  and bench locations are inferred from NPCs whose routine works one.
- Conditions are read three-valued: chapter 1 and no guild are certain, every other script variable counts as
  something the hero can still bring about. "maybe" is not a promise.
- Monster loot, ambient guild inventories and random treasure are not followed; NPC starting inventories only when
  GOTHIC.DAT is readable.
- Routines changed by dialogue are listed, not followed; a quest that moves an NPC can change these hours.
- Prices, the hero's gold, talents he must learn and fights he must win are not judged.
"""


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("stories", nargs="+")
    parser.add_argument("--json", action="store_true", help="print a JSON summary instead of Markdown")
    parser.add_argument("--game", help="Gothic install, for the NPCs' starting inventories")
    parser.add_argument("--mechanics", default=str(MECHANICS))
    parser.add_argument("--map", default=str(MAP_DATA))
    args = parser.parse_args(argv)
    game = load_game(args.mechanics, args.map, args.game)
    stories = [Story(json.loads(pathlib.Path(p).read_text(encoding="utf-8")), pathlib.Path(p).stem) for p in args.stories]
    reports = [Audit(s, game, [o for o in stories if o is not s]).run() for s in stories]
    if args.json:
        print(json.dumps([summary(r) for r in reports], ensure_ascii=False, indent=1))
        return
    print("# Playability audit\n")
    print("Chapter 1, hero without a guild. " + ("NPC inventories read from GOTHIC.DAT." if game.inventories is not None
                                                else "GOTHIC.DAT not read: NPC inventories unknown.") + "\n")
    for r in reports:
        print(f"- {r['title']} ({r['story']}): **{r['verdict']}**")
    print()
    for r in reports:
        print(markdown(r))
    print(LIMITS)


if __name__ == "__main__":
    main()

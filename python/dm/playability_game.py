"""The game side of the playability audit: what the game's own data says a guildless chapter-1 hero can reach.

Indexes the extracted mechanics (dialogues, functions, quests, world records, NPC routines) into a Game, reads the
decompiled guards three-valued, and answers whether a dialogue, a quest state or an item is within reach.
playability.py is the entry point; this module knows nothing about stories.
"""

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
                 inventories=None, objects=None, levels=None):
        self.items = {k.upper(): v for k, v in (items or {}).items()}
        self.dialogues = {d["id"].upper(): d for d in (dialogues or [])}
        self.functions = functions or {}
        self.quests = quests or {}
        self.inventories = inventories          # instance -> {item: count}; None when GOTHIC.DAT was not read
        self.levels = {k.upper(): v.get("level") for k, v in (levels or {}).items()}   # read from a running game
        self._read_world(world or [], objects)
        self._read_people(people or {})
        self._read_routines()
        self._dialogue_memo, self._quest_memo = {}, {}
        self._index()

    def _read_world(self, world, objects):
        """Waypoints, placed items, containers and interactive objects of the one world the audit plays in."""
        self.waypoints, self.placed, self.containers, self.mobs = {}, [], [], []
        for r in world:
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

    def _read_people(self, people):
        self.people = {}                        # instance -> {"name", "id", "worlds": {world: spawn}, "routine"}
        for world_name, entries in people.items():
            for p in entries:
                entry = self.people.setdefault(p["instance"].upper(), {"name": p.get("name"), "id": p.get("id"),
                                                                      "worlds": {}, "routine": None})
                entry["worlds"][world_name] = p.get("spawn") or {}
                if world_name == WORLD:
                    entry["routine"] = (p.get("routines") or {}).get(str(CHAPTER))
        self.has_people = bool(self.people)

    def _read_routines(self):
        """The routine functions' schedules, and the script's names for NPC instances (aliases)."""
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
            self._index_dialogue(did, d)
        self.function_gifts = {}        # item -> [(function, guards)]
        self.trade = {}                 # trader instance -> {item: count} in this chapter
        self.inserted = {}              # item -> [spot] put into the world by script in this chapter
        trader_of = self._traders()
        for name, body in self.functions.items():
            self._index_function(name, body, trader_of)

    def _index_dialogue(self, did, d):
        out = []
        self._walk_info(d.get("information"), [], [], out)
        self.effects[did] = out
        npc = (d.get("npc") or "").upper()
        self.npc_dialogues.setdefault(npc, []).append(did)
        for path, guards, e in out:
            self._index_effect(did, d, npc, path, guards, e)

    def _index_effect(self, did, d, npc, path, guards, e):
        """What one dialogue effect does: sets a quest, gives or makes an item, or changes someone's routine."""
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

    def _traders(self):
        """Trader suffix -> NPC instance, as B_GIVETRADEINV binds them."""
        trader_of = {}
        for r in self.functions.get("B_GIVETRADEINV", []):
            m = re.match(r'^B_GIVETRADEINV\.TRD_(\w+) = HLP_GETNPC\((\w+)\)$', r.get("set", ""))
            if m:
                trader_of[m[1]] = m[2]
        return trader_of

    def _index_function(self, name, body, trader_of):
        for r in body:
            m = SET_QUEST.match(r.get("set", ""))
            if m:
                self.quest_setters.setdefault((m[1], m[2]), []).append(("function", name, r.get("if", [])))
        if name.startswith("B_GIVETRADEINV_"):
            inst = trader_of.get(name[len("B_GIVETRADEINV_"):])
            if inst:
                self._index_trade(inst, body)
        elif name.startswith(("STARTUP_NEWWORLD", f"B_ENTER_NEWWORLD_KAPITEL_{CHAPTER}")):
            self._index_inserted(body)
        elif not name.startswith(("B_GIVETRADEINV", "B_CREATEAMBIENTINV", "B_CLEAR", "STARTUP_", "INIT_",
                                  "B_ENTER_")):
            self._index_function_gifts(name, body)

    def _index_trade(self, inst, body):
        """A trader's stock in this chapter."""
        stock = self.trade.setdefault(inst, {})
        for r in body:
            m = CREATE.search(r.get("do", ""))
            guard = " ".join(r.get("if", []))
            chapter = re.search(r'KAPITEL >= (\d+)', guard)
            if m and (not chapter or int(chapter[1]) <= CHAPTER) and "KAPITEL ==" not in guard:
                stock[m[2]] = stock.get(m[2], 0) + _int(m[3], 1)

    def _index_inserted(self, body):
        for r in body:
            m = INSERT_ITEM.search(r.get("do", ""))
            if m:
                self.inserted.setdefault(m[1], []).append(m[2])

    def _index_function_gifts(self, name, body):
        """Items a script function hands to the hero: found ones and ones created on him."""
        for r in body:
            text = r.get("do", "")
            found = [item for _, item in FIND.findall(text)]
            found += [item for target, item, _ in CREATE.findall(text) if target in ("HERO", "OTHER")]
            for item in found:
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
        return (self._placed_sources(item) + self._container_sources(item) + self._trader_sources(item)
                + self._gift_sources(item) + self._recipe_sources(item, depth) + self._carried_sources(item)
                + self._script_sources(item))

    def _placed_sources(self, item):
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
        return out

    def _container_sources(self, item):
        out = []
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
                            "text": label + ", locked: needs a lockpick and the lock-picking talent"})
            elif c.get("key"):
                out.append({"kind": "container", "reach": MAYBE, "text": label + f", locked: needs key {c['key']}"})
            else:
                out.append({"kind": "container", "reach": FALSE, "text": label + ", locked with no pick or key"})
        return out

    def _trader_sources(self, item):
        out = []
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
        return out

    def _gift_sources(self, item):
        out = []
        for did, guards, count in self.gifts.get(item, []):
            if self.dialogues[did].get("npc") == "PC_HERO" or self.presence(self.dialogues[did].get("npc"))[0] == FALSE:
                continue
            reach = t_and([self.dialogue_reachable(did)[0], self.guards(guards)])
            npc = self.dialogues[did].get("npc")
            out.append({"kind": "dialogue", "reach": reach, "npc": npc,
                        "text": f"given in {did} by {self.label(npc)}" + ("" if reach != FALSE else
                                                                         " (not reachable in chapter 1)")})
        return out

    def _recipe_sources(self, item, depth):
        """What the hero can make himself, following each ingredient's own sources two levels deep."""
        out = []
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
        return out

    def _carried_sources(self, item):
        out = []
        if self.inventories is not None:
            for npc, stock in sorted(self.inventories.items()):
                if item in stock and self.presence(npc)[0] != FALSE:
                    out.append({"kind": "carried", "reach": MAYBE,
                                "text": f"carried by {self.label(npc)} ({stock[item]}x), to steal or loot; "
                                        f"at {self.places(npc)}"})
        return out

    def _script_sources(self, item):
        return [{"kind": "script", "reach": MAYBE, "text": f"handed out by script {function}"}
                for function, _ in self.function_gifts.get(item, [])]

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
                world, people, read_inventories(game), levels=read("npc_levels.json", {}))


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

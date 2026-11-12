"""Can a player who knows only what the story has shown him find his way through it?

playability.py proves that every ending can be reached. This asks the other question: whether anything leads the
player there. A story without quest markers lives on pointers: a line that names the next person, a letter that names
a place, a remark that something only happens at night. For every way into the story (a topic in someone's menu, a
conversation, a scene, a deed a rule waits for) it looks for such a pointer in what the player can see elsewhere in
the story, and reports what the player would have to guess.

    python3 python/dm/discoverability.py <story.json>            the findings
    python3 python/dm/discoverability.py <story.json> --dossier  the story as the player meets it, for a naive-player
                                                                  agent (docs/director-brief.md, "Discoverability")

The text search is a heuristic: a name in a line counts as a pointer, so it can be fooled by a name said in passing.
It finds what is missing reliably and what is present only plausibly. Findings are warnings, never errors.
"""

import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
CHARACTERS = HERE / "characters"
GAME_ITEMS = HERE.parent / "dm_runtime" / "mechanics" / "items.json"   # the game's item names (private, quest_mine)

NIGHT_WORDS = ("nacht", "nachts", "abend", "abends", "dunkel", "mond", "spät", "mitternacht", "sterne")
DAY_WORDS = ("mittag", "mittags", "tag", "tags", "morgen", "morgens", "sonne", "hell")
# What a used object is called in speech, by the scheme a rule waits on.
OBJECT_WORDS = {"SMOKE": ("pfeife", "rauch", "wasserpfeife"), "BENCH": ("bank",), "BED": ("bett", "schlaf"),
                "CAULDRON": ("kessel", "koch"), "LAB": ("alchemie", "labor", "brau"), "BOOK": ("buch", "pult", "lese"),
                "ANVIL": ("amboss", "schmied"), "CHEST": ("truhe", "kiste"), "THRONE": ("thron", "stuhl"),
                "PRAY": ("schrein", "bete", "innos", "adanos"), "STOVE": ("herd", "ofen"), "BARBQ": ("spieß", "braten")}
STATE_WORDS = {"ZS_SMOKE_WATERPIPE": ("pfeife", "raucht", "rauch"), "ZS_SLEEP": ("schläft", "schlaf"),
               "ZS_STAND_DRINKING": ("trinkt", "bier", "fass"), "ZS_PRAY_INNOS": ("betet", "gebet")}


def _words(text):
    return set(re.findall(r"[a-zäöüß]+", text.lower()))


def _sheet_names():
    names = {}
    for path in CHARACTERS.glob("*.json"):
        try:
            sheet = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            continue
        name = sheet.get("name")
        if sheet.get("npc") and name and name not in ("Bauer", "Bäuerin", "Söldner", "Bürger"):
            names[sheet["npc"].upper()] = name
    return names


def _game_item_name(instance):
    try:
        return json.loads(GAME_ITEMS.read_text(encoding="utf-8")).get(instance.upper(), {}).get("name", "")
    except (OSError, ValueError):
        return ""


def _walk_ops(ops):
    for op in ops or []:
        if isinstance(op, dict):
            yield op
            yield from _walk_ops(op.get("ops"))


def _graph_texts(graph):
    """Everything the player sees in a conversation, in the order a conversation meets it: NPC lines, again lines,
    variants, the hero's choices."""
    nodes = (graph or {}).get("nodes", {})
    order, queue = [], [graph.get("start")] if graph else []
    while queue:
        key = queue.pop(0)
        if key in order or key not in nodes:
            continue
        order.append(key)
        node = nodes[key]
        queue += [node.get("returns")] + [c.get("goto") for c in node.get("choices", []) or []] \
            + [(c.get("chance") or {}).get("else") for c in node.get("choices", []) or [] if isinstance(c.get("chance"), dict)]
    order += [k for k in nodes if k not in order]
    for node in (nodes[k] for k in order):
        for field in ("line", "again"):
            if isinstance(node.get(field), str):
                yield node[field]
        for variant in node.get("variants", []) or []:
            if isinstance(variant, dict) and isinstance(variant.get("line"), str):
                yield variant["line"]
        for choice in node.get("choices", []) or []:
            if isinstance(choice.get("text"), str):
                yield choice["text"]


def model(story):
    """Ways into the story, what each needs a pointer to, and every text the player can see, by source."""
    names = _sheet_names()
    for character in story.get("new_characters") or []:
        if isinstance(character, dict) and character.get("npc") and character.get("name"):
            names[character["npc"].upper()] = character["name"]
    items = {}
    for op in _walk_ops(story.get("plan")):
        if op.get("op") == "rename_npc":
            names[str(op.get("instance", "")).upper()] = op.get("display_name", "")
        if op.get("op") == "spawn_creature":
            names[f"creature:{op.get('id')}"] = op.get("name", "")
        if op.get("op") == "define_item":
            items[str(op.get("item", "")).upper()] = op.get("name", "")

    entries, texts = [], []
    for op in _walk_ops(story.get("plan")):
        kind = op.get("op")
        # Each way in its own source: a conversation attached for good has no id, so it goes by its NPC.
        source = op.get("id") or (f"{kind}:{str(op.get('npc', '')).upper()}" if op.get("npc") else kind)
        if kind in ("add_topic", "add_scene", "attach_dialogue_graph"):
            npc = str(op.get("npc", "")).upper()
            entries.append({"id": source, "kind": kind, "npc": npc, "title": op.get("title"),
                            "checks": op.get("checks") or [], "requires": op.get("requires") or []})
            texts += [(source, t) for t in _graph_texts(op.get("graph"))]
            if op.get("title"):
                texts.append((source, op["title"]))
        elif kind == "add_rule":
            if op.get("on"):
                entries.append({"id": source, "kind": "deed", "on": op["on"], "checks": op.get("checks") or [],
                                "requires": op.get("when") or []})
        elif kind == "narrate":
            texts.append(("narrate", op.get("text", "")))
        elif kind == "journal":
            texts.append(("journal", op.get("entry", "")))
        elif kind == "define_item":
            texts.append((f"item:{op.get('item')}", " ".join([op.get("name", ""), op.get("description", "")]
                                                               + [str(r[0]) for r in op.get("rows", []) if r])))
    for key, graph in (story.get("conversations") or {}).items():
        if not any(t for s, t in texts if s == key):
            texts += [(key, t) for t in _graph_texts(graph)]
    return {"names": names, "items": items, "entries": entries, "texts": texts}


def _mentions(texts, words, besides):
    """Sources other than `besides` whose text names one of the words."""
    wanted = {w.lower() for w in words if w}
    return sorted({source for source, text in texts if source != besides and _words(text) & wanted})


GENERIC = {"bauer", "baeuerin", "buerger", "buergerin", "soeldner", "wache", "miliz", "novize", "pirat", "bandit"}


def _person_words(name):
    return [w for w in re.findall(r"[a-zäöüß]+", (name or "").lower()) if len(w) > 2 and w not in GENERIC]


def _name(names, instance):
    """A person's name: from a sheet or the story, else the last part of a named instance (VLK_407_HAKON: Hakon)."""
    if instance in names:
        return names[instance]
    last = instance.split("_")[-1]
    return "" if last.lower() in GENERIC or last.isdigit() else last.capitalize()


def findings(story):
    m = model(story)
    texts, names, out = m["texts"], m["names"], []
    for entry in m["entries"]:
        checks = json.dumps(entry["checks"])
        met = "heard" in checks   # a topic of someone the hero has already talked to in the game
        if entry["kind"] in ("add_topic", "attach_dialogue_graph"):
            who = _name(names, entry["npc"]) or entry["npc"]
            pointers = _mentions(texts, _person_words(_name(names, entry["npc"])), entry["id"])
            if not pointers and not entry["requires"]:
                out.append({"id": entry["id"], "level": "hook" if met else "guess",
                            "text": f"nothing leads to {who}: the player must think of talking to {who} himself"
                                    + (" (someone he has met, so a new topic shows the next time he does)" if met else "")})
            elif not pointers:
                out.append({"id": entry["id"], "level": "guess" if not met else "hint",
                            "text": f"{who} is never named elsewhere; the player finds this topic only by talking to "
                                    f"{who} again after the story has moved on"})
        if entry["kind"] == "add_scene" and not entry["requires"]:
            out.append({"id": entry["id"], "level": "hook", "text": "a scene: the NPC comes to the player"})
        for check in entry["checks"]:
            wanted = None
            if check.get("type") == "hour":
                night = check["from"] >= 18 or check["to"] <= 6 or check["from"] > check["to"]
                wanted = NIGHT_WORDS if night else DAY_WORDS
                what = f"only between {check['from']} and {check['to']} o'clock"
            elif check.get("type") == "npc_state" and check.get("state") in STATE_WORDS:
                wanted, what = STATE_WORDS[check["state"]], f"only while {check['npc']} is {check['state']}"
            if wanted and not _mentions(texts, wanted, entry["id"]):
                out.append({"id": entry["id"], "level": "guess", "text": f"{what}, and no line says so"})
        if entry["kind"] == "deed":
            on, words = entry["on"], []
            if on.get("item"):
                words = _person_words(m["items"].get(on["item"].upper()) or _game_item_name(on["item"])
                                      or on["item"].split("_")[-1])
            elif on.get("object"):
                words = next((v for k, v in OBJECT_WORDS.items() if k in on["object"].upper()), ())
            elif on.get("creature"):
                words = _person_words(names.get(f"creature:{on['creature']}", on["creature"]))
            elif on.get("target") and on["target"] != "PLAYER":
                words = _person_words(_name(names, on["target"].upper()))
            if words and not _mentions(texts, words, entry["id"]):
                out.append({"id": entry["id"], "level": "guess",
                            "text": f"the rule waits for a deed ({on['event']}) nothing in the story points at"})
    return out


def warnings(story):
    """Findings as checker warnings: what the player would have to guess."""
    found = findings(story)
    open_from_start = [e for e in model(story)["entries"] if e["kind"] != "deed" and not e["requires"]]
    out = [f"discoverability: {f['id']}: {f['text']}" for f in found if f["level"] == "guess"]
    if not open_from_start:
        out.append("discoverability: no hook: no scene comes to the player and every topic waits to be found")
    return out


def dossier(story):
    """The story as the player can meet it, without its hidden truth, plot or the author's notes: what a naive-player
    agent gets to judge where it would get stuck."""
    m = model(story)
    lines = [f"# {story.get('title', 'Eine Geschichte')}", "",
             "You are a player of Gothic II. Below is everything this side story can show you, grouped by where it "
             "appears, with the conditions under which it appears. You do not know the solution. For each step, say "
             "what you would do next and why, and name every point where nothing tells you where to go, whom to ask, "
             "or when. Do not assume you can see this list in the game: you only see a group once you are there.", ""]
    for entry in m["entries"]:
        who = m["names"].get(entry.get("npc", ""), entry.get("npc", ""))
        if entry["kind"] == "deed":
            head = f"## A deed the story waits for: {entry['on']}"
        else:
            head = f"## {'Topic' if entry['kind'] == 'add_topic' else 'Conversation'} with {who}" + \
                   (f": \"{entry['title']}\"" if entry.get("title") else "")
        conditions = []
        if entry["requires"]:
            conditions.append("after: " + ", ".join(entry["requires"]))
        for check in entry["checks"]:
            conditions.append(json.dumps(check, ensure_ascii=False))
        lines += [head, "", "Appears " + ("when " + "; ".join(conditions) if conditions else "from the start"), ""]
        lines += [f"- {text}" for source, text in m["texts"] if source == entry["id"]]
        lines.append("")
    rest = [(s, t) for s, t in m["texts"] if s in ("narrate", "journal") or s.startswith("item:")]
    if rest:
        lines += ["## Other things you may see (narrator, journal, items)", ""] + [f"- {t}" for _, t in rest]
    return "\n".join(lines)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    data = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
    if "--dossier" in sys.argv:
        print(dossier(data))
    else:
        for finding in findings(data):
            print(f"{finding['level']:5}  {finding['id']}: {finding['text']}")

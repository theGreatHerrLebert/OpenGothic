"""Joins quest_mine.py's output with the world dump into quests and mechanism candidates.

    python3 python/dm/quest_graph.py <mechanics directory> <OU.BIN>

Reads dialogues.json, functions.json, items.json, world.jsonl. Writes lines.json, quests.json, rules.json and
candidates.json next to them. Candidates are found by plain rules, so each is a lead for a person to judge.
"""

import collections
import json
import pathlib
import re
import sys

SET = re.compile(r"^([A-Z_0-9.\[\]]+) = (.+)$")
NAME = re.compile(r"\b(?:MIS_|[A-Z]+_)[A-Z0-9_]+\b")
ITEM = re.compile(r"\bIT[A-Z]{2}_[A-Z0-9_]+\b")
CALL_LOG = re.compile(r'(?:LOG_CREATETOPIC|B_LOGENTRY|LOG_ADDENTRY|LOG_SETTOPICSTATUS)\("([^"]+)"')


def flatten(tree):
    if not tree:
        return
    yield from tree["effects"]
    for sub in tree.get("choices", {}).values():
        yield from flatten(sub)


def dumps(o):
    return json.dumps(o, ensure_ascii=False)


def spoken(information):
    return re.findall(r'AI_OUTPUT\([^,]+, [^,]+, "([^"]+)"\)', dumps(list(flatten(information))).replace('\\"', '"'))


def read_lines(path):
    """OU.BIN stores each subtitle directly before its sound file name."""
    raw = pathlib.Path(path).read_bytes().decode("latin-1")
    found = {}
    for m in re.finditer(r"([^\x00-\x1f]{2,})[\x00-\x1f ]+.{0,8}?(DIA_[A-Za-z0-9_]+|[A-Za-z0-9_]+_\d\d_\d\d)\.WAV", raw):
        found.setdefault(m.group(2).upper(), m.group(1).strip())
    return found


def main():
    base = pathlib.Path(sys.argv[1])
    load = lambda n: json.loads((base / n).read_text(encoding="utf-8"))
    dialogues, functions, items = load("dialogues.json"), load("functions.json"), load("items.json")
    world = [json.loads(l) for l in (base / "world.jsonl").read_text(encoding="utf-8").splitlines()]
    lines = read_lines(sys.argv[2])
    (base / "lines.json").write_text(dumps(lines), encoding="utf-8")

    records = {}
    for d in dialogues:
        effects = list(flatten(d["information"]))
        text = dumps(effects)
        condition = dumps(d["condition"])
        writes = [SET.match(e["set"]).groups() for e in effects if "set" in e and SET.match(e["set"])]
        records[d["id"]] = {
            "d": d, "effects": effects, "text": text, "condition": condition, "writes": writes,
            "needs": sorted(set(re.findall(r"NPC_KNOWSINFO\([^,]+, ([A-Z0-9_]+)\)", condition))),
            "reads": sorted(set(NAME.findall(condition)) - {"NPC_ISINSTATE"}),
            "topics": sorted(set(CALL_LOG.findall(text.replace('\\"', '"')))),
            "said": [lines.get(k.upper(), "") for k in spoken(d["information"])],
        }

    # Layer 1: quests. A topic owns the mission variables written beside its log entries.
    quest_vars = collections.defaultdict(set)
    for r in records.values():
        for topic in r["topics"]:
            quest_vars[topic] |= {k for k, _ in r["writes"] if k.startswith("MIS_")}
    quests = {}
    for topic, variables in quest_vars.items():
        members = sorted(i for i, r in records.items() if topic in r["topics"] or variables & (set(r["reads"]) | {k for k, _ in r["writes"]}))
        edges = [[b, i, "knows"] for i in members for b in records[i]["needs"] if b in members]
        writers = collections.defaultdict(list)
        for i in members:
            for k, _ in records[i]["writes"]:
                writers[k].append(i)
        edges += [[w, i, v] for i in members for v in records[i]["reads"] for w in writers.get(v, []) if w != i]
        quests[topic] = {"variables": sorted(variables), "dialogues": members, "npcs": sorted({records[i]["d"]["npc"] for i in members if records[i]["d"]["npc"]}), "edges": edges}
    (base / "quests.json").write_text(dumps(quests), encoding="utf-8")

    # Layer 2: general rules.
    rules = {"spells": {}, "use": {}, "crime": sorted(k for k in functions if re.search("PETZ|CRIME|ABSOLUTION", k))}
    for name, body in functions.items():
        if name.startswith("SPELL_LOGIC_"):
            rules["spells"][name[12:]] = [{"state": re.findall(r"AI_STARTSTATE\([^,]+, ([A-Z_]+)", r["do"])[0], "if": r.get("if", [])}
                                          for r in body if "do" in r and "AI_STARTSTATE" in r["do"]]
        elif name.startswith("USE"):
            rules["use"][name] = [r.get("do") or r.get("set") for r in body][:12]
    (base / "rules.json").write_text(dumps(rules), encoding="utf-8")

    # Layer 3 joined: where an item can come from.
    placed, stored = collections.Counter(), collections.Counter()
    for v in world:
        if v["kind"] == "item":
            placed[v["instance"].upper()] += 1
        elif v["kind"] == "container":
            for part in filter(None, v["contents"].upper().split(",")):
                stored[part.split(":")[0].strip()] += 1
    traded = collections.Counter(i for n, b in functions.items() if n.startswith("B_GIVETRADEINV") for i in set(ITEM.findall(dumps(b))))
    given = collections.Counter(i for r in records.values() for i in ITEM.findall(" ".join(e["do"] for e in r["effects"] if "CREATEINVITEMS" in e.get("do", "") or "B_GIVEINVITEMS(SELF" in e.get("do", ""))))

    def show(i):
        r = records[i]
        return {"id": i, "npc": r["d"]["npc"], "choice": r["d"]["description"]}

    out = {}
    # Several written routes to one outcome.
    by_outcome = collections.defaultdict(list)
    for i, r in records.items():
        for k, v in set(r["writes"]):
            if not k.startswith(("DIA_", "SELF.", "OTHER.", "HERO.")) and "." not in k:
                by_outcome[(k, v)].append(i)
    out["many_routes"] = [{"outcome": f"{k} = {v}", "routes": [show(i) for i in ids]} for (k, v), ids in sorted(by_outcome.items(), key=lambda kv: -len(kv[1])) if 3 <= len(ids) <= 14][:60]
    # Clothing, carried items, guild, talents, time, deaths.
    patterns = {"wears": r"NPC_GETEQUIPPEDARMOR|NPC_HASEQUIPPEDARMOR", "guild": r"\.GUILD", "talent": r"NPC_GETTALENTSKILL", "time": r"WLD_ISTIME|WLD_GETDAY", "death": r"NPC_ISDEAD", "crime": r"PETZCRIME",
                "pickpocket": r"C_BEKLAUEN", "place": r"NPC_GETDISTTOWP", "state": r"NPC_ISINSTATE\((?:OTHER|HERO|SELF), ZS_(?!TALK)"}
    out["counts"] = {name: sum(bool(re.search(p, r["condition"])) for r in records.values()) for name, p in patterns.items()}
    out["wears"] = [show(i) for i, r in records.items() if re.search(patterns["wears"], r["condition"])]
    # Item gates, and whether the dialogue tree that needs the item also hands it out.
    gates = collections.defaultdict(list)
    for i, r in records.items():
        for item in set(ITEM.findall(" ".join(re.findall(r"NPC_HASITEMS\((?:OTHER|HERO), ([A-Z0-9_]+)", r["condition"])))):
            gates[item].append(i)
    out["item_gates"] = [{"item": item, "name": items.get(item, {}).get("name"), "used_by": [show(i) for i in ids[:6]], "placed": placed[item], "chests": stored[item], "traders": traded[item], "dialogues": given[item]}
                         for item, ids in sorted(gates.items()) if item != "ITMI_GOLD"]
    # Choices that close each other: one sets a flag, another needs it unset.
    closes = []
    for var, value in {k: 1 for r in records.values() for k, _ in r["writes"] if "." not in k}.items():
        needing = [i for i, r in records.items() if re.search(rf"\({re.escape(var)} == FALSE\)", r["condition"])]
        writers = [i for i, r in records.items() if any(k == var and v == "TRUE" for k, v in r["writes"])]
        if len(needing) >= 2 and len(writers) >= 2 and not var.startswith("DIA_"):
            closes.append({"flag": var, "needs_unset": len(needing), "set_by": len(writers), "examples": [show(i) for i in needing[:4]]})
    out["closes"] = sorted(closes, key=lambda c: -c["needs_unset"])[:40]
    # Hints: spoken lines naming an item the dialogue's own logic never touches.
    words = {}
    for item, info in items.items():
        name = info.get("name")
        if isinstance(name, str) and len(name) >= 7 and not name.startswith("NAME_"):
            words.setdefault(name.lower(), item)
    hints = collections.defaultdict(list)
    for i, r in records.items():
        said = " ".join(r["said"]).lower()
        logic = r["text"].upper() + r["condition"].upper()
        for word, item in words.items():
            if word in said and item not in logic:
                hints[item].append(i)
    out["hints"] = [{"item": item, "name": items[item].get("name"), "lines": [show(i) for i in ids[:5]], "count": len(ids)} for item, ids in sorted(hints.items(), key=lambda kv: -len(kv[1]))][:50]
    locked = [v for v in world if v["kind"] in ("container", "door") and v.get("locked")]
    out["locks"] = {"locked": len(locked), "pick_only": sum(bool(v["pick"]) and not v["key"] for v in locked), "key_only": sum(bool(v["key"]) and not v["pick"] for v in locked), "both": sum(bool(v["pick"]) and bool(v["key"]) for v in locked),
                    "keys": sorted({v["key"].upper() for v in locked if v["key"]})}
    out["layers"] = {"placed_items": sum(placed.values()), "chest_stacks": sum(stored.values())}
    (base / "candidates.json").write_text(dumps(out), encoding="utf-8")
    print(len(lines), "spoken lines,", len(quests), "quests,", len(rules["spells"]), "spells,", len(rules["use"]), "item uses")
    print(out["counts"], out["locks"]["locked"], {k: len(v) for k, v in out.items() if isinstance(v, list)})


if __name__ == "__main__":
    main()

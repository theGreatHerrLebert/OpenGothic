"""The playability audit's output: a report as Markdown, or as a short JSON summary."""

def markdown(report):
    lines = _head(report) + _items(report)
    for section in (_quests, _heard, _people, _objects, _made, _endings):
        lines += [""] + section(report)
    if report["shared"]:
        lines += ["", "### Other stories in the same game"]
        lines += [f"- {x}" for x in report["shared"]]
    lines.append("")
    return "\n".join(lines)


def _head(report):
    lines = [f"## {report['title']} ({report['story']})", "", f"**Verdict: {report['verdict']}**", ""]
    for title, key in (("Blocking", "blockers"), ("Caveats", "caveats")):
        if report[key]:
            lines.append(f"{title}:")
            lines += [f"- {x}" for x in report[key]]
            lines.append("")
    return lines


def _items(report):
    lines = ["### 1. Items"]
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
    return lines


def _who_sets(setters):
    return ", ".join(f"{s['by']} ({s['npc'] or 'script'}, {s['reach']})" for s in setters[:4]) or "nobody"


def _quests(report):
    lines = ["### 2. Quests"]
    if not report["quests"]:
        lines.append("The story checks no quest.")
    for q in report["quests"]:
        sense = "" if q["positive"] else " (inside not: the story also handles the other case)"
        lines.append(f"- **{q['quest']}** = {q['state']}{sense}: reachable {q['reach']}; checked on {'; '.join(q['where'])}"
                     + ("" if q["exists"] else " (no such quest variable)"))
        lines.append(f"  - started (running) by: {_who_sets(q['starters'])}")
        if q["state"] not in ("running", "open"):
            lines.append(f"  - set to {q['state']} by: {_who_sets(q['setters'])}")
    return lines


def _heard(report):
    lines = ["### 3. Topics heard"]
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
    return lines


def _people(report):
    lines = ["### 4. People and hours"]
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
    return lines


def _objects(report):
    lines = ["### 5. Objects"]
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
    return lines


def _made(report):
    lines = ["### 6. Made by the story"]
    for p in report["placed"]:
        lines.append(f"- places {p['item']} at {p['waypoint']} ({p['by']})" + ("" if p["exists"] else " (no such waypoint)"))
    for r in report["renamed"]:
        lines.append(f"- renames {r['npc']} ({r['was']}) to {r['name']}")
    for a in report["attached"]:
        lines.append(f"- replaces the conversations of {a['npc']} ({a['own']} own topics hidden)"
                     + (f"; needed: {', '.join(a['needed'])}" if a["needed"] else ""))
    return lines


def _endings(report):
    lines = ["### Endings"]
    for e in report["endings"]["endings"]:
        lines.append(f"- {e['rule']} ({e['kind']}): {e['status']}")
    if report["endings"]["game_gates_failing"]:
        lines.append(f"- game gates that fail: {'; '.join(report['endings']['game_gates_failing'])}")
    return lines


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

"""Checks a story written for the experiment, against the real names of the game.

    python3 python/dm/check_story.py <story.json> <world_names.json>

A story file holds "title", "significance", "hidden_truth", "plot", "conversations" and "plan", and may hold
"closures" (quiet endings) and "requires": checks that
must hold in the save before the story starts (see checks.py). Prints a JSON report.
"""

import json
import pathlib
import re
import sys
import types

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
gothic = types.ModuleType("gothic")
sys.modules["gothic"] = gothic

from dm import checks, graph, knowledge, story  # noqa: E402

STAGE_DIRECTION = re.compile(r"\([^)]*\)|\*[^*]+\*")


def _spawned(ops):
    """NPCs a plan creates itself. Who is already placed in the world is unknown offline."""
    found = set()
    for op in ops:
        if op.get("op") == "spawn_npc":
            found.add(str(op.get("instance", "")).upper())
        found |= _spawned(op.get("ops", []))
    return found


DEED_CHECKS = {"npc_state", "npc_dead", "hour", "has_item", "wears", "obsessed"}


def deeds(data):
    """What in a story the player does with their hands rather than their mouth: rules that react to an action
    (`on`), and conditions on the state of the world. Guild and conversation flags do not count."""
    found = []

    def walk(o, where):
        if isinstance(o, dict):
            where = o.get("id", where)
            if isinstance(o.get("on"), dict):
                found.append(f"{where}: {o['on'].get('event')}")
            for check in o.get("checks") or []:
                if isinstance(check, dict) and check.get("type") in DEED_CHECKS:
                    found.append(f"{where}: {check['type']}")
            for value in o.values():
                walk(value, where)
        elif isinstance(o, list):
            for value in o:
                walk(value, where)

    walk(data.get("plan", []), "plan")
    walk(data.get("conversations", {}), "conversations")
    return found


SIGNIFICANCE = ("theme", "from_play", "stakes", "choice", "changes")


def significance_problems(block):
    """Why the story matters, as the director brief asks: every answer present and more than a word or two."""
    if block is None:
        return ["no significance: say why this story matters (theme, from_play, stakes, choice, changes); "
                "see 'Why this story' in docs/director-brief.md"]
    if not isinstance(block, dict):
        return ["significance must be an object with theme, from_play, stakes, choice and changes"]
    return [f"significance.{key} is missing or too short to say anything" for key in SIGNIFICANCE
            if not isinstance(block.get(key), str) or len(block[key].split()) < 4]


def _all_ops(ops):
    for op in ops or []:
        if isinstance(op, dict):
            yield op
            yield from _all_ops(op.get("ops"))


def _gold_amounts(value):
    """Every amount of gold the story moves: choices that take or give it, give_item, checks on it."""
    if isinstance(value, list):
        for v in value:
            yield from _gold_amounts(v)
    elif isinstance(value, dict):
        for key in ("takes", "gives"):
            moved = value.get(key)
            if isinstance(moved, dict) and str(moved.get("item", "")).upper() == "ITMI_GOLD":
                yield moved.get("count", 1)
        if str(value.get("instance", value.get("item", ""))).upper() == "ITMI_GOLD" and \
                (value.get("op") == "give_item" or value.get("type") == "has_item"):
            yield value.get("count", 1)
        for v in value.values():
            yield from _gold_amounts(v)


def value_warnings(data):
    """An item of the story's own worth more than any gold the story moves: selling it may beat every choice."""
    amounts = [a for a in _gold_amounts([data.get("plan"), data.get("conversations")]) if isinstance(a, int)]
    if not amounts:
        return []
    top = max(amounts)
    out = []
    for op in _all_ops(data.get("plan")):
        if op.get("op") != "define_item":
            continue
        value = op.get("value")
        inherited = not isinstance(value, int) or value < 0   # no value of its own: the base item's
        if inherited:
            value = _game_item_gold(op.get("like", ""))
        if isinstance(value, int) and value > top:
            out.append(f"item {op.get('item')}: worth {value} gold" + (f" (from {op.get('like')})" if inherited else "")
                       + f", more than the {top} the story trades for anything; selling it may beat every choice. "
                       "Give it a value below what it is traded against, unless that is the point")
    return out


GAME_ITEMS = pathlib.Path(__file__).resolve().parent.parent / "dm_runtime" / "mechanics" / "items.json"


def _game_item_gold(instance):
    """What a game item is worth, from quest_mine's items.json (private), or None without it."""
    try:
        return json.loads(GAME_ITEMS.read_text(encoding="utf-8")).get(str(instance).upper(), {}).get("gold")
    except (OSError, ValueError):
        return None


def softlock_errors(data):
    """Refusals that lock the story: the playability audit, run against the game data when it is there (private,
    dm_runtime/mechanics); without it nothing is said."""
    if not any(op.get("op") == "refuse_talk" for op in _all_ops(data.get("plan"))):
        return []
    try:
        sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
        from playability_analysis import Audit
        from playability_game import load_game
        from playability_story import Story as AuditStory
    except ImportError:
        return []
    if not GAME_ITEMS.exists():
        return []
    audit = Audit(AuditStory(data, "story"), load_game())
    return [text for text in audit.softlocks() and audit.blockers if text.startswith("softlock")]


def duplicate_choice_warnings(data):
    """Two choices in one menu that show at the same time and lead to the same place: the player cannot tell them
    apart. Each choice should say what it does."""
    out = []
    graphs = list((data.get("conversations") or {}).items())
    graphs += [(op.get("id") or op.get("npc"), op["graph"]) for op in _all_ops(data.get("plan"))
               if isinstance(op.get("graph"), dict)]
    seen = set()
    for name, graph_data in graphs:
        for key, node in (graph_data.get("nodes") or {}).items():
            shown = {}
            for choice in node.get("choices") or []:
                when = json.dumps([choice.get("goto"), choice.get("ends"), sorted(choice.get("requires") or []),
                                   choice.get("unless"), choice.get("checks")], sort_keys=True)
                if when in shown and (name, key, when) not in seen:
                    seen.add((name, key, when))
                    out.append(f"{name}: node {key}: \"{shown[when]}\" and \"{choice.get('text')}\" show together and "
                               "lead to the same place; keep one, or make each say what it does")
                shown.setdefault(when, choice.get("text"))
    return out


def ending_warnings(data):
    """Technical weak spots of a story's endings and key items, as the brief's 'Good to play' describes. Warnings only:
    whether a story is good is for the player to say."""
    out = []
    plan = data.get("plan") or []
    own = {str(op.get("item", "")).upper() for op in _all_ops(plan) if op.get("op") == "define_item"}
    for rule in (op for op in _all_ops(plan) if op.get("op") == "add_rule"):
        inner = list(_all_ops(rule.get("ops")))
        closes = any(op.get("op") == "journal" and op.get("status") in (2, 3) for op in inner)
        if closes and not any(op.get("op") == "end_story" for op in inner):
            out.append(f"ending {rule.get('id')}: closes the journal topic but does not end the story (end_story), "
                       "so the story stays open for ever")
        if closes:
            for op in inner:
                item = str(op.get("instance", "")).upper()
                if op.get("op") == "give_item" and item not in own and item != "ITMI_GOLD":
                    out.append(f"ending {rule.get('id')}: rewards a plain game item ({item}); a reward the story is "
                               "about reads better as the story's own (define_item)")
        taken = str((rule.get("on") or {}).get("item", "")).upper()
        if (rule.get("on") or {}).get("event") == "took_item" and taken and taken not in own:
            out.append(f"{rule.get('id')}: waits for a plain game item ({taken}); the player cannot tell it is the "
                       "one the story is about. Make it the story's own (define_item)")
    return out


def lint(data):
    """Defects no conversation-level check sees: story logic that can never happen, and text that cannot be spoken."""
    errors, warnings = [], []
    written, needed, blocked = set(story.HERO_GUILD_FLAGS), {}, {}

    def walk(o, where):
        if isinstance(o, dict):
            if o.get("op") == "set_flag":
                written.add(o.get("flag") or o.get("name"))
            for key, into in (("requires", needed), ("when", needed), ("unless", blocked)):
                value = o.get(key)
                for flag in [value] if isinstance(value, str) else value if isinstance(value, list) else []:
                    into.setdefault(flag, where)
            for key, value in o.items():
                if key == "sets":
                    written.update([value] if isinstance(value, str) else value)
                walk(value, o.get("id", where))
        elif isinstance(o, list):
            for value in o:
                walk(value, where)

    walk(data["conversations"], "conversations")
    walk(data["plan"], "plan")
    walk(data.get("closures") or [], "closures")
    for flag, where in needed.items():
        if flag not in written and not flag.startswith("asked:"):  # the dialogue player writes these itself
            errors.append(f"flag is needed but never set: {flag} ({where})")
    for flag, where in blocked.items():
        if flag not in written:
            warnings.append(f"flag blocks something but is never set: {flag} ({where})")

    for name, conversation in data["conversations"].items():
        nodes = conversation["nodes"]
        seen, frontier = {conversation["start"]}, [conversation["start"]]
        while frontier:
            node = nodes[frontier.pop()]
            for target in [node.get("returns")] + [t for c in node.get("choices", []) for t in graph.choice_targets(c)]:
                if target in nodes and target not in seen:
                    seen.add(target)
                    frontier.append(target)
        for key in nodes:
            if key not in seen:
                errors.append(f"{name}: node can never be reached: {key}")
        for key, node in nodes.items():
            texts = [node.get("line", ""), node.get("again", "")] + [v["line"] for v in node.get("variants", [])] + [c["text"] for c in node.get("choices", [])]
            for text in texts:
                if STAGE_DIRECTION.search(text):
                    errors.append(f"{name}.{key}: stage direction would be read aloud: {text[:50]}")
    if not deeds(data):
        warnings.append("no deed: every way through this story is talking; see 'Deeds, not only words' in "
                        "docs/director-brief.md")
    return errors, warnings


def unlisted_graphs(data):
    """Every dialogue the plan plays, also one inside a rule's ops, must be among the conversations: only those are
    checked for what people know."""
    listed = [json.dumps(g, sort_keys=True) for g in data["conversations"].values()]
    found = []

    def walk(ops):
        for op in ops or []:
            if not isinstance(op, dict):
                continue
            if isinstance(op.get("graph"), dict) and json.dumps(op["graph"], sort_keys=True) not in listed:
                found.append(f"plan: {op.get('op')} {op.get('id') or op.get('npc')} plays a dialogue missing "
                             f"from conversations")
            walk(op.get("ops"))
    walk(data["plan"])
    return found


def check(path, names_path):
    names = json.loads(pathlib.Path(names_path).read_text(encoding="utf-8"))
    npcs, items, waypoints = set(names["npcs"]), set(names["items"]), set(names["waypoints"])

    class Npc:
        dead = False

        def __init__(self, instance):
            self.instance = instance

    class World:
        day, time, generation = 0, (8, 0), 1

        def instance_kind(self, name):
            name = name.upper()
            return "npc" if name in npcs else "item" if name in items else None

        def has_waypoint(self, name):
            return name in waypoints

        def find_npc(self, name):
            return Npc(name.upper()) if name.upper() in npcs and name.upper() not in spawned else None

    errors = []
    data = path if isinstance(path, dict) else json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    spawned = _spawned(data.get("plan", []))
    gothic.world = World()
    for key in ("title", "hidden_truth", "plot", "conversations", "plan"):
        if key not in data:
            errors.append(f"missing field: {key}")
    if errors:
        return {"ok": False, "errors": errors, "warnings": []}

    all_graphs = dict(data["conversations"])
    for name, conversation in all_graphs.items():
        problem = graph.validate(conversation)
        if problem:
            errors.append(f"{name}: {problem}")
    if errors:
        return {"ok": False, "errors": errors, "warnings": []}

    errors += unlisted_graphs(data)
    logic_errors, warnings = knowledge.check(data["plot"], data["conversations"])
    errors += logic_errors
    lint_errors, lint_warnings = lint(data)
    errors += lint_errors
    warnings += lint_warnings

    requires = data.get("requires", [])
    if not isinstance(requires, list):
        errors.append("requires must be a list of checks")
    else:
        problem = checks.validate_all(requires)
        if problem:
            errors.append(f"requires: {problem}")
    errors += significance_problems(data.get("significance"))
    from dm import discoverability
    warnings += discoverability.warnings(data)
    warnings += ending_warnings(data)
    warnings += value_warnings(data)
    warnings += duplicate_choice_warnings(data)
    errors += softlock_errors(data)
    closures = data.get("closures")
    if closures is not None and (not isinstance(closures, list) or not all(isinstance(c, dict) for c in closures)):
        errors.append("closures must be a list of rules")
        closures = []
    if not closures:
        warnings.append("no closure: the story cannot end quietly if it is never finished (a timeout with story_age, "
                        "a chapter change); see 'Endings' in docs/director-brief.md")
    elif not any("story_age" in json.dumps(c) for c in closures):
        warnings.append("no timeout: no closure waits on story_age, so an unfinished story waits for ever")
    scratch = story.Story()
    try:
        from dm import play_story
        start = play_story.prepare({**data, "closures": closures or []}, "check")
        scratch.validate([{"op": "begin_story", "story": "check", "title": data["title"], "day": 0,
                           "cast": start["cast"]}] + start["ops"])
    except story.PlanError as error:
        errors.append(f"plan: {error}")
    except (KeyError, TypeError, AttributeError) as error:
        errors.append(f"plan is malformed: {error!r}")
    return {"ok": not errors, "errors": errors, "warnings": warnings}


if __name__ == "__main__":
    print(json.dumps(check(sys.argv[1], sys.argv[2]), ensure_ascii=False, indent=1))

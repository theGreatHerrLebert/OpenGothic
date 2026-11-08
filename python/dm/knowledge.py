"""Proves a story is solvable and that its dialogue is logically consistent.

A plot has two graphs. Facts and their "needs" edges must form a DAG: a cycle
would make a mystery unsolvable. Conversations may contain cycles, such as
"Zurück", so they are checked by exploring every reachable (node, knowledge)
state. Knowledge only grows, so this always terminates.

    plot = {
      "start": ["fact ids the player knows at the beginning"],
      "facts": {"id": {"text": "...", "essential": True, "needs": [], "topic": False,
                       "known_by": ["NPC_INSTANCE"]}},
      "items": [{"ref": "ITEM", "teaches": ["id"], "needs": []}],
    }

Conversation nodes and choices may add "uses" (facts the line refers to) and
"teaches" (facts it establishes). Choices may be gated by "requires" (any of)
and "unless". A "topic" fact is conversational context, such as who "er" means,
and needs no NPC to know it.

check() returns (errors, warnings). Errors make a story invalid.
"""

MIN_SOURCES = 2


def _visible(choice, known):
    required = choice.get("requires")
    if required and not any(f in known for f in required):
        return False
    return choice.get("unless") not in known


def _explore(graph, known):
    """Return (issues, learned) over every path through one conversation."""
    issues, learned = set(), set(known)
    nodes = graph["nodes"]
    start = graph["start"]
    stack, seen = [(start, frozenset(known))], set()
    while stack:
        key, state = stack.pop()
        if (key, state) in seen:
            continue
        seen.add((key, state))
        node = nodes[key]
        for fact in node.get("uses", []):
            if fact not in state:
                issues.add(f"line uses '{fact}' before it is known: node {key}")
        after = set(state) | set(node.get("teaches", []))
        learned |= after
        for choice in node["choices"]:
            if not _visible(choice, after):
                continue
            for fact in choice.get("uses", []):
                if fact not in after:
                    issues.add(f"hero says '{fact}' before knowing it: node {key}, \"{choice['text']}\"")
            final = after | set(choice.get("teaches", []))
            learned |= final
            if not choice.get("ends"):
                stack.append((choice["goto"], frozenset(final)))
    return issues, learned


def _speaker_issues(npc, graph, facts):
    issues = set()
    for key, node in graph["nodes"].items():
        for fact in set(node.get("uses", [])) | set(node.get("teaches", [])):
            info = facts.get(fact)
            if info and not info.get("topic") and npc not in info.get("known_by", []):
                issues.add(f"{npc} cannot know '{fact}': node {key}")
    return issues


def _references(plot, conversations):
    facts = plot["facts"]
    used = set(plot.get("start", []))
    for info in facts.values():
        used |= set(info.get("needs", []))
    for item in plot.get("items", []):
        used |= set(item.get("teaches", [])) | set(item.get("needs", []))
    for graph in conversations.values():
        for node in graph["nodes"].values():
            used |= set(node.get("uses", [])) | set(node.get("teaches", []))
            for choice in node["choices"]:
                used |= set(choice.get("uses", [])) | set(choice.get("teaches", []))
                used |= set(choice.get("requires", []))
                if choice.get("unless"):
                    used.add(choice["unless"])
    return {f"unknown fact: {fact}" for fact in used - set(facts)}


def _cycle(facts):
    state = {}

    def visit(fact, path):
        state[fact] = "visiting"
        for need in facts[fact].get("needs", []):
            if need not in facts:
                continue
            if state.get(need) == "visiting":
                return path + [fact, need]
            if need not in state:
                found = visit(need, path + [fact])
                if found:
                    return found
        state[fact] = "done"
        return None

    for fact in facts:
        if fact not in state:
            found = visit(fact, [])
            if found:
                return found
    return None


def check(plot, conversations):
    facts = plot["facts"]
    errors = _references(plot, conversations)
    if errors:
        return sorted(errors), []

    cycle = _cycle(facts)
    if cycle:
        return [f"facts depend on each other: {' -> '.join(cycle)}"], []

    for npc, graph in conversations.items():
        errors |= _speaker_issues(npc, graph, facts)

    known = set(plot.get("start", []))
    while True:
        gained = set(known)
        for graph in conversations.values():
            issues, learned = _explore(graph, known)
            errors |= issues
            gained |= learned
        for item in plot.get("items", []):
            if set(item.get("needs", [])) <= known:
                gained |= set(item["teaches"])
        if gained == known:
            break
        for fact in gained - known:
            missing = set(facts[fact].get("needs", [])) - known
            if missing:
                errors.add(f"'{fact}' can be learned before {sorted(missing)}")
        known = gained

    sources = {}
    for npc, graph in conversations.items():
        _, reached = _explore(graph, known)
        taught = set()
        for node in graph["nodes"].values():
            taught |= set(node.get("teaches", []))
            for choice in node["choices"]:
                taught |= set(choice.get("teaches", []))
        for fact in taught & reached:
            sources.setdefault(fact, set()).add(npc)
    for item in plot.get("items", []):
        for fact in item["teaches"]:
            sources.setdefault(fact, set()).add(item["ref"])

    warnings = []
    for fact, info in facts.items():
        if not info.get("essential"):
            continue
        if fact not in known:
            errors.add(f"essential fact can never be learned: {fact}")
        elif len(sources.get(fact, ())) < MIN_SOURCES:
            warnings.append(f"only one source for essential fact: {fact}")
    return sorted(errors), sorted(warnings)

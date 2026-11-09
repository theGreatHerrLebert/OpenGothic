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
MAX_STATES = 200000


def _visible(choice, known):
    required = choice.get("requires")
    if required and not any(f in known for f in required):
        return False
    return choice.get("unless") not in known


def _order_issues(teaches, state, facts):
    issues = set()
    for fact in teaches:
        missing = set(facts.get(fact, {}).get("needs", [])) - set(state) - set(teaches)
        if missing and fact not in state:
            issues.add(f"'{fact}' can be learned before {sorted(missing)}")
    return issues


def _explore(graph, known, facts):
    """Return (issues, knowledge states) over every path through one conversation."""
    issues, snapshots = set(), {frozenset(known)}
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
        issues |= _order_issues(node.get("teaches", []), state, facts)
        after = set(state) | set(node.get("teaches", []))
        snapshots.add(frozenset(after))
        if node.get("returns"):
            stack.append((node["returns"], frozenset(after)))
        for choice in node.get("choices", []):
            if not _visible(choice, after):
                continue
            for fact in choice.get("uses", []):
                if fact not in after:
                    issues.add(f"hero says '{fact}' before knowing it: node {key}, \"{choice['text']}\"")
            issues |= _order_issues(choice.get("teaches", []), after, facts)
            final = after | set(choice.get("teaches", []))
            snapshots.add(frozenset(final))
            if not choice.get("ends"):
                stack.append((choice["goto"], frozenset(final)))
    return issues, snapshots


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

    # The player can talk to people in any order, so search every knowledge
    # state reachable by some order of conversations and item finds.
    start = frozenset(plot.get("start", []))
    states, pending = {start}, [start]
    truncated = False
    while pending:
        current = pending.pop()
        following = set()
        for graph in conversations.values():
            issues, snapshots = _explore(graph, current, facts)
            errors |= issues
            following |= snapshots
        for item in plot.get("items", []):
            if set(item.get("needs", [])) <= current:
                errors |= _order_issues(item["teaches"], current, facts)
                following.add(current | frozenset(item["teaches"]))
        for state in following - states:
            if len(states) >= MAX_STATES:
                truncated = True
                break
            states.add(state)
            pending.append(state)
    known = set().union(*states)

    sources = {}
    for npc, graph in conversations.items():
        reached = set()
        for state in states:
            reached |= set().union(*_explore(graph, state, facts)[1])
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

    warnings = ["story too large to check every order"] if truncated else []
    for fact, info in facts.items():
        if not info.get("essential"):
            continue
        if fact not in known:
            errors.add(f"essential fact can never be learned: {fact}")
        elif len(sources.get(fact, ())) < MIN_SOURCES:
            warnings.append(f"only one source for essential fact: {fact}")
    return sorted(errors), sorted(warnings)

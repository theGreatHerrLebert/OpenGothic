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

A fact can be false: something people believe or claim that is not so. It names the truth it gets wrong, and who
holds it, honestly or as a lie:

    "bodo_stole": {"text": "Bodo hat das Kraut gestohlen.", "false": True, "contradicts": "dar_stole",
                   "believed_by": ["SLD_803_CIPHER"], "claimed_by": ["SLD_810_DAR"]}

Only those people (and anyone in known_by, who have heard the claim) may say it. A false fact is never essential:
the player must not need a lie to finish. If the truth it contradicts can never be learned, the player is misled for
good, which is allowed but warned about.

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


def _kept(teaches, relevant):
    return set(teaches) if relevant is None else set(teaches) & relevant


def _order_issues(teaches, state, facts):
    issues = set()
    for fact in teaches:
        missing = set(facts.get(fact, {}).get("needs", [])) - set(state) - set(teaches)
        if missing and fact not in state:
            issues.add(f"'{fact}' can be learned before {sorted(missing)}")
    return issues


def _relevant_facts(plot, conversations):
    """Facts that change what can happen. Tracking only these keeps the search complete and small."""
    relevant = {f for f, info in plot["facts"].items() if info.get("essential")}
    for f, info in plot["facts"].items():
        if info.get("false"):   # whether a lie can be learned, and seen through, is part of the check
            relevant |= {f, info.get("contradicts")} - {None}
    for info in plot["facts"].values():
        relevant |= set(info.get("needs", []))
    for item in plot.get("items", []):
        relevant |= set(item.get("needs", []))
    for graph in conversations.values():
        for node in graph["nodes"].values():
            relevant |= set(node.get("uses", []))
            for choice in node["choices"]:
                relevant |= set(choice.get("uses", [])) | set(choice.get("requires", []))
                if choice.get("unless"):
                    relevant.add(choice["unless"])
    return relevant


def _explore(graph, known, facts, relevant=None):
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
        after = set(state) | _kept(node.get("teaches", []), relevant)
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
            final = after | _kept(choice.get("teaches", []), relevant)
            snapshots.add(frozenset(final))
            if not choice.get("ends"):
                stack.append((choice["goto"], frozenset(final)))
    return issues, snapshots


def _holders(info):
    """Who may say a fact: those who know it, and for a false one also those who believe or claim it."""
    holders = set(info.get("known_by", []))
    if info.get("false"):
        holders |= set(info.get("believed_by", [])) | set(info.get("claimed_by", []))
    return holders


def _speaker_issues(npc, graph, facts):
    issues = set()
    for key, node in graph["nodes"].items():
        for fact in set(node.get("uses", [])) | set(node.get("teaches", [])):
            info = facts.get(fact)
            if info and not info.get("topic") and npc not in _holders(info):
                what = "believe or claim" if info.get("false") else "know"
                issues.add(f"{npc} cannot {what} '{fact}': node {key}")
    return issues


def _belief_issues(facts):
    """Errors and warnings about false facts, apart from what the search finds."""
    errors, warnings = set(), []
    for fact, info in facts.items():
        if not info.get("false"):
            if info.get("believed_by") or info.get("claimed_by") or info.get("contradicts"):
                errors.add(f"'{fact}' has believers or contradicts something but is not marked false")
            continue
        if info.get("essential"):
            errors.add(f"a false fact cannot be essential: {fact}")
        truth = info.get("contradicts")
        if truth is None:
            errors.add(f"false fact names no truth it contradicts: {fact}")
        elif truth not in facts:
            errors.add(f"unknown fact: {truth}")
        elif facts[truth].get("false"):
            errors.add(f"false fact contradicts another false fact: {fact}")
        if not info.get("believed_by") and not info.get("claimed_by"):
            warnings.append(f"nobody believes or claims the false fact: {fact}")
        if truth in facts:
            for liar in info.get("claimed_by", []):
                if liar not in facts[truth].get("known_by", []):
                    warnings.append(f"{liar} claims '{fact}' but does not know '{truth}': a believer, not a liar")
    return errors, warnings


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
    belief_errors, belief_warnings = _belief_issues(facts)
    if belief_errors:
        return sorted(belief_errors), belief_warnings

    for npc, graph in conversations.items():
        errors |= _speaker_issues(npc, graph, facts)

    # The player can talk to people in any order, so search every knowledge
    # state reachable by some order of conversations and item finds.
    relevant = _relevant_facts(plot, conversations)
    start = frozenset(set(plot.get("start", [])) & relevant)
    states, pending = {start}, [start]
    truncated = False
    while pending:
        current = pending.pop()
        following = set()
        for graph in conversations.values():
            issues, snapshots = _explore(graph, current, facts, relevant)
            errors |= issues
            following |= snapshots
        for item in plot.get("items", []):
            if set(item.get("needs", [])) <= current:
                errors |= _order_issues(item["teaches"], current, facts)
                following.add(current | frozenset(_kept(item["teaches"], relevant)))
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
            reached |= set().union(*_explore(graph, state, facts, relevant)[1])
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

    warnings = (["story too large to check every order"] if truncated else []) + belief_warnings
    for fact, info in facts.items():
        if info.get("false") and info.get("contradicts") not in known and fact in known:
            warnings.append(f"the player can never find out that '{fact}' is wrong ({info['contradicts']} "
                            "cannot be learned)")
    for fact, info in facts.items():
        if not info.get("essential"):
            continue
        if fact not in known:
            errors.add(f"essential fact can never be learned: {fact}")
        elif len(sources.get(fact, ())) < MIN_SOURCES:
            warnings.append(f"only one source for essential fact: {fact}")
    return sorted(errors), sorted(warnings)

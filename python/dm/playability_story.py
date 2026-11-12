"""The story side of the playability audit: what one story needs and makes, collected from its plan."""

class Story:
    """What one story needs and makes, collected from its plan wherever it sits."""

    def __init__(self, story, name="story"):
        self.name, self.title = name, story.get("title", name)
        self.data = story
        self.containers = []    # dicts: kind, id, npc, requires, unless, checks, on, graph, ops, parent, extra
        self.initial_flags = set()   # flags the plan sets the moment it is submitted (top-level set_flag)
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
            entry = self._conversation(op, kind, parent)
        elif kind == "add_rule":
            entry = self._rule(op, parent)
        elif kind == "set_flag" and parent is None and op.get("value", True) and op.get("name"):
            self.initial_flags.add(op["name"])
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
            self._container(entry)
        for npc in (self.data.get("anchor") or []):
            self._role(npc, "anchor")

    def _conversation(self, op, kind, parent):
        entry = {"kind": {"attach_dialogue_graph": "graph", "add_scene": "scene", "add_topic": "topic"}[kind],
                 "id": op.get("id") or f"{op.get('npc')}", "npc": (op.get("npc") or "").upper(),
                 "requires": list(op.get("requires") or []), "unless": _list(op.get("unless")),
                 "checks": op.get("checks") or [], "graph": op.get("graph"), "parent": parent}
        self._role(op.get("npc"), {"graph": "conversation", "scene": "scene", "topic": "topic"}[entry["kind"]])
        return entry

    def _rule(self, op, parent):
        entry = {"kind": "rule", "id": op.get("id"), "npc": None, "requires": list(op.get("when") or []),
                 "unless": _list(op.get("unless")), "checks": op.get("checks") or [], "on": op.get("on"),
                 "ops": op.get("ops") or [], "parent": parent, "unseen_by_near": op.get("unseen_by_near")}
        on = op.get("on") or {}
        for field in ("target", "seen_by"):
            if on.get(field) and on[field] != "PLAYER":
                self._role(on[field], "deed")
        if op.get("unseen_by_near"):
            self._role(op["unseen_by_near"], "watcher")
        return entry

    def _container(self, entry):
        """Record a conversation or rule: the people its checks name, the items its choices give, its own ops."""
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


def _unique(values):
    out = []
    for v in values:
        if v not in out:
            out.append(v)
    return out

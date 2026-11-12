"""Pre-baked conversations and the player that shows them in the native UI.

    {"start": "a",
     "nodes": {
       "a": {"line": "Hallo.", "sets": "met_novice",
             "choices": [{"text": "Wer bist du?", "goto": "b"},
                         {"text": "Leb wohl.", "ends": true}]},
       "b": {"line": "Niemand.", "choices": [{"text": "Leb wohl.", "ends": true}]}}}

A node with "returns" has no choices of its own: after its line, the conversation
goes straight back to that earlier node's menu.

A node's "variants" replace its line when a flag is set: [{"when": flag, "line": text}].

A choice can carry "requires" (flags, any one is enough) and "unless" (a flag),
so the hero can only say what the player has actually learned. Once asked, a question
is gone for good, as in the original game, unless the choice sets "repeat". A node with "sets"
may also have "again", a line used instead once that flag is already set. Every node needs
at least one unconditional choice, so a conversation can always continue.
"""

import gothic

from dm import checks, voices


def validate(graph):
    """Return a description of the first problem, or None if the graph is sound."""
    nodes = graph.get("nodes")
    start = graph.get("start")
    if not nodes or start not in nodes:
        return "missing start node"

    can_end = set()
    for key, node in nodes.items():
        if not node.get("line"):
            return f"node has no line: {key}"
        if node.get("returns"):
            if node["returns"] not in nodes:
                return f"node returns nowhere: {key}"
            continue
        choices = node.get("choices")
        if not choices:
            return f"node has no choices: {key}"
        if all(c.get("requires") or c.get("unless") or c.get("checks") or c.get("takes") for c in choices):
            return f"node has only conditional choices: {key}"
        for choice in choices:
            if not choice.get("text"):
                return f"choice has no text: {key}"
            if choice.get("requires") or choice.get("unless") or choice.get("checks") or choice.get("takes"):
                if choice.get("goto") not in nodes and not choice.get("ends"):
                    return f"choice goes nowhere: {key}"
                continue
            if choice.get("ends"):
                can_end.add(key)
            elif choice.get("goto") not in nodes:
                return f"choice goes nowhere: {key}"

    # A node is safe if some path from it reaches an ending.
    changed = True
    while changed:
        changed = False
        for key, node in nodes.items():
            targets = [node["returns"]] if node.get("returns") else [c.get("goto") for c in node["choices"]]
            if key not in can_end and any(t in can_end for t in targets):
                can_end.add(key)
                changed = True

    reachable, frontier = {start}, [start]
    while frontier:
        current = nodes[frontier.pop()]
        targets = [current["returns"]] if current.get("returns") else [c.get("goto") for c in current["choices"]]
        for target in targets:
            if target and target not in reachable:
                reachable.add(target)
                frontier.append(target)

    stuck = reachable - can_end
    if stuck:
        return f"conversation can never end from: {sorted(stuck)[0]}"
    return None


class Player:
    def __init__(self, get_graphs, on_flag, get_flags=dict, get_topic=lambda key: None, get_special=lambda npc: None):
        self.get_graphs = get_graphs
        self.get_special = get_special   # a graph that takes over any conversation while it applies (the trip dialogue)
        self.on_flag = on_flag
        self.get_flags = get_flags
        self.get_topic = get_topic
        self.topic = None   # the story topic being played inside an NPC's own conversation
        self.visible = []
        self.partner = ""
        self.graph = None
        self.node = None
        self.path = []
        self.flagged = set()
        self.choice = None
        self.line = ""
        self.stage = "idle"

    def _enter(self, key):
        self.node = self.graph["nodes"][key]
        if key in self.path:
            # Stepping back to something already said only shows its choices. A speech broken into sentences
            # (split_lines: "chain" nodes) is passed through silently to the sentence that holds them.
            del self.path[self.path.index(key) + 1:]
            while self.node.get("chain") and self.node.get("returns") in self.graph["nodes"]:
                key = self.node["returns"]
                self.node = self.graph["nodes"][key]
                if key not in self.path:
                    self.path.append(key)
            self.stage = "offer"
            return
        self.path.append(key)
        self.stage = "say"
        flags = self.node.get("sets") or []
        if isinstance(flags, str):
            flags = [flags]
        known = self.get_flags()
        already = bool(flags) and known.get(flags[0])
        self.line = self.node["again"] if self.node.get("again") and already else self.node["line"]
        for variant in self.node.get("variants", []):
            if known.get(variant["when"]):
                self.line = variant["line"]
                break
        for flag in flags:
            if flag not in self.flagged:
                self.flagged.add(flag)
                self.on_flag(flag)

    def _asked_flag(self, choice):
        return f"asked:{self.partner}:{choice['text']}"

    def _visible_choices(self):
        flags = self.get_flags()
        shown = []
        for choice in self.node["choices"]:
            if not choice.get("repeat") and flags.get(self._asked_flag(choice)):
                continue
            required = choice.get("requires")
            if required and not any(flags.get(f) for f in required):
                continue
            if flags.get(choice.get("unless")):
                continue
            if not checks.all_hold(choice.get("checks")) or not checks.can_pay(choice):
                continue
            shown.append(choice)
        return shown

    def _say(self, text, voice, is_player, delivery=None):
        wav, ms = voices.lookup(voice, text, delivery)
        return gothic.dialog.say(text, player=is_player, ms=ms, wav=wav)

    def on_tick(self):
        dialog = gothic.dialog
        key = dialog.take_topic()
        if key is not None:
            # A story topic chosen in an NPC's own menu: play its graph, then give the NPC his menu back.
            topic = self.get_topic(key)
            partner = dialog.partner()
            if topic is None or partner is None:
                dialog.end_topic()
                return
            self.partner, self.graph, self.topic = partner.instance, topic["graph"], key
            self.path = []
            self.flagged = set()
            # As with the game's own topics, the hero says the title first; then the NPC answers.
            self.choice = {"text": topic["title"], "goto": self.graph["start"]}
            self.stage = "hero"
        elif dialog.just_opened():
            self.topic = None   # a bound NPC's own conversation is never a topic
            partner = dialog.partner()
            self.partner = partner.instance if partner else ""
            try:
                special = self.get_special(partner) if partner else None
            except Exception:   # noqa: BLE001 - a broken special dialogue must not leave the hero in an empty one
                special = None
            self.graph = special or (self.get_graphs().get(partner.instance) if partner else None)
            if self.graph is None:
                # The game handed this conversation over and nothing here can play it: end it, never leave it empty.
                dialog.close()
                self.stage = "idle"
                return
            self.path = []
            self.flagged = set()
            self._enter(self.graph["start"])

        if self.stage == "idle":
            return
        if not dialog.is_open():
            self.stage = "idle"
            self.topic = None   # a topic interrupted by closing the conversation is over
            return

        if self.stage == "say":
            if self._say(self.line, self.graph.get("voice"), False, self.node.get("delivery")):
                self.stage = "offer"
        elif self.stage == "offer":
            if not dialog.busy():
                if self.node.get("returns"):
                    self._enter(self.node["returns"])
                    return
                self.visible = self._visible_choices()
                back = [c for c in self.visible if c["text"] == "Zurück."]
                if back and len(back) == len(self.visible):
                    self._enter(back[0]["goto"])  # nothing left to ask in this branch
                    return
                dialog.set_choices([c["text"] for c in self.visible])
                self.stage = "choose"
        elif self.stage == "choose":
            index = dialog.poll_selection()
            if index is None:
                return
            self.choice = self.visible[index]
            checks.transfer(self.choice)
            is_question = self.choice.get("goto") and self.choice["goto"] not in self.path
            if is_question and not self.choice.get("repeat"):
                self.on_flag(self._asked_flag(self.choice))
            if self.choice.get("goto") in self.path:
                self._enter(self.choice["goto"])
            else:
                self.stage = "hero"
        elif self.stage == "hero":
            if self._say(self.choice["text"], voices.HERO_VOICE, True, self.choice.get("delivery")):
                self.stage = "hero_wait"
        elif self.stage == "hero_wait":
            if not dialog.busy():
                if self.choice.get("ends"):
                    if self.topic is not None:
                        dialog.end_topic()   # back to the NPC's own menu, not out of the conversation
                        self.topic = None
                    else:
                        dialog.close()
                    self.stage = "idle"
                else:
                    self._enter(self.choice["goto"])

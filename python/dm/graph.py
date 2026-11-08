"""Pre-baked conversations and the player that shows them in the native UI.

    {"start": "a",
     "nodes": {
       "a": {"line": "Hallo.", "sets": "met_novice",
             "choices": [{"text": "Wer bist du?", "goto": "b"},
                         {"text": "Leb wohl.", "ends": true}]},
       "b": {"line": "Niemand.", "choices": [{"text": "Leb wohl.", "ends": true}]}}}

A choice can carry "requires" (flags, any one is enough) and "unless" (a flag),
so the hero can only say what the player has actually learned. Every node needs
at least one unconditional choice, so a conversation can always continue.
"""

import gothic

from dm import voices


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
        choices = node.get("choices")
        if not choices:
            return f"node has no choices: {key}"
        if all(c.get("requires") or c.get("unless") for c in choices):
            return f"node has only conditional choices: {key}"
        for choice in choices:
            if not choice.get("text"):
                return f"choice has no text: {key}"
            if choice.get("requires") or choice.get("unless"):
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
            if key not in can_end and any(c.get("goto") in can_end for c in node["choices"]):
                can_end.add(key)
                changed = True

    reachable, frontier = {start}, [start]
    while frontier:
        for choice in nodes[frontier.pop()]["choices"]:
            target = choice.get("goto")
            if target and target not in reachable:
                reachable.add(target)
                frontier.append(target)

    stuck = reachable - can_end
    if stuck:
        return f"conversation can never end from: {sorted(stuck)[0]}"
    return None


class Player:
    def __init__(self, get_graphs, on_flag, get_flags=dict):
        self.get_graphs = get_graphs
        self.on_flag = on_flag
        self.get_flags = get_flags
        self.visible = []
        self.graph = None
        self.node = None
        self.path = []
        self.flagged = set()
        self.choice = None
        self.stage = "idle"

    def _enter(self, key):
        self.node = self.graph["nodes"][key]
        if key in self.path:
            # Stepping back to something already said only shows its choices.
            del self.path[self.path.index(key) + 1:]
            self.stage = "offer"
            return
        self.path.append(key)
        self.stage = "say"
        flag = self.node.get("sets")
        if flag and flag not in self.flagged:
            self.flagged.add(flag)
            self.on_flag(flag)

    def _visible_choices(self):
        flags = self.get_flags()
        shown = []
        for choice in self.node["choices"]:
            required = choice.get("requires")
            if required and not any(flags.get(f) for f in required):
                continue
            if flags.get(choice.get("unless")):
                continue
            shown.append(choice)
        return shown

    def _say(self, text, voice, is_player):
        wav, ms = voices.lookup(voice, text)
        return gothic.dialog.say(text, player=is_player, ms=ms, wav=wav)

    def on_tick(self):
        dialog = gothic.dialog
        if dialog.just_opened():
            partner = dialog.partner()
            self.graph = self.get_graphs().get(partner.instance) if partner else None
            if self.graph is None:
                self.stage = "idle"
                return
            self.path = []
            self.flagged = set()
            self._enter(self.graph["start"])

        if self.stage == "idle":
            return
        if not dialog.is_open():
            self.stage = "idle"
            return

        if self.stage == "say":
            if self._say(self.node["line"], self.graph.get("voice"), False):
                self.stage = "offer"
        elif self.stage == "offer":
            if not dialog.busy():
                self.visible = self._visible_choices()
                dialog.set_choices([c["text"] for c in self.visible])
                self.stage = "choose"
        elif self.stage == "choose":
            index = dialog.poll_selection()
            if index is None:
                return
            self.choice = self.visible[index]
            if self.choice.get("goto") in self.path:
                self._enter(self.choice["goto"])
            else:
                self.stage = "hero"
        elif self.stage == "hero":
            if self._say(self.choice["text"], voices.HERO_VOICE, True):
                self.stage = "hero_wait"
        elif self.stage == "hero_wait":
            if not dialog.busy():
                if self.choice.get("ends"):
                    dialog.close()
                    self.stage = "idle"
                else:
                    self._enter(self.choice["goto"])

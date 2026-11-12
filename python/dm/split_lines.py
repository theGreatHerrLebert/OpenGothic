"""Breaks long spoken lines into one sentence per dialogue node, chained with "returns", so each sentence is voiced,
heard and re-recorded on its own.

    python3 python/dm/split_lines.py <story.json> [...]     # rewrites the stories in place

A node keeps its id for its first sentence, so every goto and returns still lands where it did; the sentences after
it get ids <node>_2, <node>_3 ..., and every sentence but the last is marked "chain", so stepping back to the node
shows its choices without speaking it again (graph.Player). The flags a node sets and the facts it teaches or uses stay on the first sentence (they
take effect when the node is entered, as before); its choices and its own returns move to the last. Nodes with
variants or an "again" line are left whole: those replace the line as one. Very short sentences stay with their
neighbour, so a "Ja." does not become a node of its own.
"""

import json
import pathlib
import re
import sys

MIN_SENTENCE = 20   # characters: shorter sentences are joined to the one before (or after)
# A sentence ends at . ! ? or an ellipsis followed by a space and a capital or an opening quote.
_END = re.compile(r'(?<=[.!?…])\s+(?=[A-ZÄÖÜ„"»])')


def sentences(text):
    """The sentences of a spoken line, short ones joined to a neighbour."""
    parts = [p.strip() for p in _END.split(text.strip()) if p.strip()]
    merged = []
    for part in parts:
        if merged and (len(part) < MIN_SENTENCE or len(merged[-1]) < MIN_SENTENCE):
            merged[-1] = f"{merged[-1]} {part}"
        else:
            merged.append(part)
    return merged or [text]


def split_graph(graph):
    """The graph with each long line broken into a chain of sentence nodes. Returns how many nodes were split."""
    nodes = graph.get("nodes", {})
    split = 0
    for key in list(nodes):
        node = nodes[key]
        if node.get("variants") or node.get("again") or not isinstance(node.get("line"), str):
            continue
        parts = sentences(node["line"])
        if len(parts) < 2:
            continue
        chain = [key] + [f"{key}_{i}" for i in range(2, len(parts) + 1)]
        if any(name in nodes for name in chain[1:]):
            continue                          # already split, or a name taken: leave it be
        last = {"line": parts[-1], "choices": node.get("choices", [])}
        if node.get("returns"):
            last["returns"] = node["returns"]
        for field in ("delivery",):
            if field in node:
                last[field] = node[field]
        first = {k: v for k, v in node.items() if k not in ("line", "choices", "returns")}
        first.update({"line": parts[0], "choices": [], "returns": chain[1], "chain": True})
        nodes[key] = first
        for i, name in enumerate(chain[1:], 1):
            if i == len(parts) - 1:
                nodes[name] = last
            else:
                middle = {"line": parts[i], "choices": [], "returns": chain[i + 1], "chain": True}
                if "delivery" in node:
                    middle["delivery"] = node["delivery"]
                nodes[name] = middle
        split += 1
    return split


def split_story(data):
    """Splits every dialogue of a story, in its conversations and wherever its plan plays one."""
    count = 0

    def walk(value):
        nonlocal count
        if isinstance(value, dict):
            if isinstance(value.get("nodes"), dict) and "start" in value:
                count += split_graph(value)
            for v in value.values():
                walk(v)
        elif isinstance(value, list):
            for v in value:
                walk(v)
    walk(data.get("conversations", {}))
    walk(data.get("plan", []))
    return count


def main(paths):
    for name in paths:
        path = pathlib.Path(name)
        data = json.loads(path.read_text(encoding="utf-8"))
        count = split_story(data)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{path.name}: {count} lines split into sentences")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    main(sys.argv[1:])

"""Rebuilds python/dm_runtime/quotes.json, the game lines quoted as evidence in the character sheets and world facts.

    python3 python/dm/make_quotes.py build <Gothic install>    # cut the quotes out of your own install
    python3 python/dm/make_quotes.py record <Gothic install>   # after editing quotes.json: store where each quote sits

The repository keeps only quote_spans.json: a dialogue key and character positions, never the game's text. The text
comes from the subtitles of the install on this machine, so quotes.json stays private and is not committed.
"""

import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
SPANS = HERE / "quote_spans.json"
QUOTES = HERE.parent / "dm_runtime" / "quotes.json"


def game_lines(game):
    """Every subtitle by dialogue key, from the compiled script info of a Gothic II install."""
    info = pathlib.Path(game).expanduser() / "_work/Data/Scripts/_compiled/OUINFO.INF"
    text = info.read_bytes().decode("cp1252", "replace")
    return {m[1].upper(): m[2].strip().rstrip("}").strip()
            for m in re.finditer(r'AI_Output\s*\([^"]*"([^"]+)"\)\s*;\s*//\s*([^\r\n]*)', text)}


def record(game):
    lines, quotes = game_lines(game), json.loads(QUOTES.read_text(encoding="utf-8"))
    spans, missing = {}, []
    for key, excerpts in sorted(quotes.items()):
        line = lines.get(key.upper(), "")
        found = []
        for excerpt in excerpts:
            start = line.find(excerpt)
            if start < 0:
                missing.append(key)
                found.append(None)
            else:
                found.append([start, start + len(excerpt)])
        spans[key] = found
    rows = [f"{json.dumps(k)}: {json.dumps(v)}" for k, v in sorted(spans.items())]
    SPANS.write_text("{\n" + ",\n".join(rows) + "\n}\n", encoding="utf-8")
    print(f"{len(spans)} keys recorded, {len(missing)} quotes not found in the install: {sorted(set(missing))[:10]}")


def build(game):
    lines, spans = game_lines(game), json.loads(SPANS.read_text(encoding="utf-8"))
    quotes, missing = {}, 0
    for key, positions in spans.items():
        line = lines.get(key.upper())
        cut = [line[s:e] if line and pos else "(quote not available)" for pos in positions for s, e in [pos or (0, 0)]]
        missing += sum(q == "(quote not available)" for q in cut)
        quotes[key] = cut
    QUOTES.parent.mkdir(parents=True, exist_ok=True)
    QUOTES.write_text(json.dumps(quotes, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(quotes)} keys written to {QUOTES}, {missing} quotes missing")


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] not in ("build", "record"):
        sys.exit(__doc__)
    {"build": build, "record": record}[sys.argv[1]](sys.argv[2])

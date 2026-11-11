"""Every story the game master knows, and where each one stands: proposed, in progress or accepted.

The inspector reads this to list, open and promote stories. A story's stage lives in
python/dm_runtime/story_stages.json, next to the stories, which are not in the repository.

Generated stories are named by their blind id only. Their file name says which snapshot and author
wrote them, and the scoring page must stay blind, so the stem never leaves this module.
"""

import copy
import hashlib
import json
import pathlib
import re
import sys
import threading

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from dm import check_story  # noqa: E402  (installs the offline gothic module before dm.story is imported)
from dm import voices  # noqa: E402

PROPOSED, IN_PROGRESS, ACCEPTED = "proposed", "in_progress", "accepted"
STAGES = (PROPOSED, IN_PROGRESS, ACCEPTED)
# Which way a story may move. Accepting is gated, see gate().
MOVES = {PROPOSED: {IN_PROGRESS}, IN_PROGRESS: {PROPOSED, ACCEPTED}, ACCEPTED: {IN_PROGRESS}}

EXPERIMENT = voices.RUNTIME_DIR / "experiment"
STAGE_FILE = voices.RUNTIME_DIR / "story_stages.json"
# Text fixed by hand in the inspector, kept apart from the stories and graphs.json, so the blind story trial still
# shows what was generated. Keyed like graphs.json: "<story file stem>__<conversation>".
EDITS = EXPERIMENT / "edits.json"
EDIT_LOCK = threading.Lock()
MAX_LINE = 600
DEMO_ID = "tilo"
DEMO_SOURCE = pathlib.Path(__file__).resolve().parent / "stories" / "tilo.py"


def blind_id(stem):
    return hashlib.sha256(("experiment-1:" + stem).encode("utf-8")).hexdigest()[:10]


def story_paths():
    stories = EXPERIMENT / "stories"
    return [p for p in sorted(stories.glob("s*_*.json")) + sorted(stories.glob("x*_*.json")) + sorted(stories.glob("e*_*.json"))
            if not p.name.endswith((".first.json", ".final.json"))]


def path_of(story_id):
    """The file behind a generated story's blind id, or None."""
    return next((p for p in story_paths() if blind_id(p.stem) == story_id), None)


def revision(story_id):
    """Changes whenever the story's content changes, so an acceptance only holds for what was accepted."""
    path = DEMO_SOURCE if story_id == DEMO_ID else path_of(story_id)
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12] if path else None


def load_stages():
    try:
        return json.loads(STAGE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _write_stages(stages):
    temporary = STAGE_FILE.with_suffix(".tmp")
    temporary.write_text(json.dumps(stages, ensure_ascii=False, indent=1), encoding="utf-8")
    temporary.replace(STAGE_FILE)


def stage_of(story_id, stages=None, rev=None):
    """The stage, and whether an accepted story has changed since. A changed story is back in progress.

    rev identifies the content that was accepted. Callers that know more than the story file, such as every
    line and recording as reviewed, pass their own; see move().
    """
    stages = load_stages() if stages is None else stages
    entry = stages.get(story_id)
    if entry is None:
        return (ACCEPTED if story_id == DEMO_ID else PROPOSED), False
    if entry["stage"] == ACCEPTED and entry.get("rev") != (revision(story_id) if rev is None else rev):
        return IN_PROGRESS, True
    return entry["stage"], False


def gate(problems, reviews, index):
    """Why a story cannot be accepted yet, as a list of reasons. Empty means it can.

    problems: the story's check errors. reviews: valid reviews by key. index: every reviewable key and its
    content hash; keys without content (a voice line never generated) need no review.
    """
    reasons = []
    if problems:
        reasons.append(f"{len(problems)} check errors")
    keys = [key for key, content in index.items() if content is not None]
    unreviewed = sum(1 for key in keys if key not in reviews)
    rejected = sum(1 for key in keys if reviews.get(key, {}).get("verdict") == "reject")
    if unreviewed:
        reasons.append(f"{unreviewed} lines not reviewed")
    if rejected:
        reasons.append(f"{rejected} lines rejected")
    return reasons


def move(story_id, target, blockers, rev=None):
    """Move a story to another stage. Returns an error message, or None. Pass the same rev as to stage_of()."""
    if target not in STAGES:
        return "unknown stage"
    rev = revision(story_id) if rev is None else rev
    current, _ = stage_of(story_id, rev=rev)
    if target == current:
        return None
    if target not in MOVES[current]:
        return f"cannot move from {current} to {target}"
    if target == ACCEPTED and blockers:
        return "not ready: " + ", ".join(blockers)
    stages = load_stages()
    stages[story_id] = {"stage": target, "rev": rev}
    _write_stages(stages)
    return None


def generated(story_id):
    """A generated story's data and its dialogue as voiced, or (None, None).

    graphs.json holds the dialogue the voices were made from, which can be newer than the copies inside the
    story. The plan is switched over to it too, so what plays is always what was voiced.
    """
    path = path_of(story_id)
    if path is None:
        return None, None
    data = json.loads(path.read_text(encoding="utf-8"))
    graphs_file = EXPERIMENT / "graphs.json"
    baked = json.loads(graphs_file.read_text(encoding="utf-8")) if graphs_file.exists() else {}
    edits = load_edits()
    conversations = {key: edits.get(f"{path.stem}__{key}") or baked.get(f"{path.stem}__{key}", graph)
                     for key, graph in data["conversations"].items()}
    data["plan"] = _with_graphs(data["plan"], data["conversations"], conversations)
    data["conversations"] = conversations
    return data, conversations


def load_edits():
    try:
        return json.loads(EDITS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def edit_line(story_id, review_id, text):
    """Replaces one spoken text of a generated story: CONV__node, CONV__node__again, CONV__node__v0 or CONV__node__c0.
    Returns (voice, old text, new text, delivery). Raises ValueError for anything that is not a plain line."""
    text = " ".join(str(text).split())
    if not text or len(text) > MAX_LINE:
        raise ValueError(f"a line has 1 to {MAX_LINE} characters")
    if story_id == DEMO_ID:
        raise ValueError("the demo story is written in Python and is edited there")
    path = path_of(story_id)
    parts = review_id.split("__")
    if path is None or len(parts) not in (2, 3):
        raise ValueError("unknown line")
    with EDIT_LOCK:
        _, conversations = generated(story_id)
        graph = copy.deepcopy(conversations.get(parts[0]) or {})
        node = graph.get("nodes", {}).get(parts[1])
        if node is None:
            raise ValueError("unknown line")
        what = parts[2] if len(parts) == 3 else ""
        if what == "":
            holder, field, voice = node, "line", graph.get("voice")
        elif what == "again" and node.get("again"):
            holder, field, voice = node, "again", graph.get("voice")
        elif re.fullmatch(r"v\d+", what) and int(what[1:]) < len(node.get("variants", [])):
            holder, field, voice = node["variants"][int(what[1:])], "line", graph.get("voice")
        elif re.fullmatch(r"c\d+", what) and int(what[1:]) < len(node["choices"]):
            holder, field, voice = node["choices"][int(what[1:])], "text", voices.HERO_VOICE
        else:
            raise ValueError("unknown line")
        old = holder[field]
        holder[field] = text
        edits = load_edits()
        edits[f"{path.stem}__{parts[0]}"] = graph
        temporary = EDITS.with_suffix(".tmp")
        temporary.write_text(json.dumps(edits, ensure_ascii=False, indent=1), encoding="utf-8")
        temporary.replace(EDITS)
    delivery = None if field == "text" else node.get("delivery")
    return voice, old, text, delivery


def _with_graphs(ops, written, voiced):
    """The plan with each conversation it starts replaced by the voiced version of that conversation."""
    result = []
    for op in ops:
        op = dict(op)
        if "graph" in op:
            key = next((k for k, graph in written.items() if graph == op["graph"]), None)
            if key is not None:
                op["graph"] = voiced[key]
        if "ops" in op:
            op["ops"] = _with_graphs(op["ops"], written, voiced)
        result.append(op)
    return result


def check(story_id):
    """check_story's report for a generated story, as it will play: with the voiced dialogue, see generated()."""
    data, _ = generated(story_id)
    names = EXPERIMENT / "world_names.json"
    if data is None or not names.exists():
        return {"ok": False, "errors": ["story or world_names.json missing"], "warnings": []}
    return check_story.check(data, str(names))


def plan(story_id):
    """The operations that start a generated story in the game. The demo is built inside the game, see dm.api."""
    if story_id == DEMO_ID:
        raise ValueError("the demo story's plan depends on the game day; start it with dm.api.play_demo")
    data, _ = generated(story_id)
    return None if data is None else data["plan"]


def entries():
    """Every story with its stage: the demo first, then generated stories by title, which says nothing about their source."""
    stages = load_stages()
    result = []
    demo_stage, demo_changed = stage_of(DEMO_ID, stages)
    result.append({"id": DEMO_ID, "title": "Der Fall Tilo", "premise": "Die Referenzgeschichte: ein Novize, "
                   "zwei gestohlene Silberleuchter und Würfelschulden am Hafen.", "demo": True,
                   "stage": demo_stage, "changed": demo_changed})
    for path in story_paths():
        story_id = blind_id(path.stem)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            continue
        stage, changed = stage_of(story_id, stages)
        result.append({"id": story_id, "title": data.get("title", story_id), "premise": data.get("premise", ""),
                       "demo": False, "bonus": bool(data.get("bonus")), "stage": stage, "changed": changed})
    return result[:1] + sorted(result[1:], key=lambda e: (e["title"].lower(), e["id"]))

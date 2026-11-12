"""Local story inspector: read, listen to and review every line of a story.

    python3 python/dm/inspector_server.py
    then open http://127.0.0.1:8765

Serves only on this machine, because the generated voices must stay here. Reviews
are stored in python/dm_runtime/reviews.json.
"""

import copy
from html import escape as html_escape
import hashlib
import http.cookies
import http.server
import importlib
import atexit
import json
import pathlib
import re
import subprocess
import sys
import threading
import types
import urllib.parse

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))
sys.modules.setdefault("gothic", types.ModuleType("gothic"))

from dm import library  # noqa: E402  (first: it installs the offline gothic module the story checker needs)
from dm import bridge  # noqa: E402
from dm import bake_voices  # noqa: E402
from dm import knowledge as k  # noqa: E402
from dm import inspector_i18n  # noqa: E402
from dm import voices  # noqa: E402
from dm.stories import tilo as t  # noqa: E402

PORT = 8765
PAGE = ROOT / "inspector" / "page.html"
LIBRARY_PAGE = ROOT / "inspector" / "library.html"
MAP_PAGE = ROOT / "inspector" / "map.html"
MAP_DIR = voices.RUNTIME_DIR / "map"
MAP_IMAGE = re.compile(r"^/map/image/(MAP_[A-Z0-9_]+\.png)$")
CHARACTERS_PAGE = ROOT / "inspector" / "characters.html"
CHARACTERS = ROOT / "characters"
WORLD_FACTS = ROOT / "world_facts.json"
REVIEWS = voices.RUNTIME_DIR / "reviews.json"
REVIEW_LOCK = threading.Lock()  # requests arrive on separate threads
AUDIO_PATH = re.compile(r"^/audio/([0-9A-Za-z_]+)/([0-9a-f]{20})\.wav$")
TAKE_PATH = re.compile(r"^/take/([0-9A-Za-z_]+)/([0-9a-f]{20})/([0-9]{1,4})\.wav$")


def audio_url(voice, text, delivery=None):
    if not voice:
        return None
    path = voices.audio_path(voice, text, delivery)
    try:
        version = path.stat().st_mtime_ns
    except FileNotFoundError:
        return None
    # the version makes a browser fetch a re-sampled take instead of replaying the old one from its cache
    return "/audio/" + "/".join(path.parts[-2:]) + f"?v={version}"


def build():
    importlib.reload(t)
    extra={f:{"text":"","known_by":[],"topic":True,"needs":[],"essential":False} for f in ("harek_met","tilo_confessed","tilo_turned_in","tilo_threatened","tilo_helped")}
    plot=copy.deepcopy(t.PLOT); plot["facts"].update(extra)
    errors,warnings=k.check(plot,t.CONVERSATIONS)
    names={t.GORAX:"Gorax",t.PARLAN:"Parlan",t.ANSELM:"Anselm",t.HAREK:"Harek",t.TILO:"Tilo"}
    scenes={o["id"]:o for o in t.plan() if o["op"]=="add_scene"}
    rules=[o for o in t.plan() if o["op"]=="add_rule"]
    for r in rules:
        for o in r["ops"]:
            if o["op"]=="add_scene": scenes[o["id"]]=o
    order=[("barrel","Novize neben Gorax","Kloster, nach dem Diebstahl"),("tilo_before","Tilo","Kloster, vor dem Diebstahl"),("gorax","Gorax","Kloster, beim Näherkommen"),("parlan","Parlan","Kloster, beim Näherkommen"),("anselm","Anselm","Kloster, beim Näherkommen"),("harek","Harek","Hafenkneipe, immer verfügbar"),("tilo","Tilo","Hafengassen, immer verfügbar"),("tilo_ordered_home","Tilo","Bis du gehst, wenn nach Hause geschickt"),("tilo_back_at_work","Tilo","An der Kelter, nach der Heimkehr"),("tilo_after_turned_in","Tilo","Bis du gehst, wenn ausgeliefert"),("tilo_after_help","Tilo","Bis du gehst, wenn ihm geholfen wurde"),("parlan_reward","Parlan","Nachdem Tilo ausgeliefert wurde"),("anselm_bitter","Anselm","Nachdem die Belohnung bezahlt wurde"),("anselm_grateful","Anselm","Nachdem Tilo geholfen wurde")]
    g=t.all_graphs()
    data={"title":"Der Fall Tilo","frame":re.sub(r"\s+"," ",t.__doc__.split("Frame:")[1]).strip(),"truth":t.HIDDEN_TRUTH,"errors":errors,"warnings":warnings,"facts":{f:dict(essential=v.get("essential",False),topic=v.get("topic",False),needs=v.get("needs",[]),knownBy=[names.get(n,n) for n in v.get("known_by",[])]) for f,v in plot["facts"].items()},
    "convs":[{"id":i,"speaker":s,"where":w,"requires":scenes.get(i,{}).get("requires",[]),"unless":scenes.get(i,{}).get("unless") or [],"within":scenes.get(i,{}).get("within"),"scene":i in scenes,"start":g[i]["start"],"nodes":g[i]["nodes"]} for i,s,w in order],
    "rules":[{"id":r["id"],"when":r["when"],"ops":[{k:v for k,v in o.items() if k in("op","instance","count","id","waypoint","requires")} for o in r["ops"]]} for r in rules]}
    mermaid = _demo_mermaid(data, plot)
    _demo_audio(data, g)
    return data, mermaid


_CLASS_DEFS = ["  classDef conv fill:#7A1F14,stroke:#2a1c10,color:#F0E2C0",
               "  classDef fact fill:#EADBB6,stroke:#7A5F36,color:#2A1C10",
               "  classDef ess fill:#D9A441,stroke:#7A1F14,color:#2A1C10",
               "  classDef effect fill:#3E5A22,stroke:#2a1c10,color:#F0E2C0"]


def _demo_mermaid(data, plot):
    """The hand-drawn flow graph of the demo story."""
    lab={"tilo_named":"Tilos Name","tilo_absent":"Tilo fehlt","wine_trips":"seine Weingänge","silver_stolen":"Silber gestohlen","candlesticks":"zwei Leuchter","reward":"Belohnung ausgesetzt","tilo_past":"sein Vater","gambling":"Würfelschulden","harbour_lead":"Spur zum Hafen","friend_offer":"Anselms Angebot","harek_wary":"Harek ist misstrauisch","silver_sold":"Silber an Harek verkauft","tilo_nearby":"versteckt am Hafen","tilo_cornered":"am Hafen getroffen","tilo_met":"Tilo getroffen","barrel_met":"Fass-Novize getroffen","tilo_stressed":"wirkte gehetzt","tilo_turned_in":"Tilo ausgeliefert","tilo_helped":"Tilo geholfen","parlan_paid":"Belohnung bezahlt","anselm_secret":"Geheimnis erzählt","tilo_threatened":"Tilo erpresst","tilo_confessed":"Tilo gestanden"}
    conv={c["id"]:c for c in data["convs"]}
    titles={"tilo_back_at_work":"Tilo wieder bei der Arbeit","tilo_ordered_home":"Tilo gehorcht","tilo_after_help":"Tilo verabschiedet sich","tilo_after_turned_in":"Tilo verspricht zu folgen","barrel":"Der Novize an den Fässern","tilo_before":"Tilo vor dem Diebstahl","gorax":"Gorax beschwert sich","parlan":"Parlan verkündet","anselm":"Anselms Bitte","harek":"Harek","tilo":"Tilo","parlan_reward":"Parlan zahlt","anselm_bitter":"Anselm wendet sich ab","anselm_grateful":"Anselms Geheimnis"}
    L=["flowchart LR"]; facts=set(); E=set()
    def f(x):
        facts.add(x); return "f_"+x
    for cid,c in conv.items():
        L.append(f'  c_{cid}["{titles[cid]}"]:::conv')
        for nk,n in c["nodes"].items():
            for x in n.get("teaches",[]):
                if x in lab and x not in("harek_met",): E.add(f"  c_{cid} --> {f(x)}")
            for ch in n["choices"]:
                for x in ch.get("requires",[]):
                    if x in lab: E.add(f"  {f(x)} -. line .-> c_{cid}")
        for x in c["requires"]:
            if x in lab: E.add(f"  {f(x)} ==>|starts| c_{cid}")
        u=c["unless"] if isinstance(c["unless"],list) else ([c["unless"]] if c["unless"] else [])
        for x in u:
            if x in lab: E.add(f"  {f(x)} --x|closes| c_{cid}")
    E.add(f"  c_tilo --> {f('tilo_turned_in')}"); E.add(f"  c_tilo --> {f('tilo_helped')}"); E.add(f"  c_tilo --> {f('tilo_threatened')}")
    E.add(f"  {f('tilo_turned_in')} ==>|starts| c_parlan_reward"); E.add(f"  c_parlan_reward --> {f('parlan_paid')}"); E.add(f"  {f('parlan_paid')} ==>|starts| c_anselm_bitter")
    E.add(f"  {f('tilo_helped')} ==>|starts| c_anselm_grateful"); E.add(f"  c_anselm_grateful --> {f('anselm_secret')}")
    L.append('  r_gold(["200 gold"]):::effect'); E.add(f"  {f('parlan_paid')} ==> r_gold")
    L.append('  r_wine(["versteckter Wein taucht auf"]):::effect'); E.add(f"  {f('anselm_secret')} ==> r_wine")
    L.append('  r_gone(["Tilo verlässt den Hafen"]):::effect'); E.add(f"  {f('tilo_turned_in')} ==> r_gone"); E.add(f"  {f('tilo_helped')} ==> r_gone")
    for x in sorted(facts):
        L.append(f'  f_{x}("{lab[x]}"):::{"ess" if plot["facts"].get(x,{}).get("essential") else "fact"}')
    L+=sorted(E)
    L+=_CLASS_DEFS
    return "\n".join(L)


def _demo_audio(data, g):
    """The demo story's recordings, attached to copies of its nodes."""
    for conv in data["convs"]:
        voice = g[conv["id"]].get("voice")
        conv["voice"] = voice
        conv["nodes"] = copy.deepcopy(conv["nodes"])
        for n in conv["nodes"].values():
            n["audio"] = audio_url(voice, n["line"], n.get("delivery"))
            if n.get("again"):
                n["audioAgain"] = audio_url(voice, n["again"], n.get("delivery"))
            for variant in n.get("variants", []):
                variant["audio"] = audio_url(voice, variant["line"], n.get("delivery"))
            for choice in n["choices"]:
                choice["audio"] = audio_url(voices.HERO_VOICE, choice["text"])


def _text_hash(text):
    return "t:" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


_audio_hashes = {}


def _audio_hash(url):
    """Hash of a generated audio file, or None if there is none."""
    if not url:
        return None
    voice, name = url.split("?")[0].split("/")[-2:]
    path = voices.VOICE_DIR / voice / name
    try:
        stamp = (str(path), path.stat().st_mtime_ns)
    except FileNotFoundError:  # deleted since the page data was built
        return None
    if stamp not in _audio_hashes:
        _audio_hashes[stamp] = "a:" + hashlib.sha256(path.read_bytes()).hexdigest()[:16]
    return _audio_hashes[stamp]


def content_index(data):
    """What each review applies to: an approval only counts for this exact text or audio."""
    index = {}
    for conv in data["convs"]:
        for key, node in conv["nodes"].items():
            base = f"{conv['id']}__{key}"
            index[base] = _text_hash(node["line"])
            index[base + "__voice"] = _audio_hash(node.get("audio"))
            if node.get("again"):
                index[base + "__again"] = _text_hash(node["again"])
                index[base + "__again__voice"] = _audio_hash(node.get("audioAgain"))
            for i, variant in enumerate(node.get("variants", [])):  # spoken instead of the line once a flag is set
                index[f"{base}__v{i}"] = _text_hash(variant["line"])
                index[f"{base}__v{i}__voice"] = _audio_hash(variant.get("audio"))
            for i, choice in enumerate(node["choices"]):
                index[f"{base}__c{i}"] = _text_hash(choice["text"])
                index[f"{base}__c{i}__voice"] = _audio_hash(choice.get("audio"))
    return index


def story_reviews(story_id):
    """Reviews of one story that still match what it says now. Changed lines count as unreviewed."""
    index = content_index(story_view(story_id)[0])
    prefix = story_id + "/"
    return {key[len(prefix):]: value for key, value in load_reviews().items()
            if key.startswith(prefix) and value.get("hash") is not None and value["hash"] == index.get(key[len(prefix):])}


def adopt_existing_reviews():
    """Move reviews from before the story library under the demo story, and bind unhashed ones to its content."""
    index = content_index(build()[0])
    prefix = library.DEMO_ID + "/"
    with REVIEW_LOCK:
        reviews = {}
        for key, value in load_reviews().items():
            if "/" not in key:
                if "hash" not in value and index.get(key):
                    value["hash"] = index[key]
                key = prefix + key
            reviews[key] = value
        _write_reviews(reviews)


def _write_reviews(reviews):
    # write to a temporary file first, so a crash can never leave a partial file
    temporary = REVIEWS.with_suffix(".tmp")
    temporary.write_text(json.dumps(reviews, ensure_ascii=False, indent=1), encoding="utf-8")
    temporary.replace(REVIEWS)


_views = {}


def story_view(story_id):
    """(page data, Mermaid source) for any story, or (None, None). Rebuilt only when the story changes."""
    if story_id == library.DEMO_ID:
        return build()
    path = library.path_of(story_id)
    if path is None:
        return None, None
    # everything the view reads: the story, its voiced dialogue and the names the checker validates against
    stamp = (library.revision(story_id),
             *(f.stat().st_mtime_ns if f.exists() else 0
               for f in (EXPERIMENT / "graphs.json", EXPERIMENT / "world_names.json", library.EDITS)))
    if _views.get(story_id, (None,))[0] != stamp:
        _views[story_id] = (stamp, generated_view(story_id))
    page, graph = _views[story_id][1]
    return _with_audio(page), graph


def _with_audio(page):
    """Recordings are looked up on every request: voices are baked and deleted while the server runs."""
    page = {**page, "convs": copy.deepcopy(page["convs"])}
    for conv in page["convs"]:
        for node in conv["nodes"].values():
            node["audio"] = audio_url(conv["voice"], node["line"], node.get("delivery"))
            if node.get("again"):
                node["audioAgain"] = audio_url(conv["voice"], node["again"], node.get("delivery"))
            for variant in node.get("variants", []):
                variant["audio"] = audio_url(conv["voice"], variant["line"], node.get("delivery"))
            for choice in node["choices"]:
                choice["audio"] = None if choice["text"] == "Zurück." else audio_url(voices.HERO_VOICE, choice["text"])
    return page


def _describe_check(check):
    kind = check.get("type")
    if kind == "wears":
        return "trägt " + check["item"]
    if kind == "guild":
        return "Gilde " + check["guild"]
    if kind == "has_item":
        return f"hat {check.get('count', 1)}× {check['item']}"
    if kind == "not":
        return "nicht: " + _describe_check(check["check"])
    return kind


def generated_view(story_id):
    """The page data of a generated story, in the same shape as the demo story's."""
    data, conversations = library.generated(story_id)
    labels, cast = _conversation_names(data, _sheet_names())
    report = library.check(story_id)
    starts, rules = {}, []

    def strings(value):
        return [v for v in _as_list(value) if isinstance(v, str)]

    def walk(ops, when=(), unless=()):
        for op in ops:
            if op["op"] == "add_rule":
                rules.append({"id": op["id"], "when": strings(op.get("when")),
                              "ops": [{key: value for key, value in o.items() if key in ("op", "instance", "count", "id", "waypoint")}
                                      for o in op["ops"]]})
                walk(op["ops"], (*when, *strings(op.get("when"))), (*unless, *strings(op.get("unless"))))
            elif op["op"] in ("add_scene", "attach_dialogue_graph"):
                key = next((k for k, g in data["conversations"].items() if g == op["graph"]), None)
                if key is not None and key not in starts:
                    starts[key] = {"scene": op["op"] == "add_scene", "within": op.get("within"),
                                   "requires": [*when, *strings(op.get("requires"))],
                                   "unless": [*unless, *strings(op.get("unless"))],
                                   "checks": [_describe_check(c) for c in op.get("checks", [])]
                                   + ["nicht für " + g for g in op.get("not_guilds", [])]}

    walk(data["plan"])
    convs = []
    for key, graph in conversations.items():
        start = starts.get(key, {})
        nodes = copy.deepcopy(graph["nodes"])
        for node in nodes.values():
            node["teaches"] = strings(node.get("teaches")) or strings(node.get("sets"))
            for choice in node["choices"]:
                choice["requires"] = strings(choice.get("requires")) or None
        where = start.get("checks", []) if key in starts else ["nie gestartet"]
        convs.append({"id": key, "voice": graph.get("voice"), "speaker": labels[key].split(" · ")[0], "where": " · ".join(where),
                      "requires": start.get("requires", []), "unless": start.get("unless", []),
                      "within": start.get("within"), "scene": start.get("scene", False),
                      "start": graph["start"], "nodes": nodes})
    flow = story_graph(data, labels, cast)
    node_map = {f"c{i}": ["c", key] for i, key in enumerate(data["conversations"])}
    node_map.update({fid: ["f", info["id"]] for fid, info in flow["facts"].items()})
    facts = {name: {"essential": bool(v.get("essential")), "topic": bool(v.get("topic")), "needs": v.get("needs", []),
                    "knownBy": [cast.get(n, n) for n in v.get("known_by", [])]}
             for name, v in data["plot"].get("facts", {}).items()}
    page = {"title": data.get("title", story_id), "frame": data.get("premise", ""), "truth": data.get("hidden_truth", ""),
            "errors": report["errors"], "warnings": report["warnings"], "facts": facts, "convs": convs, "rules": rules,
            "nodeMap": node_map}
    return page, flow["mermaid"]


def fingerprint(story_id, index):
    """What an acceptance holds for: the story's source and every line and recording as it is reviewed now."""
    content = json.dumps([library.revision(story_id), sorted(index.items(), key=lambda pair: pair[0])])
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:12]


# --- voices: re-sample a take, or rebuild a voice's reference, through a worker that keeps the model loaded ---

_worker = {"process": None}
WORKER_LOCK = threading.Lock()
TAKE_LOCK = threading.Lock()  # choosing and removing takes of the same recording must not interleave


def ensure_worker():
    """Starts the voice worker once. It loads the model a single time and ends with this server."""
    with WORKER_LOCK:
        process = _worker["process"]
        if process is not None and process.poll() is None:
            return None
        python = bake_voices.venv_python()
        if not python.exists():
            return "the speech model is not installed: python3 python/dm/bake_voices.py setup"
        log = open(voices.RUNTIME_DIR / "voice_worker.log", "ab")
        # the worker ends when this pipe closes, which happens however this server ends
        _worker["process"] = subprocess.Popen([str(python), str(ROOT / "bake_voices.py"), "worker"],
                                              stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.PIPE)
        return None


@atexit.register
def _stop_worker():
    process = _worker["process"]
    if process is not None and process.poll() is None:
        process.terminate()


def line_of(data, review_id):
    """(voice, text, delivery) of a voice review such as CONV__node__voice, CONV__node__again__voice,
    CONV__node__v0__voice or CONV__node__c1__voice, or None."""
    if not review_id.endswith("__voice"):
        return None
    parts = review_id[:-len("__voice")].split("__")
    if len(parts) not in (2, 3):
        return None
    conv = next((c for c in data["convs"] if c["id"] == parts[0]), None)
    node = conv and conv["nodes"].get(parts[1])
    if node is None:
        return None
    what = parts[2] if len(parts) == 3 else ""
    if what == "":
        return conv["voice"], node["line"], node.get("delivery")
    if what == "again" and node.get("again"):
        return conv["voice"], node["again"], node.get("delivery")
    if re.fullmatch(r"v\d+", what) and int(what[1:]) < len(node.get("variants", [])):
        return conv["voice"], node["variants"][int(what[1:])]["line"], node.get("delivery")
    if re.fullmatch(r"c\d+", what) and int(what[1:]) < len(node["choices"]):
        return voices.HERO_VOICE, node["choices"][int(what[1:])]["text"], None
    return None


def takes_index(data):
    """How many takes each voice review has, for lines that were re-sampled."""
    found = {}
    for conv in data["convs"]:
        for key, node in conv["nodes"].items():
            base = f"{conv['id']}__{key}"
            ids = [base] + ([base + "__again"] if node.get("again") else []) \
                + [f"{base}__v{i}" for i in range(len(node.get("variants", [])))] \
                + [f"{base}__c{i}" for i in range(len(node["choices"]))]
            for review_id in ids:
                line = line_of(data, review_id + "__voice")
                count = len(bake_voices.list_takes(*line)) if line and line[0] else 0
                if count > 1:
                    found[review_id + "__voice"] = count
    return found


def takes_of(line):
    path = voices.audio_path(*line)
    chosen = bake_voices.chosen_take(*line)
    return [{"n": n, "url": f"/take/{line[0]}/{path.stem}/{n}.wav?v={(bake_voices.takes_dir(*line) / f'{n}.wav').stat().st_mtime_ns}",
             "chosen": n == chosen} for n in bake_voices.list_takes(*line)]


def story_graphs(story_id):
    if story_id == library.DEMO_ID:
        return t.all_graphs()
    return library.generated(story_id)[1]


def voice_panel(story_id, data):
    """The voices a story speaks with, who uses them, and how long each reference is."""
    graphs = story_graphs(story_id)
    used = {}
    for conv in data["convs"]:
        if conv.get("voice"):
            used.setdefault(conv["voice"], set()).add(conv["speaker"])
    if any(c for conv in data["convs"] for n in conv["nodes"].values() for c in n["choices"]):
        used.setdefault(voices.HERO_VOICE, set())
    panel = []
    for voice, speakers in sorted(used.items()):
        reference = voices.REF_DIR / f"{voice}.wav"
        seconds = None
        if reference.exists():
            import wave
            with wave.open(str(reference)) as w:
                seconds = round(w.getnframes() / w.getframerate(), 1)
        keys = bake_voices.reference_keys(voice) if reference.exists() else None
        panel.append({"voice": voice, "speakers": sorted(speakers), "seconds": seconds,
                      "count": len(keys) if keys else None, "lines": len(bake_voices.voice_lines(graphs, voice))})
    return panel


def library_data():
    """Every story with its stage, review progress and what still blocks acceptance."""
    reviews = load_reviews()
    result = []
    for entry in library.entries():
        data, _ = story_view(entry["id"])
        if data is None:
            continue
        index = content_index(data)
        prefix = entry["id"] + "/"
        valid = {key[len(prefix):]: value for key, value in reviews.items() if key.startswith(prefix)
                 and value.get("hash") is not None and value["hash"] == index.get(key[len(prefix):])}
        reviewable = [key for key, content in index.items() if content is not None]
        speakers = sorted({c["speaker"] for c in data["convs"]})
        entry["stage"], entry["changed"] = library.stage_of(entry["id"], rev=fingerprint(entry["id"], index))
        result.append({**entry, "lines": len(reviewable), "reviewed": sum(1 for key in reviewable if key in valid),
                       "rejected": sum(1 for key in reviewable if valid.get(key, {}).get("verdict") == "reject"),
                       "errors": len(data["errors"]), "warnings": len(data["warnings"]), "speakers": speakers,
                       "blockers": library.gate(data["errors"], valid, index)})
    return result


def load_reviews():
    return json.loads(REVIEWS.read_text(encoding="utf-8")) if REVIEWS.exists() else {}


def _with_quotes(entries, quotes):
    """Restore the private quoted game text for display on this machine only."""
    for entry in entries:
        excerpts = quotes.get(entry.get("key"), [])
        index = entry.get("excerpt", 0)
        entry["quote"] = excerpts[index] if index < len(excerpts) else "(quote not available)"


def character_data():
    """Every sheet and the world facts, read fresh so edits show on reload."""
    sheets = []
    for path in sorted(CHARACTERS.glob("*.json")):
        try:
            sheets.append({**json.loads(path.read_text(encoding="utf-8")), "file": path.stem})
        except ValueError as error:  # one hand-edited file must not hide the others
            sheets.append({"file": path.stem, "error": str(error)})
    facts = json.loads(WORLD_FACTS.read_text(encoding="utf-8"))["facts"] if WORLD_FACTS.exists() else []
    path = voices.RUNTIME_DIR / "quotes.json"
    quotes = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    _with_quotes(facts, quotes)
    for sheet in sheets:
        _with_quotes(sheet.get("evidence", []), quotes)
    return {"characters": sheets, "facts": facts}


EXPERIMENT = voices.RUNTIME_DIR / "experiment"
EXPERIMENT_PAGE = ROOT / "inspector" / "experiment.html"
SCORES = EXPERIMENT / "scores.json"
_blind_id = library.blind_id


def _as_list(value):
    return value if isinstance(value, list) else ([value] if value else [])


def _graph_text(text, limit=44):
    """Text that is safe inside a quoted Mermaid label."""
    text = re.sub(r"[\"#\[\]{}<>|]", "'", " ".join(str(text).split()))
    return text if len(text) <= limit else text[:limit - 1].rstrip() + "…"


def _sheet_names():
    names = {}
    for path in CHARACTERS.glob("*.json"):
        try:
            sheet = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            continue
        if sheet.get("npc") and sheet.get("name"):
            names[sheet["npc"]] = sheet["name"]
    return names


def _conversation_names(data, sheets):
    """A readable heading for each conversation, derived from the story's own cast."""
    cast = dict(sheets)
    cast.update({c["npc"]: c["name"] for c in data.get("new_characters", [])
                 if isinstance(c, dict) and c.get("npc") and c.get("name")})
    cast.update({o["instance"]: o["display_name"] for o in data["plan"]
                 if o["op"] in ("spawn_npc", "rename_npc") and o.get("display_name")})
    labels = {}
    for key in data["conversations"]:
        npc = max((n for n in cast if key == n or key.startswith(n + "_")), key=len, default=None)
        if npc is None:
            labels[key] = key
        else:
            variant = key[len(npc):].strip("_").replace("_", " ").lower()
            labels[key] = cast[npc] + (" · " + variant if variant else "")
    return labels, cast


def story_graph(data, labels, cast):
    """The Tilo-style flow graph for one generated story, read from its plan and dialogue."""
    conversations = data["conversations"]
    plot_facts = data["plot"]["facts"]
    conv_ids = {key: f"c{i}" for i, key in enumerate(conversations)}
    fact_ids, facts, effects, edges, attached = {}, {}, {}, {}, set()

    def fact(name):
        if name not in fact_ids:
            fact_ids[name] = f"f{len(fact_ids)}"
            info = plot_facts.get(name, {})
            facts[fact_ids[name]] = {"id": name, "text": info.get("text", ""), "essential": bool(info.get("essential")),
                                     "taught": [], "unlocks": []}
        return fact_ids[name]

    def note(name, field, value):
        entries = facts[fact(name)][field]
        if value not in entries:
            entries.append(value)

    def effect(label):
        return effects.setdefault(label, f"r{len(effects)}")

    def edge(line):
        edges[line] = True

    def facts_of(values):
        return [v for v in values if isinstance(v, str)]

    for key, graph in conversations.items():
        for node in graph["nodes"].values():
            for name in facts_of(_as_list(node.get("sets")) + _as_list(node.get("teaches"))):
                edge(f"  {conv_ids[key]} --> {fact(name)}")
                note(name, "taught", labels[key])
            for choice in node["choices"]:
                for name in facts_of(_as_list(choice.get("teaches"))):
                    edge(f"  {conv_ids[key]} --> {fact(name)}")
                    note(name, "taught", labels[key])
                for name in facts_of(_as_list(choice.get("requires"))):
                    edge(f"  {fact(name)} -. line .-> {conv_ids[key]}")
                    note(name, "unlocks", labels[key] + ": „" + choice["text"] + "“")

    def walk(ops, when=(), unless=()):
        for op in ops:
            if op["op"] == "add_rule":
                walk(op["ops"], facts_of(_as_list(op.get("when"))), facts_of(_as_list(op.get("unless"))))
            elif op["op"] in ("add_scene", "attach_dialogue_graph"):
                key = next(k for k, g in conversations.items() if g == op["graph"])
                attached.add(key)
                for name in list(when) + facts_of(_as_list(op.get("requires"))):
                    edge(f"  {fact(name)} ==>|starts| {conv_ids[key]}")
                    note(name, "unlocks", "Beginnt: " + labels[key])
                for name in list(unless) + facts_of(_as_list(op.get("unless"))):
                    edge(f"  {fact(name)} --x|closes| {conv_ids[key]}")
            elif op["op"] == "set_flag":
                for name in when:
                    edge(f"  {fact(name)} ==> {fact(op['name'])}")
                note(op["name"], "taught", "eine Folge in der Welt")
            elif when and _outcome(op, cast):
                target = effect(_outcome(op, cast))
                for name in when:
                    edge(f"  {fact(name)} ==> {target}")
                for name in unless:
                    edge(f"  {fact(name)} --x {target}")

    walk(data["plan"])
    return {"mermaid": _flow_mermaid(labels, conv_ids, attached, fact_ids, facts, effects, edges), "facts": facts}


def _outcome(op, cast):
    """How a plan operation shows in the flow graph, or None if it does not."""
    who = cast.get(op.get("npc") or op.get("instance"), op.get("npc") or op.get("instance"))
    if op["op"] == "give_item":
        return f"{op.get('count', 1)}× {op['instance']}"
    if op["op"] == "place_item":
        return (op.get("quest") or {}).get("description") or op["instance"]
    return {"send_npc": f"{who} geht fort", "relocate_npc": f"{who} wechselt den Ort",
            "detach_dialogue_graph": f"{who} verstummt", "spawn_npc": f"{who} erscheint",
            "rename_npc": f"{who} heisst nun anders"}.get(op["op"])


def _flow_mermaid(labels, conv_ids, attached, fact_ids, facts, effects, edges):
    """Mermaid source of a story's flow graph: conversations, facts, effects, then the edges between them."""
    lines = ["flowchart LR"]
    for key, node_id in conv_ids.items():
        mark = "" if key in attached else " (nie gestartet)"
        lines.append(f'  {node_id}["{_graph_text(labels[key] + mark)}"]:::conv')
    for name, node_id in fact_ids.items():
        info = facts[node_id]
        lines.append(f'  {node_id}("{_graph_text(info["text"] or name.replace("_", " "))}"):::{"ess" if info["essential"] else "fact"}')
    for label, node_id in effects.items():
        lines.append(f'  {node_id}(["{_graph_text(label)}"]):::effect')
    lines += list(edges)
    lines += _CLASS_DEFS
    return "\n".join(lines)


def experiment_data():
    """All stories in one fixed, shuffled order that hides which author wrote each."""
    sheets = _sheet_names()
    graphs = json.loads((EXPERIMENT / "graphs.json").read_text(encoding="utf-8"))
    stories, total, ready = [], 0, 0

    def url(voice, text, delivery=None):
        nonlocal total, ready
        total += 1
        found = audio_url(voice, text, delivery)
        ready += bool(found)
        return found

    for path in _story_paths():
        data = json.loads(path.read_text(encoding="utf-8"))
        convs = []
        labels, cast = _conversation_names(data, sheets)
        for key in data["conversations"]:
            graph = graphs[f"{path.stem}__{key}"]
            nodes = []
            for node_key, node in graph["nodes"].items():
                choices = [{"text": c["text"], "audio": None if c["text"] == "Zurück." else url(voices.HERO_VOICE, c["text"]),
                            "info": (("→ " + c["goto"]) if c.get("goto") else "Ende")
                            + ((" · braucht " + " oder ".join(c["requires"])) if c.get("requires") else "")}
                           for c in node["choices"]]
                entry = {"key": node_key, "line": node["line"], "audio": url(graph["voice"], node["line"]),
                         "returns": node.get("returns"), "choices": choices}
                if node.get("again"):
                    entry["again"] = node["again"]
                    entry["audioAgain"] = url(graph["voice"], node["again"])
                nodes.append(entry)
            convs.append({"who": labels[key], "when": "", "nodes": nodes})
        stories.append({"id": _blind_id(path.stem), "title": data["title"], "premise": data.get("premise", ""),
                        "hidden_truth": data["hidden_truth"], "convs": convs,
                        "graph": story_graph(data, labels, cast), "bonus": bool(data.get("bonus")), "stem": path.stem,
                        "rev": hashlib.sha256(path.read_bytes()).hexdigest()[:12]})
    stories.sort(key=lambda s: (s["bonus"], s["stem"] if s["bonus"] else s["id"]))  # bonus stories go last, so the scored numbering stays put
    for story in stories:
        del story["stem"]  # the file name says which snapshot and author it came from
    return {"stories": stories, "total": total, "ready": ready}


MAX_BODY, MAX_TEXT = 200_000, 20_000


_story_paths = library.story_paths


def _clean_score(request):
    """Only known stories and known fields reach the scores file."""
    if request.get("id") not in {_blind_id(p.stem) for p in _story_paths()}:
        return "unknown story", None
    score = {k: request[k] for k in ("worth", "interest", "defects", "deed", "original", "rev")
             if request.get(k) not in (None, "")}
    if score.get("worth", "yes") not in ("yes", "no"):
        return "bad verdict", None
    if score.get("deed", "yes") not in ("yes", "no"):   # experiment 2: does a deed matter
        return "bad deed verdict", None
    if score.get("original", "yes") not in ("yes", "no"):   # could it have been in the original game
        return "bad original verdict", None
    if score.get("interest", 1) not in (1, 2, 3, 4, 5):
        return "bad interest", None
    if len(str(score.get("defects", ""))) > MAX_TEXT:
        return "text too long", None
    return None, score


def load_scores():
    return json.loads(SCORES.read_text(encoding="utf-8")) if SCORES.exists() else {}


class Handler(http.server.BaseHTTPRequestHandler):
    def _language(self):
        cookies = http.cookies.SimpleCookie(self.headers.get("Cookie", ""))
        return cookies["lang"].value if "lang" in cookies and cookies["lang"].value == "de" else "en"

    def _localized(self, html):
        language = self._language()
        html = inspector_i18n.translate(html, language)
        for link in (f'<a href="{self.path}">', f'<a href="?lang={language}" hreflang="{language}">'):
            html = html.replace(link, link[:-1] + ' aria-current="page">', 1)
        return html.encode("utf-8")

    def _send(self, body, kind="application/json", status=200):
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, value):
        self._send(json.dumps(value, ensure_ascii=False).encode("utf-8"))

    def _send_page(self, page):
        self._send(self._localized(page.read_text(encoding="utf-8")), "text/html; charset=utf-8")

    def do_GET(self):
        path, _, query = self.path.partition("?")
        self.path = path.rstrip("/") or "/"
        params = dict(urllib.parse.parse_qsl(query))
        chosen = params.get("lang")
        if chosen in ("en", "de"):
            self.send_response(303)
            self.send_header("Location", self.path)
            self.send_header("Set-Cookie", f"lang={chosen}; Path=/; Max-Age=31536000; SameSite=Lax")
            self.send_header("Content-Length", "0")
            return self.end_headers()
        route = GET_ROUTES.get(self.path)
        if route is not None:
            return route(self, params)
        for pattern, route in GET_PATTERNS:
            match = pattern.match(self.path)
            if match:
                return route(self, match)
        self._send(b"{}", status=404)

    # --- GET handlers, by exact path: each takes the parsed query ---

    def _get_map_data(self, params):
        path = MAP_DIR / "map_data.json"
        if not path.exists():
            return self._send(b"{}", status=404)
        self._send(path.read_bytes())

    def _get_voice_takes(self, params):
        data = story_view(params.get("story", ""))[0]
        line = line_of(data, params.get("id", "")) if data else None
        if line is None:
            return self._send(b"{}", status=404)
        self._send(json.dumps({"takes": takes_of(line), "current": audio_url(*line),
                               "spare": bake_voices.spare_path(*line).exists()}).encode("utf-8"))

    def _get_voice_status(self, params):
        finished = bake_voices.job_result(params.get("job"))
        if finished is not None:
            return self._send_json({**finished, "finished": True})
        try:
            state = json.loads(bake_voices.JOB_STATUS.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            state = {"state": "idle"}
        process = _worker["process"]
        state["worker"] = process is not None and process.poll() is None
        self._send_json(state)

    def _get_story_data(self, params):   # the page's data again, after a line was edited
        story_id = params.get("id", "")
        data = story_view(story_id)[0]
        if data is None:
            return self._send(b"{}", status=404)
        self._send_json({**data, "id": story_id, "voices": voice_panel(story_id, data), "takes": takes_index(data)})

    def _get_vendor(self, params):
        path = voices.RUNTIME_DIR / "vendor" / self.path.rsplit("/", 1)[1]
        if path.exists():
            self._send(path.read_bytes(), "text/javascript; charset=utf-8")
        else:
            self._send(b"", "text/javascript; charset=utf-8", status=404)

    def _get_reviews(self, params):
        story_id = params.get("story", library.DEMO_ID)
        if story_view(story_id)[0] is None:
            return self._send(b"{}", status=404)
        self._send_json(story_reviews(story_id))

    # --- GET handlers, by pattern: each takes the match ---

    def _get_map_image(self, match):
        path = MAP_DIR / match[1]
        if not path.exists():
            return self._send(b"", "image/png", status=404)
        self._send(path.read_bytes(), "image/png")

    def _get_take(self, match):
        path = voices.VOICE_DIR / match[1] / "takes" / match[2] / f"{match[3]}.wav"
        if not path.exists():
            return self._send(b"{}", status=404)
        self._send(path.read_bytes(), "audio/wav")

    def _get_audio(self, match):
        path = voices.VOICE_DIR / match[1] / f"{match[2]}.wav"
        if not path.exists():
            return self._send(b"{}", status=404)
        self._send(path.read_bytes(), "audio/wav")

    def _get_story_page(self, match):
        story_id = match[1]
        data, graph = story_view(story_id)
        if data is None:
            return self._send(b"unknown story", "text/plain; charset=utf-8", status=404)
        data = {**data, "id": story_id, "voices": voice_panel(story_id, data), "takes": takes_index(data)}
        language = self._language()
        # Translate the page first, then insert the story. Only the demo story's own labels are translated,
        # generated stories stay in the language they were written in.
        labels = (lambda text: inspector_i18n.translate(text, language, inspector_i18n.LABELS)) \
            if story_id == library.DEMO_ID else (lambda text: text)
        mermaid = labels(graph) if story_id == library.DEMO_ID else html_escape(graph, quote=False)
        html = self._localized(PAGE.read_text(encoding="utf-8")).decode("utf-8").replace("%%GRAPH%%", mermaid).replace(
            "/*DATA*/null", labels(json.dumps(data, ensure_ascii=False)).replace("</", "<\\/"))
        self._send(html.encode("utf-8"), "text/html; charset=utf-8")

    def _read_json(self):
        """Another website can send requests to localhost, so only this page's own JSON is accepted."""
        allowed = {f"127.0.0.1:{PORT}", f"localhost:{PORT}"}
        host, origin = self.headers.get("Host"), self.headers.get("Origin")
        if host not in allowed or (origin and origin != f"http://{host}"):
            return "wrong origin", None
        if not (self.headers.get("Content-Type") or "").startswith("application/json"):
            return "expected JSON", None
        try:
            length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            return "missing length", None
        if not 0 < length <= MAX_BODY:
            return "bad length", None
        try:
            request = json.loads(self.rfile.read(length))
        except ValueError:
            return "malformed JSON", None
        return (None, request) if isinstance(request, dict) else ("expected an object", None)

    def do_POST(self):
        route = POST_ROUTES.get(self.path)
        if route is None:
            return self._send(b"{}", status=404)
        problem, request = self._read_json()
        if problem:
            return self._send(json.dumps({"error": problem}).encode("utf-8"), status=400)
        route(self, request)

    def _score(self, request):
        problem, score = _clean_score(request)
        if problem:
            return self._send(json.dumps({"error": problem}).encode("utf-8"), status=400)
        with REVIEW_LOCK:
            scores = load_scores()
            scores[request["id"]] = score
            temporary = SCORES.with_suffix(".tmp")
            temporary.write_text(json.dumps(scores, ensure_ascii=False, indent=1), encoding="utf-8")
            temporary.replace(SCORES)
        self._send(b"{}")

    def _review(self, request):
        story_id = request.get("story", library.DEMO_ID)
        data = story_view(story_id)[0] if isinstance(story_id, str) else None
        target = content_index(data).get(request.get("id")) if data else None
        if target is None or request.get("verdict") not in (None, "approve", "reject") or len(str(request.get("reason", ""))) > MAX_TEXT:
            return self._send(b'{"error": "bad review"}', status=400)
        with REVIEW_LOCK:
            reviews = load_reviews()
            key = story_id + "/" + request["id"]
            if request.get("verdict"):
                reviews[key] = {"verdict": request["verdict"], "reason": request.get("reason", ""), "hash": target}
            else:
                reviews.pop(key, None)
            _write_reviews(reviews)
        if request.get("verdict") == "reject":   # start the next take now, so re-sampling can swap it in at once
            line = line_of(data, request["id"])
            if line and not ensure_worker():
                bake_voices.queue({"kind": "spare", "lines": [list(line)]}, urgent=False)
        self._send(b"{}")

    def _error(self, message, status=400):
        self._send(json.dumps({"error": message}, ensure_ascii=False).encode("utf-8"), status=status)

    def _stage(self, request):
        story_id = request.get("id")
        data = story_view(story_id)[0] if isinstance(story_id, str) else None
        if data is None:
            return self._error("unknown story")
        index = content_index(data)
        rev = fingerprint(story_id, index)
        with REVIEW_LOCK:
            blockers = library.gate(data["errors"], story_reviews(story_id), index)
            problem = library.move(story_id, request.get("stage"), blockers, rev)
        if problem:
            return self._error(problem, status=409)
        self._send(json.dumps({"stage": library.stage_of(story_id, rev=rev)[0]}).encode("utf-8"))

    def _resample(self, request):
        story_id = request.get("story")
        data = story_view(story_id)[0] if isinstance(story_id, str) else None
        line = line_of(data, str(request.get("id", ""))) if data else None
        if line is None or not voices.audio_path(*line).exists():
            return self._error("no recording to re-sample")
        problem = ensure_worker()
        if problem:
            return self._error(problem, status=503)
        ready = bake_voices.spare_path(*line).exists()
        job = bake_voices.queue({"kind": "resample", "lines": [list(line)]})
        self._send(json.dumps({"job": job, "ready": ready}).encode("utf-8"))

    def _edit(self, request):
        story_id, review_id, text = request.get("story"), request.get("id"), request.get("text")
        if not all(isinstance(x, str) for x in (story_id, review_id, text)):
            return self._error("bad request")
        try:
            voice, old, new, delivery = library.edit_line(story_id, review_id, text)
        except ValueError as problem:
            return self._error(str(problem), status=409)
        job = None
        if new != old and voice and (voices.REF_DIR / f"{voices.reference_name(voice, delivery)}.wav").exists() \
                and not voices.audio_path(voice, new, delivery).exists() and not ensure_worker():
            job = bake_voices.queue({"kind": "speak", "lines": [[voice, new, delivery]]})  # the new text, voiced now
        self._send(json.dumps({"job": job, "text": new}, ensure_ascii=False).encode("utf-8"))

    def _take(self, request, choose):
        story_id = request.get("story")
        data = story_view(story_id)[0] if isinstance(story_id, str) else None
        line = line_of(data, str(request.get("id", ""))) if data else None
        number = request.get("n")
        if line is None or not isinstance(number, int):
            return self._error("bad request")
        try:
            with TAKE_LOCK:
                (bake_voices.choose_take if choose else bake_voices.discard_take)(line, number)
        except ValueError as problem:
            return self._error(str(problem), status=409)
        self._send(json.dumps({"takes": takes_of(line), "current": audio_url(*line)}).encode("utf-8"))

    def _reference(self, request):
        story_id = request.get("story")
        data = story_view(story_id)[0] if isinstance(story_id, str) else None
        voice, count = request.get("voice"), request.get("count")
        if data is None or not isinstance(voice, str) or not re.fullmatch(r"\d{2}", voice) \
                or count not in (1, 2, 3, 4, 5, 6):
            return self._error("bad request")
        problem = ensure_worker()
        if problem:
            return self._error(problem, status=503)
        job = bake_voices.queue({"kind": "reference", "voice": voice, "count": count, "graphs": story_graphs(story_id)})
        self._send(json.dumps({"job": job}).encode("utf-8"))

    @staticmethod
    def _play_generated(story_id):
        """A generated story, started like play_story does: closures, its own ids, its cast and requirements."""
        start = library.start(story_id)
        return bridge.call("play", start["title"], start["ops"], start["requires"], start["story"], start["cast"])

    def _play(self, request):
        story_id = request.get("id")
        data = story_view(story_id)[0] if isinstance(story_id, str) else None
        if data is None:
            return self._error("unknown story")
        if library.stage_of(story_id, rev=fingerprint(story_id, content_index(data)))[0] != library.ACCEPTED:
            return self._error("only accepted stories can be played", status=409)
        reply = bridge.call("play_demo") if story_id == library.DEMO_ID else \
            self._play_generated(story_id)
        if reply.get("error") or reply.get("ok") is False:
            return self._error(reply.get("error") or "the game refused the story", status=502)
        self._send(b"{}")

    def log_message(self, *args):
        pass


def _page(page):
    return lambda handler, params: handler._send_page(page)


def _static(path, kind):
    return lambda handler, params: handler._send(path.read_bytes(), kind)


def _json(read):
    return lambda handler, params: handler._send_json(read())


# exact paths, after the query and a trailing slash are stripped
GET_ROUTES = {
    "/": _page(LIBRARY_PAGE),
    "/map": _page(MAP_PAGE),
    "/map/data": Handler._get_map_data,
    "/voice/takes": Handler._get_voice_takes,
    "/voice/status": Handler._get_voice_status,
    "/library/data": _json(library_data),
    "/story/data": Handler._get_story_data,
    "/vendor/mermaid.min.js": Handler._get_vendor,
    "/vendor/svg-pan-zoom.min.js": Handler._get_vendor,
    "/gothic.css": _static(ROOT / "inspector" / "gothic.css", "text/css; charset=utf-8"),
    "/characters": _page(CHARACTERS_PAGE),
    "/characters.json": _json(character_data),
    "/experiment": _page(EXPERIMENT_PAGE),
    "/experiment/data": _json(experiment_data),
    "/experiment/scores": _json(load_scores),
    "/reviews": Handler._get_reviews,
}

# tried in order when no exact path matches; anything else is a 404
GET_PATTERNS = [
    (MAP_IMAGE, Handler._get_map_image),
    (TAKE_PATH, Handler._get_take),
    (re.compile(r"^/story/(.*)$", re.DOTALL), Handler._get_story_page),
    (AUDIO_PATH, Handler._get_audio),
]

# the full request path, query included: anything else is a 404 before the body is read
POST_ROUTES = {
    "/reviews": Handler._review,
    "/experiment/score": Handler._score,
    "/library/stage": Handler._stage,
    "/library/play": Handler._play,
    "/voice/resample": Handler._resample,
    "/voice/reference": Handler._reference,
    "/voice/choose": lambda handler, request: handler._take(request, True),
    "/voice/discard": lambda handler, request: handler._take(request, False),
    "/line/edit": Handler._edit,
}


if __name__ == "__main__":
    adopt_existing_reviews()
    print(f"Story inspector: http://127.0.0.1:{PORT}")
    http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()

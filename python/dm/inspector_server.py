"""Local story inspector: read, listen to and review every line of a story.

    python3 python/dm/inspector_server.py
    then open http://127.0.0.1:8765

Serves only on this machine, because the generated voices must stay here. Reviews
are stored in python/dm_runtime/reviews.json.
"""

import copy
import hashlib
import http.cookies
import http.server
import importlib
import json
import pathlib
import re
import sys
import threading
import types
import urllib.parse

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))
sys.modules.setdefault("gothic", types.ModuleType("gothic"))

from dm import knowledge as k  # noqa: E402
from dm import inspector_i18n  # noqa: E402
from dm import voices  # noqa: E402
from dm.stories import tilo as t  # noqa: E402

PORT = 8765
PAGE = ROOT / "inspector" / "page.html"
CHARACTERS_PAGE = ROOT / "inspector" / "characters.html"
CHARACTERS = ROOT / "characters"
WORLD_FACTS = ROOT / "world_facts.json"
REVIEWS = voices.RUNTIME_DIR / "reviews.json"
REVIEW_LOCK = threading.Lock()  # requests arrive on separate threads
AUDIO_PATH = re.compile(r"^/audio/([0-9A-Za-z_]+)/([0-9a-f]{20})\.wav$")


def audio_url(voice, text, delivery=None):
    if not voice or not voices.audio_path(voice, text, delivery).exists():
        return None
    return "/audio/" + "/".join(voices.audio_path(voice, text, delivery).parts[-2:])


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
    data={"frame":re.sub(r"\s+"," ",t.__doc__.split("Frame:")[1]).strip(),"truth":t.HIDDEN_TRUTH,"errors":errors,"warnings":warnings,"facts":{f:dict(essential=v.get("essential",False),topic=v.get("topic",False),needs=v.get("needs",[]),knownBy=[names.get(n,n) for n in v.get("known_by",[])]) for f,v in plot["facts"].items()},
    "convs":[{"id":i,"speaker":s,"where":w,"requires":scenes.get(i,{}).get("requires",[]),"unless":scenes.get(i,{}).get("unless") or [],"within":scenes.get(i,{}).get("within"),"scene":i in scenes,"start":g[i]["start"],"nodes":g[i]["nodes"]} for i,s,w in order],
    "rules":[{"id":r["id"],"when":r["when"],"ops":[{k:v for k,v in o.items() if k in("op","instance","count","id","waypoint","requires")} for o in r["ops"]]} for r in rules]}
    lab={"tilo_named":"Tilos Name","tilo_absent":"Tilo fehlt","wine_trips":"seine Weingänge","silver_stolen":"Silber gestohlen","candlesticks":"zwei Leuchter","reward":"Belohnung ausgesetzt","tilo_past":"sein Vater","gambling":"Würfelschulden","harbour_lead":"Spur zum Hafen","friend_offer":"Anselms Angebot","harek_wary":"Harek ist misstrauisch","silver_sold":"Silber an Harek verkauft","tilo_nearby":"versteckt am Hafen","tilo_cornered":"am Hafen getroffen","tilo_met":"Tilo getroffen","barrel_met":"Fass-Novize getroffen","tilo_stressed":"wirkte gehetzt","tilo_turned_in":"Tilo ausgeliefert","tilo_helped":"Tilo geholfen","parlan_paid":"Belohnung bezahlt","anselm_secret":"Geheimnis erzählt","tilo_threatened":"Tilo erpresst","tilo_confessed":"Tilo gestanden"}
    conv={c["id"]:c for c in data["convs"]}
    titles={"tilo_back_at_work":"Tilo wieder bei der Arbeit","tilo_ordered_home":"Tilo gehorcht","tilo_after_help":"Tilo verabschiedet sich","tilo_after_turned_in":"Tilo verspricht zu folgen","barrel":"Der Novize an den Fässern","tilo_before":"Tilo vor dem Diebstahl","gorax":"Gorax beschwert sich","parlan":"Parlan verkündet","anselm":"Anselms Bitte","harek":"Harek","tilo":"Tilo","parlan_reward":"Parlan zahlt","anselm_bitter":"Anselm wendet sich ab","anselm_grateful":"Anselms Geheimnis"}
    L=["flowchart LR"]; seen=set(); facts=set(); E=set()
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
    L+=["  classDef conv fill:#7A1F14,stroke:#2a1c10,color:#F0E2C0","  classDef fact fill:#EADBB6,stroke:#7A5F36,color:#2A1C10","  classDef ess fill:#D9A441,stroke:#7A1F14,color:#2A1C10","  classDef effect fill:#3E5A22,stroke:#2a1c10,color:#F0E2C0"]
    for conv in data["convs"]:
        voice = g[conv["id"]].get("voice")
        conv["nodes"] = copy.deepcopy(conv["nodes"])
        for n in conv["nodes"].values():
            n["audio"] = audio_url(voice, n["line"], n.get("delivery"))
            if n.get("again"):
                n["audioAgain"] = audio_url(voice, n["again"], n.get("delivery"))
            for choice in n["choices"]:
                choice["audio"] = audio_url(voices.HERO_VOICE, choice["text"])
    return data, "\n".join(L)


def _text_hash(text):
    return "t:" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


_audio_hashes = {}


def _audio_hash(url):
    """Hash of a generated audio file, or None if there is none."""
    if not url:
        return None
    voice, name = url.split("/")[-2:]
    path = voices.VOICE_DIR / voice / name
    stamp = (str(path), path.stat().st_mtime_ns)
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
            for i, choice in enumerate(node["choices"]):
                index[f"{base}__c{i}"] = _text_hash(choice["text"])
                index[f"{base}__c{i}__voice"] = _audio_hash(choice.get("audio"))
    return index


def current_reviews():
    """Reviews still valid for what the story says now. Changed lines count as unreviewed."""
    index = content_index(build()[0])
    return {key: value for key, value in load_reviews().items()
            if value.get("hash") is not None and value["hash"] == index.get(key)}


def adopt_existing_reviews():
    """Bind reviews written before hashing to the content as it is now."""
    index = content_index(build()[0])
    with REVIEW_LOCK:
        reviews = load_reviews()
        for key, value in reviews.items():
            if "hash" not in value and index.get(key):
                value["hash"] = index[key]
        temporary = REVIEWS.with_suffix(".tmp")
        temporary.write_text(json.dumps(reviews, ensure_ascii=False, indent=1), encoding="utf-8")
        temporary.replace(REVIEWS)


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
def _blind_id(name):
    return hashlib.sha256(("experiment-1:" + name).encode("utf-8")).hexdigest()[:10]


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

    def outcome(op):
        who = cast.get(op.get("npc") or op.get("instance"), op.get("npc") or op.get("instance"))
        if op["op"] == "give_item":
            return f"{op.get('count', 1)}× {op['instance']}"
        if op["op"] == "place_item":
            return (op.get("quest") or {}).get("description") or op["instance"]
        return {"send_npc": f"{who} geht fort", "relocate_npc": f"{who} wechselt den Ort",
                "detach_dialogue_graph": f"{who} verstummt", "spawn_npc": f"{who} erscheint",
                "rename_npc": f"{who} heisst nun anders"}.get(op["op"])

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
            elif when and outcome(op):
                target = effect(outcome(op))
                for name in when:
                    edge(f"  {fact(name)} ==> {target}")
                for name in unless:
                    edge(f"  {fact(name)} --x {target}")

    walk(data["plan"])
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
    lines += ["  classDef conv fill:#7A1F14,stroke:#2a1c10,color:#F0E2C0",
              "  classDef fact fill:#EADBB6,stroke:#7A5F36,color:#2A1C10",
              "  classDef ess fill:#D9A441,stroke:#7A1F14,color:#2A1C10",
              "  classDef effect fill:#3E5A22,stroke:#2a1c10,color:#F0E2C0"]
    return {"mermaid": "\n".join(lines), "facts": facts}


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


def _story_paths():
    stories = EXPERIMENT / "stories"
    return [p for p in sorted(stories.glob("s*_*.json")) + sorted(stories.glob("x*_*.json"))
            if not p.name.endswith((".first.json", ".final.json"))]


def _clean_score(request):
    """Only known stories and known fields reach the scores file."""
    if request.get("id") not in {_blind_id(p.stem) for p in _story_paths()}:
        return "unknown story", None
    score = {k: request[k] for k in ("worth", "interest", "defects", "rev") if request.get(k) not in (None, "")}
    if score.get("worth", "yes") not in ("yes", "no"):
        return "bad verdict", None
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

    def do_GET(self):
        path, _, query = self.path.partition("?")
        self.path = path.rstrip("/") or "/"
        chosen = dict(urllib.parse.parse_qsl(query)).get("lang")
        if chosen in ("en", "de"):
            self.send_response(303)
            self.send_header("Location", self.path)
            self.send_header("Set-Cookie", f"lang={chosen}; Path=/; Max-Age=31536000; SameSite=Lax")
            self.send_header("Content-Length", "0")
            return self.end_headers()
        if self.path == "/":
            data, graph = build()
            language = self._language()
            # Translate the page first, then insert the story, whose own text only has its labels swapped.
            labels = lambda text: inspector_i18n.translate(text, language, inspector_i18n.LABELS)
            html = self._localized(PAGE.read_text(encoding="utf-8")).decode("utf-8").replace("%%GRAPH%%", labels(graph)).replace(
                "/*DATA*/null", labels(json.dumps(data, ensure_ascii=False)).replace("</", "<\\/"))
            self._send(html.encode("utf-8"), "text/html; charset=utf-8")
        elif self.path == "/gothic.css":
            self._send((ROOT / "inspector" / "gothic.css").read_bytes(), "text/css; charset=utf-8")
        elif self.path == "/characters":
            self._send(self._localized(CHARACTERS_PAGE.read_text(encoding="utf-8")), "text/html; charset=utf-8")
        elif self.path == "/characters.json":
            self._send(json.dumps(character_data(), ensure_ascii=False).encode("utf-8"))
        elif self.path == "/experiment":
            self._send(self._localized(EXPERIMENT_PAGE.read_text(encoding="utf-8")), "text/html; charset=utf-8")
        elif self.path == "/experiment/data":
            self._send(json.dumps(experiment_data(), ensure_ascii=False).encode("utf-8"))
        elif self.path == "/experiment/scores":
            self._send(json.dumps(load_scores(), ensure_ascii=False).encode("utf-8"))
        elif self.path == "/reviews":
            self._send(json.dumps(current_reviews(), ensure_ascii=False).encode("utf-8"))
        else:
            match = AUDIO_PATH.match(self.path)
            path = voices.VOICE_DIR / match[1] / f"{match[2]}.wav" if match else None
            if path is not None and path.exists():
                self._send(path.read_bytes(), "audio/wav")
            else:
                self._send(b"{}", status=404)

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
        if self.path not in ("/reviews", "/experiment/score"):
            return self._send(b"{}", status=404)
        problem, request = self._read_json()
        if problem:
            return self._send(json.dumps({"error": problem}).encode("utf-8"), status=400)
        if self.path == "/experiment/score":
            problem, score = _clean_score(request)
            if problem:
                return self._send(json.dumps({"error": problem}).encode("utf-8"), status=400)
            with REVIEW_LOCK:
                scores = load_scores()
                scores[request["id"]] = score
                temporary = SCORES.with_suffix(".tmp")
                temporary.write_text(json.dumps(scores, ensure_ascii=False, indent=1), encoding="utf-8")
                temporary.replace(SCORES)
            return self._send(b"{}")
        target = content_index(build()[0]).get(request.get("id"))
        if target is None or request.get("verdict") not in (None, "approve", "reject") or len(str(request.get("reason", ""))) > MAX_TEXT:
            return self._send(b'{"error": "bad review"}', status=400)
        with REVIEW_LOCK:
            reviews = load_reviews()
            if request.get("verdict"):
                reviews[request["id"]] = {"verdict": request["verdict"], "reason": request.get("reason", ""),
                                          "hash": target}
            else:
                reviews.pop(request["id"], None)
            # write to a temporary file first, so a crash can never leave a partial file
            temporary = REVIEWS.with_suffix(".tmp")
            temporary.write_text(json.dumps(reviews, ensure_ascii=False, indent=1), encoding="utf-8")
            temporary.replace(REVIEWS)
        self._send(b"{}")

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    adopt_existing_reviews()
    print(f"Story inspector: http://127.0.0.1:{PORT}")
    http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()

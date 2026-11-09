"""Local story inspector: read, listen to and review every line of a story.

    python3 python/dm/inspector_server.py
    then open http://127.0.0.1:8765

Serves only on this machine, because the generated voices must stay here. Reviews
are stored in python/dm_runtime/reviews.json.
"""

import copy
import hashlib
import http.server
import importlib
import json
import pathlib
import re
import sys
import threading
import types

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))
sys.modules.setdefault("gothic", types.ModuleType("gothic"))

from dm import knowledge as k  # noqa: E402
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
    order=[("barrel","Novize neben Gorax","Monastery, after the theft"),("tilo_before","Tilo","Monastery, before the theft"),("gorax","Gorax","Monastery, on approach"),("parlan","Parlan","Monastery, on approach"),("anselm","Anselm","Monastery, on approach"),("harek","Harek","Harbour tavern, always available"),("tilo","Tilo","Harbour alleys, always available"),("tilo_ordered_home","Tilo","Until you leave, if ordered home"),("tilo_back_at_work","Tilo","At the winery, after being ordered home"),("tilo_after_turned_in","Tilo","Until you leave, if turned in"),("tilo_after_help","Tilo","Until you leave, if helped"),("parlan_reward","Parlan","After Tilo is turned in"),("anselm_bitter","Anselm","After the reward is paid"),("anselm_grateful","Anselm","After Tilo is helped")]
    g=t.all_graphs()
    data={"frame":re.sub(r"\s+"," ",t.__doc__.split("Frame:")[1]).strip(),"truth":t.HIDDEN_TRUTH,"errors":errors,"warnings":warnings,"facts":{f:dict(essential=v.get("essential",False),topic=v.get("topic",False),needs=v.get("needs",[]),knownBy=[names.get(n,n) for n in v.get("known_by",[])]) for f,v in plot["facts"].items()},
    "convs":[{"id":i,"speaker":s,"where":w,"requires":scenes.get(i,{}).get("requires",[]),"unless":scenes.get(i,{}).get("unless") or [],"within":scenes.get(i,{}).get("within"),"scene":i in scenes,"start":g[i]["start"],"nodes":g[i]["nodes"]} for i,s,w in order],
    "rules":[{"id":r["id"],"when":r["when"],"ops":[{k:v for k,v in o.items() if k in("op","instance","count","id","waypoint","requires")} for o in r["ops"]]} for r in rules]}
    lab={"tilo_named":"Tilo's name","tilo_absent":"Tilo is missing","wine_trips":"his wine trips","silver_stolen":"silver was stolen","candlesticks":"two candlesticks","reward":"reward offered","tilo_past":"his father","gambling":"dice debt","harbour_lead":"try the harbour","friend_offer":"Anselm's offer","harek_wary":"Harek is wary","silver_sold":"silver sold to Harek","tilo_nearby":"hiding near harbour","tilo_cornered":"met him at the harbour","tilo_met":"met Tilo","barrel_met":"met the barrel novice","tilo_stressed":"he looked stressed","tilo_turned_in":"Tilo turned in","tilo_helped":"Tilo helped","parlan_paid":"reward paid","anselm_secret":"secret told","tilo_threatened":"Tilo shaken down","tilo_confessed":"Tilo confessed"}
    conv={c["id"]:c for c in data["convs"]}
    titles={"tilo_back_at_work":"Tilo back at work","tilo_ordered_home":"Tilo obeys","tilo_after_help":"Tilo says goodbye","tilo_after_turned_in":"Tilo promises to follow","barrel":"The novice at the barrels","tilo_before":"Tilo before the theft","gorax":"Gorax complains","parlan":"Parlan announces","anselm":"Anselm's plea","harek":"Harek","tilo":"Tilo","parlan_reward":"Parlan pays","anselm_bitter":"Anselm turns away","anselm_grateful":"Anselm's secret"}
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
    L.append('  r_wine(["hidden wine appears"]):::effect'); E.add(f"  {f('anselm_secret')} ==> r_wine")
    L.append('  r_gone(["Tilo leaves the harbour"]):::effect'); E.add(f"  {f('tilo_turned_in')} ==> r_gone"); E.add(f"  {f('tilo_helped')} ==> r_gone")
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


class Handler(http.server.BaseHTTPRequestHandler):
    def _send(self, body, kind="application/json", status=200):
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/":
            data, graph = build()
            html = PAGE.read_text(encoding="utf-8").replace("%%GRAPH%%", graph).replace(
                "/*DATA*/null", json.dumps(data, ensure_ascii=False).replace("</", "<\\/"))
            self._send(html.encode("utf-8"), "text/html; charset=utf-8")
        elif self.path == "/gothic.css":
            self._send((ROOT / "inspector" / "gothic.css").read_bytes(), "text/css; charset=utf-8")
        elif self.path == "/characters":
            self._send(CHARACTERS_PAGE.read_bytes(), "text/html; charset=utf-8")
        elif self.path == "/characters.json":
            self._send(json.dumps(character_data(), ensure_ascii=False).encode("utf-8"))
        elif self.path == "/reviews":
            self._send(json.dumps(current_reviews(), ensure_ascii=False).encode("utf-8"))
        else:
            match = AUDIO_PATH.match(self.path)
            path = voices.VOICE_DIR / match[1] / f"{match[2]}.wav" if match else None
            if path is not None and path.exists():
                self._send(path.read_bytes(), "audio/wav")
            else:
                self._send(b"{}", status=404)

    def do_POST(self):
        if self.path != "/reviews":
            return self._send(b"{}", status=404)
        request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        target = content_index(build()[0]).get(request["id"])
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

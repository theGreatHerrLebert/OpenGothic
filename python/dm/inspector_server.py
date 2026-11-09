"""Local story inspector: read, listen to and review every line of a story.

    python3 python/dm/inspector_server.py
    then open http://127.0.0.1:8765

Serves only on this machine, because the generated voices must stay here. Reviews
are stored in python/dm_runtime/reviews.json.
"""

import copy
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
    order=[("barrel","Novize neben Gorax","Monastery, after the theft"),("tilo_before","Tilo","Monastery, before the theft"),("gorax","Gorax","Monastery, on approach"),("parlan","Parlan","Monastery, on approach"),("anselm","Anselm","Monastery, on approach"),("harek","Harek","Harbour tavern, always available"),("tilo","Tilo","Harbour alleys, always available"),("tilo_ordered_home","Tilo","Until you leave, if ordered home"),("tilo_after_turned_in","Tilo","Until you leave, if turned in"),("tilo_after_help","Tilo","Until you leave, if helped"),("parlan_reward","Parlan","After Tilo is turned in"),("anselm_bitter","Anselm","After the reward is paid"),("anselm_grateful","Anselm","After Tilo is helped")]
    g=t.all_graphs()
    data={"frame":re.sub(r"\s+"," ",t.__doc__.split("Frame:")[1]).strip(),"truth":t.HIDDEN_TRUTH,"errors":errors,"warnings":warnings,"facts":{f:dict(essential=v.get("essential",False),topic=v.get("topic",False),needs=v.get("needs",[]),knownBy=[names.get(n,n) for n in v.get("known_by",[])]) for f,v in plot["facts"].items()},
    "convs":[{"id":i,"speaker":s,"where":w,"requires":scenes.get(i,{}).get("requires",[]),"unless":scenes.get(i,{}).get("unless") or [],"within":scenes.get(i,{}).get("within"),"scene":i in scenes,"start":g[i]["start"],"nodes":g[i]["nodes"]} for i,s,w in order],
    "rules":[{"id":r["id"],"when":r["when"],"ops":[{k:v for k,v in o.items() if k in("op","instance","count","id","waypoint","requires")} for o in r["ops"]]} for r in rules]}
    lab={"tilo_named":"Tilo's name","tilo_absent":"Tilo is missing","wine_trips":"his wine trips","silver_stolen":"silver was stolen","candlesticks":"two candlesticks","reward":"reward offered","tilo_past":"his father","gambling":"dice debt","harbour_lead":"try the harbour","friend_offer":"Anselm's offer","harek_wary":"Harek is wary","silver_sold":"silver sold to Harek","tilo_nearby":"hiding near harbour","tilo_cornered":"met him at the harbour","tilo_met":"met Tilo","barrel_met":"met the barrel novice","tilo_stressed":"he looked stressed","tilo_turned_in":"Tilo turned in","tilo_helped":"Tilo helped","parlan_paid":"reward paid","anselm_secret":"secret told","tilo_threatened":"Tilo shaken down","tilo_confessed":"Tilo confessed"}
    conv={c["id"]:c for c in data["convs"]}
    titles={"tilo_ordered_home":"Tilo obeys","tilo_after_help":"Tilo says goodbye","tilo_after_turned_in":"Tilo promises to follow","barrel":"The novice at the barrels","tilo_before":"Tilo before the theft","gorax":"Gorax complains","parlan":"Parlan announces","anselm":"Anselm's plea","harek":"Harek","tilo":"Tilo","parlan_reward":"Parlan pays","anselm_bitter":"Anselm turns away","anselm_grateful":"Anselm's secret"}
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
    L+=["  classDef conv fill:#A8421B,stroke:#A8421B,color:#fff","  classDef fact fill:#E4DECD,stroke:#B9B09A,color:#23201A","  classDef ess fill:#F0C9A8,stroke:#A8421B,color:#23201A","  classDef effect fill:#2F6B3E,stroke:#2F6B3E,color:#fff"]
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


def load_reviews():
    return json.loads(REVIEWS.read_text(encoding="utf-8")) if REVIEWS.exists() else {}


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
        elif self.path == "/reviews":
            self._send(json.dumps(load_reviews(), ensure_ascii=False).encode("utf-8"))
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
        with REVIEW_LOCK:
            reviews = load_reviews()
            if request.get("verdict"):
                reviews[request["id"]] = {"verdict": request["verdict"], "reason": request.get("reason", "")}
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
    print(f"Story inspector: http://127.0.0.1:{PORT}")
    http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()

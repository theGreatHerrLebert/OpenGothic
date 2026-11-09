"""Der Fall Tilo, the first complete story. Written against docs/director-brief.md.

Frame: Tilo is a soft novice who wants to be hard. His father beat him, thought him
a nobody and stuck him in the monastery. Selling the monastery's wine in Khorinis,
he goes to the harbour bar to act tough, and is cheated at dice by Harek. Unable to
pay, he steals two silver candlesticks at night, pays Harek and means to sign on with
a ship. The blockade stops every ship, so he hides in the harbour district.
"""

GORAX = "KDF_508_GORAX"
PARLAN = "KDF_504_PARLAN"
ANSELM = "NOV_610_NOVIZE"
TILO = "NOV_606_NOVIZE"
HAREK = "VLK_4006_BOTE"

VOICES = {GORAX: "14", PARLAN: "05", ANSELM: "13", HAREK: "09", TILO: "03"}


def fact(*known_by, essential=False, needs=(), topic=False):
    return {"text": "", "known_by": list(known_by), "essential": essential,
            "needs": list(needs), "topic": topic}


PLOT = {
    "start": [],
    "facts": {
        "tilo_named": fact(topic=True),
        "tilo_absent": fact(GORAX, PARLAN, ANSELM, essential=True),
        "wine_trips": fact(GORAX, ANSELM),
        "silver_stolen": fact(PARLAN, ANSELM, TILO, HAREK, essential=True),
        "candlesticks": fact(PARLAN, TILO, HAREK, essential=True),
        "reward": fact(PARLAN),
        "tilo_past": fact(ANSELM, TILO),
        "gambling": fact(ANSELM, HAREK, TILO, essential=True),
        "harbour_lead": fact(ANSELM, HAREK, TILO, essential=True),
        "friend_offer": fact(ANSELM),
        "harek_wary": fact(topic=True),
        "silver_sold": fact(HAREK, TILO),
        "tilo_nearby": fact(HAREK, essential=True, needs=["harbour_lead"]),
        "tilo_cornered": fact(topic=True),
    },
    "items": [{"ref": "ROBE", "teaches": ["tilo_absent"], "needs": []}],
}


def node(line, sets=(), choices=(), uses=(), again=None, delivery=None):
    result = {"line": line, "choices": list(choices)}
    if sets:
        result["sets"] = list(sets)
        result["teaches"] = list(sets)
    if uses:
        result["uses"] = list(uses)
    if again:
        result["again"] = again
    if delivery:
        result["delivery"] = delivery
    return result


def go(text, target, requires=None, unless=None, uses=()):
    return _choice(text, {"goto": target}, requires, unless, uses)


def end(text="Leb wohl.", requires=None, unless=None, uses=()):
    return _choice(text, {"ends": True}, requires, unless, uses)


def _choice(text, base, requires, unless, uses):
    choice = dict(base, text=text)
    if requires:
        choice["requires"] = list(requires)
    if unless:
        choice["unless"] = unless
    if uses:
        choice["uses"] = list(uses)
    return choice


BACK = "Zurück."

GORAX_SCENE = {"voice": VOICES[GORAX], "start": "a", "nodes": {
    "a": node("Hey du! Hast du den Novizen Tilo gesehen? Der Bengel ist heute früh nicht zur Arbeit erschienen. Die Presse steht still, und der Wein keltert sich schließlich nicht von selbst!",
              ["tilo_named", "tilo_absent"], [
                  go("Ich habe am Hafen einen Kerl getroffen, der nicht dorthin passt.", "c", requires=["tilo_cornered"], uses=["tilo_cornered"]),
                  go("Wer ist dieser Tilo?", "b"),
                  end("Ich bin nicht dein Laufbursche."),
                  end("Wenn ich ihn sehe, sage ich es dir.")]),
    "b": node("Er bringt unseren Wein in die Stadt. Seit Wochen kommt er später und später zurück. Wenn er sich mit Gesindel abgibt, kann er was erleben.",
              ["wine_trips"], [go(BACK, "a"), end("Ich halte die Augen offen.")], uses=["tilo_named"]),
    "c": node("Am Hafen? Das sähe ihm ähnlich, dem Taugenichts. Geh zu Meister Parlan damit, nicht zu mir.",
              [], [go(BACK, "a"), end("Mache ich.")], uses=["tilo_named"]),
}}

PARLAN_SCENE = {"voice": VOICES[PARLAN], "start": "a", "nodes": {
    "a": node("Bleib stehen, Fremder. Es ist unfassbar, aber heute Nacht wurde aus unserer Kapelle Silber gestohlen. Zwei Leuchter, im Hause Innos'! Wer den Dieb findet und zu mir bringt, dem soll es nicht zum Schaden sein.",
              ["silver_stolen", "candlesticks", "reward"], [
                  go("Am Hafen bietet jemand silberne Leuchter an.", "h", requires=["silver_sold"], uses=["silver_sold"]),
                  go("Hast du einen Verdacht?", "b"),
                  go("Was ist euch das wert?", "c"),
                  end("Ich werde sehen, was ich tun kann.")]),
    "b": node("Ich spreche keinen Verdacht aus, wenn ich keinen Beweis habe. Aber es fehlt heute ein Novize, und das gefällt mir nicht.",
              [], [go(BACK, "a"), end("Ich werde mich umhören.")], uses=["silver_stolen"]),
    "h": node("Am Hafen? Dann hat sich der Dieb nicht weit gewagt. Finde ihn, und bring ihn zu mir. Es wird dein Schaden nicht sein.",
              [], [go(BACK, "a"), end("Ich kümmere mich darum.")], uses=["silver_stolen"]),
    "c": node("Innos belohnt Gerechtigkeit. Das Kloster zahlt zweihundert Goldstücke, wenn der Dieb vor mir steht. Vorher keine Münze.",
              [], [go(BACK, "a"), end("Das klingt gerecht.")], uses=["reward"]),
}}

ANSELM_SCENE = {"voice": VOICES[ANSELM], "start": "a", "nodes": {
    "a": node("Warte! Du warst bei Meister Parlan, nicht wahr? Es geht um Tilo. Er ist mein Freund. Was immer sie dir erzählen, er ist kein schlechter Kerl.",
              ["tilo_named"], [
                  go("Glaubst du, er hat das Silber gestohlen?", "b", requires=["silver_stolen"], uses=["silver_stolen"]),
                  go("Wo könnte er stecken?", "c"),
                  go("Warum sorgst du dich so um ihn?", "d"),
                  go("Parlan zahlt gut für den Dieb.", "e", requires=["reward"], uses=["reward"]),
                  end("Das geht mich nichts an.")]),
    "b": node("Ich will es nicht glauben. Aber er hatte Angst, seit Tagen. Er hat beim Würfeln Geld verloren, viel Geld, und das konnte er niemals bezahlen.",
              ["gambling", "silver_stolen"], [go(BACK, "a"), end("Danke.")], uses=["tilo_named"]),
    "c": node("Wenn er den Wein in die Stadt bringt, geht er danach immer in die Hafenkneipe. Da spielt er den harten Kerl. Frag dort nach ihm.",
              ["wine_trips", "harbour_lead"], [go(BACK, "a"), end("Danke.")], uses=["tilo_named"]),
    "d": node("Sein Vater hat ihn geprügelt, jahrelang, und ihm gesagt, er sei ein Nichts. Dann hat er ihn hier abgeladen. Tilo will nur einmal stark sein, verstehst du?",
              ["tilo_past"], [go(BACK, "a"), end("Ich verstehe.")], uses=["tilo_named"]),
    "e": node("Ich weiß. Bitte, bring ihn nicht einfach zurück. Hilf ihm, und ich erzähle dir etwas über das Kloster, das du sonst nie erfahren würdest.",
              ["friend_offer"], [go(BACK, "a"), end("Ich denke darüber nach.")], uses=["tilo_named"]),
}}

HAREK_GRAPH = {"voice": VOICES[HAREK], "start": "a", "nodes": {
    "a": node("Was glotzt du? Wenn du Fisch willst, geh zu Halvor.", ["harek_met"],
              again="Du schon wieder. Was denn noch?", choices=[
                  go("Ich suche wertvolle Dinge, die man kaufen kann.", "g", unless="harek_wary"),
                  go("Ich suche wertvolle Dinge, die man kaufen kann.", "g2", requires=["harek_wary"]),
                  go("Du kennst einen Novizen namens Tilo.", "b", requires=["tilo_named"], uses=["tilo_named"]),
                  go("Du hast mit einem Novizen gewürfelt, nicht wahr?", "w", requires=["gambling"], uses=["gambling"]),
                  go("Hast du das gestohlene Silber versetzt?", "c", requires=["silver_stolen"], uses=["silver_stolen"]),
                  go("Hat dir ein Novize etwas verkauft?", "c", requires=["tilo_absent"], unless="silver_stolen", uses=["tilo_absent"]),
                  end("Vergiss es.")]),
    "g": node("Wertvolles, ja? Vielleicht habe ich da etwas. Zwei silberne Leuchter, feine Arbeit, frisch ... aus gutem Hause. Frag lieber nicht, woher.",
              ["candlesticks", "silver_stolen", "silver_sold"], [go(BACK, "a"), end("Vergiss es.")]),
    "g2": node("Du hältst mich wohl für bescheuert, was? Ich merke doch, dass du wissen willst, ob Tilo mir gestohlene Sachen aus dem Kloster gebracht hat.",
               [], [go(BACK, "a"), end("Vergiss es.")], delivery="drohend"),
    "b": node("Tilo? Der Kleine aus dem Kloster schuldet mir noch dreihundert Gold vom Würfeln. Hat er dich geschickt?",
              ["harek_wary", "gambling"], [
                  go("Er ist aus dem Kloster verschwunden.", "d", requires=["tilo_absent"], uses=["tilo_absent"]),
                  go(BACK, "a"), end("Vergiss es.")], uses=["tilo_named"]),
    "w": node("Und wenn? Gewürfelt ist gewürfelt. Wenn die Würfel einen Klosterjungen nicht mögen, ist das sein Pech. Hat er sich etwa beschwert?",
              ["harek_wary"], [go("Du hast ihn betrogen.", "x"), go(BACK, "a"), end("Vergiss es.")]),
    "x": node("Pass auf, was du sagst. Hier im Hafenviertel kann schnell jemand auf den Gedanken kommen, du willst ihn bei der Miliz anschwärzen. Und das würde nicht gut für dich enden.",
              ["harek_wary"], [go(BACK, "a"), end("Vergiss es.")], delivery="drohend"),
    "c": node("Pass auf, was du sagst. Hier im Hafenviertel kann schnell jemand auf den Gedanken kommen, du willst ihn bei der Miliz anschwärzen. Und das würde nicht gut für dich enden.",
              ["harek_wary"], [
                  go("Im Kloster sind einige wertvolle Leuchter aus Silber verschwunden.", "d2", requires=["candlesticks"], uses=["candlesticks"]),
                  go("Im Kloster ist etwas Wertvolles verschwunden.", "d2", unless="candlesticks"),
                  go(BACK, "a"), end("Vergiss es.")], delivery="drohend"),
    "d": node("Na schön. Er kam letzte Nacht mit einem Sack voll Silber. Das deckt seine Schulden, mehr nicht. Er wollte auf einem Schiff anheuern und verschwinden, aber seit der Blockade läuft keines aus.",
              ["silver_sold", "silver_stolen"], [go("Wo ist er jetzt?", "e"), go(BACK, "a"), end("Danke.")], uses=["tilo_named"]),
    "d2": node("Na schön. Der kleine Tilo aus dem Kloster kam letzte Nacht mit einem Sack voll Silber. Das deckt seine Schulden, mehr nicht. Er wollte auf einem Schiff anheuern und verschwinden, aber seit der Blockade läuft keines aus.",
               ["tilo_named", "silver_sold", "silver_stolen", "gambling"], [go("Wo ist er jetzt?", "e"), go(BACK, "a"), end("Danke.")]),
    "e": node("Irgendwo hier am Hafen, schätze ich. Der Kerl ist ein Schwächling und würde niemals eine Überfahrt als Matrose überstehen. Novizen sind doch alles Söhnchen von reichen Oberstadt-Pinkeln!",
              ["tilo_nearby", "harbour_lead"], [go(BACK, "a"), end("Danke.")], uses=["tilo_named"]),
}}

TILO_GRAPH = {"voice": VOICES[TILO], "start": "a", "nodes": {
    "a": node("Was willst du? Ich bin hier Stammgast, klar? Die Leute am Hafen kennen mich. Also such dir jemand anderen zum Anglotzen.",
              ["tilo_cornered"], again="Was willst du denn noch? Lass mich in Ruhe.", choices=[
                  go("Ich weiß von den Leuchtern.", "b", requires=["candlesticks"], uses=["candlesticks"]),
                  go("Ich weiß, was du gestohlen hast.", "b", requires=["silver_stolen"], unless="candlesticks", uses=["silver_stolen"]),
                  go("Du bist Tilo aus dem Kloster.", "a2", requires=["tilo_named"], uses=["tilo_named"]),
                  go("Du siehst nicht aus wie einer von hier.", "a3"),
                  go("Dein Freund Anselm macht sich Sorgen.", "b2", requires=["friend_offer"], uses=["friend_offer"]),
                  end("Schon gut. Ich gehe wieder.")]),
    "a2": node("Kloster? Nie gehört. Ich bin Seemann. Sobald die Blockade weg ist, heuere ich an, und dann siehst du mich hier nie wieder.",
               [], [go("Du siehst nicht aus wie ein Seemann.", "b"), go(BACK, "a"), end("Wie du meinst.")]),
    "a3": node("Ach ja? Ich bin Seemann, Mann. Ich warte nur, bis die Blockade weg ist. Geh weiter, hier gibt es nichts zu sehen.",
               [], [go(BACK, "a"), end("Wie du meinst.")]),
    "b2": node("Anselm? Der ... der sollte sich nicht um mich sorgen. Sag ihm das. Sag ihm, es tut mir leid.",
               [], [go("Was hast du getan?", "b"), end("Ich sage es ihm.")]),
    "b": node("Ich ... wer hat dir das erzählt? Harek? Verdammt. Hör zu, das ist nicht so, wie es aussieht. Ich kann das erklären.",
              [], [go("Dann erklär es.", "c"), end("Spar dir das.")]),
    "c": node("Ich hab gewürfelt, hier am Hafen. Erst lief es gut, und dann waren es auf einmal dreihundert Gold. Harek hätte mich aufgeschlitzt. Also hab ich die Leuchter aus der Kapelle genommen. Ich wollte sie zurückholen, ehrlich!",
              ["tilo_confessed", "candlesticks", "gambling", "silver_stolen", "silver_sold"], [
                  go("Du kommst mit mir zu Parlan.", "d", requires=["reward"], uses=["reward"]),
                  go("Gib mir, was du noch hast, dann schweige ich.", "e"),
                  go("Verschwinde aus Khorinis. Parlan erfährt nichts von mir.", "f")]),
    "d": node("Zu Parlan? Der wird mich ... Nein. Du hast recht. Ich komme mit, bevor ich es mir anders überlege.",
              ["tilo_turned_in"], [end()]),
    "e": node("Ich hab nichts mehr! Nichts! Du bist genau wie die da unten. Und so wollte ich auch mal sein. Innos, was bin ich für ein Narr.",
              ["tilo_threatened"], [end()]),
    "f": node("Warum tust du das? Ich ... Das werde ich dir nie vergessen. Wirklich nicht.",
              ["tilo_helped"], [end()]),
}}

PARLAN_REWARD = {"voice": VOICES[PARLAN], "start": "a", "nodes": {
    "a": node("Der Novize Tilo hat alles gestanden. Er wird seine Strafe tragen. Du hast dem Kloster einen großen Dienst erwiesen, und Innos vergisst das nicht. Hier ist dein Lohn.",
              ["parlan_paid"], [end("Es war mir eine Ehre.")]),
}}

ANSELM_BITTER = {"voice": VOICES[ANSELM], "start": "a", "nodes": {
    "a": node("Zweihundert Goldstücke, ja? Dafür hast du ihn verkauft. Sprich mich nicht mehr an.",
              [], [end("Er war ein Dieb.")]),
}}

ANSELM_GRATEFUL = {"voice": VOICES[ANSELM], "start": "a", "nodes": {
    "a": node("Du hast ihn laufen lassen. Ich weiß es. Danke. Also gut, ich halte mein Wort: Neben der Weinpresse versteckt Gorax seinen besten Tropfen vor Meister Parlan. Niemand weiß davon.",
              ["anselm_secret"], [end("Das bleibt unter uns.")]),
}}

CONVERSATIONS = {GORAX: GORAX_SCENE, PARLAN: PARLAN_SCENE, ANSELM: ANSELM_SCENE, HAREK: HAREK_GRAPH, TILO: TILO_GRAPH}

HIDDEN_TRUTH = ("Tilo, cheated at dice by Harek and owing him 300 gold, stole two silver candlesticks from the "
                "chapel at night, left his robe at the wine press, paid Harek and tried to sign on with a ship. "
                "The blockade stopped him, so he hides in the harbour district.")

ROBE = {"description": "Zerknitterte Novizenrobe",
        "lines": ["Jemand hat sie an der Weinpresse zurückgelassen.", "Der Stoff riecht nach Wein und kaltem Schweiß."]}


FATE = ["tilo_turned_in", "tilo_helped"]  # once decided, the early scenes no longer make sense


def plan():
    return [
        {"op": "commit_fact", "id": "truth", "text": HIDDEN_TRUTH, "known_by": []},
        {"op": "spawn_npc", "instance": HAREK, "waypoint": "NW_CITY_HABOUR_TAVERN01_01", "display_name": "Harek"},
        {"op": "attach_dialogue_graph", "npc": HAREK, "graph": HAREK_GRAPH},
        {"op": "place_item", "instance": "ITAR_NOV_L", "waypoint": "NW_MONASTERY_WINEMAKER_01", "quest": ROBE},
        {"op": "add_scene", "id": "gorax", "npc": GORAX, "graph": GORAX_SCENE, "within": 500, "unless": FATE},
        {"op": "add_scene", "id": "parlan", "npc": PARLAN, "graph": PARLAN_SCENE, "within": 500, "requires": ["tilo_absent"], "unless": FATE},
        {"op": "add_scene", "id": "anselm", "npc": ANSELM, "graph": ANSELM_SCENE, "within": 450, "requires": ["reward"], "unless": FATE},
        {"op": "add_rule", "id": "tilo_turned_in", "when": ["tilo_turned_in"], "ops": [
            {"op": "remove_npc", "instance": TILO},
            {"op": "add_scene", "id": "parlan_reward", "npc": PARLAN, "graph": PARLAN_REWARD, "within": 600},
            {"op": "add_scene", "id": "anselm_bitter", "npc": ANSELM, "graph": ANSELM_BITTER, "within": 450, "requires": ["parlan_paid"]}]},
        {"op": "add_rule", "id": "reward_paid", "when": ["parlan_paid"], "ops": [
            {"op": "give_item", "instance": "ITMI_GOLD", "count": 200}]},
        {"op": "add_rule", "id": "tilo_helped", "when": ["tilo_helped"], "ops": [
            {"op": "remove_npc", "instance": TILO},
            {"op": "add_scene", "id": "anselm_grateful", "npc": ANSELM, "graph": ANSELM_GRATEFUL, "within": 450, "requires": ["friend_offer"]}]},
        {"op": "add_rule", "id": "secret_told", "when": ["anselm_secret"], "ops": [
            {"op": "place_item", "instance": "ITFO_WINE", "waypoint": "NW_MONASTERY_WINEMAKER_03"}]},
        {"op": "relocate_npc", "instance": TILO, "waypoint": "NW_CITY_HABOUR_POOR_AREA_PATH_08",
         "armor": "ITAR_VLK_L", "display_name": "Tilo"},
        {"op": "attach_dialogue_graph", "npc": TILO, "graph": TILO_GRAPH},
    ]


def all_graphs():
    return {"gorax": GORAX_SCENE, "parlan": PARLAN_SCENE, "anselm": ANSELM_SCENE, "harek": HAREK_GRAPH,
            "tilo": TILO_GRAPH, "parlan_reward": PARLAN_REWARD, "anselm_bitter": ANSELM_BITTER,
            "anselm_grateful": ANSELM_GRATEFUL}

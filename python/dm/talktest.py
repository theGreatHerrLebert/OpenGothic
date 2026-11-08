"""Manual check of the dialogue bridge.

    py import dm.talktest as t
    py t.start()

Walk up to the NPC that appears and talk to it.
"""

import gothic

_npc = None
_home = None
_state = "idle"


def _tick(dt):
    global _state
    try:
        d = gothic.dialog
        if _npc is not None and not d.is_open():
            x, y, z = _npc.position
            if abs(x - _home[0]) + abs(z - _home[2]) > 30:
                _npc.stop()
                _npc.set_position(*_home)
        if d.just_opened():
            _state = "greet"
        if _state == "greet" and d.say("Grüß dich. Ich hörte Märchen über Feuer, Größe und Weißheit."):
            _state = "offer"
        elif _state == "offer" and not d.busy():
            d.set_choices(["Wer bist du?", "Leb wohl."])
            _state = "choose"
        elif _state == "choose":
            choice = d.poll_selection()
            if choice == 0 and d.say("Das habe ich leider vergessen."):
                _state = "offer"
            elif choice == 1:
                d.close()
                _state = "idle"
    except RuntimeError:
        _state = "idle"


def start():
    global _npc, _home
    _npc = gothic.world.spawn("VLK_4250_Jorgen")
    _home = _npc.position
    _npc.display_name = "Aldarius"
    gothic.dialog.bind(_npc)
    if not getattr(gothic, "_dm_talktest_registered", False):
        gothic.on_tick(lambda dt: __import__("dm.talktest").talktest._tick(dt))
        gothic._dm_talktest_registered = True
    gothic.announce("Aldarius wartet auf dich.")

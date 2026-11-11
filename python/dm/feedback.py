"""Feedback from inside the game. Alt+F opens a menu in the DM panel, Alt+1 to Alt+5 pick, Alt+F closes it.

Flagging a moment records what was on screen: the story, the conversation, the node and its line, the time and the
place, and the last few events. Rating a story asks the story trial page's questions and marks the story played,
which is the signal a live game master waits for before starting the next one. Notes in words are added afterwards in
the inspector, where every entry appears with its context.

Entries are appended to python/dm_runtime/feedback.jsonl, one JSON object per line.
"""

import json
import pathlib
import time

RUNTIME_DIR = pathlib.Path(__file__).resolve().parent.parent / "dm_runtime"
PATH = RUNTIME_DIR / "feedback.jsonl"
EVENTS = RUNTIME_DIR / "events.jsonl"
RECENT_EVENTS = 10
CONFIRM_SECONDS = 2.0

TAGS = {"1": "fehler", "2": "langweilig", "3": "gut", "4": "unlogisch"}
TAG_LABELS = {"fehler": "Fehler hier", "langweilig": "Langweilig", "gut": "Gut so", "unlogisch": "Unlogisch"}

# The panel shows fixed text only, never anything from a story but its title.
MAIN = "\n".join(["Rückmeldung"] + [f"Alt+{k}  {TAG_LABELS[t]}" for k, t in TAGS.items()]
                 + ["Alt+5  Geschichte bewerten …", "Alt+F  schließen"])
ASK_WORTH = "Lohnt es sich, sie zu spielen?\nAlt+1  ja\nAlt+2  nein\nAlt+F  abbrechen"
ASK_INTEREST = "Wie spannend, 1 bis 5?\nAlt+1 … Alt+5\nAlt+F  abbrechen"
ASK_DEED = "Hat etwas gezählt, das du getan\nund nicht gesagt hast?\nAlt+1  ja\nAlt+2  nein\nAlt+F  abbrechen"
NO_STORY = "Keine Geschichte läuft."
SAVED = "Vermerkt."
RATED = "Bewertet. Danke."


class Menu:
    """The menu's states, without the game. press() returns the text to show ("" closes the panel) and an entry to
    record, or None."""

    def __init__(self):
        self.state = "closed"
        self.rating = {}

    def press(self, key, story_title=None):
        if key == "feedback":
            if self.state == "closed":
                self.state = "main"
                return MAIN, None
            self.state = "closed"
            return "", None
        if self.state == "main":
            if key in TAGS:
                self.state = "closed"
                return SAVED, {"kind": "moment", "tag": TAGS[key]}
            if key == "5":
                if not story_title:
                    self.state = "closed"
                    return NO_STORY, None
                self.state = "worth"
                self.rating = {"story": story_title}
                return f"„{story_title}“\n{ASK_WORTH}", None
        elif self.state == "worth" and key in ("1", "2"):
            self.rating["worth"] = "yes" if key == "1" else "no"
            self.state = "interest"
            return ASK_INTEREST, None
        elif self.state == "interest" and key in ("1", "2", "3", "4", "5"):
            self.rating["interest"] = int(key)
            self.state = "deed"
            return ASK_DEED, None
        elif self.state == "deed" and key in ("1", "2"):
            self.rating["deed"] = "yes" if key == "1" else "no"
            self.state = "closed"
            entry = {"kind": "rating", **self.rating, "played": True}
            self.rating = {}
            return RATED, entry
        return None, None   # a key that means nothing here changes nothing


def recent_events(path=None, count=RECENT_EVENTS):
    """The last few observed events, read from the end of the log so a long game stays cheap."""
    try:
        with (path or EVENTS).open("rb") as f:
            f.seek(0, 2)
            start = max(0, f.tell() - 32768)
            f.seek(start)
            lines = f.read().decode("utf-8", errors="replace").splitlines()
            if start > 0:
                lines = lines[1:]   # the first line read is probably cut off
    except OSError:
        return []
    events = []
    for line in lines[-count:]:
        try:
            events.append(json.loads(line))
        except ValueError:
            pass
    return events


# Log entries the story layer writes for itself, rather than a story the game master submitted.
INTERNAL = ("player", "Szene beendet: ", "Wahrgenommen: ", "Regel: ")


def current_story(story_module):
    """Title of the story submitted last, or None."""
    titles = [entry.get("reason") for entry in story_module._story.log
              if entry.get("reason") and not entry["reason"].startswith(INTERNAL)
              and any(op.get("op") != "do_nothing" for op in entry.get("ops", []))]
    return titles[-1] if titles else None


def context(gothic, story_module):
    """Everything about this moment that can be read without asking the player."""
    hour, minute = gothic.world.time
    found = {"day": gothic.world.day, "hour": hour, "minute": minute,
             "waypoint": gothic.player.waypoint, "room": gothic.player.room,
             "position": list(gothic.player.position),
             "story": current_story(story_module), "events": recent_events()}
    player = story_module._player
    partner = gothic.dialog.partner()
    if partner is not None:
        found["partner"] = partner.instance
        if player.stage != "idle" and player.graph is not None:
            found["conversation"] = next((key for key, graph in story_module._story.graphs_now().items()
                                          if graph is player.graph), player.partner)
            found["node"] = player.path[-1] if player.path else None
            found["line"] = player.line
    return found


def append(entry, path=PATH):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def load(path=PATH):
    if not path.exists():
        return []
    entries = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            entries.append(json.loads(line))
        except ValueError:
            pass
    return entries


def played(path=PATH):
    """Titles of the stories the player has rated, which counts as having played them."""
    return {e["story"] for e in load(path) if e.get("kind") == "rating" and e.get("played")}


_menu = Menu()
_close_at = None


def _tick(_dt):
    global _close_at
    import gothic
    from dm import story
    if _close_at is not None and time.monotonic() >= _close_at:
        _close_at = None
        if _menu.state == "closed":
            gothic.overlay.menu("")
    for key in gothic.take_keys():
        try:
            title = current_story(story)
        except Exception:
            title = None
        text, entry = _menu.press(key, title)
        if entry is not None:
            try:
                found = context(gothic, story)
            except RuntimeError:
                found = {"story": title}   # no world while loading; keep what the player said
            append({**found, **entry, "at": time.time()})
        if text is None:
            continue
        gothic.overlay.menu(text)
        _close_at = time.monotonic() + CONFIRM_SECONDS if text and _menu.state == "closed" else None


def start():
    """Safe to call repeatedly."""
    import gothic
    if getattr(gothic, "_dm_feedback_registered", False):
        return
    gothic.on_tick(_tick)
    gothic._dm_feedback_registered = True

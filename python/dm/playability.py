"""Can a story be played to the end in the real game? A playability audit against the game's own data.

    python3 python/dm/playability.py <story.json> [...] [--json] [--game <Gothic install>]

check_story.py proves a story is sound in itself. This asks the game: can the hero, in chapter 1 and without a guild,
get every item the story wants, start and finish every quest it checks, hear every topic it waits for, find every
person it needs at the hours it needs them, and sit at every object it waits for while no one else sits there?

It reads what quest_mine.py, map_data.py and tools/world_dump.cpp extracted, all in the gitignored dm_runtime folder:
mechanics/{items,dialogues,functions,quests}.json, mechanics/world.jsonl and map/map_data.json. When the game is
installed (--game, or dm_runtime/settings.json), the NPCs' own starting inventories come from its GOTHIC.DAT.
Nothing here is specific to one story. The report names items and people but never quotes the game's dialogue.

What the hero has is judged by a three-valued reading of the game's own conditions: chapter 1 and no guild are
certain, every other script variable is taken as something the hero could still bring about. "Blocked" means the
game's own rules rule it out; everything else is reachable as far as the data can tell.

The work is split by side: playability_game.py reads the game, playability_story.py reads a story,
playability_analysis.py audits one against the other and playability_report.py writes the result.
"""

import argparse
import json
import pathlib

from playability_analysis import Audit, _dedupe  # noqa: F401
from playability_game import (  # noqa: F401
    ACTIVITY_OBJECT, ADDCHOICE, ASLEEP, CHAPTER, CREATE, FALSE, FIND, GIVE, HASITEMS, HERE, HERO_GUILD, INSERT_ITEM,
    KNOWN_OBJECTS, LOG, MAP_DATA, MAYBE, MECHANICS, MOBSI, QUEST_STATE, ROUTINE_SWAP, RUNTIME, SET_QUEST,
    STATE_ACTIVITY, TA, TALENT, TRUE, WORLD, Expr, Game, _arg_name, _int, clock, hour_window, load_game, minutes,
    read_inventories, spans, t_and, t_not, t_or, tokenize, truth)
from playability_report import LIMITS, markdown, summary  # noqa: F401
from playability_story import (  # noqa: F401
    Story, _checks_with_polarity, _choices, _flat_checks, _list, _nodes, _unique, describe)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("stories", nargs="+")
    parser.add_argument("--json", action="store_true", help="print a JSON summary instead of Markdown")
    parser.add_argument("--game", help="Gothic install, for the NPCs' starting inventories")
    parser.add_argument("--mechanics", default=str(MECHANICS))
    parser.add_argument("--map", default=str(MAP_DATA))
    args = parser.parse_args(argv)
    game = load_game(args.mechanics, args.map, args.game)
    stories = [Story(json.loads(pathlib.Path(p).read_text(encoding="utf-8")), pathlib.Path(p).stem) for p in args.stories]
    reports = [Audit(s, game, [o for o in stories if o is not s]).run() for s in stories]
    if args.json:
        print(json.dumps([summary(r) for r in reports], ensure_ascii=False, indent=1))
        return
    print("# Playability audit\n")
    print("Chapter 1, hero without a guild. " + ("NPC inventories read from GOTHIC.DAT." if game.inventories is not None
                                                else "GOTHIC.DAT not read: NPC inventories unknown.") + "\n")
    for r in reports:
        print(f"- {r['title']} ({r['story']}): **{r['verdict']}**")
    print()
    for r in reports:
        print(markdown(r))
    print(LIMITS)


if __name__ == "__main__":
    main()

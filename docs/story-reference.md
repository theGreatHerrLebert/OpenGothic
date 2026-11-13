# Story reference

How a story is built: the file, its parts and what each does. `docs/director-brief.md` says what makes a story good;
`docs/story-ops.md` lists every operation with an example (generated from `python/dm/op_reference.py`). Live
conditions are in `python/dm/checks.py`, deeds in `python/dm/perceptions.py`, conversations in `python/dm/graph.py`.

## The file and its checks

A story file holds `title`, `significance`, `premise`, `hidden_truth`, `plot`, `conversations`, `plan`, `closures`,
and may hold `requires`, `anchor`, `omens` and `new_characters`.

- `significance` has `theme`, `from_play`, `stakes`, `choice` and `changes`; the checker refuses a missing or empty one.
- Top-level `requires` is a list of checks tested once when the story starts in a save:
  `[{"type": "chapter", "from": 2}, {"type": "guild", "guild": "GIL_SLD"}]`. A story that names a mercenary's arrest,
  a dragon or a guild robe requires the chapter or guild that makes it true; one built on a snapshot requires what the
  snapshot showed.
- `omens`: up to three cryptic lines for the DM panel, at most 55 characters, naming no one (`status.check_omens`).

Check every story before submitting:

    python3 python/dm/check_story.py <story.json> python/dm_runtime/experiment/world_names.json
    python3 python/dm/discoverability.py <story.json>            what the player would have to guess
    python3 python/dm/discoverability.py <story.json> --dossier  the story as the player meets it, for a naive player
    python3 python/dm/playability.py <story.json>                every ending against the real game, and softlocks
    python3 python/dm/split_lines.py ...                         long lines broken into one sentence per node
                                                                  (nodes with variants or an again line stay whole)

`discoverability.py` wants a pointer to every topic, conversation and deed elsewhere in the story, and a hint for
anything that works only at an hour or while someone sleeps or smokes. The checker reports flags never set, unreachable nodes, stage directions in spoken text, missing deeds and closures,
endings that do not end the story, plain game items where the story's own belong, items worth more than the gold
around them, twin choices, and refusals that lock the story.

## Deeds and what the story notices

A rule with `on` fires when the game sees the player do something: `took_item`, `hit`, `knocked_down`, `killed`,
`cast_spell`, `entered_room`, `read_item`, `drew_weapon`, `used_object`. Narrow it with `target` (may be `PLAYER`, for
what is done to the hero), `item`, `spell`, `creature`, and `seen_by` (that person saw it) or `unseen` (nobody did).

    {"op": "add_rule", "id": "found_letter", "when": [], "on": {"event": "read_item", "item": "ITWR_..."},
     "ops": [{"op": "set_flag", "name": "letter_read", "value": true}]}

Patterns: evidence on a waypoint, a rule on `took_item` teaching the fact, taken `seen_by` its owner a different branch
from `unseen`; a letter (an `ITWR_` item, opens on use, raises `read_item`) saying what nobody will; a scene with an
`hour` check so the player has to come back; knocking the culprit down so he talks in a scene that requires that flag;
a sleeping guard (`npc_state`) letting the player past. What the hero does himself is attributed (`knocked_down` with a
`target`, or `target: PLAYER` for him being knocked down); a fight between two others is not: there only who is
unconscious (`npc_state`) and who is near tells.

## Live conditions

Flags record what the story remembers; a `checks` list on a scene, rule or choice tests what is true now: `has_item`,
`wears`, `guild`, `npc_state` (asleep, burning, frozen, fleeing, unconscious, smoking at the water pipes, drinking at a
barrel...), `npc_dead`, `npc_has` (someone carries an item), `near` (the hero within so many cm of someone, default
1500), `obsessed`, `hour` (wraps past midnight), `quest` (the game's own quest state, `{"type": "quest", "quest":
"MIS_LOBART_RUEBEN", "state": "success"}`), `heard` (the hero has heard one of the game's own topics), `chapter`,
`level` and `day` (ranges, both ends included, either optional; the first day is 0), `story_age` (days since the story
began), `not`, `any`.

A line that judges the hero by what others see needs a check: recognised by clothing, the first scene checks `wears`;
addressed by rank, it checks `guild`. Excluding guilds with `not_guilds` is not enough.

## Things and people

- **Where things lie.** Outdoors, in a public place, or where the story has made it the hero's to take. A house is its
  owner's home; taking from inside reads as theft. Use a waypoint outside, or `"position"` beside the door.
- **Items of the story's own.** `define_item` makes an item on an unused carrier: own name, inventory rows, `value`
  (without one it keeps its base's: an ore nugget is worth 200), extra `damage`, and a `look`: a tint of the base model,
  or a model of its own (`{"model": "x.obj", "texture": "x.png"}` from `dm_runtime/assets/models`, y up, 1 unit = 1 cm,
  `"scale": 100` for metres). From then on the story names it by its id everywhere, and it never counts as the item it
  was made like.
- **Pockets.** `npc_item` puts an item into someone's inventory for real. In conversation, what the hero hands over
  (`takes`) goes into the partner's pocket, and what the partner `gives` comes out of his pocket when he carries it.
- **Moving people.** `place_item`, `send_npc`, `relocate_npc`, `spawn_npc` (an existing character), `rename_npc`. Only
  NPCs on the safe list from `get_story_state` may be removed. The inspector's map shows who stands where at each hour.
- **Rewards.** `give_item`, and `give_xp` through the game's own message and sound: chapter one pays 50 for an errand,
  100 for a task with some risk, 150 to 200 for several steps or a fight, never more than 300. Give it in the rule
  that resolves the story.
- **Fights.** `attack` starts the game's own brawl, at the hero or between two people (`target`); it waits until no
  conversation runs, ends in a knock-down, and the winner robs a beaten hero as the game does. Give its rule a `near`
  check.

## Conversations

A graph has nodes with a `line` and `choices`; a node with `returns` goes back to an earlier menu after its line.
One or two sentences per node; a longer speech is a chain of nodes. Choices carry `requires` (flags, any one is
enough), `unless`, `checks`, `takes`/`gives` (`{"item": ..., "count": ...}`; a choice with `takes` appears only while the hero has the item),
`repeat` (asked again), and are otherwise asked once per story. A checked choice never counts as the way out of a node;
every node needs an unconditional one. Nodes and choices declare the facts they `uses` and `teaches`; the hero may only
say what the player knows. A first meeting needs an `again` line, and `variants` replace a line once a flag is set
(the first that holds); a variant's `unless` keeps it away while the flags that would make it false are set, which a
line saying what the hero did not do always needs (the checker warns).
Conversations can only be left from the main menu, though a story may end one deliberately; offer "Zurück" only where
more can be asked.

- **Gambles.** `"chance": {"percent": 40, "else": "lost"}` decides when the choice is picked; with `"dice": {}` the
  throw is played out (rattle, a pause, both throws on screen), and `{"dice": {"hero": 6}}` is a loaded throw that
  always wins. Combine with `takes` and `repeat`.
- **False facts.** A sheet's `beliefs` lists what someone believes or claims that is not so. Commit it as
  `{"text": ..., "false": true, "contradicts": "<true fact>", "believed_by": [...], "claimed_by": [...]}`: believers say
  it honestly, claimers know better, nobody else says it, it is never essential, and the truth must be learnable.
- **Topics beside an NPC's own.** `add_topic` puts a topic into the menu of an NPC with a scripted role; its ending
  returns to his menu. Let it follow the game's own conversation with `{"type": "heard", "info": "DIA_..."}`,
  and hide it once it has done its work with a flag its graph sets. Prefer it to a one-off scene for people with a role.
  `attach_dialogue_graph` replaces all of an NPC's conversations, so use it only on people without a scripted role.
- **Scenes.** `add_scene`: the NPC comes to the hero once he is in sight.
- **Refusals.** `refuse_talk` makes someone refuse every conversation, trade included, until `unless` is set, `days`
  have passed (then he grumbles the `after` line once), or the story ends.
- **From off-screen.** `narrate` plays a line with a subtitle outside any conversation, queued until nobody talks and
  voiced with the rest of the story (`voice`, default the narrator); use it rarely, best from a rule on a deed.

## Effects and creatures

- **A trip.** `{"op": "trip", "profile": "kriegsgesang"}` (also `nordmar`, `wasserpfeife`, `mindcap`): a few minutes
  of music, a breathing picture and the hero's own thoughts (`"thoughts": [[0.3, "..."], ...]`, intensity 0 to 1, at
  most eight). While it is strong the hero cannot start a conversation, so put talk that matters before or after.
  Fire it from a deed or choice, never by surprise, one at a time. A player may switch the picture off; music and
  thoughts remain.
- **A creature of the story's own.** `spawn_creature` remixes a nameless creature (name, look, scale, hp, strength,
  level, loot). Refer to it by id in `npc_dead` and `killed`; give endings for killing it, fleeing and never coming.

## Endings

Every rule that ends the story the player's way (its journal topic closed with status 2 or 3) ends with
`{"op": "end_story", "outcome": "..."}`; the story's number is filled in when it is played. Ending retires the story's
rules, scenes, topics and refusals; attached conversations stay, so words afterwards belong in their `variants`.
Top-level `closures` end a story that is never finished: `[{"id": "too_late", "outcome": "timeout", "checks":
[{"type": "story_age", "days": 5}], "ops": [...]}]`, and one for each death that matters. If a cast member dies and no
closure speaks of it, the game master ends the story quietly.

## Names that mislead

Some of the game's creatures carry names that sound like people or deeds. They are animals: they eat fields and
people, they never steal, set fires, talk or bargain.

- **Feldräuber**: giant insects that eat the fields bare (not robbers). **Pestkäfer**, **Blutfliege**,
  **Minecrawler**: insects too.
- **Scavenger**: a large running bird. **Snapper**, **Razor**, **Waran**, **Feuerwaran**: lizards.
- **Lurker**: a swamp reptile. **Schattenläufer**: a great horned beast of the night. **Warg**: a wolf-like beast.
- **Gobbo** and **Ork** are creatures with a culture of their own; **Banditen** and **Wegelagerer** are people.

When a hut burns or a purse is stolen, it was people.

## Voices and limits

Voices are baked after a plan is accepted (`bake_voices.py`); unvoiced lines appear as silent subtitles. Stories cannot
invent new people or new kinds of creature: `spawn_npc` brings an existing character, `rename_npc` renames, and
`spawn_creature` remixes one the game has. No standalone operation takes an item out of someone's pocket (only a
conversation's `gives`), and memory across stories is not yet an operation.

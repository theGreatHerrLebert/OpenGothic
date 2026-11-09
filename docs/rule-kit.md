# The rule kit

What Gothic 2's quests are built from, extracted from the install's compiled scripts and world files, so that new
stories can combine verified blocks and add new ones. First pass: counts are exact, the grouping is a person's reading.

Regenerate with `python/dm/quest_mine.py`, `python/dm/tools/world_dump.cpp` and `python/dm/quest_graph.py`. Output goes
to the gitignored `python/dm_runtime/mechanics`, because it quotes the game's text. This file names mechanisms only.

Scope of the data: 4,139 dialogues, 213 quest log topics (159 with three or more dialogues), 18,041 spoken lines,
77 spells, 284 item-use scripts, 108 NPC states, 5,130 placed items, 879 chest stacks, 249 locks.

## Two kinds of mechanism

- **Authored branches.** Every route is a written dialogue. The city gate offers a bribe, a pass, farmer's clothes plus
  a cover story, and herbs for the alchemist, all ending in one flag.
- **World rule plus a hint.** A general system already allows it, and one line points at it. The sleep spell puts any
  human to sleep unless they are swimming, down, immortal, a mage, a paladin or a dementor. Lares mentions it once, and
  the armour sits in an unlocked chest guarded by an ordinary militia man. No script connects those three things.

The second kind costs almost nothing to write, since the solution already exists. It is the main thing to remix.

## The blocks

| Block | Evidence | Story layer today |
|---|---|---|
| Earlier conversation unlocks a line | `Npc_KnowsInfo` in 1,157 conditions | Yes (`requires`) |
| Guild changes what is offered | 412 conditions | Yes (`guild` check) |
| Item carried opens a line | 250 conditions, 132 distinct items | Yes (`has_item`) |
| Worn clothes change treatment | 2 conditions; also `C_PlayerHasFakeGuild`, `C_PlayerIsFakeBandit` | Yes (`wears`); NPC reactions no |
| NPC death changes the world | 219 conditions | Yes (`npc_dead`) |
| Pickpocketing | 227 dialogues (`C_Beklauen`) | No |
| Being in a place | 174 conditions | Scene range only |
| Talent gates | 49 conditions | No |
| Crime and forgiveness | 24 conditions; `B_AddPetzCrime`, `B_GrantAbsolution` | No |
| Time and day | 18 conditions | Yes (`hour`) |
| Several routes, one outcome | 47 outcomes found with 3 to 14 routes | Yes, by hand |
| A route closes the others | 17 flags, mostly "already let in" guards | Yes (`unless`) |
| Locks | 185 lockpick only, 61 key only; 55 distinct keys | No |
| Chests and placed items | Contents and positions per world | Placement only |
| Items with scripted use | 284 scripts | No |
| NPC reactions to the player | `B_Assess*`: damage, theft, drawn weapon, entering a room, murder, sneaking | Partly (`on`: took_item, hit, knocked_down, killed, cast_spell, entered_room) |
| Status states | `ZS_MagicBurn`, `MagicSleep`, `MagicFreeze`, `MagicShrink`, `MagicFlee`, `Whirlwind`, `Unconscious` | Yes (`npc_state`) |
| Obsession | `B_SCIsObsessed`, `B_ClearSCObsession`, `Use_HealObsession`, `C_IsShrineObsessed` | Yes (`obsessed`, hero only) |
| Who belongs where | `C_NpcBelongsToCity`, `Farm`, `Monastery`; `C_IsTakenItemMyPossession` | No |

Checks are defined in `python/dm/checks.py` and work on scenes, rules and dialogue choices. They are unit-tested against a fake game and have not yet been exercised in a running game. The knowledge checker ignores them, as it does guild gates.

## Known limits

- The hint search matches item names in spoken lines. It is noisy, and needs a person or a model to read it.
- Conditions tested only inside an `information` body are stored as guards on effects, and are not counted above.
- The world dump covers authored placement, not what scripts insert at runtime, though `STARTUP_*` functions list those.
- Reading a mechanism from names, as in the fake-guild checks, still needs its function body read before use.

## Building on it

The kit gives stories three new kinds of thing to depend on: **states** ("this NPC is burning, asleep, obsessed"),
**perceptions** ("the player just stole, drew a weapon, cast at someone"), and **possession** ("carries, wears, has
opened"). Our own ideas are rules over those, for example: someone possessed who catches fire does something new.
Each addition needs a typed condition, a submission check, and a path through the checker, as on the verb ladder.

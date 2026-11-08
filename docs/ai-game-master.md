# AI Game Master for OpenGothic

Status: proposal. Branch: `python-repl`.

## Goal

An AI game master that proactively creates stories inside a running Gothic 2,
based on how the player chooses to live, and that often chooses to do nothing.

The first target is not an AI-directed Khorinis. It is one thread at the
monastery that makes the player want to investigate without being told to.

## Principles

1. **Daedalus stays authoritative.** The original scripts are not translated.
   AI content runs beside them.
2. **New content, not new rules.** The AI cannot change the simulation's
   mechanics.
3. **Hidden facts are committed when an event is created.** The AI can improvise
   how a story unfolds, but it cannot rewrite what already happened.
4. **World constraints bind the AI.** Rank, wealth, and who could plausibly know
   what all limit what NPCs may say and do.
5. **The AI uses the simplest mechanism that works:** structured operations,
   then generated scripts, then engine extensions. V1 has only the first.
6. **The harness is deterministic.** A probabilistic director sits on top of a
   testable, replayable execution layer.

## Architecture

```
OpenGothic + original Daedalus      authoritative simulation
        |
Game harness (C++ / Python)         events, stable handles, story operations
        |
Story log + world model             hidden facts, NPC knowledge, threads
        |
Validator                           deterministic; can reject any plan
        |
Director (LLM)                      advance a thread, start one, or do nothing
```

### Director and Implementer

The Director decides what should happen. The Implementer turns that decision
into story operations and dialogue graphs. They are separate roles so that
dramatic intent does not excuse a shortcut in implementation. The main safety
boundary is still the deterministic Validator, not the separation of models.

### Observation

The Observer provides structured events: player location changes, conversations,
items taken, trespassing, NPC deaths, day changes. It must distinguish what
the world knows from what each NPC knows.

Today only `on_tick` exists. Events can begin as tick-based diffs in Python and
move to engine hooks where polling is too costly or misses things.

### Story operations (V1)

| Operation | Purpose |
| --- | --- |
| `commit_fact` | Record a hidden fact about the story |
| `remove_npc_temporarily` | Take a safe-listed NPC out of the world |
| `place_item` | Put a story item at a waypoint |
| `attach_dialogue_graph` | Give an NPC a pre-baked conversation |
| `set_flag` | Set story state owned by the harness |
| `do_nothing` | An explicit, logged decision to wait |

Each operation is typed, validated, applied at a safe point in the game loop,
and appended to the story log. If any part of a plan fails, none of it applies.

### Validation

Checks, in the order they should be built:

1. Schema and reference checks: NPCs, items and waypoints exist.
2. **Vanilla dependency map:** which NPCs, items and locations the original
   scripts rely on, derived offline from the compiled scripts. Operations
   touching a required entity are rejected. The monastery safe list comes from
   this.
3. Reachability: the player can get to anything a thread depends on.
4. Knowledge: an NPC's dialogue uses only facts that NPC could know.
5. Completion: a thread can end, or can safely be left unresolved.

### Persistence

Python state is not in savegames today. Store the story log beside the save,
keyed to it, and rebuild story state by replaying the log on load. Loading an
older save therefore also rewinds the story.

Open question: how to detect a story log whose save has been deleted or
overwritten, and what happens to an NPC removed by a log that no longer applies.

### Dialogue

Conversations are pre-baked as graphs and committed before the player arrives,
which avoids visible LLM latency. They display in the native dialogue UI.

## Story logic: two graphs

Playtesting showed that a story must be logically consistent before any line is
written. `python/dm/knowledge.py` enforces this with two graphs:

- **Knowledge graph (acyclic).** Facts, plus "needs" edges between them. A cycle
  means a mystery that cannot be solved, so it is rejected.
- **Conversation graph (cycles allowed).** Lines and choices declare the facts
  they use and teach. Every reachable combination of node and player knowledge
  is explored, so problems on any path are found.

The checker rejects a line that refers to something not yet established on that
path (including who a pronoun means), a hero line about something the player has
not learned, an NPC stating what they could not know, a fact learned before what
it depends on, and an essential fact with no source. Each essential fact should
have at least two independent sources, so one missed NPC cannot end a story.

The writing order follows from this: the Director produces the knowledge graph,
the checker proves it solvable, conversations are written against it, a German
editing pass reviews each line in context and for natural Gothic-flavoured
speech, and audio is generated last.

## Character sheets

The knowledge graph decides what a character can say. A character sheet decides
how they would say it, and gives the Director motives to work with. Each sheet
records role, manner of speech, and attitudes toward factions, important people,
those immediately around them, politics and game state, plus how those attitudes
change with story state:

```json
{"npc": "HAREK", "voice": "09", "role": "Seemann und Hehler im Hafenviertel",
 "speech": "grob, misstrauisch, kurze Sätze",
 "attitudes": {"factions": {"Kloster": "Söhnchen von Oberstadt-Pinkeln"},
               "people": {"Tilo": "Schwächling, schuldet ihm Geld"},
               "politics": "Die Blockade trifft die Kleinen, nie die Reichen."},
 "reacts_to": {"harek_wary": "Hält den Helden für einen Spitzel."}}
```

Sheets feed the Director, the dialogue writer and the editing pass, which rejects
lines the character would not say and generic filler that could belong to anyone.

Important facts should be reachable by different approaches, not only from
different people: asking someone who knows, tricking someone who would not tell,
or confronting the culprit. An approach can also close off another; showing your
hand ends a later attempt to deceive that person.

## Known constraints

- **Voice.** Gothic is fully voiced and generated lines are silent subtitles.
  Options are TTS, or fiction and pacing that make silence acceptable. Decide
  this before tuning dialogue, since it shapes how much NPCs should say.
- **Stable handles.** `PyNpc.id` is an array index and goes stale when the world
  reindexes after a spawn. It once caused an Orc Scout to be pinned in place of
  the intended NPC. The harness needs identity that survives reindexing.
- **Routines.** Stripping an NPC's routine or state removes `PERC_ASSESSTALK`
  and makes them untalkable. Freezing should only clear the AI queue and stop
  walking.
- **Lost work.** The June 2026 agent NPC code (`python/agent.py`, `world.spawn`,
  the `gothic.dialog` bridge, `DialogMenu` agent mode) was never committed and
  no copy has been found. It has to be rebuilt.
- **No test suite.** Validation is manual today. The filesystem bridge
  (`OPENGOTHIC_PY_BRIDGE=1`, `scripts/pyeval`) is the likely base for scripted
  in-game checks.

## First experiment: the missing novice

1. The Director picks a minor novice from the safe list and commits the hidden
   facts: what happened, who is responsible, and who noticed what.
2. The novice disappears at night, with no quest entry or notification.
3. One other NPC gains a pre-baked conversation containing a clue.
4. One clue item appears in the world.
5. The whole thread survives save and reload.

**Success measure:** the player goes looking for the novice without being
instructed to. Quest count is not a measure.

The Director's sense of when to intervene is out of scope here. A human can act
as Director at first, working from the logs, to learn what good decisions look
like.

## Build order

1. Confirm the merged `python-repl` build runs against real game data, including
   NPC turning near walls.
2. Rebuild `spawn` and the dialogue bridge on stable handles.
3. Add the event stream.
4. Add story operations, the log, replay, and save integration.
5. Build the dependency map and the Validator, including the two-graph checks.
6. Run the experiment with a human Director.
7. Add the LLM Director.

## Later

- A 20-in-game-day monastery run with about ten NPCs and an ordinary profession
  such as scribe.
- Generated Python against a constrained API, when structured operations cannot
  express something.
- Automated simulation using the replayable log.
- Judging whether a quiet stretch is enjoyed routine or a story failing to
  appear. This is the hardest open problem.

# Plan: an automatic game master with no human in the loop

Status: revised after an independent review. Nothing new here is built yet.

## Goal

A system that produces stories like Der Fall Tilo for a running Gothic 2 game and runs them
unattended. A player must never have to review the stories they will play, because that spoils
them. Stories nobody will play can be read freely, and those are how the system is judged.

## The main uncertainty

Can a Director write a story worth playing at all? Nothing has tested that. So we measure it
first, cheaply, and build heavy machinery only for what the results show is needed.

## Default architecture

Generate and validate stories **between play sessions**. Each story carries explicit
preconditions. In the game, simple deterministic code picks a story when its conditions hold.
No model runs during play. This removes most timing, pause and stale-content problems. Writing
stories live is a later option, along with building content lazily.

## What exists today

Working in the game along the paths played so far: event observer, typed story operations,
per-save story log, one-off scenes with sight checks, consequence rules, quest items, journal,
dialogue graphs with conditions, character sheets for five people, pre-generated voices, an MCP
server, and a local inspector whose approvals are bound to exact text and audio.

Known to be weaker than it sounds:
- The logic checker models conversations only. It ignores scene conditions, rules and guild gates,
  covers 7 of Der Fall Tilo's 14 conversations, and trusts each line's declared facts.
- Der Fall Tilo fails the checker as written, because five flags are undeclared.
- Rule contents are barely validated when submitted, so bad data surfaces during play.
- Plans are all-or-nothing only for operations that have an undo.
- The dependency map guards removal and relocation only, and lists just two safe NPCs.
- The Director cannot see the hero's guild, chapter or level.

## Phases

Each phase has a test that can fail.

### 0. Honest foundation

Declare the missing flags and check all conversations, in the automated tests. Validate the contents
of rules and scenes when submitted. Enforce the NPC allow-list on every operation. Give the
Director the hero's guild, chapter, level and quest state, and treat dead NPCs as absent.

*Done when* Der Fall Tilo passes the checker in the test suite, and a story with a bad waypoint inside a
rule is rejected at submission.

### 1. Cast and world sheet

Write character sheets for the people a story can use, starting with the monastery and the harbour, with
a section on how they see the hero, covering only the cases that can actually occur. For a prefilled story
those are decided in advance; a live Director would fill them in from the game state. Count who can actually be used. Add a hand-made fact sheet
of factions, places, chapter state and named people, in place of a full lore system. Sheets for minor
characters may be drafted by a model from the game's own dialogue and corrected by a person.

*Done when* about 15 usable people have sheets, and the count shows whether enough stories are possible.

### 2. The throwaway experiment

Fix the scoring and the kill criterion **before** generating anything. Record 3 to 5 snapshots of real
play. With only the Director brief and these sheets, generate about 20 stories offline, without the game.
A person reads and scores each for defects and interest, tagging each defect with the rule it breaks.

*Kill or pivot criterion:* at least 5 of 20 are worth playing after automatic checking. Otherwise change the
approach before building anything further.

This also yields the labelled data for phase 4, and real figures for cost and checker pass rate.

### 3. One blind vertical slice

The best-performing setup writes a story for one location and one to three people, using scenes, ideally a
small vignette rather than a mystery. The player plays it unseen. Voices follow the current private setup.

*Done when* it runs unaided from start to end. *Success* is that the player follows it up without being
told to. This is a sample of one, played by the system's author, so it is a smoke test.

### 4. Only the checks that earned their place

Add the two or three critics that phase 2's defects call for, each measured on held-out stories with
confidence intervals. Repair single lines with a retry limit, and track rejection rate, because too many
critics reject everything or push the writing towards bland.

Add a check that a line's declared facts match its text, since the logic checker depends on those.

*Done when* agreed thresholds are met on held-out data.

### 5. A checker that models the game

Compile plan, rules, scenes and graphs into one state model and check that, including guild gates and
item pickups. Treat a single source for an essential fact as an error, and record each source's approach.

*Done when* it catches seeded faults that today's checker misses.

### 6. Stories that can fail gracefully

Fail closed before a story starts, and fail safe once it has. Every story ships with a closure: a validated
quiet ending for a dead cast member, a chapter change or a timeout. Add preconditions for each
story, and operations for retiring a thread. Rules blocked by a passing condition, such as being in another
world, wait instead of dying. Add a spoiler-free health report, so a quiet world and a broken one
can be told apart.

*Done when* a path-walking test kills each cast member at each stage and every story still closes.

### 7. Unattended runner

Build generation as a real program with budgets, retries and a story library, running with only the
MCP tools. Plans get ids and are bound to the state they were written for. Define a safe point, including
combat, cutscenes and loading.

*Done when* it fills a library unattended, and a duplicate or stale plan is refused.

### Later, if justified

- **Additive dialogue:** story topics inside the normal `C_INFO` menu, so important NPCs can be used.
- **Fuller lore ledger** based on Evident Light. A found quote proves only that the passage exists.
- **Lazy building**, cached by what each line depends on.
- **Designed voices**, required for anything distributed. Cloned voices stay a private experiment.
- A `that was wrong` key that records context for later analysis.

## Immediate work on Der Fall Tilo

Keep playing it as the reference: turning Tilo in, harbour first, the mage path, and the wine location.
Replace most repeat playthroughs with a path-walking test built on the existing fakes.

## Known risks

- Taste. Passing checks shows a story is not broken, not that it is good.
- One person's taste, and one story, shape all of this.
- Too few usable NPCs, or too few safe story shapes, may limit variety.
- Cost of many model calls.
- Vanilla logic the dependency map cannot see.

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
No model runs during play. This removes most timing, pause and stale-content problems. This is the
first target and stays as the fallback. The intended end state is writing stories in the background
during play; see "Live authoring and the DM overlay".

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

**Knowledge base.** The fact sheet grows into a small graph of people, places, factions, items and quests.
Build it from the game's own data first, since scripts and dialogue are exact and match this install. Add fan
wikis only for what scripts cannot tell, keeping each fact's source and marking wiki facts as secondary, because
wikis describe versions, mods and opinions and may carry licence terms that matter if anything is shared.
Stories are generated offline, so the Director can look things up there; nothing is fetched during play.

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

## Live authoring and the DM overlay

The goal is for the Director to write in the background while the player plays. A story need not appear
instantly: it starts once it is ready and the moment suits. The pre-generated library stays as the fallback,
so a slow or failed generation never leaves the world empty.

Voices take about 7 to 8 seconds per line here, so a typical 40-line story needs roughly 5 minutes plus
writing and checks.

Requirements:

- **Measure first.** The game and the voice model share one GPU, and they have never run together. Measure the
  frame rate with and without generation, and generation speed with and without the game. Stutter would rule out
  generating voices during play.
- **Stale stories.** The player keeps playing while a story is written, so a cast member may die or a chapter may
  end. Bind each plan to the state it was written for (phase 7) and check again just before it starts.
- **The same checks as offline.** Live stories get no weaker validation.

**Overlay.** A small corner panel with a toggle key, for example `DM · schreibt … → prüft 3/5 → Stimmen 23/41 →
bereit`. It doubles as phase 6's spoiler-free health report.

- It shows the process and the quest's title, at the player's request: no names, places or plot, and not which check failed.
- Voices and checks show real counts. Writing has no known length, so it gets a moving indicator, not a
  percentage.
- A small Tempest widget, fed from Python over the existing bridge.

## Open question: pacing and balance over a long game

Not decided yet. Gothic's balance rests on a finite world, with a fixed amount of XP, gold and enemies, so
every added quest pushes the hero ahead of the curve, and an endless supply of stories adds up without limit.
Stories cannot grant XP today, as there is no operation for it. They pay out through `give_item`, with amounts
chosen by the author, up to 120 gold in one experiment story.

Starting ideas:

- **A budget per chapter, enforced by code.** A story declares a reward tier such as small or medium. The
  deterministic picker turns that into real XP and gold from what is left of the chapter's budget. A model never
  sets the numbers. When the budget is spent, stories still run but stop paying.
- **Rewards that leave the curve alone.** Information, changed relationships, better prices, an opened door. XP
  stays rare and marks the larger stories.
- **Limit stories against time played.** The picker caps how many run per chapter or in-game day, which sets the
  pacing and keeps the world from filling up with people who have a problem for you.

Settle the reward schema no later than the story library in phase 7, so stories declare a tier rather than
hard-coded amounts. Retrofitting that across a filled library is the expensive path.

## Open idea: a DM character setting

A player-chosen setting from fully Gothic-native to total chaos. Stories are written between sessions, so it can
be a parameter of the Director brief and a tag on each story in the library. The picker offers only stories at or
below the chosen level, and nothing extra runs during play.

Each level has to change specific rules, since "be more chaotic" alone produces noise. A first draft:

| Level | Tone | Canon | Stakes and rewards |
|---|---|---|---|
| Native | Gothic's dry, grounded voice; could pass for a vanilla side quest | Nothing contradicts the game; only established people and places | Small, inside the chapter budget |
| Folk tale | Odd and funny, but the people still believe it | Canon holds, with invented rumours, feuds and local oddities | Same budget |
| Wild | Absurd premises played straight | New characters and events may bend the world; quest-critical NPCs and the main plot stay safe | Larger, stranger rewards |
| Chaos | Anything goes | Lore yields; only technical limits still apply | Budget off; the player accepts a broken curve |

- Logic and safety checks apply at every level, including whether a story can finish and whether it strands a
  quest-critical NPC. Only the tone and lore critics relax as the setting rises.
- Silly tone and broken lore are separate things, and a story can be absurd yet fully canon. Start with one
  slider and split it into two only if one proves wrong.
- Calibrate with experiment 1: after scoring, tag each story with the level it landed on and see which levels
  were rated worth playing. The stories rated best at each level become its examples.

## Open idea: a ladder of story verbs

Stories can only talk, set flags, move people and hand out items today, and experiment 1 shows that already
carries a lot. New verbs come one rung at a time, cheapest first, because each makes a story harder to keep from
breaking. A rung is finished when it has typed operations, submission checks and a path-walking test.

1. **Inventory (built, not yet tried in the running game).** Taking an item from the hero, real handovers on a dialogue line (`takes`, `gives`), and letters on
   the game's own document screen (`doc_create` and friends in `common/gothic.cpp`), with "has read it" as a flag. The
   stories already pretend to do this: letters are borrowed vanilla items with a new description, and nothing can
   leave the hero's inventory. Each letter needs its own text and must survive save and load.
2. **Fights.** An NPC who attacks, or a duel the hero can lose and still carry on from. Depends on phase 6, since a
   story must still close whoever dies, and on knowing which NPCs are quest-critical.
3. **Sorcery.** Curses, transformations, scrolls that do something odd. Easiest to break, so it starts at the Wild and
   Chaos levels of the DM setting.

Alongside the ladder, since it does not depend on any rung:

- **Narrator voice.** An operation that plays a pre-generated line with a subtitle, without opening a conversation, so
  a voice can comment from off-screen as the player moves around. Combined with `on` perceptions it can react to what
  the player just did. It must not talk over a conversation or another narrator line, and needs a cooldown so it stays
  a treat. Today every line has to come from someone in a dialogue.

## Immediate work on Der Fall Tilo

Keep playing it as the reference: turning Tilo in, harbour first, the mage path, and the wine location.
Replace most repeat playthroughs with a path-walking test built on the existing fakes.

## Known risks

- Taste. Passing checks shows a story is not broken, not that it is good.
- One person's taste, and one story, shape all of this.
- Too few usable NPCs, or too few safe story shapes, may limit variety.
- Cost of many model calls.
- Vanilla logic the dependency map cannot see.

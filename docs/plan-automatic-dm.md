# Plan: an automatic game master with no human in the loop

Status: draft for review. Nothing here is built yet.

## Goal

A Director that writes and runs stories like Der Fall Tilo inside a running Gothic 2 game,
unattended. The player must never have to read or approve content, because reviewing a story
spoils it. Human review was how we learned the rules; it cannot be how the system runs.

## What exists today

Running on branch `python-repl`: event observer, typed story operations with all-or-nothing
plans, per-save story log, one-off scenes with sight checks, consequence rules, quest items,
journal, dialogue graphs with conditions, a logic checker that searches all orders of play, an NPC
dependency map, character sheets, pre-generated voices, an MCP server, and a local inspector
whose approvals are bound to the exact text and audio. One story, Der Fall Tilo, was written by
hand with a human and has been played through once along one path.

Known weaknesses: the checker proves logic only; rules in `docs/quest-design.md` are mostly
unenforced prose; a story dialogue replaces an NPC's whole conversation list; nothing has been
produced by a Director yet.

## Principle: replace the reviewer with layers, and fail closed

A plan reaches the game only if it passes every layer. Any failure means the Director retries
within a budget, and then does nothing. Doing nothing is always an acceptable result.

1. **Deterministic checks.** Schema, logic and every order of play, dependency map, physical rules
   (waypoints exist, placement unseen, no clue that incurs theft, guild gating), economy bounds on
   rewards, unique content, every essential fact has two sources of different approaches, every
   ending carries a cost.
2. **Lore ledger.** Based on Evident Light. Every claim about the existing world cites an exact
   passage from the game's scripts, found by a script and not by the model. Anything else must be
   declared as invention. Contradiction with a cited passage rejects the plan.
3. **Independent critics.** Separate model calls that never see the author's reasoning, each with
   one job: does this line answer what was just said on every path; is it true for this speaker and
   this player; does it match the character sheet; is the German natural; is it filler; is the
   story fair. Structured verdicts with reasons.
4. **Runtime safety.** Applied only at safe points, atomic, logged, reversible through the story log
   where possible, and a hard limit on how much the Director may change per game day.
5. **After-the-fact player signal.** A key to mark "that was wrong" with no spoilers. Marks are
   stored for later analysis and become new rules. It is the only human input, and it is optional.

## Measuring the critics before trusting them

Critics are unproven and could approve poor work or reject good work. Before they are used:

- Build a labelled set from this project: the lines and reasons the human rejected, recoverable
  from `git log -p python/dm/stories/tilo.py`, plus the approved lines of the current story. Add
  deliberately broken variants for each rule.
- Measure catch rate and false rejection rate per critic against that set, with a held-out part
  never used when writing their prompts.
- The set is small and from one story by one person, so these numbers are a floor for a working
  system, not proof that it generalises.

## Phases

Each phase ends with a check that can fail.

1. **Finish the template.** Remaining Tilo runs: turn him in, harbour first, mage path, wine location.
   Done when all three main paths play with no manual intervention.
2. **Additive dialogue.** Inject story topics into the normal `C_INFO` menu so vanilla conversations
   survive. Done when Gorax offers his normal topics and a story topic together, and any NPC can
   be used without detaching. Needed first because it changes what the Director may do.
3. **Enforce the written rules.** Turn every checkable rule in `quest-design.md` into a check, and
   list what remains as critic work.
4. **Lore ledger.** Done when every claim in Der Fall Tilo cites a passage or is declared invented.
5. **Critics and evaluation.** Done when catch and false rejection rates on the held-out set meet
   thresholds agreed before seeing the results.
6. **Director pipeline.** Observe; decide (usually do nothing); commit hidden truth; plot; checks;
   dialogue; critics and revise; German edit; bake voices; submit. Runs out of band, with a budget.
7. **Blind trial.** A story the player has not seen, generated from their real play. Success
   measures: they pursue it without instruction, it completes without intervention, and the count
   of "that was wrong" marks per hour. Compare against Der Fall Tilo, and against doing nothing.
8. **Lazy building.** Only after a blind trial succeeds: build dialogue when it becomes relevant and
   cache it by what it depends on, ahead of the player, falling back to existing lines.

## Decisions worth challenging

- Pre-baking conversations rather than generating them live.
- Using separate model calls as critics, which may share the author's blind spots.
- Doing additive dialogue before the Director instead of after.
- Fail-closed with "do nothing" as the default, which could make the world feel empty.
- Restricting stories to one location and a few NPCs for the first trials.
- Cloned original voices remain a private experiment and are never distributed; anything shipped
  uses designed voices. An automatic Director must therefore not depend on cloned voices.

## Known risks

- Taste. Nothing above proves a story is any good, only that it is not broken.
- Rule explosion: every playtest added rules, and checks may reject most plans.
- Cost and latency of many model calls for each story.
- Vanilla interactions the dependency map cannot see, such as logic outside the scripts.
- Overfitting the whole system to one story and one player's taste.

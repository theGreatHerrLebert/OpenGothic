# Experiment 2: do stories gain deeds without losing their worth?

Written before any story was generated. Do not change it after seeing results; add a dated note instead.

## Why

Experiment 1 passed its bar early: 9 of 20 stories were judged worth playing by the time of writing, all 9 of
those judged so far. But none of its 24 stories reacts to anything the player does. The story layer hears thefts,
blows, spells, letters read and rooms entered, and can test who is asleep, dead or where at what hour, yet every
story is solved by talking. Commit 8818cc5b changed the Director brief and the design rules to ask for at least one
moment resolved by a deed, and `check_story.py` now warns about a story without one.

## Question

Does the changed brief produce stories in which a deed matters, without making them less worth playing?

## Setup

- Two arms that differ only in the documents the author reads:
  - **A, before:** `docs/director-brief.md` and `docs/quest-design.md` as of commit 5cccdab4.
  - **B, deeds:** the same files as of commit 8818cc5b.
- 5 stories per arm, 10 in all: one per arm from each of experiment 1's five snapshots, so both arms see the same play.
- Everything else as in experiment 1: separate agents with no access to the project's conversation, the same model,
  character sheets, world facts, Der Fall Tilo as a format example that must not be copied, the same NPC limits,
  and one chance to repair a story that fails automatic checking. Neither arm gets the character map's data.
- Stories are stored like experiment 1's, under names that do not reveal the arm; the arm of each is recorded in a
  separate key file that the reader does not open before scoring is complete.
- None of experiment 1's stories is reused: the reader has already seen them in the story library.

## Scoring

The reader is the user, who reads the 10 stories in random order on the story trial page, without knowing the arm.
For each story, as in experiment 1:

| Field | Values |
|---|---|
| Worth playing | yes / no |
| Interest | 1 to 5 |
| Defects | each tagged with the rule it breaks, from `docs/quest-design.md`, or "new" |

and one new field, added to the page before generation:

| Field | Values |
|---|---|
| A deed matters | yes / no: at least one thing the player does, not says, changes what they learn or how it ends |

Measured automatically, without the reader: whether `check_story.py` finds a deed, how many, and of which kinds;
checker pass rate before and after repair.

## Results that decide

- **Adopt the brief** if at least 4 of 5 B stories have a deed that matters (reader's field), and B has no more than
  one fewer worth-playing story than A.
- **Deeds without weight:** if B stories have deeds by the checker but the reader marks most as not mattering, the
  brief produces decoration. Next step: worked examples of deeds in the brief, or a critic that asks what each deed
  changes.
- **Worse stories:** if B has two or more fewer worth-playing stories than A, look at the defects before deciding
  whether the deed rule crowds out the rest.
- **No change:** if B has no more deeds that matter than A, the documents are not the lever. Next step: new verbs
  in the story layer, starting with being in a place.

## Limits

One reader, who wrote the change and hopes it works; blinding the arm is the only guard against that. Five stories per
arm can show a large effect, such as deeds going from none to most, but not a small one in interest. Reading is not
playing: a deed reads differently from doing it. Both arms come from one model family.

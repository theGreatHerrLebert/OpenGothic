# Experiment 3: are the stories good to play, not only good to read?

Written before any story was generated. Do not change it after seeing results; add a dated note instead.

## Why

Experiments 1 and 2 scored stories by reading them on the story trial page. Five stories have since been played end to
end in the game, but they were designed together with the player in conversation, so he knew most of them before they
played. An outside review (2026-11-12) asked the question none of this answers: did any story produce a moment that
surprised the player *as a player*? Reading cannot measure that, nor whether the way through a story without quest
markers can be found. Since then the brief asks every story why it matters (`significance`), the checker looks for
pointers to every step (`discoverability.py`), stories end quietly when unfinished (`closures`), and the in-game
rating asks three separate things.

## Question

Do stories written by author agents from the user's own play, which he has not read, work in the game, belong in
Gothic, and are they good to play, judged while playing?

## Setup

- 6 stories, each from a fresh snapshot of the user's current playthrough (one snapshot per story, taken where the
  player happens to be, so the stories grow out of different deeds).
- Authors as in experiment 2, arm B: separate agents with no access to the project's conversation, the same model,
  the current `docs/director-brief.md`, `docs/quest-design.md`, `docs/story-ops.md`, character sheets and world facts.
  Every story must pass `check_story.py` (significance, closures, discoverability warnings answered) with one chance
  to repair.
- Before play, a naive-player agent reads each story's dossier (`discoverability.py <story> --dossier`) and reports
  where it would get stuck. Its report is stored, not shown to the player, and not used to fix the story: it is a
  prediction to compare with the player's own `way` answer.
- The player does not read the stories. They are started in the game by number; titles are not shown until he meets
  them. Voices are baked before play.

## Scoring

In the game, with Alt+5 after a story ends or is abandoned (`feedback.py`):

| Dimension | Questions |
|---|---|
| Technical | Did anything break? Plus every Alt+1 "Fehler hier" moment |
| Narrative | Could it be from the original game? How exciting, 1 to 5? Did a deed count? |
| Player experience | Worth playing? Found the way alone / with luck / only with help? Surprised as a player? |

`python3 python/dm/feedback.py` sums them per story.

## What counts as an answer

- **Works:** at least 5 of 6 run clean.
- **Belongs:** at least half could be from the original game.
- **Good to play:** at least half worth playing, and at least two surprised the player.
- **Findable:** the naive-player agent's prediction matches the player's `way` answer for at least 4 of 6. If it
  does, the agent can screen stories before a player sees them; if not, discoverability needs players.

Only after this does an unattended runner (plan phase 7) make sense.

## Note, 2026-11-12, after the first story

Story 6 ("Der freie Strohsack") was played blind on both paths and ran clean, but was rated not worth playing,
excitement 2, not like the original game, way "with luck", no surprise. The player: no hard decision (return or keep,
neither costs anything), stakes too small, no consequence for framing a mercenary, no hidden layer, and the pouch and
sickle were plain game items. The naive-player agent predicted "alone"; it missed. The director brief gained the
section "Good to play" and the checker warns about endings that do not end the story and plain key items. Story 6
counts for brief v1; the remaining five stories are written with the revised brief, so the experiment now compares
the two only loosely.

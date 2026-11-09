# Experiment 1: can a Director write a story worth playing?

Written before any story was generated. Do not change it after seeing results; add a dated note instead.

## Question

Given only the Director brief, the design rules, character sheets, world facts and a snapshot of
real play, can a model write Gothic 2 side stories a player would want to play?

## Setup

- 20 stories, written by separate agents with no access to the project's conversation.
- 5 snapshots of recorded play, 4 stories each. The real runs teleported the player to the monastery;
  each snapshot states that the hero is a novice in chapter 1, as the design assumes.
- Stories may use any NPC with a sheet through one-off scenes, but ongoing dialogue only for
  NPCs with no scripted dialogue. Der Fall Tilo may be read as an example of the format and must not be
  copied. Reusing its premise (a missing novice, stolen candlesticks) counts as a defect.
- Automatic checking runs first, using the game's real NPC, item and waypoint names. Each author gets
  one chance to repair a story that fails.

## Scoring

The reader is the user, who reads all stories that pass checking, in random order, without
knowing which snapshot or agent produced them. For each story:

| Field | Values |
|---|---|
| Worth playing | yes / no |
| Interest | 1 to 5 |
| Defects | each tagged with the rule it breaks, from `docs/quest-design.md`, or "new" |

## Results that decide

- **Continue** if at least 5 of 20 are rated worth playing. Stories failing automatic checking after repair
  count as not worth playing.
- **Change approach** if fewer than 5. Look at which defects dominate before deciding what to change.

Also recorded, without deciding anything: checker pass rate before and after repair, and the
defects by rule, which become the evidence for which critics to build.

## Limits

One reader, who designed the rules and has a stake in the outcome. Twenty stories from one model family.
Reading is not playing: a story can read well and play badly. Interest ratings are one person's taste.

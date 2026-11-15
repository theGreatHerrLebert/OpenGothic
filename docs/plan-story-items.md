# Story items that do something when used, and more carriers (plan, 2026-11-15)

Stories so far have items of their own (`define_item` on an unused carrier) that can be carried, given, taken, checked,
and, since the story books, read. A story could not make an item that *does* something when the hero uses it. The
first story to need it (a fire mage's weather contract) has three kinds:

- **a ritual tool**, used at a place (the weather rune on a field): nothing visible but a light; a rule of the story
  reacts to the use (and only where it holds, e.g. near the field);
- **one-shot scrolls**: used up, each brings a magical weather for about five real minutes (ice storm, arcane mist,
  meteor rain), then the climate takes over again;
- **a keepsake with a cooldown** (an orc's drum): kept, summons a short thunderstorm, once a game day.

That story also needs about six carriers more than are free.

## What is there

- `define_item` copies every field of the base item (`like`) onto the carrier, its `on_state` script included
  (`GameScript::initializeInstanceItem`). Using a defined item today runs the *base's* script: a scroll would cast its
  real spell, a potion would heal.
- The books: `World::setStoryDocument(cls, …)`; `Inventory::use` checks it first and never runs a script for it; the
  read is recorded as the perception `read_item`, which rules can wait for (`on`).
- Rules fire once. A repeating effect (the drum) cannot be a rule.
- Weather from a story: the `weather` op, with `hours` in game hours (the game clock runs 14.5 times real time:
  five real minutes are about 1.2 game hours); when they run out the climate takes over.
- `gothic.world.play_effect(name, x, y, z, seconds)` plays a visual effect (with its sound) at a place.

## Design

### `define_item` gains `use`

```json
{"op": "define_item", "item": "EISSTURM_ROLLE", "like": "ITSC_ICECUBE", "name": "Spruchrolle Eissturm",
 "use": {"consume": true, "effect": "SPELLFX_ICECUBE",
         "weather": {"kind": "crystal", "intensity": 0.8, "fade": 10, "wind": [6, 2], "hours": 1.2}}}
```

- `consume` (bool, default false): one is taken from the hero when used.
- `effect` (optional): a visual effect played at the hero (a name from the game's VFX, `SPELLFX_`/`MFX_`, checked to
  exist when the plan is submitted).
- `animation` (optional): the hero plays one of a short allowlist of the game's own animations (a mage's practice
  gestures, `T_PRACTICEMAGIC`.. `T_PRACTICEMAGIC5`; reading, `T_MAP_STAND_2_S0`-like). Kept to an allowlist so a story
  cannot name a missing animation.
- `weather` (optional): the arguments of a `weather` op (validated by the same check, `hours` required), applied when
  used, so it ends by itself and the climate takes over.
- `every_hours` (optional, game hours, 1..240): after a use, using it again does nothing until that many game hours
  have passed. It excludes `consume` (a used-up item has no second use).
- Every use (also one on cooldown? no: only a use that took effect) is a perception `used_item` with the item, so a
  rule can wait for it, with its own checks (near the field, after a flag). The ritual is exactly that: an item with
  only an `effect` and an `animation`, and a rule `on: {"event": "used_item", "item": "WETTERRUNE"}` with a check that
  the hero is near Lobart's field.

An item with `use` cannot also have `pages` (a book is read, not used).

### Engine

- `World::setStoryUse(cls, bool consume)` beside `setStoryDocument` (cleared with an empty call, like the books).
- `Inventory::use`: after the story-document check, a story-use item: for the player, record the perception
  `used_item` (item symbol name) and, if `consume`, remove one; never the base's script, never equipped (a scroll's
  base would otherwise go to a spell slot). For an NPC: nothing. Returns false (nothing was equipped).
- Not saved: the story sets it again after every load, as it does the definitions and documents.

### Python

- `gothic.world.set_use(carrier, on, consume)`.
- `story.py`: `define_item` validates and folds `use`; `_define_in_world` calls `set_use` (and clears it when a
  redefinition has none), every load too.
- `perceptions.py`: the event `used_item` (item field).
- The use effect itself is the story layer's: in `_take_perceptions`, a `used_item` of a story item with `use`:
  - on cooldown (`every_hours` and the last use within it): nothing, and the event is not passed to rules;
  - otherwise a logged op `item_used` (item, game time) is applied (so the cooldown survives a save and load), then
    the effect at the hero, the animation, and the weather as a `weather` op with `hours` counted from now.
- A consumed item on cooldown cannot happen (`consume` excludes `every_hours`).

### Carriers

A carrier must be an item instance the game never makes on its own: no script creates, gives, sells or checks it
outside debug code, no world places it, no chest holds it, the engine does not name it, and it is not a key (a lock
in the world could name it). Searched with the DAT reader (`depmap.parse`) and the world dump: referenced only by
`ITEMHOSHI`, `PC_ITEMFELLER`, `PC_ROCKEFELLER`, `PC_BANDIT` (debug inventories) or not at all.

- **Out of the pool**: `ITFO_XPSTEW` (Thekla gives it), `ITFO_ADDON_FIRESTEW` (Snaf), `ITFO_CORAGONSBEER` (Coragon),
  `ITRI_ADDON_STR_01` (Greg). None was used by a saved story yet; a story item on them would turn into the game's
  real stew, beer or ring when the game hands that out (and the other way round).
- **Into the pool** (16): `ITMI_PACKET`, `ITMI_GOLDPLATE_MIS`, `ITMI_STONEOFKNOWLEGDE_MIS`,
  `ITFO_ADDON_KROKOFLEISCH_MISSION`, `ITWR_ADDON_AXTANLEITUNG`, `ITWR_ADDON_PIRATENTOD`,
  `ITWR_ADDON_RUNEMAKING_KDW_CIRC2`..`CIRC6`, `ITWR_VATRAS_KDFEMPFEHLUNG_ADDON`, `STANDARDBRIEF`, `STANDARDBUCH`,
  `ITSC_PALLIGHTHEAL`, `ITSC_SUMMONMUD`, `ITRU_TELEPORT_3`, `ITPO_STORY`. The carrier's own type does not matter: every
  field, the main flag included, comes from `like`.
- Order kept: the pool's first entries stay first (a carrier, once given, stays the item's; the state records it).

## Tests

- `test_story.py`: `use` validated (consume with every_hours refused, pages with use refused, weather checked, unknown
  effect refused); folded; `set_use` called on define, on rebind after a load, cleared on redefinition without `use`;
  a `used_item` perception applies the weather and effect, logs `item_used`; a second use within `every_hours` does
  nothing and does not reach rules; after it, works again; a rule `on used_item` fires.
- `test_checks.py`: `used_item` validates and matches.
- Carriers: the four out, the sixteen in, no duplicates.
- Engine: untested by the suite; checked in the game with the three scrolls and the drum.

## Revised after Codex's plan review (2026-11-15)

- **One transaction, in Python.** The engine only records the request (`used_item`: item, position, world) and never
  takes anything. The story layer accepts it: cooldown checked, one taken (`consume`) with `remove_item`, `item_used`
  logged, then the weather; the effect and the animation are cosmetic and best effort (a failed `play_effect` changes
  nothing). A request that is lost (queue overflow, no game master) costs the hero nothing.
- **Inert.** An item with `use` is made harmless in `initializeInstanceItem`: its main flag set to none, `on_equip`,
  `on_unequip`, `on_state`, spell and magic cleared, so no automatic equipping, no state use by an NPC, no copied script
  anywhere; flagged a mission item, so traders do not buy it. It keeps the base's look (`like` is only its look).
- **Fixed once defined.** A redefinition may not add or remove `use` (refused when the plan is submitted): saved copies
  keep their fields, so the item is inert or plain for good.
- **Where it was used** travels with the request: `near` works for `used_item` like for `used_object`, so the ritual
  matches where the rune was used, not where the hero stands when the event is processed. Witness filters (`seen_by`,
  `unseen`) are refused for `used_item` (nobody is measured).
- **Cooldown** per item of the story (not per copy), in elapsed game hours (`day*24 + hour + minute/60`, as the
  weather's `hours`), kept by the logged `item_used`; loading an earlier save loads the earlier log with it.
  `consume` and `every_hours` may go together (a stack of scrolls, rate-limited).
- **The weather** of a use replaces whatever weather a story set (one slot); "five minutes" is about 1.2 game hours and
  only approximate across sleeping.
- **Carriers:** the three key carriers already in the pool were checked against every lock in the worlds (none names
  them). The additions are 18, not 16.
- **The weather of a use is an overlay, not the story's weather** (after the story review): kept apart in the state
  (`item_weather`, with its own end), it wins while it lasts; when it ends, the story's own weather (if it still owns
  the sky) is set again, with its heat and fog, else the climate's. A story's weather set while an overlay runs is
  kept underneath and shows when the overlay ends. Loading restores whichever is active.
- **The item text says what it does** (the scrolls: a storm for a few minutes, nothing more), written by the story in
  `description`/`rows`.

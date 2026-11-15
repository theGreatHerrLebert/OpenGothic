# Story books (plan, 2026-11-15)

A story can give the hero something to read: a book of several pages, a letter, a note, in its own words. First use:
the weather-magic book the monastery's scholar hands a fire mage (a co-written story, see python/dm_runtime/stories_wip).

## What exists

- `define_item` gives an unused item instance (a carrier) the story's own name, description, rows, value and look.
- A story's quest evidence with an `ITWR_` carrier already reads as a one-page letter from its text rows
  (`Inventory::use`, `showStoryLetter`), and reading it is recorded (`World::recordDocumentRead`), which rules can see.
- `DocumentMenu` draws all pages of a document side by side and closes on Escape or the inventory key; it cannot turn
  pages. The game's own books are always two pages (left and right image).

## Design

- **Story op:** `define_item` gains `pages` (1 to 16 strings of our own text, each at most 480 characters and about 14 lines of 34 characters, no stage
  directions) and `style` (`book`: the mage book's two-page spread, turned two pages at a time; `letter`: one sheet per
  page). Validated when submitted, like every op. Kept in the story's state with the item; set again after a load
  (the same path `define_item` already takes on rebind).
- **Engine:** the world keeps the story documents by item class (`World::setStoryDocument(cls, pages, style)`, not
  saved: the story sets them again on load). `Inventory::use` shows a story document for its item when the player uses
  it, instead of the carrier's own script (so the original book's text never shows), records the read like the
  letters do, and returns without consuming it.
- **Turning pages:** `DocumentMenu::Show` gains `spread` (pages shown at once: 2 for a book, 1 for a letter, 0 = all,
  as today). With more pages than one spread, Left/Right (and the strafe keys) turn; a small page count shows at the
  foot. Documents the game's scripts make keep `spread` 0 and behave as before.
- **Look:** book: the game's mage-book images (left and right) and its book font and margins, as its own books use
  them; letter: `letters.TGA` as the story letters today.
- **Python:** `gothic.world.set_document(carrier, pages, style)` (and with no pages, clears it).

## Not yet

Pictures in a book, maps, writing in a book, NPCs reading.

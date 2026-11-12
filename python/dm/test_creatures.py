"""A story's own creatures against a fake game. Run: python3 python/dm/test_creatures.py"""

import pathlib
import sys
import tempfile
import types

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
fake = types.ModuleType("gothic")
sys.modules["gothic"] = fake


class Npc:
    def __init__(self, instance):
        self.instance, self.display_name, self.dead = instance, "", False
        self.attrs, self.level, self.items, self.variant, self.scale = {}, 0, [], 0, None
        self.body_mesh = "Wol_Body"

    def set_attribute(self, name, value): self.attrs[name] = value
    def set_scale(self, x): self.scale = x
    def set_body_texture(self, v): self.variant = v
    def add_item(self, item, count=1): self.items.append((item, count))
    def in_state(self, s): return s == "ZS_MM_ATTACK"


class World:
    generation, day, time = 1, 1, (12, 0)

    def __init__(self):
        self.npcs = [Npc("WOLF")]   # an ordinary wolf, which must never be taken for the story's

    def instance_kind(self, n): return "npc" if n.upper() in ("WOLF", "PEPE") else "item" if n.upper().startswith("IT") else None
    def has_waypoint(self, n): return n.startswith("NW_")
    def find_npc(self, n): return None

    def spawn(self, instance, waypoint):
        npc = Npc(instance.upper())
        self.npcs.append(npc)
        return npc

    def remove_npc(self, npc): self.npcs.remove(npc)


registered, exported = {}, []
fake.world = World()
fake.resources = types.SimpleNamespace(
    mesh_textures=lambda mesh: ["WOL_BODY_V0.TGA", "WOL_TEETH.TGA"] if mesh == "Wol_Body.ASC" else [],
    export_texture=lambda name, path, tint, strength, brighten: exported.append(name) or True,
    register_texture=lambda name, path: registered.__setitem__(name, path))
fake.player = types.SimpleNamespace(position=(0, 0, 0), guild=0, items=[])
fake.daedalus = types.SimpleNamespace(get=lambda n, i=0: 0)
fake.dialog = types.SimpleNamespace(partner=lambda: None, bind=lambda n: None, unbind=lambda n=None: None)

from dm import checks, creatures, perceptions, play_story, story as st  # noqa: E402

creatures.ASSETS = pathlib.Path(tempfile.mkdtemp())
st.SAVES_DIR = pathlib.Path(tempfile.mkdtemp())
st.ATTACHABLE.add("WOLF")
WOLF = {"op": "spawn_creature", "id": "white_wolf", "like": "WOLF", "waypoint": "NW_PASTURE", "name": "Weißer Wolf",
        "look": {"tint": [0.92, 0.96, 1.0], "brighten": 2.2}, "scale": 1.3, "hp": 400, "strength": 70, "level": 20,
        "loot": [{"item": "ITAT_WOLFFUR", "count": 2}]}


def rejected(op, word):
    try:
        st.Story().validate([op])
    except st.PlanError as err:
        assert word in str(err), (word, err)
        return
    raise AssertionError(f"accepted: {op}")


# Checked when submitted.
st.Story().validate([WOLF])
rejected(dict(WOLF, like="PEPE"), "nameless creature")
rejected(dict(WOLF, waypoint="X"), "waypoint")
rejected(dict(WOLF, scale=5), "scale")
rejected(dict(WOLF, hp=0), "hp")
rejected(dict(WOLF, look={"tint": [3, 1, 1]}), "tint")
rejected(dict(WOLF, look={"texture": "../x.png"}), "texture")
rejected(dict(WOLF, loot=[{"item": "WOLF"}]), "loot")
rejected(dict(WOLF, name=""), "name")
s = st.Story()
try:
    s.validate([WOLF, dict(WOLF, id="second")])
    raise AssertionError("same name accepted twice")
except st.PlanError as err:
    assert "name" in str(err)

# Spawned and made its own; the ordinary wolf stays as it was.
s.apply_plan({"reason": "r", "ops": [WOLF]})
wolf = fake.world.npcs[-1]
assert wolf.display_name == "Weißer Wolf" and wolf.variant == 50 and wolf.scale == 1.3 and wolf.level == 20
assert wolf.attrs == {"hp_max": 400, "hp": 400, "strength": 70} and wolf.items == [("ITAT_WOLFFUR", 2)]
assert list(registered) == ["WOL_BODY_V50.TGA"] and exported == ["WOL_BODY_V0.TGA"]   # only the variant texture
assert fake.world.npcs[0].variant == 0 and s.state["creatures"]["white_wolf"]["variant"] == 50
assert s.log[0]["ops"][0]["variant"] == 50          # the log keeps the variant, so a load replays the same

# A second creature gets the next variant.
s.apply_plan({"reason": "r", "ops": [dict(WOLF, id="grey", name="Alter Grauer", look=None)]})
assert s.state["creatures"]["grey"]["variant"] == 51 and fake.world.npcs[-1].variant == 0   # no look: game fur

# Checks and perceptions find it by id, never the ordinary wolf.
st._story = s
assert not checks.all_hold([{"type": "npc_dead", "creature": "white_wolf"}])
assert checks.all_hold([{"type": "npc_state", "creature": "white_wolf", "state": "ZS_MM_ATTACK"}])
assert not checks.all_hold([{"type": "npc_dead", "creature": "not_yet"}])      # not spawned is not dead
killed = {"kind": "killed", "actor": "PLAYER", "target": "WOLF", "target_name": "Weißer Wolf", "item": "", "seen_by": []}
other = dict(killed, target_name="Wolf")
on = {"event": "killed", "creature": "white_wolf"}
assert perceptions.validate(on) is None and checks.validate({"type": "npc_dead", "creature": "white_wolf"}) is None
assert perceptions.matches(on, killed) and not perceptions.matches(on, other)
wolf.dead = True
assert checks.all_hold([{"type": "npc_dead", "creature": "white_wolf"}])
fake.world.npcs.remove(wolf)
fake.world.generation += 1
assert checks.all_hold([{"type": "npc_dead", "creature": "white_wolf"}])        # gone counts as dead

# After a load the fur is registered again and put back on.
fake.world.npcs.append(wolf)
wolf.dead, wolf.variant = False, 0
registered.clear()
t = st.Story()
s.save("creatures")
t.load("creatures")
fake.world.generation += 1
t.rebind()
assert wolf.variant == 50 and "WOL_BODY_V50.TGA" in registered

# A story's creature ids are namespaced like its other ids.
ops = play_story.namespaced([WOLF, {"op": "add_rule", "id": "r", "when": [], "checks": [{"type": "npc_dead", "creature": "white_wolf"}],
                                    "ops": []}], "story_6")
assert ops[0]["id"] == "story_6:white_wolf" and ops[1]["checks"][0]["creature"] == "story_6:white_wolf"
print("creatures ok")

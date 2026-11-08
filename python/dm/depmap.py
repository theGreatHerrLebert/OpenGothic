"""Finds which NPCs the original game scripts depend on, from compiled GOTHIC.DAT.

    python3 python/dm/depmap.py <path to GOTHIC.DAT> [deps.json] [safe_npcs.json]

An NPC counts as depended on when its instance is pushed by code outside its
own dialogues, its own init function, and world setup. Such code can break,
or a quest can become impossible, if the NPC disappears.
"""

import collections
import json
import struct
import sys

MEMBER = 1 << 2  # the symbol is a class field and stores no value here
T_FLOAT, T_INT, T_STRING, T_CLASS, T_FUNC, T_PROTOTYPE, T_INSTANCE = 1, 2, 3, 4, 5, 6, 7

OP_BL, OP_BE, OP_PUSHI, OP_PUSHV, OP_PUSHVI = 61, 62, 64, 65, 67
OP_B, OP_BZ, OP_GMOVI, OP_PUSHVV, OP_MOVI, OP_RSR = 75, 76, 80, 245, 9, 60
WITH_ARG = {OP_BL, OP_BE, OP_PUSHI, OP_PUSHV, OP_PUSHVI, OP_B, OP_BZ, OP_GMOVI}

SETUP_PREFIXES = ("STARTUP_", "INIT_", "RTN_", "B_ENTER_", "B_INITNPCGLOBALS")
SAFE_GROUPS = ("NOV_",)  # novices are the only group stories may remove so far


class Reader:
    def __init__(self, data):
        self.data, self.pos = data, 0

    def u8(self):
        self.pos += 1
        return self.data[self.pos - 1]

    def u32(self):
        self.pos += 4
        return struct.unpack_from("<I", self.data, self.pos - 4)[0]

    def i32(self):
        self.pos += 4
        return struct.unpack_from("<i", self.data, self.pos - 4)[0]

    def line(self):
        end = self.pos
        while self.data[end] not in (0, 10, 13):
            end += 1
        text = self.data[self.pos:end].decode("latin-1")
        self.pos = end + 1
        return text


def parse(data):
    r = Reader(data)
    r.u8()
    count = r.u32()
    r.pos += 4 * count
    symbols = []
    for index in range(count):
        name = r.line() if r.u32() else ""
        r.u32()
        bits = r.u32()
        size, kind, flags = bits & 0xFFF, (bits >> 12) & 0xF, (bits >> 16) & 0x3F
        r.pos += 20
        address = None
        if not flags & MEMBER:
            if kind == T_FLOAT or kind == T_INT:
                r.pos += 4 * size
            elif kind == T_STRING:
                for _ in range(size):
                    r.line()
            elif kind == T_CLASS:
                r.u32()
            elif kind in (T_FUNC, T_PROTOTYPE, T_INSTANCE):
                address = r.i32()
        parent = r.i32()
        symbols.append(dict(index=index, name=name.upper(), kind=kind, address=address, parent=parent))
    code_size = r.u32()
    return symbols, data[r.pos:r.pos + code_size]


def instructions(code):
    pos = 0
    while pos < len(code):
        op = code[pos]
        start = pos
        pos += 1
        arg = None
        if op in WITH_ARG:
            arg = struct.unpack_from("<I", code, pos)[0]
            pos += 4
        elif op == OP_PUSHVV:
            arg = struct.unpack_from("<I", code, pos)[0]
            pos += 5
        yield start, op, arg


def root_class(symbols, sym):
    seen = 0
    while sym["parent"] != -1 and seen < 16:
        sym = symbols[sym["parent"]]
        seen += 1
    return sym["name"]


def analyze(symbols, code):
    by_name = {s["name"]: s for s in symbols}
    info_npc = by_name["C_INFO.NPC"]["index"]
    owned_fields = {by_name[f]["index"] for f in ("C_INFO.CONDITION", "C_INFO.INFORMATION")}
    npc_flags = by_name["C_NPC.FLAGS"]["index"]
    immortal_flag = by_name["NPC_FLAG_IMMORTAL"]["index"]
    get_npc = by_name["HLP_GETNPC"]["index"]

    npcs = {s["index"]: s for s in symbols
            if s["kind"] == T_INSTANCE and s["address"] and s["address"] > 0 and root_class(symbols, s) == "C_NPC"}

    # every instruction address belongs to the function starting at or before it
    bodies = sorted((s["address"], s["index"]) for s in symbols
                    if s["kind"] in (T_FUNC, T_INSTANCE, T_PROTOTYPE) and s["address"] and s["address"] > 0)
    starts = [a for a, _ in bodies]

    import bisect

    def owner_of(address):
        at = bisect.bisect_right(starts, address) - 1
        return bodies[at][1] if at >= 0 else None

    ops = list(instructions(code))
    info_owner = {}          # C_INFO instance symbol -> npc symbol
    func_of_info = {}        # function symbol -> C_INFO instance symbol
    immortal = set()
    pushes = collections.defaultdict(list)

    # Scripts rarely use an NPC directly. They write X = Hlp_GetNpc(NPC_INSTANCE)
    # and use the variable X, so variables are traced back to their NPC.
    alias = {}
    for i in range(len(ops) - 2):
        (_, a_op, a_arg), (_, b_op, b_arg), (_, c_op, c_arg) = ops[i], ops[i + 1], ops[i + 2]
        if a_op == OP_PUSHI and a_arg in npcs and b_op == OP_BE and b_arg == get_npc and c_op == OP_PUSHVI:
            alias[c_arg] = a_arg

    for i, (address, op, arg) in enumerate(ops[:-1]):
        next_op, next_arg = ops[i + 1][1], ops[i + 1][2]
        field = next_arg if next_op == OP_PUSHV else None
        owner = owner_of(address)
        if op == OP_PUSHI and field == info_npc:
            info_owner[owner] = arg
        elif op == OP_PUSHI and field in owned_fields:
            func_of_info[arg] = owner
        elif op == OP_PUSHV and arg == immortal_flag and field == npc_flags and owner in npcs:
            immortal.add(owner)
        elif op == OP_PUSHI and arg in npcs and not (next_op == OP_BE and next_arg == get_npc):
            pushes[arg].append(owner)
        elif op == OP_PUSHVI and arg in npcs:
            pushes[arg].append(owner)
        elif op == OP_PUSHVI and arg in alias and owner != alias[arg]:
            pushes[alias[arg]].append(owner)

    dialogues = collections.Counter(info_owner.values())
    result = {}
    for index, npc in npcs.items():
        external = collections.Counter()
        for owner in pushes.get(index, []):
            name = symbols[owner]["name"] if owner is not None else "?"
            if owner == index or name.startswith(SETUP_PREFIXES):
                continue
            info = func_of_info.get(owner, owner)
            if info_owner.get(info) == index:
                continue
            external[name] += 1
        result[npc["name"]] = {
            "dialogues": dialogues.get(index, 0),
            "immortal": index in immortal,
            "external_refs": sum(external.values()),
            "referenced_by": sorted(external),
        }
    return result


def main():
    with open(sys.argv[1], "rb") as f:
        symbols, code = parse(f.read())
    result = analyze(symbols, code)
    if len(sys.argv) > 2:
        with open(sys.argv[2], "w", encoding="utf-8") as f:
            json.dump(result, f, indent=1, sort_keys=True)
    print(f"{len(symbols)} symbols, {len(code)} bytes of code, {len(result)} NPC instances")
    safe = sorted(k for k, v in result.items()
                  if k.startswith(SAFE_GROUPS) and "TOTER" not in k
                  and not v["external_refs"] and not v["dialogues"] and not v["immortal"])
    print("safe:", safe)
    if len(sys.argv) > 3:
        with open(sys.argv[3], "w", encoding="utf-8") as f:
            json.dump(safe, f, indent=1)
            f.write("\n")
    novices = {k: v for k, v in result.items() if k.startswith("NOV_")}
    for name, row in sorted(novices.items(), key=lambda kv: (kv[1]["external_refs"], kv[1]["dialogues"])):
        print(f"{name:28} refs={row['external_refs']:3} dialogues={row['dialogues']:3} immortal={row['immortal']} {row['referenced_by'][:4]}")
    for name in ("NONE_100_XARDAS", "KDF_500_PYROKAR", "NOV_600_PEDRO", "VLK_4250_JORGEN"):
        if name in result:
            r = result[name]
            print("SANITY", name, r["external_refs"], r["dialogues"], r["immortal"], r["referenced_by"][:6])


if __name__ == "__main__":
    main()

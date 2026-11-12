"""Reads every dialogue out of compiled GOTHIC.DAT as conditions and effects.

    python3 python/dm/quest_mine.py <path to GOTHIC.DAT> <output directory>

Writes dialogues.json (one record per C_INFO), functions.json (every other script function) and
items.json. A small stack simulator turns bytecode into readable expressions, and each effect keeps the
`if` guards that enclose it. The output quotes the game's text, so it belongs in the gitignored runtime folder.
"""

import bisect
import json
import pathlib
import sys

import depmap as dm

F_RETURN, BINARY = 2, {0: "+", 1: "-", 2: "*", 3: "/", 4: "%", 5: "|", 6: "&", 7: "<", 8: ">", 11: "||", 12: "&&",
                       13: "<<", 14: ">>", 15: "<=", 16: "==", 17: "!=", 18: ">="}
UNARY = {30: "+", 31: "-", 32: "!", 33: "~"}
ASSIGN = {9: "=", 25: "+=", 26: "-=", 27: "*=", 28: "/=", 70: "=", 71: "=", 72: "=", 73: "=", 74: "="}
OBJECT_CLASSES = {"C_ITEM", "C_NPC", "C_INFO"}
LITERAL = "\u0178"  # string literals are named 0xFF + number, and the parser upper-cases names


class Program:
    def __init__(self, data):
        self.symbols, self.code = dm.parse(data)
        self.ops = list(dm.instructions(self.code))
        self.aiv_names = {s["ints"][0]: s["name"] for s in reversed(self.symbols)  # AIV_* constants name the slots of AIVAR
                          if s["name"].startswith("AIV_") and s["kind"] == dm.T_INT and s["ints"]}
        self.addresses = [a for a, _, _ in self.ops]
        self.by_address = {}
        bodies = [s for s in self.symbols if s["kind"] in (dm.T_FUNC, dm.T_INSTANCE, dm.T_PROTOTYPE) and s["address"] and s["address"] > 0
                  and not s["flags"] & 8]
        for s in bodies:
            self.by_address.setdefault(s["address"], s)
        self.starts = sorted(self.by_address)

    def name(self, index):
        s = self.symbols[index]
        if s["kind"] == dm.T_STRING and s["strings"] and (s["flags"] & 1 or s["name"].startswith(LITERAL)):
            return json.dumps(s["strings"][0], ensure_ascii=False)
        return s["name"]

    def aivar(self, slot):
        return self.aiv_names.get(slot, slot)

    def literal(self, value):
        """An integer that is really an item, NPC or dialogue is shown by name; small amounts stay numbers."""
        if 1000 < value < len(self.symbols):
            s = self.symbols[value]
            if s["kind"] == dm.T_INSTANCE and dm.root_class(self.symbols, s) in OBJECT_CLASSES:
                return s["name"]
            if s["kind"] == dm.T_FUNC and not s["name"].startswith(LITERAL):
                return s["name"]
        return str(value)

    def run(self, symbol):
        """Simulates one body and returns its statements as {do|set|return, if}."""
        start = symbol["address"]
        at = bisect.bisect_right(self.starts, start)
        end = self.starts[at] if at < len(self.starts) else len(self.code)
        first = bisect.bisect_left(self.addresses, start)
        stack, guards, out, owner = [], [], [], None

        def pop():
            return stack.pop() if stack else "?"

        def emit(kind, text):
            record = {kind: text}
            if guards:
                record["if"] = [g for g, _ in guards]
            out.append(record)

        def call(callee):
            args = list(reversed([pop() for _ in range(callee["size"])]))
            text = f"{callee['name']}({', '.join(args)})"
            if callee["flags"] & F_RETURN:
                stack.append(text)
            else:
                emit("do", text)

        for i in range(first, len(self.ops)):
            address, op, arg = self.ops[i]
            if address >= end:
                break
            while guards and address >= guards[-1][1]:
                guards.pop()
            if op == dm.OP_GMOVI:  # the next field access belongs to this instance, as in other.guild
                owner = self.symbols[arg]["name"]
            elif op == dm.OP_PUSHI:
                stack.append(self.literal(arg))
            elif op in (dm.OP_PUSHV, dm.OP_PUSHVI, dm.OP_PUSHVV):
                text = self.name(arg)
                if op == dm.OP_PUSHVV:
                    text += f"[{self.aivar(self.code[address + 5]) if text.endswith('.AIVAR') else self.code[address + 5]}]"
                if owner and "." in text and text.split(".")[0].startswith("C_"):
                    text = owner + "." + text.split(".", 1)[1]
                    owner = None
                stack.append(text)
            elif op in BINARY:
                left, right = pop(), pop()
                stack.append(f"({left} {BINARY[op]} {right})")
            elif op in UNARY:
                stack.append(f"{UNARY[op]}{pop()}")
            elif op in ASSIGN:
                target, value = pop(), pop()
                emit("set", f"{target} {ASSIGN[op]} {value}")
            elif op == dm.OP_BE:
                call(self.symbols[arg])
            elif op == dm.OP_BL:
                if arg in self.by_address:
                    call(self.by_address[arg])
            elif op == dm.OP_BZ:
                guards.append((pop(), arg))
            elif op == dm.OP_B:
                following = self.ops[i + 1][0] if i + 1 < len(self.ops) else end
                if guards and guards[-1][1] == following:
                    condition, _ = guards.pop()
                    guards.append((f"!{condition}", arg))
            elif op == dm.OP_RSR:
                if symbol["kind"] == dm.T_FUNC and symbol["flags"] & F_RETURN and stack:
                    emit("return", pop())
                stack.clear()
        return out


def fields(records):
    """Assignments an instance makes to its own class fields, as a dict."""
    found = {}
    for r in records:
        if "set" in r and " = " in r["set"] and "." in r["set"].split(" = ")[0]:
            key, value = r["set"].split(" = ", 1)
            found[key.split(".", 1)[1]] = value
    return found


def unquote(text):
    return json.loads(text) if text and text.startswith('"') else text


def main():
    program = Program(pathlib.Path(sys.argv[1]).read_bytes())
    symbols, out = program.symbols, pathlib.Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    by_name = {s["name"]: s for s in symbols}
    dialogues, items, npcs, used = [], {}, {}, set()

    def body(name, seen):
        s = by_name.get(name)
        if s is None or s["kind"] != dm.T_FUNC or not s["address"] or name in seen:
            return None
        seen.add(name)
        used.add(name)
        records = program.run(s)
        branches = {}
        for r in records:  # a menu choice runs another function: keep the whole tree with its dialogue
            if r.get("do", "").startswith("INFO_ADDCHOICE("):
                target = r["do"].rstrip(")").rsplit(", ", 1)[-1]
                sub = body(target, seen)
                if sub:
                    branches[target] = sub
        return {"effects": records, "choices": branches} if branches else {"effects": records}

    for s in symbols:
        if s["kind"] != dm.T_INSTANCE or not s["address"] or s["address"] <= 0:
            continue
        root = dm.root_class(symbols, s)
        if root == "C_INFO":
            f = fields(program.run(s))
            dialogues.append({"id": s["name"], "npc": f.get("NPC"), "nr": f.get("NR"), "important": f.get("IMPORTANT") == "1",
                              "permanent": f.get("PERMANENT") == "1", "description": unquote(f.get("DESCRIPTION")),
                              "condition": body(f.get("CONDITION"), set()), "information": body(f.get("INFORMATION"), set())})
        elif root == "C_ITEM":
            f = fields(program.run(s))
            items[s["name"]] = {k.lower(): unquote(f.get(k)) for k in ("NAME", "VALUE", "ON_STATE[0]", "MAINFLAG") if k in f}
        elif root == "C_NPC":
            f = fields(program.run(s))
            npcs[s["name"]] = {k.lower(): unquote(f.get(k)) for k in ("NAME", "LEVEL", "GUILD") if k in f}
    # An item's value is usually a constant (VALUE_NUGGET): its number, so a checker can price a story's items.
    constants = {s["name"]: s["ints"][0] for s in symbols if s["kind"] == dm.T_INT and s.get("ints")}
    for item in items.values():
        value = item.get("value")
        if isinstance(value, str):
            item["gold"] = int(value) if value.lstrip("-").isdigit() else constants.get(value)
    for npc in npcs.values():   # how strong someone is, so a checker knows whom a hero cannot knock down
        level = npc.get("level")
        if isinstance(level, str):
            npc["level"] = int(level) if level.lstrip("-").isdigit() else constants.get(level)
    functions = {s["name"]: program.run(s) for s in symbols
                 if s["kind"] == dm.T_FUNC and s["address"] and s["address"] > 0 and not s["flags"] & 8 and s["name"] not in used
                 and "." not in s["name"]}
    for name, data in (("dialogues", dialogues), ("functions", functions), ("items", items), ("npcs", npcs)):
        (out / f"{name}.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(len(dialogues), "dialogues,", len(functions), "other functions,", len(items), "items")


if __name__ == "__main__":
    main()

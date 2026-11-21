#!/usr/bin/env python3
"""Minimal systemd hwdb.bin compiler (for chroots where systemd-hwdb can't run).

Usage: hwdb_build.py [output]   (default /etc/udev/hwdb.bin)
"""
import os, struct, sys

DIRS = ["/etc/udev/hwdb.d", "/usr/lib/udev/hwdb.d", "/lib/udev/hwdb.d"]
OUT = sys.argv[1] if len(sys.argv) > 1 else "/etc/udev/hwdb.bin"

HDR = struct.Struct("<8s9Q")      # trie_header_f (80 bytes)
NODE = struct.Struct("<QB7xQ")    # trie_node_f (24)
CHILD = struct.Struct("<B7xQ")    # trie_child_entry_f (16)
VAL = struct.Struct("<QQQIHH")    # trie_value_entry2_f (32)


class Node:
    __slots__ = ("prefix", "children", "values")

    def __init__(self, prefix=""):
        self.prefix = prefix
        self.children = {}
        self.values = {}


def insert(root, search, key, val):
    node, i = root, 0
    while True:
        pre = node.prefix
        p = 0
        while p < len(pre):
            if i + p < len(search) and pre[p] == search[i + p]:
                p += 1
                continue
            # split node at p
            child = Node(pre[p + 1:])
            child.children, child.values = node.children, node.values
            node.prefix = pre[:p]
            node.children = {pre[p]: child}
            node.values = {}
            break
        i += p
        if i == len(search):
            node.values[key] = val
            return
        c = search[i]
        nxt = node.children.get(c)
        if nxt is None:
            new = Node(search[i + 1:])
            new.values[key] = val
            node.children[c] = new
            return
        node, i = nxt, i + 1


def collect_files():
    files = {}
    for d in reversed(DIRS):          # /etc wins on same basename
        if os.path.isdir(d):
            for f in os.listdir(d):
                if f.endswith(".hwdb"):
                    files[f] = os.path.join(d, f)
    return [files[k] for k in sorted(files)]


def main():
    root = Node()
    count = 0
    for prio, path in enumerate(collect_files(), 1):
        matches, in_props = [], False
        with open(path, encoding="utf-8", errors="replace") as fh:
            for lineno, raw in enumerate(fh, 1):
                line = raw.rstrip("\r\n")
                if line.startswith("#"):
                    continue
                if not line.strip():
                    matches, in_props = [], False
                    continue
                if line[0] in " \t":
                    if not matches or "=" not in line:
                        continue
                    k, v = line.strip().split("=", 1)
                    in_props = True
                    for m in matches:
                        insert(root, m, " " + k, (v, path, lineno, prio))
                        count += 1
                else:
                    if in_props:      # new record without blank line
                        matches, in_props = [], False
                    matches.append(line.rstrip())

    # string table (dedup)
    strings = bytearray(b"\0")
    soff = {}

    def s(x):
        if x not in soff:
            soff[x] = len(strings)
            strings.extend(x.encode() + b"\0")
        return soff[x]

    # layout nodes (DFS, root first)
    order, stack = [], [root]
    while stack:
        n = stack.pop()
        order.append(n)
        stack.extend(n.children[c] for c in sorted(n.children, key=ord, reverse=True))
    noff, pos = {}, HDR.size
    for n in order:
        noff[id(n)] = pos
        pos += NODE.size + CHILD.size * len(n.children) + VAL.size * len(n.values)
    nodes_len = pos - HDR.size
    sbase = pos

    body = bytearray()
    for n in order:
        body += NODE.pack(sbase + s(n.prefix), len(n.children), len(n.values))
        for c in sorted(n.children, key=ord):
            body += CHILD.pack(ord(c), noff[id(n.children[c])])
        for k in sorted(n.values):
            v, fn, ln, pr = n.values[k]
            body += VAL.pack(sbase + s(k), sbase + s(v), sbase + s(fn), ln, pr, 0)

    total = HDR.size + len(body) + len(strings)
    hdr = HDR.pack(b"KSLPHHRH", 257, total, HDR.size, NODE.size, CHILD.size,
                   VAL.size, HDR.size, nodes_len, len(strings))
    tmp = OUT + ".tmp"
    with open(tmp, "wb") as fh:
        fh.write(hdr + body + strings)
    os.replace(tmp, OUT)
    print(f"wrote {OUT}: {count} properties, {len(order)} nodes, {total} bytes")


if __name__ == "__main__":
    main()

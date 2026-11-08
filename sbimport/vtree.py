"""Minimal reader/writer for JUCE ValueTree binary streams (ValueTree::writeToStream)."""
import struct

MARK_INT, MARK_TRUE, MARK_FALSE, MARK_DOUBLE, MARK_STRING, MARK_INT64 = 1, 2, 3, 4, 5, 6


class Tree:
    def __init__(self, type_, props=None, children=None):
        self.type = type_
        self.props = props if props is not None else []  # list of (name, (marker, payload bytes))
        self.children = children if children is not None else []

    def get(self, name):
        for k, v in self.props:
            if k == name:
                return decode_var(v)
        return None

    def set_string(self, name, value):
        var = (MARK_STRING, value.encode() + b'\x00')
        for i, (k, _) in enumerate(self.props):
            if k == name:
                self.props[i] = (k, var)
                return
        self.props.append((name, var))

    def set_int64(self, name, value):
        var = (MARK_INT64, struct.pack('<q', value))
        for i, (k, _) in enumerate(self.props):
            if k == name:
                self.props[i] = (k, var)
                return
        self.props.append((name, var))

    def remove(self, name):
        self.props = [(k, v) for k, v in self.props if k != name]


def decode_var(var):
    marker, data = var
    if marker == MARK_INT:
        return struct.unpack('<i', data)[0]
    if marker == MARK_TRUE:
        return True
    if marker == MARK_FALSE:
        return False
    if marker == MARK_DOUBLE:
        return struct.unpack('<d', data)[0]
    if marker == MARK_STRING:
        return data.rstrip(b'\x00').decode()
    if marker == MARK_INT64:
        return struct.unpack('<q', data)[0]
    return data


class Reader:
    def __init__(self, buf):
        self.buf, self.pos = buf, 0

    def cstring(self):
        end = self.buf.index(b'\x00', self.pos)
        s = self.buf[self.pos:end].decode()
        self.pos = end + 1
        return s

    def cint(self):
        n = self.buf[self.pos]
        self.pos += 1
        neg = bool(n & 0x80)
        n &= 0x7f
        v = int.from_bytes(self.buf[self.pos:self.pos + n], 'little')
        self.pos += n
        return -v if neg else v

    def var(self):
        size = self.cint()
        if size == 0:
            return (None, b'')
        marker = self.buf[self.pos]
        data = self.buf[self.pos + 1:self.pos + size]
        self.pos += size
        return (marker, bytes(data))

    def tree(self):
        t = Tree(self.cstring())
        for _ in range(self.cint()):
            name = self.cstring()
            t.props.append((name, self.var()))
        for _ in range(self.cint()):
            t.children.append(self.tree())
        return t


def cint_bytes(v):
    neg = v < 0
    v = abs(v)
    raw = v.to_bytes(max(1, (v.bit_length() + 7) // 8), 'little') if v else b''
    return bytes([len(raw) | (0x80 if neg else 0)]) + raw


def write_tree(t):
    out = bytearray(t.type.encode() + b'\x00')
    out += cint_bytes(len(t.props))
    for name, (marker, data) in t.props:
        out += name.encode() + b'\x00'
        if marker is None:
            out += cint_bytes(0)
        else:
            out += cint_bytes(len(data) + 1) + bytes([marker]) + data
    out += cint_bytes(len(t.children))
    for c in t.children:
        out += write_tree(c)
    return bytes(out)


def parse(buf):
    r = Reader(buf)
    t = r.tree()
    return t, buf[r.pos:]

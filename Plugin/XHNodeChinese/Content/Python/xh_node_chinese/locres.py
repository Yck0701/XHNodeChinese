"""Read UE locres v0-v3; write documented compact v1 without hashed text keys.

The binary layout follows UE's TextLocalizationResource.cpp. No original plugin
code or dictionary is used. Hashes of source text are preserved from the engine.
"""
import io
import struct
from collections import defaultdict
from pathlib import Path

MAGIC = struct.pack('<4I', 0x7574140E, 0xFC034A67, 0x9D90154A, 0x1B7F37C3)
META_MAGIC = struct.pack('<4I', 0xA14CEE4F, 0x83554868, 0xBD464C6C, 0x7C50DA70)


class Reader:
    def __init__(self, data):
        self.stream = io.BytesIO(data)
        self.size = len(data)

    def take(self, size):
        if size < 0 or size > self.size:
            raise ValueError('Invalid locres length')
        value = self.stream.read(size)
        if len(value) != size:
            raise ValueError('Truncated locres')
        return value

    def number(self, fmt):
        return struct.unpack('<' + fmt, self.take(struct.calcsize('<' + fmt)))[0]

    def count(self):
        value = self.number('I')
        if value > self.size:
            raise ValueError('Invalid locres count')
        return value

    def string(self):
        length = self.number('i')
        if not length:
            return ''
        data = self.take(abs(length) * (2 if length < 0 else 1))
        suffix = b'\0\0' if length < 0 else b'\0'
        if not data.endswith(suffix):
            raise ValueError('Unterminated locres string')
        return data[:-len(suffix)].decode('utf-16-le' if length < 0 else 'utf-8')


def read(path):
    reader = Reader(Path(path).read_bytes())
    modern = reader.size >= 17 and reader.take(16) == MAGIC
    if modern:
        version = reader.number('B')
    else:
        version = 0
        reader.stream.seek(0)
    if version > 3:
        raise ValueError(f'Unsupported locres version: {version}')
    strings = []
    if version >= 1:
        offset = reader.number('q')
        if not 0 <= offset < reader.size:
            raise ValueError('Invalid locres string-table offset')
        position = reader.stream.tell()
        reader.stream.seek(offset)
        for _ in range(reader.count()):
            strings.append(reader.string())
            if version >= 2:
                reader.number('i')
        reader.stream.seek(position)
    if version >= 2:
        reader.count()  # Total entry count, only an allocation hint in UE.

    def key():
        if version >= 2:
            reader.number('I')  # Both optimized versions store a 32-bit hash.
        return reader.string()

    result = []
    for _ in range(reader.count()):
        namespace = key()
        for _ in range(reader.count()):
            entry_key = key()
            source_hash = reader.number('I')
            if version:
                index = reader.number('i')
                if not 0 <= index < len(strings):
                    raise ValueError('Invalid locres string index')
                text = strings[index]
            else:
                text = reader.string()
            result.append((namespace, entry_key, source_hash, text))
    return result


def pack_string(value):
    if '\0' in value:
        raise ValueError('NUL is not allowed in localization text')
    try:
        raw = value.encode('ascii') + b'\0'
        return struct.pack('<i', len(raw)) + raw
    except UnicodeEncodeError:
        raw = value.encode('utf-16-le') + b'\0\0'
        return struct.pack('<i', -(len(raw) // 2)) + raw


def encode(entries):
    namespaces = defaultdict(dict)
    for namespace, key, source_hash, text in entries:
        if key in namespaces[namespace]:
            raise ValueError(f'Duplicate localization identity: {namespace}/{key}')
        namespaces[namespace][key] = (source_hash, text)
    strings, indices = [], {}
    body = bytearray(struct.pack('<I', len(namespaces)))
    for namespace in sorted(namespaces):
        values = namespaces[namespace]
        body += pack_string(namespace) + struct.pack('<I', len(values))
        for key in sorted(values):
            source_hash, text = values[key]
            if text not in indices:
                indices[text] = len(strings)
                strings.append(text)
            body += pack_string(key) + struct.pack('<Ii', source_hash, indices[text])
    table = struct.pack('<I', len(strings)) + b''.join(map(pack_string, strings))
    return MAGIC + b'\x01' + struct.pack('<q', 25 + len(body)) + body + table


def metadata(target):
    # Initial locmeta format: native culture and relative native resource path.
    return META_MAGIC + b'\x00' + pack_string('en') + pack_string(f'en/{target}.locres')

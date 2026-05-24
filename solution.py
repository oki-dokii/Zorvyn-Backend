# Input : line 1 = T; then per case: line A = root name, line B = compact JSON.
# Output: per-case blocks joined by a line `---`, ending with one '\n'.

import json
import sys


class ObjectType:
    __slots__ = ('fields', 'total_count')

    def __init__(self):
        self.fields = {}
        self.total_count = 0


class FieldInfo:
    __slots__ = ('present_count', 'primitives', 'object_type', 'array_info')

    def __init__(self):
        self.present_count = 0
        self.primitives = set()
        self.object_type = None
        self.array_info = None


class ArrayInfo:
    __slots__ = ('primitives', 'object_type', 'has_elements')

    def __init__(self):
        self.primitives = set()
        self.object_type = None
        self.has_elements = False


def merge_object(obj_type, d):
    obj_type.total_count += 1
    for key, value in d.items():
        f = obj_type.fields.get(key)
        if f is None:
            f = FieldInfo()
            obj_type.fields[key] = f
        f.present_count += 1
        process_value(f, value)


def process_value(field, value):
    if value is None:
        field.primitives.add('null')
    elif isinstance(value, bool):
        field.primitives.add('boolean')
    elif isinstance(value, (int, float)):
        field.primitives.add('number')
    elif isinstance(value, str):
        field.primitives.add('string')
    elif isinstance(value, dict):
        if field.object_type is None:
            field.object_type = ObjectType()
        merge_object(field.object_type, value)
    elif isinstance(value, list):
        if field.array_info is None:
            field.array_info = ArrayInfo()
        for elem in value:
            field.array_info.has_elements = True
            process_array_element(field.array_info, elem)


def process_array_element(ai, value):
    if value is None:
        ai.primitives.add('null')
    elif isinstance(value, bool):
        ai.primitives.add('boolean')
    elif isinstance(value, (int, float)):
        ai.primitives.add('number')
    elif isinstance(value, str):
        ai.primitives.add('string')
    elif isinstance(value, dict):
        if ai.object_type is None:
            ai.object_type = ObjectType()
        merge_object(ai.object_type, value)


def assign_names(root_obj, root_name):
    used = {root_name}
    name_map = {id(root_obj): root_name}

    def visit(obj):
        for key in sorted(obj.fields.keys()):
            field = obj.fields[key]
            base = key[0].upper() + key[1:]
            children = []
            if field.object_type is not None:
                children.append(field.object_type)
            if field.array_info is not None and field.array_info.object_type is not None:
                children.append(field.array_info.object_type)
            for child in children:
                if id(child) in name_map:
                    continue
                name = base
                n = 2
                while name in used:
                    name = base + str(n)
                    n += 1
                used.add(name)
                name_map[id(child)] = name
                visit(child)

    visit(root_obj)
    return name_map


def array_type_str(ai, name_map):
    elems = list(ai.primitives)
    if ai.object_type is not None:
        elems.append(name_map[id(ai.object_type)])
    if not elems:
        return 'unknown[]'
    elems.sort()
    if len(elems) == 1:
        return elems[0] + '[]'
    return '(' + ' | '.join(elems) + ')[]'


def field_type_str(field, name_map):
    parts = list(field.primitives)
    if field.object_type is not None:
        parts.append(name_map[id(field.object_type)])
    if field.array_info is not None:
        parts.append(array_type_str(field.array_info, name_map))
    parts.sort()
    return ' | '.join(parts)


def emit_interface(obj, name, name_map):
    if not obj.fields:
        return 'export interface ' + name + ' {}'
    lines = ['export interface ' + name + ' {']
    for key in sorted(obj.fields.keys()):
        field = obj.fields[key]
        opt = '?' if field.present_count < obj.total_count else ''
        t = field_type_str(field, name_map)
        lines.append('  ' + key + opt + ': ' + t + ';')
    lines.append('}')
    return '\n'.join(lines)


def solve(root_name, json_text):
    data = json.loads(json_text)
    root = ObjectType()
    for d in data:
        merge_object(root, d)
    name_map = assign_names(root, root_name)

    name_to_obj = {}

    def collect(obj):
        if id(obj) not in name_map:
            return
        name = name_map[id(obj)]
        if name in name_to_obj:
            return
        name_to_obj[name] = obj
        for _, f in obj.fields.items():
            if f.object_type is not None:
                collect(f.object_type)
            if f.array_info is not None and f.array_info.object_type is not None:
                collect(f.array_info.object_type)

    collect(root)
    blocks = [emit_interface(name_to_obj[n], n, name_map) for n in sorted(name_to_obj.keys())]
    return '\n\n'.join(blocks)


def main():
    lines = sys.stdin.read().split('\n')
    t = int(lines[0])

    blocks = []
    for i in range(t):
        root_name = lines[1 + 2 * i].strip()
        json_text = lines[2 + 2 * i]
        blocks.append(solve(root_name, json_text))

    sys.stdout.write('\n---\n'.join(blocks) + '\n')


if __name__ == '__main__':
    main()

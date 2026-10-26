"""AD 技能的 MCP 工具定义：每个工具对应 native_ad.py 的一个子命令。"""

SCRIPT = 'native_ad.py'


def _schema(properties, required=()):
    return {'type': 'object', 'properties': properties, 'required': list(required)}


PATH = {'type': 'string', 'description': '文件或目录路径（相对路径按 MCP 服务器的工作目录解析）'}
PLAN = {'type': 'string', 'description': '建模计划 JSON 文件路径，或直接写 JSON 文本'}


def _optional(arguments, flag, key):
    return [flag, str(arguments[key])] if arguments.get(key) else []


TOOLS = [
    {
        'name': 'ad_env',
        'description': 'Report OS, Python, Pillow and whether Altium Designer is available on this machine.',
        'schema': _schema({}),
        'args': lambda a, m: ['env'],
    },
    {
        'name': 'ad_check',
        'description': 'Deterministic layout check of an AD plan before any native step: grid, dangling wires, '
        'floating labels, implicit shorts, predicted netlist vs pin_map, text overlap/text over lines, '
        'wires through parts, sheet density, value notation. Optional draft PNG preview.',
        'schema': _schema({'plan': PLAN, 'preview': PATH}, ['plan']),
        'args': lambda a, m: ['check', m(a['plan']), *_optional(a, '--preview', 'preview')],
    },
    {
        'name': 'ad_create',
        'description': 'Write an editable SchDoc and PrjPcb from a plan (any OS, byte-identical output). '
        'Refuses to write when the layout check has errors.',
        'schema': _schema({'plan': PLAN, 'folder': PATH}, ['plan', 'folder']),
        'args': lambda a, m: ['create', m(a['plan']), a['folder']],
    },
    {
        'name': 'ad_import',
        'description': 'Import an existing SchDoc (the current drawing) into an editable plan JSON. Parts with '
        'library graphics are listed as unsupported; set allow_partial to write the plan anyway.',
        'schema': _schema(
            {'schematic': PATH, 'plan': PATH, 'allow_partial': {'type': 'boolean'}}, ['schematic', 'plan']
        ),
        'args': lambda a, m: [
            'import',
            a['schematic'],
            a['plan'],
            *(['--allow-partial'] if a.get('allow_partial') else []),
        ],
    },
    {
        'name': 'ad_edit',
        'description': 'Apply edit operations to a plan and re-check it. Operations: move {ref,dx,dy|to}, '
        'set_value {ref,value}, move_text {ref,field:designator|comment,at}, rename {ref,to}, add_part, '
        'remove_part, add_wire {points}, remove_wire {index|touching}, add_label, remove_label, '
        'add_power_port, remove_power_port, set_canvas, shift_all, fit_canvas {margin}. Wires attached to '
        'moved pins are re-routed orthogonally.',
        'schema': _schema(
            {
                'plan': PLAN,
                'operations': {'type': 'string', 'description': '操作数组的 JSON 文本或 JSON 文件路径'},
                'output': PATH,
            },
            ['plan', 'operations', 'output'],
        ),
        'args': lambda a, m: ['edit', m(a['plan']), m(a['operations']), a['output']],
    },
    {
        'name': 'ad_render',
        'description': 'Portable render of a SchDoc or plan to PNG/SVG that closely matches the native AD export '
        '(no Altium needed). A preview for debugging, not a native export.',
        'schema': _schema({'source': PATH, 'target': PATH, 'scale': {'type': 'number'}}, ['source', 'target']),
        'args': lambda a, m: ['render', m(a['source']), a['target'], *_optional(a, '--scale', 'scale')],
    },
    {
        'name': 'ad_screenshot',
        'description': 'Screenshot the drawing: on Windows with AD, open AD and capture its window; otherwise '
        'fall back to the portable render.',
        'schema': _schema({'schematic': PATH, 'target': PATH}, ['schematic', 'target']),
        'args': lambda a, m: ['screenshot', a['schematic'], a['target']],
    },
    {
        'name': 'ad_verify',
        'description': 'Windows + AD: compile a copy of the project natively and export the pin-level netlist; '
        'compare with expected.json when given.',
        'schema': _schema({'project': PATH, 'folder': PATH, 'expected': PATH}, ['project', 'folder']),
        'args': lambda a, m: ['verify', a['project'], a['folder'], *_optional(a, '--expected', 'expected')],
    },
    {
        'name': 'ad_export',
        'description': 'Windows + AD: native EMF/PNG export with a text overlap/clipping/text-over-line review.',
        'schema': _schema({'schematic': PATH, 'folder': PATH}, ['schematic', 'folder']),
        'args': lambda a, m: ['export', a['schematic'], a['folder']],
    },
    {
        'name': 'ad_deliver',
        'description': 'Build the customer folder (project and drawings only, no zip) and a separate archive '
        'folder for scripts, plans and reports, with a SHA-256 manifest.',
        'schema': _schema(
            {
                'work': PATH,
                'output': PATH,
                'name': {'type': 'string'},
                'include': {'type': 'array', 'items': {'type': 'string'}},
            },
            ['work', 'output'],
        ),
        'args': lambda a, m: [
            'deliver',
            a['work'],
            a['output'],
            *_optional(a, '--name', 'name'),
            *[x for pattern in a.get('include', []) for x in ('--include', pattern)],
        ],
    },
]

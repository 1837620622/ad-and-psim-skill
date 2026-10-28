"""PSIM 技能的 MCP 工具定义：每个工具对应 native_psim.py 或 analyze_waveform.py 的一个命令。"""

import json

SCRIPT = 'native_psim.py'


def _schema(properties, required=()):
    return {'type': 'object', 'properties': properties, 'required': list(required)}


PATH = {'type': 'string', 'description': '文件或目录路径（相对路径按 MCP 服务器的工作目录解析）'}
PLAN = {'type': 'string', 'description': '建模计划 JSON 文件路径，或直接写 JSON 文本'}
RENDER_OPTIONS = {
    'renderer': {'type': 'string', 'enum': ['auto', 'gdi', 'resvg', 'pillow']},
    'font_files': {'type': 'array', 'items': {'type': 'string'}},
    'font_dirs': {'type': 'array', 'items': {'type': 'string'}},
    'no_system_fonts': {'type': 'boolean'},
}


def _optional(arguments, flag, key):
    return [flag, str(arguments[key])] if arguments.get(key) not in (None, '') else []


def _repeat(arguments, flag, key):
    """重复参数：接受列表、JSON 数组文本或单个字符串，避免把字符串逐字符展开。"""
    value = arguments.get(key)
    if isinstance(value, str):
        value = json.loads(value) if value.lstrip().startswith('[') else [value]
    return [v for item in value or [] for v in (flag, str(item))]


def _render_options(arguments):
    return [
        *_optional(arguments, '--renderer', 'renderer'),
        *_repeat(arguments, '--font-file', 'font_files'),
        *_repeat(arguments, '--font-dir', 'font_dirs'),
        *(['--no-system-fonts'] if arguments.get('no_system_fonts') else []),
    ]


def _waveform(a, m):
    args = [a['csv']]
    for key in (
        'pin',
        'pout',
        'vin',
        'iin',
        'vout',
        'iout',
        'gate',
        'start',
        'end',
        'fundamental_hz',
        'cycles',
        'threshold',
    ):
        args += _optional(a, '--' + key.replace('_', '-'), key)
    for signal in a.get('signals', []):
        args += ['--signal', signal]
    if a.get('steady'):
        args.append('--steady')
    return args


TOOLS = [
    {
        'name': 'psim_handoff',
        'description': 'Prepare an offline Windows execution job from a plan on Mac/Linux/Windows. '
        'Windows run.bat creates, simulates and exports through the installed PSIM, preserving original data.',
        'script': 'native_job.py',
        'schema': _schema(
            {
                'plan': PLAN,
                'folder': PATH,
                'name': {'type': 'string'},
                'include': {'type': 'array', 'items': {'type': 'string'}},
            },
            ['plan', 'folder'],
        ),
        'args': lambda a, m: [
            'prepare',
            'psim',
            m(a['plan']),
            a['folder'],
            *_optional(a, '--name', 'name'),
            *_repeat(a, '--include', 'include'),
        ],
    },
    {
        'name': 'psim_receive',
        'description': 'Verify and receive returned Windows results against the original job. '
        'Copies the native PNG, SMV and CSV unchanged. Refuses failed or modified results.',
        'script': 'native_job.py',
        'schema': _schema({'job': PATH, 'returned': PATH, 'output': PATH}, ['job', 'returned', 'output']),
        'args': lambda a, m: ['receive', a['job'], a['returned'], a['output']],
    },
    {
        'name': 'psim_compare',
        'description': 'Compare file SHA-256 hashes, or CSV signals on the original time grids. '
        'Reports byte identity, numerical equality or tolerance agreement separately. Does not run a solver.',
        'script': 'compare_results.py',
        'schema': _schema(
            {
                'reference': PATH,
                'candidate': PATH,
                'waveforms': {'type': 'boolean'},
                'signals': {'type': 'array', 'items': {'type': 'string'}, 'description': 'CSV 列名；默认比较全部列'},
                'time': {'type': 'string', 'description': '时间列名，默认 Time'},
                'atol': {'type': 'number'},
                'rtol': {'type': 'number'},
                'time_atol': {'type': 'number'},
            },
            ['reference', 'candidate'],
        ),
        'args': lambda a, m: [
            a['reference'],
            a['candidate'],
            *(['--waveforms'] if a.get('waveforms') else []),
            *_repeat(a, '--signal', 'signals'),
            *_optional(a, '--time', 'time'),
            *_optional(a, '--atol', 'atol'),
            *_optional(a, '--rtol', 'rtol'),
            *_optional(a, '--time-atol', 'time_atol'),
        ],
    },
    {
        'name': 'psim_env',
        'description': 'Report OS, Python, Pillow and whether PSIM with its Python API is available.',
        'schema': _schema({}),
        'args': lambda a, m: ['env'],
    },
    {
        'name': 'psim_check',
        'description': 'Layout check of a PSIM plan: orthogonal wires, grid, text overlap, text on symbols or '
        'wires, wires through symbols, simulation-control placement, font size and value notation.',
        'schema': _schema({'plan': PLAN}, ['plan']),
        'args': lambda a, m: ['check', m(a['plan'])],
    },
    {
        'name': 'psim_preflight',
        'description': 'Any OS, no PSIM needed: predict the native result before going to Windows. Runs the layout '
        'check with native text positions, renders a Windows-look preview and pre-simulates linear circuits. '
        'ready_for_windows=true means no known blocker remains.',
        'schema': _schema({'plan': PLAN, 'folder': PATH}, ['plan', 'folder']),
        'args': lambda a, m: ['preflight', m(a['plan']), a['folder']],
    },
    {
        'name': 'psim_plan_edit',
        'description': 'Apply edit operations to a PSIM plan and re-check it. Operations: move {name|type, '
        'dx,dy|to} (wire ends on its ports follow and are re-squared around symbols), set {name,field,value}, '
        'move_text {name,field,dx,dy|area}, add_element, remove_element, add_wire {from,to}, remove_wire {at}, '
        'shift_all {dx,dy}, place_text {names?} (re-places labels that overlap text, symbols or wires, using '
        'the native text rule).',
        'schema': _schema(
            {
                'plan': PLAN,
                'operations': {'type': 'string', 'description': '操作数组的 JSON 文本或 JSON 文件路径'},
                'output': PATH,
            },
            ['plan', 'operations', 'output'],
        ),
        'args': lambda a, m: ['plan-edit', m(a['plan']), m(a['operations']), a['output']],
    },
    {
        'name': 'psim_render',
        'description': 'Render a PSIM plan without PSIM. PNG defaults to the Windows-look renderer (gdi) with the '
        'native export scale, margins and text placement. Still a preview, not a native export.',
        'schema': _schema(
            {'plan': PLAN, 'target': PATH, 'scale': {'type': 'number'}, **RENDER_OPTIONS}, ['plan', 'target']
        ),
        'args': lambda a, m: [
            'render',
            m(a['plan']),
            a['target'],
            *_optional(a, '--scale', 'scale'),
            *_render_options(a),
        ],
    },
    {
        'name': 'psim_presim',
        'description': 'Any OS: offline pre-simulation of a linear plan (R, L, C, VDC, VSIN, probes) with the same '
        'method class as PSIM (nodal analysis, fixed-step trapezoidal). Writes a CSV and step/duration findings. '
        'Not a PSIM result; refuses switches and controls.',
        'schema': _schema({'plan': PLAN, 'csv': PATH}, ['plan', 'csv']),
        'args': lambda a, m: ['presim', m(a['plan']), a['csv']],
    },
    {
        'name': 'psim_package',
        'description': 'Any OS: build a Windows kit (plan, tools, build.bat). On a Windows PC with PSIM, '
        'double-clicking build.bat makes PSIM write the native psimsch, solve it and export the drawing.',
        'schema': _schema({'plan': PLAN, 'folder': PATH, 'name': {'type': 'string'}}, ['plan', 'folder']),
        'args': lambda a, m: ['package', m(a['plan']), a['folder'], *_optional(a, '--name', 'name')],
    },
    {
        'name': 'psim_screenshot',
        'description': 'Screenshot: on Windows with PSIM, open the psimsch in PSIM and capture the window; '
        'otherwise render the plan JSON portably.',
        'schema': _schema({'source': PATH, 'target': PATH}, ['source', 'target']),
        'args': lambda a, m: ['screenshot', a['source'], a['target']],
    },
    {
        'name': 'psim_create',
        'description': 'Windows + PSIM: create the native psimsch from a plan through the PSIM API.',
        'schema': _schema({'plan': PLAN, 'target': PATH}, ['plan', 'target']),
        'args': lambda a, m: ['create', m(a['plan']), a['target']],
    },
    {
        'name': 'psim_inspect',
        'description': 'Windows + PSIM: list element types, names and parameters of a native psimsch.',
        'schema': _schema({'source': PATH}, ['source']),
        'args': lambda a, m: ['inspect', a['source']],
    },
    {
        'name': 'psim_edit',
        'description': 'Windows + PSIM: change parameters of a native psimsch and save a copy. changes: '
        '[{"type":"R","name":"R1","parameters":{"Resistance":"200"}}].',
        'schema': _schema(
            {'source': PATH, 'changes': {'type': 'string', 'description': 'JSON 文本或文件路径'}, 'target': PATH},
            ['source', 'changes', 'target'],
        ),
        'args': lambda a, m: ['edit', a['source'], m(a['changes']), a['target']],
    },
    {
        'name': 'psim_simulate',
        'description': 'Windows + PSIM: run the native solver, save result.smv and native.csv.',
        'schema': _schema(
            {'source': PATH, 'folder': PATH, 'parameters': {'type': 'string', 'description': '可选的求解参数 JSON'}},
            ['source', 'folder'],
        ),
        'args': lambda a, m: [
            'simulate',
            a['source'],
            a['folder'],
            *(['--parameters', m(a['parameters'])] if a.get('parameters') else []),
        ],
    },
    {
        'name': 'psim_export',
        'description': 'Windows + PSIM: native EMF/PNG export with a text overlap/clipping/text-over-line review.',
        'schema': _schema(
            {'source': PATH, 'target': {'type': 'string', 'description': '输出 .emf 路径'}}, ['source', 'target']
        ),
        'args': lambda a, m: ['export', a['source'], a['target']],
    },
    {
        'name': 'psim_measure',
        'description': 'Time-weighted measurements from a native CSV: mean, RMS, peak-to-peak, power, '
        'efficiency only when steady is asserted, gate frequency, output sampling interval.',
        'schema': _schema(
            {
                'csv': PATH,
                'signals': {'type': 'array', 'items': {'type': 'string'}},
                'pin': {'type': 'string'},
                'pout': {'type': 'string'},
                'vin': {'type': 'string'},
                'iin': {'type': 'string'},
                'vout': {'type': 'string'},
                'iout': {'type': 'string'},
                'gate': {'type': 'string'},
                'start': {'type': 'number'},
                'end': {'type': 'number'},
                'fundamental_hz': {'type': 'number'},
                'cycles': {'type': 'integer'},
                'threshold': {'type': 'number'},
                'steady': {'type': 'boolean'},
            },
            ['csv'],
        ),
        'script': 'analyze_waveform.py',
        'args': _waveform,
    },
    {
        'name': 'psim_deliver',
        'description': 'Build the customer folder (psimsch, SMV/CSV results, drawings; no zip) and a separate '
        'archive folder for scripts, plans and reports, with a SHA-256 manifest.',
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
            *_repeat(a, '--include', 'include'),
        ],
    },
]

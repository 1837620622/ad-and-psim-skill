"""MCP 服务器（stdio，JSON-RPC 2.0，只用标准库）：把技能命令提供给支持 MCP 的 Agent。

用法：python mcp_server.py [--with 另一个技能的 scripts 目录 ...]
默认提供同目录 mcp_tools.py 中的工具；加 --with 可在一个服务器里同时提供 AD 与 PSIM 工具。
每次调用都在子进程里运行对应技能的命令行，两项技能的同名模块互不干扰。两项技能各带一份相同的副本。
"""

import argparse
import base64
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

SERVER = {'name': 'ad-and-psim-skill', 'version': '1.2.0'}
PROTOCOLS = ('2025-11-25', '2025-06-18', '2025-03-26', '2024-11-05')
INSTRUCTIONS = (
    'Tools for Altium Designer (ad_*) and PSIM (psim_*). Call *_env first to see what this machine can run. '
    'AD file generation, plan check/edit, render, package, handoff, receive, compare and deliver are portable. '
    'PSIM native creation, verify/export/simulate and window screenshots need Windows with the native software. '
    'Handoff prepares a Windows job; receive verifies and copies native preview pixels and results unchanged. '
    'Fix every layout-check error '
    'before native steps. Renders are previews, not native exports.'
)
IMAGE_KEYS = ('screenshot', 'render', 'preview', 'compact_png', 'png')
# 部分客户端即使服务器没声明也会询问资源和提示词，回复空列表即可。
EMPTY_LISTS = {
    'resources/list': 'resources',
    'resources/templates/list': 'resourceTemplates',
    'prompts/list': 'prompts',
}
MAX_IMAGE_BYTES = 4 << 20


def load_tools(directory):
    directory = Path(directory).resolve()
    path = directory / 'mcp_tools.py'
    spec = importlib.util.spec_from_file_location(f'mcp_tools_{abs(hash(str(directory)))}', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return {tool['name']: dict(tool, script=directory / tool.get('script', module.SCRIPT)) for tool in module.TOOLS}


class Server:
    def __init__(self, directories):
        self.tools = {}
        for directory in directories:
            self.tools.update(load_tools(directory))
        self.timeout = float(os.environ.get('MCP_TOOL_TIMEOUT', '900'))

    def describe(self):
        return [
            {'name': name, 'description': tool['description'], 'inputSchema': tool['schema']}
            for name, tool in self.tools.items()
        ]

    def call(self, name, arguments):
        tool = self.tools.get(name)
        if tool is None:
            raise KeyError(name)
        missing = [k for k in tool['schema'].get('required', []) if k not in arguments]
        if missing:
            return self.result({'error': f'缺少参数：{", ".join(missing)}'}, True)
        with tempfile.TemporaryDirectory(prefix='mcp_') as scratch:
            counter = iter(range(1000))

            def materialize(value, suffix='.json'):
                # 参数可以是文件路径，也可以是 JSON 文本或对象；后两者写成临时文件交给命令行。
                if isinstance(value, str) and value.lstrip()[:1] in ('{', '['):
                    value = json.loads(value)
                if isinstance(value, (dict, list)):
                    path = Path(scratch) / f'input{next(counter)}{suffix}'
                    path.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
                    return str(path)
                return str(value)

            try:
                argv = [sys.executable, str(tool['script']), *tool['args'](arguments, materialize)]
            except ValueError as error:
                return self.result({'error': f'参数不是有效的 JSON：{error}'}, True)
            try:
                done = subprocess.run(
                    argv,
                    capture_output=True,
                    timeout=self.timeout,
                    env=dict(os.environ, PYTHONIOENCODING='utf-8'),
                    check=False,
                )
            except subprocess.TimeoutExpired:
                return self.result({'error': f'命令超过 {self.timeout:.0f} 秒未完成'}, True)
        stdout = done.stdout.decode('utf-8', errors='replace').strip()
        stderr = done.stderr.decode('utf-8', errors='replace').strip()
        payload = {}
        if stdout:
            try:
                payload = json.loads(stdout)
            except json.JSONDecodeError:
                payload = {'output': stdout[-8000:]}
        if not isinstance(payload, dict):
            payload = {'result': payload}
        if stderr:
            try:
                details = json.loads(stderr)
            except json.JSONDecodeError:
                details = None
            payload.update(details if isinstance(details, dict) else {'stderr': stderr[-4000:]})
        return self.result(payload, done.returncode != 0)

    @staticmethod
    def result(payload, failed):
        content = [{'type': 'text', 'text': json.dumps(payload, ensure_ascii=False, indent=2)}]
        if isinstance(payload, dict):
            for key in IMAGE_KEYS:
                value = payload.get(key)
                path = Path(value) if isinstance(value, str) and value.lower().endswith('.png') else None
                if path and path.is_file() and path.stat().st_size <= MAX_IMAGE_BYTES:
                    content.append(
                        {
                            'type': 'image',
                            'mimeType': 'image/png',
                            'data': base64.b64encode(path.read_bytes()).decode('ascii'),
                        }
                    )
                    break
        return {'content': content, 'isError': bool(failed)}

    def handle(self, message):
        if not isinstance(message, dict):
            return {'jsonrpc': '2.0', 'id': None, 'error': {'code': -32600, 'message': '请求必须是 JSON-RPC 对象'}}
        method, ident = message.get('method'), message.get('id')
        if message.get('jsonrpc') != '2.0' or not isinstance(method, str):
            return {'jsonrpc': '2.0', 'id': ident, 'error': {'code': -32600, 'message': '无效的 JSON-RPC 请求'}}
        if ident is None:
            return None  # 通知（如 notifications/initialized）不需要回复
        try:
            if method == 'initialize':
                requested = message.get('params', {}).get('protocolVersion')
                result = {
                    'protocolVersion': requested if requested in PROTOCOLS else PROTOCOLS[0],
                    'capabilities': {'tools': {'listChanged': False}},
                    'serverInfo': SERVER,
                    'instructions': INSTRUCTIONS,
                }
            elif method == 'ping':
                result = {}
            elif method == 'tools/list':
                result = {'tools': self.describe()}
            elif method == 'tools/call':
                params = message.get('params', {})
                result = self.call(params.get('name'), params.get('arguments') or {})
            elif method in EMPTY_LISTS:
                result = {EMPTY_LISTS[method]: []}
            else:
                return {'jsonrpc': '2.0', 'id': ident, 'error': {'code': -32601, 'message': f'未知方法：{method}'}}
        except KeyError as error:
            return {'jsonrpc': '2.0', 'id': ident, 'error': {'code': -32602, 'message': f'未知工具：{error}'}}
        except Exception as error:  # 服务器不能因单次调用失败而退出
            return {'jsonrpc': '2.0', 'id': ident, 'error': {'code': -32603, 'message': str(error)}}
        return {'jsonrpc': '2.0', 'id': ident, 'result': result}

    def serve(self, reader=None, writer=None):
        reader = reader or sys.stdin.buffer
        writer = writer or sys.stdout.buffer
        for raw in reader:
            line = raw.strip()
            if not line:
                continue
            try:
                message = json.loads(line.decode('utf-8'))
            except (UnicodeDecodeError, json.JSONDecodeError):
                reply = {'jsonrpc': '2.0', 'id': None, 'error': {'code': -32700, 'message': 'JSON 解析失败'}}
            else:
                if isinstance(message, list):
                    reply = [r for r in (self.handle(m) for m in message) if r is not None] or None
                else:
                    reply = self.handle(message)
            if reply is not None:
                writer.write(json.dumps(reply, ensure_ascii=False).encode('utf-8') + b'\n')
                writer.flush()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        '--with', dest='extra', action='append', default=[], type=Path, help='再加载一个技能的 scripts 目录'
    )
    parser.add_argument('--list', action='store_true', help='只列出工具后退出')
    args = parser.parse_args()
    server = Server([Path(__file__).resolve().parent, *args.extra])
    if args.list:
        print(json.dumps([t['name'] for t in server.describe()], ensure_ascii=False))
        return 0
    server.serve()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

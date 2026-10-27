"""从 Windows 卸载注册表读取安装位置，兼容安装在自定义盘符的软件。"""

import os
from pathlib import Path
import re


def installed_locations(product):
    if os.name != 'nt':
        return []
    import winreg

    found = set()
    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        for branch in (
            r'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall',
            r'SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall',
        ):
            try:
                with winreg.OpenKey(hive, branch) as root:
                    for index in range(winreg.QueryInfoKey(root)[0]):
                        try:
                            with winreg.OpenKey(root, winreg.EnumKey(root, index)) as entry:
                                name = winreg.QueryValueEx(entry, 'DisplayName')[0]
                                if not re.search(product, str(name), re.IGNORECASE):
                                    continue
                                for field in ('InstallLocation', 'DisplayIcon'):
                                    try:
                                        value = str(winreg.QueryValueEx(entry, field)[0]).strip()
                                    except OSError:
                                        continue
                                    if field == 'DisplayIcon':
                                        match = re.match(r'^"([^"]+)"', value)
                                        value = match.group(1) if match else re.sub(r',-?\d+$', '', value)
                                    if not value:
                                        continue
                                    path = Path(os.path.expandvars(value))
                                    if path.is_file():
                                        found.add(path)
                                        found.update(list(path.parents)[:3])
                                    elif path.is_dir():
                                        found.add(path)
                        except OSError:
                            continue
            except OSError:
                continue
    return sorted(found)

"""将两项技能接入常见 Agent 目录；只建入口，不覆盖已有内容。"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

NAMES=('ad-schematic-layout','psim-simulation-layout')
PROFILES={'common':'.agents/skills','claude':'.claude/skills','zcode':'.zcode/skills'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile',action='append',choices=PROFILES,required=True)
    parser.add_argument('--home',type=Path,default=Path.home())
    parser.add_argument('--check',action='store_true')
    parser.add_argument('--report',type=Path)
    args=parser.parse_args();root=Path(__file__).resolve().parents[1];results=[]
    for profile in dict.fromkeys(args.profile):
        base=args.home.resolve()/PROFILES[profile]
        for name in NAMES:
            source=root/'skills'/name;target=base/name
            record={'profile':profile,'entry':str(target),'source':str(source)}
            try:
                if not (source/'SKILL.md').is_file():raise FileNotFoundError(source/'SKILL.md')
                if os.path.lexists(target):
                    if target.resolve()!=source.resolve():raise FileExistsError('同名目录或链接已存在，已保留')
                elif args.check:raise FileNotFoundError('入口尚未安装')
                else:
                    base.mkdir(parents=True,exist_ok=True)
                    if os.name=='nt':
                        quote=lambda p:"'"+str(p).replace("'","''")+"'"
                        command='New-Item -ItemType Junction -Path '+quote(target)+' -Target '+quote(source)+' | Out-Null'
                        subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',command],check=True,capture_output=True)
                    else:target.symlink_to(source,target_is_directory=True)
                if (target/'SKILL.md').read_bytes()!=(source/'SKILL.md').read_bytes():raise RuntimeError('入口内容不一致')
                record['passed']=True
            except Exception as error:record.update(passed=False,error=str(error))
            results.append(record)
    result={'passed':all(x['passed']for x in results),'entries':results,
            'scope':'文件入口与内容检查；不代表所有 Agent 已进行端到端运行'}
    output=json.dumps(result,ensure_ascii=False,indent=2)
    if args.report:args.report.write_text(output+'\n',encoding='utf-8')
    print(output);return 0 if result['passed']else 1


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    raise SystemExit(main())

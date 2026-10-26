"""创建基础原生图纸，调用 AD 原生脚本验证、出图或执行受控的本地脚本。"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import time

HERE=Path(__file__).resolve().parent
NATIVE=HERE.parent/'references/native'


def build(plan):
    """把建模计划转换为内存中的图纸记录，不写文件；create 与排版预检共用。"""
    from ad_document import Sheet, pin_end
    from tidy_wires import tidy
    if plan.get('units')!='10mil':raise ValueError('坐标单位须明确写为 10mil')
    width,height=plan['canvas']
    if width<=0 or height<=0:raise ValueError('画布尺寸须为正数')
    grid=plan.get('grid',10);font=plan.get('font',1)
    s=Sheet((width,height));seen=set()
    for part in plan.get('parts',[]):
        ref=part.get('ref')
        if not isinstance(ref,str)or not ref or ref in seen:raise ValueError(f'重复或空位号：{ref!r}')
        seen.add(ref);kind=part['kind']
        if kind in('R','C','L','Y'):
            scale=part.get('symbol_scale',.5)
            if scale<=0:raise ValueError('symbol_scale 须为正数')
            x,y=part['at']
            # 文字保持完整字高和行距，不随小符号一起压缩。
            idx=s.passive(ref,part['value'],x,y,vertical=part.get('vertical',False),kind=kind,
                          scale=scale,grid=grid,font=font,
                          des_pos=part.get('designator_at'),comment_pos=part.get('comment_at'))
        elif kind=='component':
            pins=part['pins'];expected=part.get('expected_pin_count')
            if expected is not None and len(pins)!=expected:raise ValueError('引脚总数不符：'+ref)
            if len({str(p['number'])for p in pins})!=len(pins):raise ValueError('引脚编号重复：'+ref)
            directions={'right':0,'up':1,'left':2,'down':3}
            electrical={'input':0,'bidirectional':1,'output':2,'open_collector':3,'passive':4,'power':7}
            idx=s.component(ref,part['value'],part['body'],
                            [(str(p['number']),p.get('name',''),*p['at'],directions[p['direction']],
                              electrical[p.get('electrical','passive')])for p in pins],
                            des_pos=part.get('designator_at'),comment_pos=part.get('comment_at'),
                            pin_length=part.get('pin_length',20),font=font)
        else:raise ValueError('基础生成器不支持此符号；应使用已核实的原生库或本地脚本：'+kind)
        s.pins[ref]={r['DESIGNATOR']:pin_end(r)for r in s.records[idx+1:]
                     if r.get('OWNERINDEX')==str(idx-1)and r.get('RECORD')=='2'}
    def position(value):
        if isinstance(value,str):
            ref,_,num=value.rpartition('.')
            if num not in s.pins.get(ref,{}):raise ValueError(f'引用了不存在的引脚：{value}')
            return s.pins[ref][num]
        return tuple(value)
    for wire in plan.get('wires',[]):s.wire(*[position(p)for p in wire])
    for label in plan.get('labels',[]):s.label(*position(label['at']),label['name'])
    for port in plan.get('power_ports',[]):
        i=s.power(*position(port['at']),port['name'],ground=port.get('ground',False))
        if'orientation'in port:s.records[i]['ORIENTATION']=str(port['orientation'])
    for point in plan.get('junctions',[]):s.junction(position(point))
    if plan.get('border',True):s.rect(20,20,width-20,height-20)
    for text in plan.get('texts',[]):s.text(*text['at'],text['text'],font=text.get('font',font))
    s.records=tidy(s.records)
    return s


def create(plan, folder, allow_layout_errors=False):
    from check_layout import check_records
    folder=Path(folder).resolve()
    name=plan.get('name','Schematic')
    if not re.fullmatch(r'[\w-]+',name):raise ValueError('name 只接受字母、数字、中文、下划线或短横线')
    sch=folder/(name+'.SchDoc');project=sch.with_suffix('.PrjPcb')
    if sch.exists()or project.exists():raise FileExistsError('输出图纸已存在，请使用新的工作目录')
    s=build(plan)
    layout,_,_=check_records(s.records,plan.get('pin_map'),grid=plan.get('grid',10))
    if layout['summary']['errors']and not allow_layout_errors:
        first='; '.join(f"{f['code']}: {f['message']}"for f in layout['findings']if f['severity']=='error')
        raise ValueError(f"排版预检有 {layout['summary']['errors']} 项错误，未写出图纸。先运行 check_layout.py 查看并修正：{first[:600]}")
    folder.mkdir(parents=True,exist_ok=True)
    s.save(sch)
    project.write_text('[Design]\nVersion=1.0\nHierarchyMode=0\n\n[Document1]\nDocumentPath='+sch.name+'\nAnnotationEnabled=1\nAnnotateScope=All\n',encoding='utf-8-sig')
    if'pin_map'in plan:(folder/'expected.json').write_text(json.dumps({'pin_map':plan['pin_map']},ensure_ascii=False,indent=2),encoding='utf-8')
    (folder/'layout-check.json').write_text(json.dumps(layout,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return {'schematic':str(sch),'project':str(project),'parts':len(plan.get('parts',[])),
            'layout_check':dict(layout['summary'],report=str(folder/'layout-check.json')),
            'native_validation_required':True}


def invoke(ad_exe, script, procedure, job, timeout):
    ad_exe=Path(ad_exe).resolve()
    if not ad_exe.is_file():raise FileNotFoundError(ad_exe)
    if not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*',procedure):raise ValueError('过程名无效')
    project=job/'Job.PrjScr'
    project.write_text('[Design]\nVersion=1.0\n[Document1]\nDocumentPath='+script.name+'\n',encoding='ascii')
    argument=f'-RScriptingSystem:RunScript(ProjectName="{project}"|ProcName="{script.name}>{procedure}")'
    # 传入原始 Windows 命令行，保留 AD 自身脚本分派器所需引号。
    subprocess.Popen(f'"{ad_exe}" {argument}',creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),
                     stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    deadline=time.monotonic()+timeout;status=job/'status.txt'
    while time.monotonic()<deadline:
        if status.exists():
            text=status.read_text(encoding='utf-8-sig',errors='replace')
            if re.search(r'(?m)^Failed=',text):raise RuntimeError('AD 原生脚本报告失败：'+text.strip()[-500:])
            if'Complete'in text:return text
        time.sleep(.25)
    raise TimeoutError('AD 未在时限内写出完成状态；检查原生脚本面板，勿把旧输出当成功')


def job_folder():
    job=Path(tempfile.mkdtemp(prefix='ad_native_'))
    if not str(job).isascii():raise ValueError('本机脚本路径需要 ASCII 临时目录，请配置 TMP/TEMP')
    return job


def verify(ad_exe, project, folder, timeout, expected=None):
    from compare_pin_nets import compare,load_pin_map
    project=Path(project).resolve();folder=Path(folder).resolve();folder.mkdir(parents=True,exist_ok=True)
    raw=project.read_bytes()
    try:text=raw.decode('utf-8-sig')
    except UnicodeDecodeError:text=raw.decode('gb18030')
    job=job_folder();stage=job/'source';stage.mkdir()
    paths=[]
    def stage_document(match):
        value=match.group(1).strip();source=(project.parent/value).resolve()
        if not source.is_file():raise FileNotFoundError(source)
        try:relative=source.relative_to(project.parent)
        except ValueError:relative=Path('_external')/hashlib.sha256(str(source).encode('utf-8')).hexdigest()[:12]/source.name
        target=stage/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
        if source.suffix.lower()=='.schdoc':paths.append(target)
        return'DocumentPath='+str(relative)
    staged_text=re.sub(r'(?m)^DocumentPath=([^\r\n]+)',stage_document,text)
    staged_project=stage/project.name;staged_project.write_text(staged_text,encoding='utf-8-sig')
    if not paths:raise ValueError('工程未引用 SchDoc')
    (job/'inputs.txt').write_text('\n'.join(map(str,[staged_project]+paths)),encoding='utf-16')
    script=(NATIVE/'VerifyProject.pas').read_text('ascii')
    for a,b in [('__INPUTS__','inputs.txt'),('__STATUS__','status.txt'),('__MESSAGES__','messages.txt'),('__NETS__','nets.txt')]:
        script=script.replace(a,str(job/b))
    target=job/'Verify.pas';target.write_text(script,encoding='ascii')
    invoke(ad_exe,target,'VerifyProject',job,timeout)
    copied={}
    for name in('status.txt','messages.txt','nets.txt'):
        data=(job/name).read_bytes()
        try:value=data.decode('utf-8-sig')
        except UnicodeDecodeError:value=data.decode('gb18030')
        (folder/name).write_text(value,encoding='utf-8');copied[name]=value
    status=copied['status.txt'];errors=len(re.findall(r'^\[(?:Error|Fatal)\]',status,re.M));warnings=len(re.findall(r'^\[Warning\]',status,re.M))
    result={'job':str(job),'errors':errors,'warnings':warnings,
            'compile_return_true':'DM_Compile_return=True'in status,'cancelled':'Cancelled=True'in status,
            'netlist':str(folder/'nets.txt')}
    if expected:result['topology']=compare(load_pin_map(expected),load_pin_map(folder/'nets.txt'))
    result['passed']=result['compile_return_true']and not result['cancelled']and errors==0 and result.get('topology',{'match':True})['match']
    return result


def text_review(raw):
    """原生 EMF 的文字重叠、越界与压线摘要；只作提示，不能代替逐区审图。"""
    from review_emf_text import review
    try:result=review(raw)
    except (ValueError,struct.error)as error:return {'status':'未能审查：'+str(error)}
    return {'passed':not(result['overlaps']or result['outside_indices']or result['text_line_conflicts'])
            and result['coverage_complete_for_text_records'],
            'text_count':result['text_count'],'overlaps':result['overlaps'][:10],
            'outside':[result['texts'][i]['text']for i in result['outside_indices']][:10],
            'text_line_conflicts':[{k:c[k]for k in('text','box','line_count')}for c in result['text_line_conflicts'][:10]],
            'coverage_complete':result['coverage_complete_for_text_records']}


def export(ad_exe, schematic, folder, timeout, dpi):
    folder=Path(folder).resolve();folder.mkdir(parents=True,exist_ok=True)
    schematic=Path(schematic).resolve();job=job_folder();source=job/'source.SchDoc';shutil.copy2(schematic,source)
    (job/'inputs.txt').write_text(str(source)+'|'+str(job/'native.emf'),encoding='utf-16')
    script=(NATIVE/'ExportSchematic.pas').read_text('ascii').replace('__INPUTS__',str(job/'inputs.txt')).replace('__STATUS__',str(job/'status.txt'))
    target=job/'Export.pas';target.write_text(script,encoding='ascii')
    invoke(ad_exe,target,'ExportSchematic',job,timeout)
    raw=(job/'native.emf').read_bytes();data=bytearray(raw)
    bounds=struct.unpack_from('<4i',data,8);device=struct.unpack_from('<4i',data,72)
    if min(device)<=0:raise RuntimeError('EMF 设备信息无效')
    frame=[round(bounds[i]*device[2+i%2]*100/device[i%2])for i in range(4)]
    struct.pack_into('<4i',data,24,*frame)
    name=schematic.stem;emf=folder/(name+'.emf');emf.write_bytes(data)
    result={'emf':str(emf),'native_original':str(job/'native.emf'),'graphics_unchanged':data[:24]==raw[:24]and data[40:]==raw[40:]}
    result['text_review']=text_review(bytes(data))
    try:
        from PIL import Image
        Image.MAX_IMAGE_PIXELS=None
        with Image.open(emf)as picture:
            picture.load(dpi=dpi);picture=picture.convert('RGB');picture.save(folder/(name+'.png'))
            result['png']=str(folder/(name+'.png'));result['pixel_size']=list(picture.size)
    except ImportError:result['png_status']='需要 Pillow；原生矢量 EMF 已保留'
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ad-exe',type=Path)
    parser.add_argument('--report',type=Path)
    parser.add_argument('--timeout',type=float,default=120)
    sub=parser.add_subparsers(dest='command',required=True)
    item=sub.add_parser('create');item.add_argument('plan',type=Path);item.add_argument('folder',type=Path)
    item.add_argument('--allow-layout-errors',action='store_true',help='仅用于调试：排版预检有错误时仍写出图纸')
    item=sub.add_parser('verify');item.add_argument('project',type=Path);item.add_argument('folder',type=Path);item.add_argument('--expected',type=Path)
    item=sub.add_parser('export');item.add_argument('schematic',type=Path);item.add_argument('folder',type=Path);item.add_argument('--dpi',type=int,default=20)
    item=sub.add_parser('run-script');item.add_argument('script',type=Path);item.add_argument('procedure')
    args=parser.parse_args()
    try:
        if args.timeout<=0:raise ValueError('timeout 须为正数')
        if args.report:
            protected=[getattr(args,k,None)for k in ('plan','project','expected','schematic','script')]
            if args.report.resolve()in[p.resolve()for p in protected if p]:raise ValueError('报告不能覆盖输入')
        if args.command=='create':result=create(json.loads(args.plan.read_text(encoding='utf-8-sig')),args.folder,args.allow_layout_errors)
        else:
            if os.name!='nt'or not args.ad_exe:raise ValueError('此操作需要 Windows 与 --ad-exe')
            if args.command=='verify':result=verify(args.ad_exe,args.project,args.folder,args.timeout,args.expected)
            elif args.command=='export':result=export(args.ad_exe,args.schematic,args.folder,args.timeout,args.dpi)
            else:
                job=job_folder();target=job/'Run.pas'
                source=args.script.read_text(encoding='utf-8-sig')
                if '__STATUS__'not in source:raise ValueError('自定义脚本须以 __STATUS__ 占位指定完成状态文件')
                target.write_text(source.replace('__STATUS__',str(job/'status.txt')),encoding='ascii')
                result={'status':invoke(args.ad_exe,target,args.procedure,job,args.timeout),'job':str(job)}
        value=json.dumps(result,ensure_ascii=False,indent=2)
        if args.report:args.report.write_text(value+'\n',encoding='utf-8')
        print(value);return 1 if result.get('passed')is False else 0
    except Exception as error:
        print(json.dumps({'error':str(error)},ensure_ascii=False),file=sys.stderr);return 1


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8');sys.stderr.reconfigure(encoding='utf-8')
    raise SystemExit(main())

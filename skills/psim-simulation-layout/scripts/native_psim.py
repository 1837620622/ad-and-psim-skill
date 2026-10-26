"""使用本机 PSIM 原生接口创建、修改、绘图与求解电路。"""
import argparse
import csv
import ctypes
from ctypes import wintypes as W
import hashlib
import json
import math
from pathlib import Path
import struct
import sys


def initialize(directory):
    directory=Path(directory).resolve()
    wrapper=directory/'Python/Samples/Psim_Class.py'
    if not wrapper.is_file() or not (directory/'PSIM2.dll').is_file():
        raise ValueError('未找到本机 PSIM 包装器与 PSIM2.dll')
    sys.path.insert(0,str(wrapper.parent))
    from Psim_Class import PSIM
    psim=PSIM(str(directory))
    if not psim or not psim.IsValid():
        raise RuntimeError('PSIM 原生接口初始化失败')
    return psim


def inspect(psim, path):
    sch=psim.PsimFileOpen(str(Path(path).resolve()))
    if not sch or not sch.value:raise RuntimeError('原生模型打开失败')
    try:
        elements=psim.PsimGetElementList(sch,1)
        if elements is None:raise RuntimeError('原生元件枚举失败')
        return [{'type':e.Type,'name':e.Name,'wrapper_index':e.Index,
                 'index_reliable':False,
                 'parameters':{p.Name:str(p.Value)for p in e.Params}}for e in elements]
    finally:sch.free()


def create(psim, plan, target, overwrite=False):
    target=Path(target).resolve()
    if target.suffix.lower()!='.psimsch':raise ValueError('原生模型应使用 .psimsch')
    if target.exists()and not overwrite:raise FileExistsError(target)
    seen=set();elements=plan.get('elements')
    if not isinstance(elements,list)or not elements:raise ValueError('计划须含非空 elements 数组')
    for e in elements:
        kind=e['type'];name=e.get('name','');attrs=e.get('attributes',{})
        if not isinstance(kind,str)or not isinstance(name,str)or not isinstance(attrs,dict):
            raise ValueError('元件的 type、name、attributes 类型错误')
        if kind.upper()not in('WIRE','TEXT','TEXTLINK','GROUND','SIMCONTROL'):
            if not name or name in seen:raise ValueError('元件名称为空或重复：'+name)
            seen.add(name)
        if any('\n'in str(k)or'\n'in str(v)for k,v in attrs.items()):
            raise ValueError('创建参数不接受换行；多行参数文件应使用原生专用接口')
        if kind.upper()=='WIRE':
            a,b,c,d=(float(attrs[k])for k in('X1','Y1','X2','Y2'))
            if a!=c and b!=d:raise ValueError('WIRE 须为正交线段')
    sch=psim.PsimFileNew()
    if not sch or not sch.value:raise RuntimeError('创建原生文档失败')
    try:
        for e in elements:
            index=psim.PsimCreateNewElement(sch,e['type'],e.get('name',''),**e.get('attributes',{}))
            # 此函数返回创建索引，0 是合法索引，-1 才表示失败。
            if index is None or index==-1:raise RuntimeError('原生创建失败：'+str(e))
            for label in e.get('textlinks',[]):
                attrs={'DIRECTION':0,'PAGE':0,'XFLIP':0,'_OPTIONS_':0,
                       'FontName':'Arial','FontSize':-15,'Color':'0',
                       'FontOptions':65936,'FormatFactor':18.325623}
                attrs.update(label)
                if not all(k in attrs for k in ('AREA','FieldName','FieldIndex')):
                    raise ValueError('关联文字须含 AREA、FieldName 和本机核实的 FieldIndex')
                attrs['OWNERINDEX']=index
                if psim.PsimCreateNewElement(sch,'TEXTLINK','',**attrs)==-1:
                    raise RuntimeError('创建原生关联文字失败：'+str(label))
        target.parent.mkdir(parents=True,exist_ok=True)
        if not psim.PsimFileSave(sch,str(target)):raise RuntimeError('原生保存失败')
    finally:sch.free()
    return inspect(psim,target)


def edit(psim, source, changes, target, overwrite=False):
    target=Path(target).resolve();source=Path(source).resolve()
    if target==source:raise ValueError('修改工具保存到新副本；不直接覆盖输入模型')
    if target.exists()and not overwrite:raise FileExistsError(target)
    sch=psim.PsimFileOpen(str(source))
    if not sch or not sch.value:raise RuntimeError('原生模型打开失败')
    try:
        for change in changes:
            matches=[e for e in psim.PsimGetElementList(sch,1)
                     if e.Type==change['type']and e.Name==change['name']]
            if len(matches)!=1:raise ValueError('类型和名称未唯一匹配：'+str(change))
            for field,value in change['parameters'].items():
                # 本机包装器把所有 Index 初始化为 0，使用唯一类型与名称定位。
                if not psim.PsimSetElmValue2(sch,change['type'],change['name'],field,str(value)):
                    raise RuntimeError('原生更新失败：'+field)
        target.parent.mkdir(parents=True,exist_ok=True)
        if not psim.PsimFileSave(sch,str(target)):raise RuntimeError('原生保存失败')
    finally:sch.free()
    return inspect(psim,target)


def simulate(psim, source, folder, parameters):
    source=Path(source).resolve();folder=Path(folder).resolve()
    folder.mkdir(parents=True,exist_ok=True)
    graph_path=folder/'result.smv';csv_path=folder/'native.csv'
    if graph_path.exists()or csv_path.exists():raise FileExistsError('仿真输出已存在，请选择新目录')
    parameters=dict(parameters);parameters['Simview']=0
    result=psim.PsimSimulate(str(source),str(graph_path),**parameters)
    if result is None or result.Result==0:raise RuntimeError(getattr(result,'ErrorMessage','原生求解失败'))
    curves=result.Graph
    if not curves:raise RuntimeError('原生求解没有返回波形')
    names=[str(c.Name)for c in curves];counts=[int(c.Rows)for c in curves]
    if len(set(names))!=len(names)or len(set(counts))!=1 or counts[0]<2:
        raise RuntimeError('波形列名、长度或样本数量无效')
    time_index=next((i for i,n in enumerate(names)if n.casefold()=='time'),None)
    if time_index is None:raise RuntimeError('原生波形缺少 Time 列')
    previous=None
    with csv_path.open('w',newline='',encoding='utf-8-sig')as stream:
        writer=csv.writer(stream);writer.writerow(names)
        for i in range(counts[0]):
            row=[float(c.Values[i])for c in curves]
            if any(not math.isfinite(v)for v in row):raise RuntimeError('原生波形包含非有限值')
            if previous is not None and row[time_index]<=previous:raise RuntimeError('Time 没有严格递增')
            previous=row[time_index];writer.writerow(row)
    if not graph_path.is_file()or not graph_path.stat().st_size:raise RuntimeError('原始 SMV 未写出')
    return {'model_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
            'solver_version':list(psim.get_psim_version()),'parameters':parameters,
            'graph':str(graph_path),'csv':str(csv_path),'columns':names,'samples':counts[0]}


def to_python(psim, source, target):
    target=Path(target).resolve()
    if target.suffix.lower()!='.py' or target.exists():raise ValueError('请选择不存在的 .py 输出路径')
    target.parent.mkdir(parents=True,exist_ok=True)
    if not psim.PsimConvertToPython(str(Path(source).resolve()),str(target)):
        raise RuntimeError('原生转换失败；本机需支持 ConvertToPythonW')
    if not target.is_file() or not target.stat().st_size:raise RuntimeError('转换没有写出文件')
    return {'python':str(target),'execute_status':'仅导出，未执行；运行前检查脚本与输出路径'}


def export(psim, source, target, dpi=120):
    if sys.platform!='win32':raise RuntimeError('此原生绘图入口需要 Windows GDI')
    target=Path(target).resolve();target.parent.mkdir(parents=True,exist_ok=True)
    if target.exists():raise FileExistsError(target)
    sch=psim.PsimFileOpen(str(Path(source).resolve()))
    if not sch or not sch.value:raise RuntimeError('原生模型打开失败')
    user=ctypes.windll.user32;gdi=ctypes.windll.gdi32
    user.CreateWindowExW.argtypes=[W.DWORD,W.LPCWSTR,W.LPCWSTR,W.DWORD,
                                  ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,
                                  W.HWND,W.HMENU,W.HINSTANCE,ctypes.c_void_p]
    user.CreateWindowExW.restype=W.HWND
    user.DestroyWindow.argtypes=[W.HWND];user.DestroyWindow.restype=W.BOOL
    gdi.CreateEnhMetaFileW.argtypes=[W.HDC,W.LPCWSTR,ctypes.c_void_p,W.LPCWSTR];gdi.CreateEnhMetaFileW.restype=W.HDC
    gdi.CloseEnhMetaFile.argtypes=[W.HDC];gdi.CloseEnhMetaFile.restype=W.HANDLE
    gdi.DeleteEnhMetaFile.argtypes=[W.HANDLE];gdi.DeleteEnhMetaFile.restype=W.BOOL
    create_window=psim.psimHandle.CreateSchematicWindow
    create_window.argtypes=[W.HWND,ctypes.c_int];create_window.restype=ctypes.c_int
    draw=psim.psimHandle.ViewSchematicDraw
    draw.argtypes=[ctypes.c_int,W.HDC,ctypes.c_int];draw.restype=ctypes.c_int
    destroy=psim.psimHandle.DestroySchematicWindow
    destroy.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_int];destroy.restype=ctypes.c_int
    host=dc=None;created=False
    try:
        host=user.CreateWindowExW(0,'STATIC','',0x80000000,0,0,800,600,None,None,None,None)
        if not host:raise RuntimeError('原生绘图宿主创建失败')
        if not create_window(host,sch.value):raise RuntimeError('PSIM 绘图视图创建失败')
        created=True
        dc=gdi.CreateEnhMetaFileW(None,str(target),None,'PSIM\0Schematic\0\0')
        if not dc:raise RuntimeError('EMF 上下文创建失败')
        if not draw(sch.value,dc,0):raise RuntimeError('PSIM 原生绘图失败')
    finally:
        if dc:
            meta=gdi.CloseEnhMetaFile(dc)
            if meta:gdi.DeleteEnhMetaFile(meta)
        if created:destroy(None,None,sch.value)
        if host:user.DestroyWindow(host)
        sch.free()
    raw=target.read_bytes()
    if len(raw)<88:raise RuntimeError('原生 EMF 不完整')
    bounds=struct.unpack_from('<4i',raw,8)
    data=bytearray(raw);device=struct.unpack_from('<4i',raw,72)
    if min(device)<=0:raise RuntimeError('EMF 设备信息无效')
    frame=[round(bounds[i]*device[2+i%2]*100/device[i%2])for i in range(4)]
    struct.pack_into('<4i',data,24,*frame)
    target.write_bytes(data)
    result={'emf':str(target),'native_device_bounds':list(bounds),'bytes':len(data),
            'graphics_unchanged':data[:24]==raw[:24] and data[40:]==raw[40:]}
    try:
        from PIL import Image,ImageChops
        with Image.open(target)as picture:
            picture.load(dpi=dpi);picture=picture.convert('RGB')
            full=target.with_suffix('.png');picture.save(full)
            box=ImageChops.difference(picture,Image.new('RGB',picture.size,'white')).getbbox()
            if not box:raise RuntimeError('原生导出为空白')
            margin=max(20,round(dpi/4))
            box=(max(0,box[0]-margin),max(0,box[1]-margin),
                 min(picture.width,box[2]+margin),min(picture.height,box[3]+margin))
            compact=target.with_name(target.stem+'-compact.png');picture.crop(box).save(compact)
            result.update(png=str(full),compact_png=str(compact),pixel_size=list(picture.size),
                          blank_crop_bounds=list(box))
    except ImportError:result['png_status']='需要 Pillow；完整原生 EMF 已保留'
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--psim-dir',required=True,type=Path)
    parser.add_argument('--report',type=Path)
    sub=parser.add_subparsers(dest='command',required=True)
    sub.add_parser('version')
    item=sub.add_parser('inspect');item.add_argument('source',type=Path)
    item=sub.add_parser('to-python');item.add_argument('source',type=Path);item.add_argument('target',type=Path)
    item=sub.add_parser('create');item.add_argument('plan',type=Path);item.add_argument('target',type=Path);item.add_argument('--overwrite',action='store_true')
    item=sub.add_parser('edit');item.add_argument('source',type=Path);item.add_argument('changes',type=Path);item.add_argument('target',type=Path);item.add_argument('--overwrite',action='store_true')
    item=sub.add_parser('simulate');item.add_argument('source',type=Path);item.add_argument('folder',type=Path);item.add_argument('--parameters',type=Path)
    item=sub.add_parser('export');item.add_argument('source',type=Path);item.add_argument('target',type=Path);item.add_argument('--dpi',type=int,default=120)
    args=parser.parse_args();psim=None
    try:
        if args.report:
            protected=[getattr(args,k,None)for k in ('source','plan','changes','parameters','target')]
            if args.report.resolve()in[p.resolve()for p in protected if p]:raise ValueError('报告不能覆盖输入或工程输出')
        psim=initialize(args.psim_dir)
        if args.command=='version':data={'version':list(psim.get_psim_version()),'name':psim.get_psim_version_name()}
        elif args.command=='inspect':data=inspect(psim,args.source)
        elif args.command=='to-python':data=to_python(psim,args.source,args.target)
        elif args.command=='create':data=create(psim,json.loads(args.plan.read_text(encoding='utf-8-sig')),args.target,args.overwrite)
        elif args.command=='edit':data=edit(psim,args.source,json.loads(args.changes.read_text(encoding='utf-8-sig')),args.target,args.overwrite)
        elif args.command=='simulate':data=simulate(psim,args.source,args.folder,json.loads(args.parameters.read_text(encoding='utf-8-sig'))if args.parameters else{})
        else:
            if not 20<=args.dpi<=600:raise ValueError('dpi 须在 20–600 之间')
            data=export(psim,args.source,args.target,args.dpi)
        text=json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False)
        if args.report:args.report.write_text(text+'\n',encoding='utf-8')
        print(text);return 0
    except Exception as error:
        print(json.dumps({'error':str(error)},ensure_ascii=False),file=sys.stderr);return 1
    finally:psim=None


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8');sys.stderr.reconfigure(encoding='utf-8')
    raise SystemExit(main())

"""合并重合的同色同线宽直线，在真实分支点和引脚热端处分段，只在 T 形分支放连接点。"""
from collections import defaultdict
from copy import deepcopy


def tidy(records):
    groups=defaultdict(list)
    segments=[];vertices=set();junctions=set();pins={}
    for row in records:
        if row.get('RECORD')=='2':
            # 引脚从热端指向器件本体；作为一个分支方向参与连接点判断。
            direction=int(row['PINCONGLOMERATE'])&3
            dx,dy=((1,0),(0,1),(-1,0),(0,-1))[direction]
            length=float(row.get('PINLENGTH',0))
            hot=(round(float(row['LOCATION.X'])+dx*length),round(float(row['LOCATION.Y'])+dy*length))
            pins.setdefault(hot,set()).add(('L','D','R','U')[direction])
        if row.get('RECORD')=='29':
            junctions.add((int(row['LOCATION.X']),int(row['LOCATION.Y'])))
        if row.get('RECORD')!='27':continue
        pts=[(int(row[f'X{i}']),int(row[f'Y{i}']))for i in range(1,int(row['LOCATIONCOUNT'])+1)]
        vertices.update(pts)
        for a,b in zip(pts,pts[1:]):
            if a==b:continue
            assert a[0]==b[0]or a[1]==b[1],('非正交导线',a,b)
            segments.append((a,b))
            if a[1]==b[1]:key=('H',a[1],row.get('LINEWIDTH','1'),row.get('COLOR','8388608'));interval=sorted((a[0],b[0]))
            else:key=('V',a[0],row.get('LINEWIDTH','1'),row.get('COLOR','8388608'));interval=sorted((a[1],b[1]))
            groups[key].append(interval)
    points=set();pin_cuts=set()
    for p in vertices|junctions|set(pins):
        dirs=set()
        px,py=p
        for a,b in segments:
            if a[1]==b[1]==py and min(a[0],b[0])<=px<=max(a[0],b[0]):
                if min(a[0],b[0])<px:dirs.add('L')
                if max(a[0],b[0])>px:dirs.add('R')
            elif a[0]==b[0]==px and min(a[1],b[1])<=py<=max(a[1],b[1]):
                if min(a[1],b[1])<py:dirs.add('D')
                if max(a[1],b[1])>py:dirs.add('U')
        if p in pins and dirs:
            # 导线在热端处保持端点，AD 直接按端点连接，不依赖热端落在线段中段。
            pin_cuts.add(p);dirs|=pins[p]
        if len(dirs)>=3:points.add(p)
    kept=[i for i,r in enumerate(records)if r.get('RECORD')not in('27','29')]
    mapping={old:new for new,old in enumerate(kept)}
    result=[]
    for i in kept:
        row=deepcopy(records[i])
        if 'OWNERINDEX'in row:
            old=int(row['OWNERINDEX'])+1
            if old in mapping:row['OWNERINDEX']=str(mapping[old]-1)
        result.append(row)
    for (axis,pos,width,color),intervals in sorted(groups.items()):
        merged=[]
        for start,end in sorted(intervals):
            if merged and start<=merged[-1][1]:merged[-1][1]=max(merged[-1][1],end)
            else:merged.append([start,end])
        for start,end in merged:
            # 在真实分支点分段，使四向交点同时具有导线端点，原生编译可直接识别。
            cuts=sorted({start,end}|{(x if axis=='H'else y)for x,y in points|pin_cuts
                                    if (y if axis=='H'else x)==pos
                                    and start<(x if axis=='H'else y)<end})
            for lo,hi in zip(cuts,cuts[1:]):
                a,b=((lo,pos),(hi,pos))if axis=='H'else((pos,lo),(pos,hi))
                result.append({'RECORD':'27','LINEWIDTH':width,'COLOR':color,'LOCATIONCOUNT':'2',
                               'X1':str(a[0]),'Y1':str(a[1]),'X2':str(b[0]),'Y2':str(b[1])})
    for x,y in sorted(points):
        result.append({'RECORD':'29','INDEXINSHEET':'-1','OWNERPARTID':'-1',
                       'LOCATION.X':str(x),'LOCATION.Y':str(y),'COLOR':'8388608'})
    return result

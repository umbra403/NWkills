import sys,os
from .emu import *
from .emu import DATA
EXTRA={0x87c318:8,0x87c31c:3,0x87c320:11,0x87c324:2,0x87c330:10,0x87c328:12,0x87c32c:11,0xa6f2a0:1}
def probe(e,a): e.r['esp']=(e.r['esp']-e.r['eax'])&M32
def h_46d880(e,args):
    cur=e.rd(args(1),4); n=e.rd(e.rd(args(2),4),4) if False else e.rd(args(2),4)
    e.cursor=cur; v=e.readbits(n); e.wr(args(3),4,v); e.wr(args(1),4,e.cursor)
def h_474810(e,args):
    v=e.readbits(16); e.r['eax']=v; e.r['esp']+=4
def run_packet(pl,trace=False):
    e=Emu(pl,8*len(pl)); S=e.S
    e.hooks[0x626e60]=probe; e.hooks[0x474810]=h_474810
    e.hooks[0x46d880]=lambda e,a:None
    e.stepinto={0x46fb70}
    # 46d880 is cdecl 5 args: wrap
    def h46d880(e,args):
        cp=args(1); outp=args(2); n=e.rd(e.rd(args(3),4),4) if False else e.rd(args(3),4)
        e.cursor=e.rd(cp,4); v=e.readbits(n); e.wr(outp,4,v); e.wr(cp,4,e.cursor)
    def h46d760(e,args):
        cp=args(1); outp=args(2); n=e.rd(args(3),4)
        e.cursor=e.rd(cp,4)
        for i in range(0,n,8):
            k=min(8,n-i); v=e.readbits(k); e.wr(outp+(i>>3),1,v)
        e.wr(cp,4,e.cursor)
    e.hooks[0x46d760]=h46d760
    e.stepmin=0x46d400; e.stepmax=0x46f000; e.stepinto={0x46fb70}
    e.hooks[0x46d880]=h46d880
    orig=e.readbits
    def rb(n):
        e.cursor=e.rd(S+0x5f0,4); v=orig(n); e.wr(S+0x5f0,4,e.cursor); return v
    e.readbits=rb
    import pickle
    for a,v in pickle.load(open(os.path.join(DATA,'statmem.pkl'),'rb')).items(): e.mem[a]=v
    for a,v in EXTRA.items(): e.wr(a,4,v)
    e.cursor=24
    e.wr(S+0x5ec,4,8*len(pl)); e.wr(S+0x5f0,4,11)
    e.wr(0x40000000,4,0)           # peer index
    e.wr(0x40000010,1,1)           # flag
    e.r['esp']=0x10000000
    e.push(0x40000010); e.push(S); e.push(0x40000000)   # arg3,arg2,arg1  (arg1=&peer, arg2=stream, arg3=&flag)
    e.push(0xdeadbeef); e.r['ecx']=0x41000000
    return e

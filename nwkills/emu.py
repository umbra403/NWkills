import re,struct,pickle,os,hashlib
M32=0xffffffff
DATA=os.path.join(os.path.dirname(os.path.abspath(__file__)),'data')
EXE_SHA256='ff4a28c51bed49fe4bbb4bb96389f7611894f6d031bf68fff661efdc946dae13'
INS,NEXT,RET=pickle.load(open(os.path.join(DATA,'ins_subset.pkl'),'rb'))
IMG=b''
def load_exe(path):
    """Load the user's mb_warband.exe (data sections are read from it). Returns True if it is the exact build the tables were made for."""
    global IMG
    IMG=open(path,'rb').read()
    return hashlib.sha256(IMG).hexdigest()==EXE_SHA256
def img_read(addr,n):
    if 0x401000<=addr<0x401000+0x3bd000: o=addr-0x401000+0x400
    elif 0x7be000<=addr<0x7be000+0xa0000: o=addr-0x7be000+0x3bd000
    elif 0x85e000<=addr<0x85e000+0xdc00: o=addr-0x85e000+0x45d000
    else: return bytes(n)
    return IMG[o:o+n]
R32=['eax','ecx','edx','ebx','esp','ebp','esi','edi']
R16=['ax','cx','dx','bx','sp','bp','si','di']
R8L=['al','cl','dl','bl']; R8H=['ah','ch','dh','bh']
def retimm(f):
    if f in RET: return RET[f]
    raise Exception('unknown call target %x'%f)
class NoStep:
    def __contains__(self,a): return 0x46f000<a<0x4788c0 and a!=0x46fb70
class Stop(Exception): pass
class Emu:
    def __init__(self,bits,total,hooks=None):
        self.mem={}; self.r={k:0 for k in R32}; self.zf=self.sf=self.cf=self.of=0
        self.bits=bits; self.total=total; self.cursor=0
        self.S=0x20000000; self.hooks=hooks or {}; self.log=[]
        self.reads=[]  # (bitpos,nbits,value)
        self.retcache={}; self.tr=None; self.stepinto=set(); self.stepmin=1; self.stepmax=0; self.nostep=set(); self.enter=[]; self.calls=[]
    # memory
    def rd(self,a,n):
        out=bytearray()
        for i in range(n):
            x=(a+i)&M32
            if x in self.mem: out.append(self.mem[x])
            else: out+=img_read(x,1)
        return int.from_bytes(out,'little')
    def wr(self,a,n,v):
        v&=(1<<(8*n))-1
        for i in range(n): self.mem[(a+i)&M32]=(v>>(8*i))&0xff
    # stream
    def readbits(self,n):
        v=0
        for i in range(n):
            p=self.cursor+i
            if p>=self.total: raise Stop('eof')
            v|=((self.bits[p>>3]>>(p&7))&1)<<i
        self.reads.append((self.cursor,n,v)); self.cursor+=n; return v
    # operands
    def ea(self,s):
        s=s.strip()
        m=re.match(r'(?:(?:BYTE|WORD|DWORD|QWORD) PTR )?(?:(\w\w):)?\[(.*)\]$',s)
        if m: expr=m.group(2)
        else:
            m=re.match(r'(?:(?:BYTE|WORD|DWORD|QWORD) PTR )?(?:ds:|es:|ss:)?(0x[0-9a-f]+)$',s)
            if m: return int(m.group(1),16)
            raise Exception('ea '+s)
        tot=0
        for term in re.split(r'(?=[+-])',expr.replace(' ','')):
            if not term: continue
            sign=-1 if term[0]=='-' else 1
            t=term.lstrip('+-')
            if '*' in t:
                a,b=t.split('*'); tot+=sign*self.r[a]*int(b,0)
            elif t in self.r: tot+=sign*self.r[t]
            else: tot+=sign*int(t,0)
        return tot&M32
    def size(self,s):
        if s.startswith('BYTE'): return 1
        if s.startswith('WORD'): return 2
        if s.startswith('DWORD'): return 4
        if s.startswith('QWORD'): return 8
        return None
    def getreg(self,n):
        if n in self.r: return self.r[n],4
        if n in R16: return self.r[R32[R16.index(n)]]&0xffff,2
        if n in R8L: return self.r[R32[R8L.index(n)]]&0xff,1
        if n in R8H: return (self.r[R32[R8H.index(n)]]>>8)&0xff,1
        raise Exception('reg '+n)
    def setreg(self,n,v):
        if n in self.r: self.r[n]=v&M32; return
        if n in R16:
            k=R32[R16.index(n)]; self.r[k]=(self.r[k]&0xffff0000)|(v&0xffff); return
        if n in R8L:
            k=R32[R8L.index(n)]; self.r[k]=(self.r[k]&0xffffff00)|(v&0xff); return
        if n in R8H:
            k=R32[R8H.index(n)]; self.r[k]=(self.r[k]&0xffff00ff)|((v&0xff)<<8); return
        raise Exception('reg '+n)
    def isreg(self,s): return s in self.r or s in R16 or s in R8L or s in R8H
    def get(self,s,sz=None):
        s=s.strip()
        if self.isreg(s): return self.getreg(s)
        if re.match(r'^-?0x[0-9a-f]+$',s) or re.match(r'^-?\d+$',s):
            return int(s,0)&M32,sz or 4
        z=self.size(s) or sz or 4
        return self.rd(self.ea(s),z),z
    def put(self,s,v,sz=None):
        s=s.strip()
        if self.isreg(s): self.setreg(s,v); return
        z=self.size(s) or sz or 4
        self.wr(self.ea(s),z,v)
    def flags(self,res,sz,cf=None,of=None):
        m=(1<<(8*sz))-1; res&=m
        self.zf=int(res==0); self.sf=int(res>>(8*sz-1)); 
        if cf is not None: self.cf=cf
        if of is not None: self.of=of
    def push(self,v): self.r['esp']=(self.r['esp']-4)&M32; self.wr(self.r['esp'],4,v)
    def pop(self): v=self.rd(self.r['esp'],4); self.r['esp']=(self.r['esp']+4)&M32; return v
    def cond(self,m):
        zf,sf,cf,of=self.zf,self.sf,self.cf,self.of
        t={'je':zf,'jne':1-zf,'jb':cf,'jae':1-cf,'jbe':cf|zf,'ja':1-(cf|zf),'jl':int(sf!=of),'jge':int(sf==of),
           'jle':zf|int(sf!=of),'jg':int((not zf) and sf==of),'js':sf,'jns':1-sf}
        return t[m]
    def signed(self,v,sz): 
        m=1<<(8*sz); v&=m-1; return v-m if v>>(8*sz-1) else v
    def run(self,pc,maxsteps=20000,stop_ret_at=None):
        steps=0; depth0=self.r['esp']
        while steps<maxsteps:
            steps+=1
            m,o=INS[pc]; nxt=NEXT[pc]
            if self.tr is not None: self.tr.append((pc,dict(self.r)))
            ops=[x.strip() for x in re.split(r',(?![^\[]*\])',o)] if o else []
            if m=='mov':
                v,sz=self.get(ops[1],None); 
                if self.size(ops[0]) is None and not self.isreg(ops[0]): pass
                dsz=self.getreg(ops[0])[1] if self.isreg(ops[0]) else (self.size(ops[0]) or sz)
                self.put(ops[0],v,dsz)
            elif m=='lea': self.put(ops[0],self.ea(ops[1]))
            elif m=='push':
                v,_=self.get(ops[0]); self.push(v)
            elif m=='pop':
                self.put(ops[0],self.pop())
            elif m in('add','sub','cmp','and','or','xor','test','adc','sbb'):
                a,sa=self.get(ops[0]); b,sb=self.get(ops[1],sa)
                sz=sa if self.isreg(ops[0]) else (self.size(ops[0]) or sb)
                if not self.isreg(ops[0]) and self.size(ops[0]) is None: sz=4
                a,_=self.get(ops[0]) if True else (a,0)
                mask=(1<<(8*sz))-1
                if sz<4 and self.size(ops[0]) is None and not self.isreg(ops[0]): pass
                b&=mask; a&=mask
                if re.match(r'^-?0x',ops[1]): b=int(ops[1],0)&mask
                if m in('add','adc'):
                    c=self.cf if m=='adc' else 0
                    r=a+b+c; cf=int(r>mask); of=int(((a^r)&(b^r))>>(8*sz-1)&1); self.flags(r,sz,cf,of); self.put(ops[0],r,sz)
                elif m in('sub','cmp','sbb'):
                    c=self.cf if m=='sbb' else 0
                    r=a-b-c; cf=int(a<b+c); of=int((((a^b)&(a^r))>>(8*sz-1))&1); self.flags(r,sz,cf,of)
                    if m!='cmp': self.put(ops[0],r,sz)
                else:
                    r={'and':a&b,'or':a|b,'xor':a^b,'test':a&b}[m]; self.flags(r,sz,0,0)
                    if m!='test': self.put(ops[0],r,sz)
            elif m in('inc','dec'):
                a,sz=self.get(ops[0]); sz=self.size(ops[0]) or sz
                r=a+1 if m=='inc' else a-1; cf=self.cf; self.flags(r,sz,cf,0); self.put(ops[0],r,sz)
            elif m=='neg':
                a,sz=self.get(ops[0]); r=-a; self.flags(r,sz,int(a!=0),0); self.put(ops[0],r,sz)
            elif m=='not':
                a,sz=self.get(ops[0]); self.put(ops[0],~a,sz)
            elif m in('shl','shr','sar'):
                a,sz=self.get(ops[0]); sz=self.size(ops[0]) or sz
                c,_=self.get(ops[1]) if len(ops)>1 else (1,1)
                if ops[-1]=='cl': c=self.r['ecx']&0xff
                c&=31; mask=(1<<(8*sz))-1
                if m=='shl': r=(a<<c)&mask
                elif m=='shr': r=a>>c
                else: r=(self.signed(a,sz)>>c)&mask
                if c: self.flags(r,sz,0,0)
                self.put(ops[0],r,sz)
            elif m=='imul':
                if len(ops)==3: a,_=self.get(ops[1]); b,_=self.get(ops[2]); r=self.signed(a,4)*self.signed(b,4); self.put(ops[0],r)
                elif len(ops)==2: a,_=self.get(ops[0]); b,_=self.get(ops[1]); r=self.signed(a,4)*self.signed(b,4); self.put(ops[0],r)
                else:
                    a,_=self.get(ops[0]); r=self.signed(self.r['eax'],4)*self.signed(a,4); self.r['eax']=r&M32; self.r['edx']=(r>>32)&M32
            elif m=='idiv':
                a,_=self.get(ops[0]); n=self.signed((self.r['edx']<<32)|self.r['eax'],8) if False else self.signed(self.r['eax'],4)
                d=self.signed(a,4) or 1; q=int(n/d); self.r['eax']=q&M32; self.r['edx']=(n-q*d)&M32
            elif m in('shld','shrd'):
                a,_=self.get(ops[0]); b,_=self.get(ops[1]); c,_=self.get(ops[2]); c&=31
                if c:
                    if m=='shld': r=((a<<c)|(b>>(32-c)))&M32
                    else: r=((a>>c)|(b<<(32-c)))&M32
                    self.flags(r,4,0,0); self.put(ops[0],r)
            elif m=='cdq': self.r['edx']=M32 if self.r['eax']>>31 else 0
            elif m=='cwde': ax=self.r['eax']&0xffff; self.r['eax']=(ax|0xffff0000) if ax&0x8000 else ax
            elif m=='movzx':
                v,sz=self.get(ops[1]); sz=self.size(ops[1]) or sz; self.put(ops[0],v&((1<<(8*sz))-1))
            elif m=='movsx':
                v,sz=self.get(ops[1]); sz=self.size(ops[1]) or sz; self.put(ops[0],self.signed(v,sz)&M32)
            elif m.startswith('set'):
                c={'sete':self.zf,'setne':1-self.zf,'seta':1-(self.cf|self.zf),'setl':int(self.sf!=self.of)}[m]; self.put(ops[0],c,1)
            elif m=='cmova':
                if not (self.cf|self.zf):
                    v,_=self.get(ops[1]); self.put(ops[0],v)
            elif m.startswith('j'):
                if m=='jmp':
                    if ops[0].startswith('0x'): nxt=int(ops[0],16)
                    else:
                        t=self.ea(ops[0]); nxt=self.rd(t,4)
                elif self.cond(m): nxt=int(ops[0],16)
            elif m=='call':
                tgt=ops[0]
                if tgt.startswith('0x'): f=int(tgt,16)
                else: f=self.rd(self.ea(tgt),4) if '[' in tgt or 'ds:' in tgt else self.get(tgt)[0]
                if f not in self.hooks and (f in self.stepinto or (self.stepmin<=f<=self.stepmax and f not in self.nostep)):
                    self.push(nxt); self.enter.append((f,self.cursor)); pc=f; continue
                self.docall(f,nxt)
            elif m=='ret':
                ra=self.pop(); imm=int(o,16) if o else 0
                self.r['esp']=(self.r['esp']+imm)&M32
                if self.enter and ra!=0xdeadbeef:
                    f,c0=self.enter.pop(); self.calls.append((f,c0,self.cursor))
                if ra==0xdeadbeef: return ('ret',o)
                nxt=ra
            elif m in('rep',):
                # rep movs dword
                cnt=self.r['ecx']
                for _ in range(cnt):
                    v=self.rd(self.r['esi'],4); self.wr(self.r['edi'],4,v); self.r['esi']+=4; self.r['edi']+=4
                self.r['ecx']=0
            elif m in('nop','int3','cld','fld','fld1','fldz','fst','fstp','fadd','fmul','fsub','fsubp','fild','fxch','fcom','fcompp','fcomp','fnstsw','fdiv','fsubr','faddp','fmulp','fsubrp','fdivp','fdivrp','fchs','fabs','fsqrt','fucompp','fucomp','fistp','fist','fldpi','fadd'):
                if m=='fnstsw': self.setreg('ax',0x4500)
            else:
                raise Exception('unhandled %s %s @%x'%(m,o,pc))
            pc=nxt
        raise Stop('steps')
    def docall(self,f,ret):
        h=self.hooks.get(f)
        esp=self.r['esp']
        args=lambda i:self.rd(esp+4*i,4)
        if f in(0x46e0a0,0x46e040):
            n=self.rd(args(0),4); mn=self.rd(args(1),4)
            if mn==0x80000000: v=self.readbits(32)
            else: v=(self.readbits(n)+self.signed(mn,4))&M32
            self.r['eax']=v; self.r['esp']+=8
        elif f==0x46df40:
            n=self.rd(args(0),4); v=self.readbits(n); self.r['eax']=v; self.r['esp']+=8
        elif f==0x46dfb0:
            n=self.rd(args(0),4); mn=self.rd(args(1),4)
            if mn==0xffff8000: v=self.readbits(16)
            else: v=self.readbits(n)+self.signed(mn,4)
            self.r['eax']=self.signed(v,2)&M32; self.r['esp']+=8
        elif f==0x46e220:
            n=self.rd(args(1),4)  # bits
            for _ in range(3): self.readbits(n)
            self.r['eax']=0x30000000; self.r['esp']+=16
        elif h:
            h(self,args); 
        else:
            if self.r['ecx']==self.S:
                raise Exception('UNKNOWN READER-LIKE call %x (ecx=stream)'%f)
            ri=retimm(f); self.r['eax']=0; self.r['esp']+=ri
            self.log.append(('call',hex(f)))

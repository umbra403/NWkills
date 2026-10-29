"""Native parser for the tail of an NW server packet (time block + agent list + player list)."""
PROP_W=[33,10,10,8,10,10,10,9,3,3,2,2,3,11,32,32,32,32,14,14,14,14,1,1,1,1,1,8,1]
STRIDE=29
def bits(b,pos,n):
    if n==0: return 0
    end=pos+n
    if end>len(b)*8: return None
    i=pos>>3
    j=(end+7)>>3
    v=int.from_bytes(b[i:j],'little')>>(pos&7)
    return v&((1<<n)-1)
def varint23(b,pos):
    v=0;sh=0
    while True:
        c=bits(b,pos,24)
        if c is None: return None,pos
        v|=(c&0x7fffff)<<sh; pos+=24; sh+=23
        if not (c>>23)&1: break
        if sh>200: return None,pos
    return v,pos
def gap(b,pos):
    v=0;sh=0
    while True:
        c=bits(b,pos,5)
        if c is None: return None,pos
        v|=(c&15)<<sh; pos+=5; sh+=4
        if not (c>>4)&1: break
        if sh>64: return None,pos
    return v,pos
def parse_tail(b,pos):
    """returns dict(time, extra, agents=[(agent,prop,value)], players=[(player,prop,value)], end) or None on error"""
    t,pos=varint23(b,pos)
    if t is None: return None
    fl=bits(b,pos,1); pos+=1
    extra=None
    if fl is None: return None
    if fl:
        t2,pos=varint23(b,pos)
        if t2 is None: return None
        vec=[bits(b,pos+17*i,17) for i in range(3)]; pos+=51
        fl8=bits(b,pos,8); f10a=bits(b,pos+8,10); f10b=bits(b,pos+18,10); pos+=28
        extra=(t2,vec,fl8,f10a,f10b)
        if None in vec or fl8 is None or f10b is None: return None
    agents=[]; idx=-1
    while True:
        g,pos=gap(b,pos)
        if g is None: return None
        if g==0: break
        idx+=g
        a,p=divmod(idx,STRIDE); w=PROP_W[p]
        v=bits(b,pos,w)
        if v is None: return None
        agents.append((a,p,v)); pos+=w
    players=[]; idx=-1
    while True:
        g,pos=gap(b,pos)
        if g is None: return None
        if g==0: break
        idx+=g
        pl,p=divmod(idx,2); w=13 if p==0 else 10
        v=bits(b,pos,w)
        if v is None: return None
        players.append((pl,p,v)); pos+=w
    return dict(time=t,extra=extra,agents=agents,players=players,end=pos)

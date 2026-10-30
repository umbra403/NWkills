import csv,json,os,collections
WCODE={2:'self-inflicted? (class 2)',20:'artillery: cannonball',21:'artillery: shrapnel/canister',22:'artillery: explosion',17:'melee: bayonet/spear',12:'melee: sword/sabre',5:'firearm: musket/rifle',10:'firearm: pistol',0:'headshot'}
MAXSLOT=250
def load_roster(path):
    r={}
    if path and os.path.exists(path):
        for row in csv.DictReader(open(path,encoding='utf-8-sig')): r[int(row['player_id'])-1]=row['name']
    return r
def decode(recs,roster=None,local_slot=None,items=None,namer=None):
    roster=roster or {}
    if namer is None: namer=lambda s,t: roster.get(s,s)
    kills=[];last=None
    owner=[]  # (t,agent,slot)
    t18=[]; miss=[]
    obs=collections.defaultdict(list); dm=collections.defaultdict(list)
    for r in recs:
        t=r['t']
        for ty,v,w in r['msgs']:
            f=v[1:]; ws=w[1:]
            if ty==13 and len(f)>=5:
                vic=f[0]-1; kil=f[1]-1; wc=f[2]
                hit=f[-1] if ws[-1]==9 else None
                key=(vic,kil)
                if last and last[0]==key and t-last[1]<4: last=(key,t); continue
                last=(key,t); kills.append(dict(t=t,victim=vic,killer=kil,wcode=wc,hit=hit,mode=f[3] if len(f)>3 else None,nextra=len(f)-5))
            elif ty==5 and len(f)>20 and f[0]>0:
                if f[1]-1<=MAXSLOT: owner.append((t,f[0]-1,f[1]-1))
            elif ty==18 and f and f[0]>0: t18.append((t,f[0]-1))
            elif ty==6 and len(f)>=6: miss.append((t,f[4]-1,f[5]-1))
        tl=r['tail']
        if tl:
            for a,p,val in tl['agents']:
                if p==27 and 0<val<=MAXSLOT+1: owner.append((t if t>=30 else 0,a,val-1))
                if p==13 and val==1: dm[a].append(t)
            for pl,p,val in tl['players']:
                if p==0: obs[pl].append((t,val-8192 if val>=4096 else val))
    kills=[k for k in kills if any(abs(x-k['t'])<3 for x in dm.get(k['victim'],[]))]
    seen=set(); k2=[]
    for k in kills:
        key=(k['victim'],round(k['t']/6))
        if key in seen: continue
        seen.add(key); k2.append(k)
    kills=k2
    owner=sorted(set(owner))
    if local_slot is None:
        c=collections.Counter()
        for k in kills:
            s=[o for o in owner if o[1]==k['victim'] and o[0]<k['t']-0.3]
            if s and any(k['t']<x[0]<k['t']+10 and not [o for o in owner if o[1]==x[1] and abs(o[0]-x[0])<4] for x in t18) and s[-1][2]>=0: c[s[-1][2]]+=1
        local_slot=c.most_common(1)[0][0] if c else None
    cur=[o[1] for o in owner if o[0]==0 and o[2]==local_slot]
    cur=cur[0] if cur else None
    for k in kills:
        if cur is not None and k['victim']==cur:
            n=[x for x in t18 if k['t']<x[0]<k['t']+10]
            if n: owner.append((n[0][0],n[0][1],local_slot)); cur=n[0][1]
    owner=sorted(set(owner))
    def who(a,t):
        c=[o for o in owner if o[1]==a and o[0]<t-0.3]
        return c[-1][2] if c else None
    lastv={}; out=[]
    by_slot=collections.defaultdict(list)
    for o in owner: by_slot[o[2]].append(o)
    for k in kills:
        t=k['t']; ks=who(k['killer'],t); vs=who(k['victim'],t)
        dl=None
        if ks is not None:
            w=[x for tt,x in obs.get(ks,[]) if t-0.3<=tt<=t+2.5]
            if w:
                b=[x for tt,x in obs.get(ks,[]) if tt<t-0.3]
                if b:
                    dl=w[0]-b[-1]
                    if dl==0: dl=None
        resp=None
        if vs is not None and vs>=0:
            nx=[o[0]-t for o in by_slot.get(vs,[]) if o[0]>t+0.5 and o[1]!=k['victim']]
            if nx and min(nx)<=120: resp=round(min(nx),1)
        wn=WCODE.get(k['wcode'],'class %d'%k['wcode'])
        if k['wcode']==0 and k.get('mode')!=2: wn='no blow (mode %s)'%k.get('mode')
        elif k['wcode']==0:
            pi=[it for tt,sh,it in miss if sh==k['killer'] and -1.0<t-tt<1.0]
            if pi and items and 0<=pi[0]<len(items): wn+=' ('+items[pi[0]][4:]+')'
        out.append(dict(time=round(t,2),killer=namer(ks,t),victim=namer(vs,t),weapon=wn,teamkill='yes' if dl is not None and dl<0 else '',killer_slot=ks,victim_slot=vs,killer_agent=k['killer'],victim_agent=k['victim'],hit=k['hit'],dl=dl,mode=k.get('mode'),respawn=resp,wcode=k['wcode'],nextra=k.get('nextra')))
    return out,local_slot

import bisect, csv,json,os,collections
# weapon class (5-bit field of the kill message) -> killfeed icon, read from the exe's jump table at 0x4bce0c (function 0x4bb310).
# Names marked (icon) are the engine's icon names; the module draws its own art for them (e.g. ico_crossbow shows the musket).
WCODE={0:'headshot',1:'melee: couched lance (cavalry)',2:'fists (punch)',3:'cavalry: horse charge (rider hit)',4:'bow (ico_bow)',
 5:'firearm: musket/rifle',6:'thrown axe (ico_axethrow)',7:'thrown knife (ico_knifethrow)',8:'javelin (ico_javelin)',9:'thrown stone (ico_stonethrow)',
 10:'firearm: pistol',11:'firearm: musket (ico_musket)',12:'melee: sword/sabre',13:'melee: two-handed sword (ico_swordtwo)',14:'melee: one-handed axe (ico_axeone)',
 15:'melee: two-handed axe (ico_axetwo)',16:'melee: mace/club',17:'melee: bayonet/spear',18:'melee: morningstar (ico_morningstar)',19:'melee: hammer/mallet',
 20:'artillery: cannonball',21:'artillery: shrapnel/canister',22:'artillery: explosion',23:'drowning',
 24:'special: custom icon 5 (ico_custom_5)',25:'special: custom icon 6 (ico_custom_6)',26:'special: custom icon 7 (ico_custom_7)'}
MAXSLOT=250
import re
_ADM=[(re.compile(r'^(.+?) Slayed Player (.+)\.$'),'slay'),(re.compile(r'^(.+?) Slayed Everyone\.?$'),'slay_all'),(re.compile(r'^(.+?) Swapped Everyone to Spectators\.?$'),'swap_all')]
def admin_lines(recs):
    """Admin actions the server announces as text lines -> [(t, kind, admin, target)], kind slay / slay_all / swap_all (each line arrives in 2 copies)."""
    out=[]
    for r in recs:
        for s in r['txt']:
            for rx,kind in _ADM:
                m=rx.match(s.strip())
                if m:
                    tg=m.group(2) if kind=='slay' else None
                    if not any(o[1]==kind and o[3]==tg and abs(o[0]-r['t'])<1.0 for o in out): out.append((r['t'],kind,m.group(1),tg))
                    break
    return out
def load_roster(path):
    r={}
    if path and os.path.exists(path):
        for row in csv.DictReader(open(path,encoding='utf-8-sig')): r[int(row['player_id'])-1]=row['name']
    return r

import os as _os
_MODE = _os.environ.get('NWOBS', '3')
def _good_scores(raw, mode=None):
    """Score updates (player, value) from the state block. The server repeats an update in every tick until it is acknowledged, so a real value
    shows up in several packets within a moment; a value that appears once, or only in packets that did not parse cleanly, is usually a
    mis-read (random values like 222 or -2615 in the score history made fake teamkills). mode 0 = keep everything (old behaviour)."""
    mode = _MODE if mode is None else mode
    if mode == '0':
        return [(pl, t, v) for t, pl, v, ok in raw]
    cl = {}
    for t, pl, v, ok in raw:
        if mode != '0' and not ok: continue
        cl.setdefault((pl, v), []).append(t)
    keep = []
    for (pl, v), ts in cl.items():
        ts.sort(); grp = [[ts[0]]]
        for x in ts[1:]:
            if x - grp[-1][-1] < 1.0: grp[-1].append(x)
            else: grp.append([x])
        for g in grp:
            if mode == '1' or len(g) >= 2 or (mode == '3' and abs(v) <= 60):
                keep += [(pl, t, v) for t in g]
    keep.sort(key=lambda x: x[1])
    return keep
def decode(recs,roster=None,local_slot=None,items=None,namer=None):
    roster=roster or {}
    if namer is None: namer=lambda s,t: roster.get(s,s)
    kills=[];last=None
    owner=[]  # (t,agent,slot)
    spawn_msg=[]
    t18=[]; miss=[]; obs_raw=[]
    team_hist=collections.defaultdict(list)      # agent -> [(t, team)] from the spawn messages (type 5, 3-bit field): the client's own teamkill test compares these
    obs=collections.defaultdict(list); dm=collections.defaultdict(list); rid=collections.defaultdict(list)
    # map-change / reset blocks: the server kills every agent at once (killer == victim), hundreds of messages in a few seconds, often in queued
    # packets. They are not kills: self-deaths are dropped when 8 or more different agents have one within 3 seconds.
    adm_all=[a[0] for a in admin_lines(recs) if a[1] in ('slay_all','swap_all')]      # blocks announced by the server as an admin action are kept (and labelled in the kills file)
    selft=sorted((r['t'],v[1]) for r in recs for ty,v,w in r['msgs'] if ty==13 and len(v)>=6 and v[1]==v[2])
    mass=set()
    j=0
    for i,(t0,_) in enumerate(selft):
        while selft[j][0]<t0-1.5: j+=1
        k=i
        while k+1<len(selft) and selft[k+1][0]<=t0+1.5: k+=1
        if len(set(x[1] for x in selft[j:k+1]))>=8 and not any(a-2.5<=t0<=a+1.5 for a in adm_all): mass.add(t0)      # distinct agents: one death is sent again and again (up to 20 copies) while the client is slow to acknowledge
    for r in recs:
        t=r['t']
        for ty,v,w in r['msgs']:
            f=v[1:]; ws=w[1:]
            if ty==13 and len(f)>=5 and f[0]==f[1] and t in mass: continue
            if ty==13 and len(f)>=5:
                vic=f[0]-1; kil=f[1]-1; wc=f[2]
                hit=f[-1] if ws[-1]==9 else None
                key=(vic,kil)
                if last and last[0]==key and t-last[1]<4: last=(key,t); continue
                last=(key,t); kills.append(dict(t=t,victim=vic,killer=kil,wcode=wc,hit=hit,mode=f[3] if len(f)>3 else None,nextra=len(f)-5))
            elif ty==5 and len(f)>20 and f[0]>0:
                team_hist[f[0]-1].append((t,f[3]))
                if f[1]-1<=MAXSLOT: owner.append((t,f[0]-1,f[1]-1)); spawn_msg.append((f[0]-1,t))
            elif ty==18 and f and f[0]>0: t18.append((t,f[0]-1))
            elif ty==6 and len(f)>=6: miss.append((t,f[4]-1,f[5]-1))
        tl=r['tail']
        ok_tail=bool(tl) and r['L']-tl['end']<8 and not r['err']     # the property list of a packet whose tail did not parse to the end can hold garbage owner values
        if tl:
            for a,p,val in tl['agents']:
                if p==27 and 0<val<=MAXSLOT+1 and ok_tail: owner.append((t if t>=30 else t*1e-6,a,val-1))   # first 30 s: known from the start, but keep their order (a stale value is corrected a moment later)
                if p==13 and val==1: dm[a].append(t)
                if p in (6,7): rid[a].append(t)      # rider agents carry properties 6/7; horses do not
            for pl,p,val in tl['players']:
                if p==0: obs_raw.append((t,pl,val-8192 if val>=4096 else val,r['L']-tl['end']<8 and not r['err']))
    for pl, tt, vv in _good_scores(obs_raw): obs[pl].append((tt, vv))
    kills=[k for k in kills if any(abs(x-k['t'])<3 for x in dm.get(k['victim'],[]))]
    lastk={}; k2=[]
    for k in kills:      # an agent cannot die twice within a few seconds: drop repeats of the same death message (no bucket edges)
        if k['victim'] in lastk and k['t']-lastk[k['victim']]<6: continue
        lastk[k['victim']]=k['t']; k2.append(k)
    kills=k2
    owner=sorted(set(owner))
    if local_slot is None:
        c=collections.Counter()
        for k in kills:
            s=[o for o in owner if o[1]==k['victim'] and o[0]<k['t']-0.3]
            if s and any(k['t']<x[0]<k['t']+10 and not [o for o in owner if o[1]==x[1] and abs(o[0]-x[0])<4] for x in t18) and s[-1][2]>=0: c[s[-1][2]]+=1
        local_slot=c.most_common(1)[0][0] if c else None
    cur=[o[1] for o in owner if o[0]<1e-4 and o[2]==local_slot]
    cur=cur[0] if cur else None
    for k in kills:
        if cur is not None and k['victim']==cur:
            n=[x for x in t18 if k['t']<x[0]<k['t']+10]
            if n: owner.append((n[0][0],n[0][1],local_slot)); cur=n[0][1]
    owner=sorted(set(owner))
    def who(a,t):
        c=[o for o in owner if o[1]==a and o[0]<t-0.3]
        return c[-1][2] if c else None
    by_agent=collections.defaultdict(list)
    for o in owner: by_agent[o[1]].append(o)
    spawn_t=collections.defaultdict(list)
    for a_,t_ in spawn_msg: spawn_t[a_].append(t_)
    death_t=collections.defaultdict(list)
    for k in kills: death_t[k['victim']].append(k['t'])
    def who_late(a,t,win=120.0):
        """Owner of agent a learned from data that arrives AFTER the event (agents already present when the capture started
        are only listed later). Used only when nothing earlier is known. Sightings are ignored if they come with a spawn message
        of that agent id (the id was re-created, so it is another agent) or after the agent's next death; accepted only if all
        remaining sightings within win seconds agree on one player."""
        nd=min([x for x in death_t.get(a,[]) if x>t+0.3],default=1e18)
        c=[o for o in by_agent.get(a,[]) if t-0.3<=o[0]<=t+win and o[0]<nd and not any(abs(o[0]-x)<0.5 for x in spawn_t.get(a,[]))]
        sl=set(o[2] for o in c)
        return sl.pop() if len(sl)==1 else None
    for a_ in team_hist: team_hist[a_].sort()
    def team_of(a,t):
        """Team of agent a from its latest spawn message at or before t (None if its spawn was not in the capture)."""
        h=team_hist.get(a)
        if not h: return None
        i=bisect.bisect_right(h,(t+0.05,99))-1
        return h[i][1] if i>=0 else None
    lastv={}; out=[]
    by_slot=collections.defaultdict(list)       # spawn messages only: owner records from agent property lists also describe agents that were already there
    sp_set=set((round(t_,2),a_) for a_,t_ in spawn_msg)
    for o in owner:
        if (round(o[0],2),o[1]) in sp_set: by_slot[o[2]].append(o)
    # The client shows the RIDER as the killer when the killer agent is a horse that has a rider (killfeed routine 0x4bb310: agent kind 1 -> the agent in its
    # rider field +0x118, which the server keeps current with message type 30). Do the same: the latest link of that horse since its latest spawn message.
    link_hist=collections.defaultdict(list)       # horse agent -> [(t, rider agent or -1)]
    for r in recs:
        for a_,b_ in r.get('links') or (): link_hist[a_].append((r['t'],b_))
        # a rider is spawned together with its horse: the rider's spawn message (it has an owner) is followed directly by the horse's (no owner, team 0)
        seq=[v for ty,v,w in r['msgs'] if ty==5 and len(v)>21 and v[1]>0]
        for a_,b_ in zip(seq,seq[1:]):
            if a_[2]>0 and b_[2]==0 and b_[4]==0 and r['t']>=30: link_hist[b_[1]-1].append((r['t'],a_[1]-1))      # not in the first 30 s: the list of agents already on the map is in no useful order
    for a_ in link_hist: link_hist[a_].sort()
    for k in kills:
        if k['wcode']==3 and k['killer'] in link_hist:
            sp=max([x for x in spawn_t.get(k['killer'],()) if x<=k['t']+0.3],default=-1e9)
            ln=[x for x in link_hist[k['killer']] if sp-0.05<=x[0]<=k['t']+0.3]
            if not ln: continue
            lt,rd=ln[-1]
            # the client only substitutes a rider that is an active agent: one that has died (or been re-spawned) since the link is gone
            gone = rd<0 or any(lt+0.05<x<k['t']+0.3 for x in death_t.get(rd,())) or any(lt+0.5<x<=k['t']+0.3 for x in spawn_t.get(rd,()))
            if not gone:
                k['horse_agent']=k['killer']; k['killer']=rd; k['via_link']=True
            else: k['link_none']=True      # no rider (dismounted, or the rider died): the scoreboard may still credit the last rider, so the score decides first
    for k in kills:
        t=k['t']; ks=who(k['killer'],t); vs=who(k['victim'],t)
        late=[]
        if ks is None:
            ks=who_late(k['killer'],t)
            if ks is not None: late.append('killer')
        # a victim whose owner is not known by the time of death stays unknown: guessing it from the agent id's NEXT life (a respawn
        # ~35 s later) depends on where the capture started, so two recordings of one event would disagree
        dl=None; dl_base_t=None
        if ks is not None:
            w=[x for tt,x in obs.get(ks,[]) if t-0.3<=tt<=t+2.5]
            if w:
                b=[x for tt,x in obs.get(ks,[]) if tt<t-0.3]
                if b:
                    dl_base_t=[tt for tt,x in obs.get(ks,[]) if tt<t-0.3][-1]
                    dl=w[0]-b[-1]
                    if abs(dl)>=2 and -1<=w[0]<=1: dl=w[0]      # a jump no single kill makes: the scoreboard was reset to 0 without us seeing it, so b[-1] is last round's value
                    if dl==0: dl=None
                elif -3 <= w[0] < 0: dl = w[0]      # first score ever sent for this player: the server omits a score of 0, so the baseline was 0
        resp=None
        if vs is not None and vs>=0:
            nx=[o[0]-t for o in by_slot.get(vs,[]) if o[0]>t+0.5 and o[1]!=k['victim']]
            if nx and min(nx)<=120: resp=round(min(nx),1)
        # no-blow death of a player-owned agent that has never shown rider properties = the player's horse
        horse=False
        if k.get('mode')!=2 and vs is not None and vs>=0 and ks is not None and ks>=0 and ks!=vs and rid:
            horse=not any(t-20<=x<=t+0.5 for x in rid.get(k['victim'],[]))
        wn=WCODE.get(k['wcode'],'class %d'%k['wcode'])
        if k['wcode']==0 and k.get('mode')!=2: wn='no blow (mode %s)'%k.get('mode')
        elif k['wcode']==0:
            pi=[it for tt,sh,it in miss if sh==k['killer'] and -1.0<t-tt<1.0]
            if pi and items and 0<=pi[0]<len(items): wn+=' ('+items[pi[0]][4:]+')'
        # The client decides a teamkill from the two agents' teams (a friendly relation between them), not from the score. Used when both players' agents
        # have a spawn message in the capture; otherwise the killer's score change decides (older behaviour).
        tm=None
        if k.get('mode')==2 and ks is not None and ks>=0 and vs is not None and vs>=0 and k['killer']!=k['victim']:
            kt,vt=team_of(k['killer'],t),team_of(k['victim'],t)
            if kt is not None and vt is not None: tm=(kt==vt)
        tk_now = tm if tm is not None else (dl is not None and dl<0)
        out.append(dict(time=round(t,2),killer=namer(ks,t),victim=namer(vs,t),weapon=wn,teamkill='yes' if tk_now else '',tk_team=tm,killer_slot=ks,victim_slot=vs,killer_agent=k['killer'],victim_agent=k['victim'],hit=k['hit'],dl=dl,dl_base_t=dl_base_t,mode=k.get('mode'),respawn=resp,wcode=k['wcode'],nextra=k.get('nextra'),late=late,horse=horse,via_link=k.get('via_link',False),link_none=k.get('link_none',False)))
    # Several kills by one player within a few seconds (artillery, canister) share one scoreboard change, so the per-kill test above gives them all the
    # same verdict. Use the whole change instead: n kills with a net change D contain (n - D) / 2 teamkills. Which of them are teamkills is a guess
    # (victims with the killer's regiment prefix first) and flagged 'burst'.
    def _pre(nm):
        return str(nm).split('_')[0].lower() if isinstance(nm,str) else ''
    by_k=collections.defaultdict(list)
    for e in out:
        if e['mode']==2 and e['killer_slot'] is not None and e['killer_slot']>=0 and e['killer_slot']!=e['victim_slot']: by_k[e['killer_slot']].append(e)
    for ks,L in by_k.items():
        L.sort(key=lambda e:e['time']); i=0
        while i<len(L):
            j=i
            while j+1<len(L) and L[j+1]['time']-L[j]['time']<=2.5: j+=1
            g=L[i:j+1]; i=j+1
            if len(g)<2: continue
            for e in g: e['in_group']=True
            if all(e['tk_team'] is not None for e in g): continue      # every verdict in the volley comes from the teams: nothing to guess
            t0,t1=g[0]['time'],g[-1]['time']
            ob=obs.get(ks,[])
            b=[x for tt,x in ob if tt<t0-0.3]
            w=[x for tt,x in ob if t0-0.3<=tt<=t1+2.5]
            n=len(g)
            if not w:
                if not b or n%2: continue
                w=[b[-1]]            # the server only sends a score when it changes: no update after n kills means a net change of 0 (artillery hitting friend and foe)
            base=b[-1] if b else (0 if -3<=w[0]<=3 else None)
            if base is None: continue
            if abs(w[0]-base)>n and abs(w[0])<=n: base=0      # reset to 0 that we did not see (b[-1] is last round's value)
            cur=base
            for xi,x in enumerate(w):                        # follow the changes while they can come from these kills; stop at a later reset to 0 (the first change after the kills is theirs: 3 -> 1 after two kills is two teamkills)
                if xi and abs(x-cur)>=2 and abs(cur)>=2 and -1<=x<=1: break
                if abs(x-base)>n: break
                cur=x
            D=cur-base
            if (n-D)%2 or not 0<=(n-D)//2<=n: continue
            tk=(n-D)//2
            unk=[x for x in range(n) if g[x]['tk_team'] is None]       # kills whose teams are known keep their verdict; the guess only covers the others
            rem=tk-sum(1 for e in g if e['tk_team'])
            if not unk or not 0<=rem<=len(unk): continue
            order=sorted(unk,key=lambda x:(0 if _pre(g[x]['victim'])==_pre(g[x]['killer']) else 1, x))
            flag=set(order[:rem])
            for x in unk:
                g[x]['teamkill']='yes' if x in flag else ''
                g[x]['burst']=0<rem<len(unk)
    # Cavalry charge kills whose horse has no known owner (spawned unowned): the scoreboard credits the rider. Every score change of +-1 that one of the
    # player's own kills explains (same sign, within [kill - 0.3, kill + 2.5]) is set aside; the changes left over belong to kills we could not attribute.
    # A charge kill takes the player of a leftover change in its window when that is the only one; assignments are repeated, so a change claimed by a
    # neighbouring charge kill no longer counts as a rival. Flagged killer-from-score.
    ch=collections.defaultdict(list)            # slot -> [(t, delta)]
    for pl,ob in obs.items():
        for (t0,v0),(t1,v1) in zip(ob,ob[1:]):
            if abs(v1-v0)==1: ch[pl].append((t1,v1-v0))
    left=collections.defaultdict(list)
    for pl,L in ch.items():
        own=sorted((e['time'],-1 if e['teamkill'] else 1) for e in out if e['killer_slot']==pl and e['mode']==2)
        free=sorted(L)
        for tk_,sg in own:
            for i,(to,d) in enumerate(free):
                if tk_-0.3<=to<=tk_+2.5 and d==sg: del free[i]; break
        left[pl]=free
    rows=[e for e in out if e['wcode']==3 and e['mode']==2 and (e['killer_slot'] is None or e['killer_slot']<0)]
    todo=list(rows)
    while todo:
        pick=None
        for lo,hi in ((0.3,0.5),(0.3,2.5)):         # first the changes that arrive with the kill itself, then the wider window
            for e in todo:
                c=[(pl,to,d) for pl,L in left.items() for to,d in L if e['time']-lo<=to<=e['time']+hi]
                if c and len({x[0] for x in c})==1:   # one player (he may have two changes in the window: the nearest is taken)
                    pick=(e,min(c,key=lambda x:abs(x[1]-e['time']))); break
            if pick: break
        if not pick: break
        e,(pl,to,d)=pick
        left[pl].remove((to,d)); todo.remove(e)
        e['killer_slot']=pl; e['killer']=namer(pl,e['time']); e['teamkill']='yes' if d<0 else ''; e['tk_team']=None; e['late']=list(e['late'])+['killer-from-score']; e['burst']=False
    # A charge kill that nobody's score can claim, with no unexplained change in the window at all, was most likely made by a horse without a rider
    # (horses move on their own and can bump into players hard enough to kill). The kill is nobody's; the victim's death still counts.
    for e in todo:
        # nobody rides the horse (link says so, or its rider is dead) and nobody's score claims the kill: a horse without a rider
        if e.get('link_none') and not any(e['time']-0.3<=to<=e['time']+2.5 for pl,L in left.items() for to,d in L):
            e['killer']='(runaway horse)'; e['runaway']=True
    # cross-check: a team verdict that the killer's own score change contradicts (single kills only; a volley shares one change)
    # Events of one player a fraction of a second apart (a kill and then a fall or drowning) each have their own score step: the window above read the
    # first step for both. When the number of steps equals the number of events, hand them out in order.
    byk=collections.defaultdict(list)
    for e in out:
        if e['killer_slot'] is not None and e['killer_slot']>=0 and not e.get('in_group'): byk[e['killer_slot']].append(e)
    for ks_,L in byk.items():
        L.sort(key=lambda x:x['time']); i=0
        while i<len(L):
            j=i
            while j+1<len(L) and L[j+1]['time']-L[j]['time']<3.0: j+=1
            if j>i:
                grp=L[i:j+1]; ob=obs.get(ks_,[])
                base=[v for tt,v in ob if tt<grp[0]['time']-0.3]
                st=[(tt,v) for tt,v in ob if grp[0]['time']-0.3<=tt<=grp[-1]['time']+2.5]
                if base and st:
                    vals=[base[-1]]+[v for tt,v in st]
                    steps=[b-a for a,b in zip(vals,vals[1:]) if b!=a]
                    if len(steps)==len(grp) and all(abs(x)==1 for x in steps) and all(b['time']>a['time'] for a,b in zip(grp,grp[1:])):      # events with the same timestamp are a volley: handled below
                        for e,d in zip(grp,steps):
                            e['dl']=d
                            if e['tk_team'] is None: e['teamkill']='yes' if d<0 else ''
            i=j+1
    # A kill by the same player within a few seconds shares the score change (the window above reads both), so the check says nothing then.
    kt=collections.defaultdict(list)
    for e in out:
        if e['killer_slot'] is not None and e['killer_slot']>=0: kt[e['killer_slot']].append(e['time'])
    for e in out:
        crowded=e['killer_slot'] is not None and sum(1 for x in kt.get(e['killer_slot'],()) if abs(x-e['time'])<3.0)>1
        e['tk_check']= e['tk_team'] is not None and not e.get('in_group') and not crowded and e['dl'] is not None and (e['dl']<0)!=e['tk_team']
    return out,local_slot

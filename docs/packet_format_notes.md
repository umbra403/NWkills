# NW 1.210 (mb_warband.exe v1.174) – client packet format, findings so far

## Packet (server->client UDP payload, LSB-first bit stream)
- bits 0-10   : total packet length in bytes (11 bits)   [verified 3000/3000 packets]
- bit 11      : flag (always 0 in captures); stream continues at bit 24 (flag=0) or 32
- bits 24-39  : 16-bit sequence number (+1 per packet)
- bits 40-55  : 16-bit ack / last received seq of the other side
- bits 56-63  : message count + 1   (raw 0 => special, 1 => no messages)
- bits 64-67  : (w-1); w = bit width of the per-message "idx" field
- then `count` messages: [type 6 bits][idx w bits][payload ...]
- after the list: 46ee20 section (23-bit values, positions) and the replicated agent-update section
  (generic descriptor-driven, function 0x4788c0) – NOT decoded.
- Bit widths of ids come from static initialisers (47d540 = bit length of 250 => 8 bits etc.).

## Method
Python x86 emulator (emu.py) runs the game's own reader functions (0x473ca0 packet reader, 0x46fb70
message dispatcher with 64-way jump table at 0x473b98, reader primitives 0x46d880/0x46d760 hooked).
`survey.py` parses every multi-message packet of a capture: list of (type, [(bits,value)...]).
Needs mb.exe + `objdump -d -M intel --no-show-raw-insn mb.exe > mb.asm` in the same folder.

## Message type 13  (case at 0x4703b0, calls apply-blow 0x4bb310 which prints the killfeed line)
 idx(w) | victim agent+1 (10b) | attacker agent+1 (10b) | 5 bits | 2-bit mode | 1-bit flag
 [flag: 3 x 7 bits] | mode1: 4x11b pos / mode3: 7b + pos | 9 bits item index (+1)
- Agent ids, NOT player ids. In the clean capture killer L = agent 142 on every L kill.
- Reliable: resent in consecutive packets until acked.
- Present ~1.9 s before the server-log time for kills 0,1,4,5,6 (L's kills). Absent for kills by U/B and
  for L's swordone kills => other kill types arrive some other way (not found yet).
- Teamkill text is not sent; composed locally in 0x4bb310 using team relation table.

## Retraction
Earlier "types 13/77" were bits 4..10 of the body = start of message 1 (type 6 bits + 1st idx bit); so
13 was already the true first-message type, but the 'T' measure only saw message #1 of each packet.

## Update 2026-10-29 (tail section decoded structurally)
After the message list (flag=1 path):
 1. 0x46ee20: [24-bit-chunk varint time64][1 flag bit][if flag: varint, 3x17-bit, 8b float, 10b float, 10b float]
 2. 0x478b80: sequence of entries. gap = nibble-varint (4 bits + 1 continue bit, LSB first); gap 0 ends.
    idx += gap (starts at -1); agent = idx // 29, property = idx % 29 (divisor = static 0xdd842c = 0x1d, or 0x1c if a config option is 0).
    Value width per property (bits): 0:33 (3x11 pos) 1:10 2:10 3:8 4:10 5:10 6:10 7:9 8:3 9:3 10:2 11:2 12:3 13:11
    14..17:32 18..21:14(some 8/10) 22-26:1 27:8 28:1 (see jump table 0x4799b8)
 - In the clean capture agent 142 = L (matches type-13 killer id 142). Other visible agents 155, 191, 136.
 - These are movement/animation/state sync (position, rotation, action ids), not kill events per se.
 - Large 1 Hz batch packets (e.g. t=38.39, 67.38) mis-parse in the emulator (garbage agent ids) -> some message
   type/width in the list is still wrong (unknown static widths 0x87c318/0x87c31c, or unhandled types).
 - Kills without type 13 are therefore still not located. Next: fix the 1 Hz batch parsing, then look for
   agent removal / health (props 13,22-28) changes and message types 12/20.

## Update 2 (2026-10-29 afternoon) - widths fixed, whole capture parses
Runtime bit widths (object at 0x87c2e0, built at startup by 0x47dc10):
 0x87c318=8 (251 players)   0x87c31c=3   0x87c320=11 (scene props 1641)   0x87c324=2 (skins 2+1)
 0x87c330=11 (scene-prop instances)   (0x87c2cc=4, 0x87c2d0=16, 0x87c2d4/d8/dc=8)
 Divisor for the per-agent table 0xdd842c = 29 (28 if a config option is off).
With these, all 1637 multi-message S2C packets parse with message count == header count, and the
per-agent tail ends within 8 bits of the packet end (3/3 test packets).
Emulator fix: do NOT step into game logic 0x46f000-0x4788c0 (corrupts stack) - treat as no-op calls.

Findings
 - Type 13 (blow) appears 5 times as real kill messages (L's kills 0,1,4,5,6). Other type-13 hits in the
   big 51.74 / 77.38 / 139.4 packets are non-lethal/garbled. No other type carries killer+victim ids.
 - Message type 38 = scripted network event: [7-bit event id][4 x 32-bit ints] (module scripts use
   multiplayer_send_N_int_to_player; events seen: 111 particle, 120 hit effect, 78, 86 score...).
   Event 120 (hit effect) coincides with most kills (11-12/15) but carries positions, not names.
 - Kill feed lines in NW are produced CLIENT-SIDE by the trigger ti_on_agent_killed_or_wounded
   (script multiplayer_client_on_agent_killed_or_wounded_common) when the local simulation kills an agent;
   there is no dedicated 'X killed Y' network message. That explains why most kills have no
   killer/victim message in the capture.
 - Consequence: a packet-only decoder can only recover killer/victim from blows that arrive as type 13.

## Update 3 (2026-10-29 evening) - corrected statics, death markers, scoreboard
Corrected runtime statics (verified: message list end == start of tail time block for types 20/21/52/12/43/25/26):
  0x87c318=8  0x87c31c=3  0x87c320=11  0x87c324=2  0x87c330=9  0xa6f2a0=1 (type 20 then reads an extra 1-bit)  0xdd842c=29
  (earlier guesses 87c330=11/10 were wrong; Python hook run2 sets nostep for 0x46f000-0x4788c0.)
Packet tail layout (after message list), all gap-lists use the 4-bit-chunk+continue varint:
  1. time block (0x46ee20): varint(23-bit chunks, cont bit) ; flag ; [if flag: varint, 3x17b, 8b, 10b, 10b]
     chunk value ~ 1535 * seconds since start (server tick)
  2. LIST 1 (agents): gap-coded index idx; agent=idx//29, prop=idx%29; value width per prop
  3. LIST 2 (players): idx; player=idx//2; prop0 = 13-bit signed (kill/score counter), prop1 = 10-bit (ping)
Results on the clean capture (15 kills in the server log):
  * LIST 2 prop0 of player slot 9 (=L) increments with each of L's kills (0@31.4,1@38.5,3@77.4,4@85.7,5@96.4,6@108.8,7@223.4,8@239.9)
  * LIST 1 prop 13 of an agent drops to 1 when the agent is killed. First-sight times (about 1.8 s before the log time):
    k0 31.37 a155 | k1 38.51 a136 | k3 67.38 a154 | k4 77.41 a136 | k5 85.69 a174 | k6 96.37 a155 | k7 108.83 a191 |
    k8 126.37 a136 | k10 166.69 a155 | k11 194.45 a136 | k12 201.85 a154 | k13 223.42 a142 | k14 239.87 a136
    -> 13 of 15 kills have a death marker (missing: k2 54.2 and k9 157.2: packets at 51.7 and 155.4 not fully parsed)
  * Agent ids are recycled between players; agent->player map must come from the spawn data (prop 27 = owner player id+1 at
    initial sync: agent142 -> 10, agent155 -> 4).  Type 5 = agent spawn announcement (agent id+1 only).
  * Killer: only for L (via counter) and for kills carried by type 13. Weapon: only type 13 (item idx 431/434/...), 5 kills.

## Update 4: all 15 kills found as death markers
- Bug: functions above 0x486000 are not stepped by the emulator, so type 6 (handler 0x470701 -> 0x4f40b0) read only 17 bits. Real type 6 = 6b type + flag + 10b id + [vec 3x17, vec 3x9, 12b float, 10b, 10b(0x87c328, assumed 10), 32b, 10b, 32b] = ~202 bits. It is the spawn-projectile (missile) message, so it may carry the weapon/item for ranged kills. Hook h4f40b0 in exe/t52.py; full re-extraction in full4.pkl (t53.py, 2 procs).
- With that fix every packet's message list ends exactly at the time block, and prop 13 -> 1 (11b) appears for all 15 kills (victim agents 155,136,191,154,136,174,155,191,136,142,155,136,154,142,136 at the log times).
- Next: agent->player mapping, killer attribution, weapon (type 6 items, type 13 item), compare against server log.

## Update 5: killer, teamkill, ranged weapon decoded (exe/decode_kills.py on full4.pkl)
- Type 13 = (flag/counter) victim agent+1 (10b), killer agent+1 (10b), 5b, 2b, 1b, 9b HIT LOCATION (429 = head; NOT an item). Present for all 15 kills.
- Scoreboard LIST2 prop0 (13b signed, player = idx//2) changes at each kill: killer's score +1 (enemy) or -1 (teamkill). Verified: all 15 killers (L=slot 9, U=14, B=3) and exactly the 4 log teamkills (k3,k8,k10,k12).
- Type 6 = projectile spawn: after 10b id: vec17x3, vec9x3, 12b speed, 10b shooter agent+1, 10b item (+1?), 32b, 10b, 32b. Item -> weapon for ranged kills (pistol=item 6, musket etc.). Melee weapon still unknown.
- Type 28 = hit/damage (attacker agent+1, victim agent+1, ...). Type 7 = agent removed ~3 s after death. Types 5/18 = agent spawn announcements (no owner id). Agent prop 13 = health (->1 on death).
- Agent->player: prop27 (owner slot+1) only at initial sync (agent 155 -> 4 = slot 3 = B). Victim player identity for later spawns not found yet (agents recycled). Killer player is solved via scoreboard instead.

## Update 6: agent spawn message = type 5 (owner + loadout)
- Type 5 handler 0x470368 -> 0x4f8b80 (above the emulator step limit, so it was skipped). Real layout: 10b agent+1, 8b OWNER PLAYER+1, 2b, 3b, 8b, 32b, 11 x 10b item ids (+1) = equipment/loadout, 2 x 10b, vec 3x17, 12b float, 3 x 7b, 1b. Hook h4f8b80 in exe/t63.py; full5.pkl.
- Verified vs log: owner of spawned agents (U=15, B=4, L=10) matches 13/13 lives that have a type 5; 14/15 victims resolved (L's own respawn at 159.4 arrives as type 18 only; no type 5).
- Loadout items include rifle/musket/bayonet/sabre, e.g. U: baker rifle, training musket, jaeger bayonet (log 'spear' kill by U); L: baker rifle + light inf officer sabre (log 'swordone'). So melee weapon = melee item of the killer's loadout (wielded one not yet known). Item id = raw-1 into item_kinds1 order (items.json).
- Remaining: wielded-weapon at kill time (agent props?), L's own respawn owner (type 18), initial-sync agents' loadout, some LIST2 noise after type 5 packets.

## Update 7: weapon class = 5-bit field of type 13; full match on the clean capture
- Type 13 5-bit field (after victim/killer) = weapon class. Observed: 20 cannonball (log custom_1), 21 canister/shrapnel (custom_2; also a burst of ~40 type-6 projectiles with item 34 cannon_canister_dummy), 22 explosion (custom_3), 17 bayonet/spear, 12 sword/sabre, 5 musket/rifle bullet, 10 pistol, 0 headshot (then use the type-6 projectile item within 1 s: pistol item 6, musket 38/40/42/50...).
- Note: the log's custom_1/2/3 = artillery (cannonball/shrapnel/explosion), per the user.
- Local player's respawn: first type-18 within 10 s after the local agent dies gives the new local agent (type 5 is not sent for it). LOCAL_SLOT is hard-coded to 9 (L) in decode_kills.py; needs deriving from the join/auth data for other captures.
- decode_kills.py on full5.pkl now matches the server log for all 15 kills: killer, victim, weapon class, 4/4 teamkills.

## Update 8 - NWE bit widths (this fixed ~75% -> 95% clean packets)
NWE statics differ from NW: 0x87c328=12 (item id bits; type 6 projectile uses 12-bit item), 0x87c32c=11 (read by 0x4f5bb0, which type 7 calls: 4b, 11b, 32b, 32b, 3x17b, 4x12b - must be stepped into), 0x87c330=10 (type 20 first field).
Type 5 (agent create) on NWE: 8,2,3,8,32, 11x12b loadout, 10,10,51,10,7,7,7,1 plus 9 extra bits (constant value 6, origin unknown) -> hook h4f8b80 in t63.py.
Result: 96157/101193 NWE packets parse to the end; the rest are mostly 144-bit non-state packets.
Kills: 2031 on NWE; weapon classes almost all known (20,21,22,17,12,5,10,0); unknown 2,3,16,19.
Video check (offset -44s): of 857 video kills with both names read, 511 match killer+victim from packets (60%); most misses are garbled OCR names.

## Update 9 - standalone tool `nwkills` (deliver/nwkills.zip)
- Decoder runs from a 6k-instruction trace (nwkills/data/ins_subset.pkl, saturated: two independent samples gave identical sets) + the user's exe for data sections (sha256 ff4a28c5...).
- Per-server bit widths are auto-calibrated (packets that parse to their end): NWE X328=12, S330=10, type5 items 12b + 9 extra; NW(Wednesday) X328=10, S330=9, type5 items 10b + 8 extra; S32C=11 for both.
- Roster comes from the capture itself: <0x06><player id><u16 len><name> at any bit offset; slots are reused, so lookup uses the latest name first seen before the kill.
- NW Wednesday capture: 114273/116591 packets clean, 2792 kills, 9 min on 2 cores. NWE: 76% of video kills with known names match killer+victim.
- Teamkill labels (killer score delta -1) are consistent with a 2-team split: 6 of 2042 labelled kills violate it within 5-minute windows (random labels: 31%).

## Update 10 - list wrap-around, type 15, roster fill
- Update lists (agents and players) are not monotonic: a gap can be negative (stored as 32-bit wrap, e.g. 4294960974), restarting at low indices. idx=(idx+g)&0xFFFFFFFF fixed the Thursday server (14% -> 99.4% clean) and the last few % elsewhere.
- Type 15 = (8b player id, S324 bits state); S324 (0x87c324) is 10 on NW/Thursday, 11 on NWE. Type 5 uses the same field; remaining type-5 size is calibrated (IA,T5X).
- Names missing from join records also appear as <pid><u16 len><ASCII name> next to chat/other records; repeated sightings (or a tag-like name) fill the roster.
- Results: Thursday 84957/85458 packets clean (99.4%), 3308 kills, ~96% fully named; Wednesday 98.9%, 2801 kills; NWE 99.4%, 2031 kills, 604/759 (80%) video kills with known names match killer+victim.
- Self-inflicted kills (class 2, mostly killer==victim) count as teamkills when the killer's score drops.

## Update 11 - non-blow deaths
Type 13 mode field (2 bits): 2 = blow kill (has 9-bit hit location). Modes 0/1 have no hit location and no weapon: they were being mislabelled "headshot" (wcode 0). Most (about 80%) have an AI/unowned victim (bots/horses). Remaining player cases: mode 0/1 player victims (median respawn ~50 s, 55% never respawn -> likely leave/class change), killer agent -1 (world: fall/drown), killer==victim (class 2 mostly). Server log shows suicide = ico_punch (victim only) and leaving = ico_headshot (victim only). No ground-truth capture of these yet.

## Update 12: round detection
Signals (NWE/NW/Thursday): >=15 players' score >0 -> <=0 within 10 s (primary); type-51 flood >=500 msgs/5 s (full resync at map/round change, seen at 2215 s and 3255 s on NWE); packet gap >=2 s; spawn burst follows. Merged within 60 s. Gives 4-5 rounds per ~1 h capture (~900-1050 s each). The NWE video `round` column has 7 rounds, so some video rounds (short/dud, ~720 s and ~1286-1356 s) are not visible as score resets: unvalidated for those. Implemented in nwkills/rounds.py.

## Update 13: round signals (second pass)
- No explicit "round start" message exists among the decoded types. Searched all 50+ types on NWE/Wed/Thu.
- Type 0 (team setup: 16-bit + ten 8-bit values) + type 39 + big type-62 scene-prop blob + type-51 flood = MAP/MISSION LOAD. Matches score resets exactly: Thu 944/1959, Wed 1049/2124/3161, NWE 1280/2217/3255. (NWE 509: small type 0/11/62 pair, unexplained.)
- Types 32/33 are chat text (8-bit chars, 16-bit length). Type 59 (8-bit id 35) is not a round marker. Types 29/30 pair up during pre-round class selection.
- In-map rounds = activity lull (spawns+deaths <30% of median for >=40 s) then spawn wave. NWE check vs video: real rounds start 1440 / 2430 (video 1441 / 2427); duds after map loads 1280-1440 and 2220-2430 (video R4/R6, 9-12 kills). Implemented in nwkills/rounds.py.

## Update 14: team tickets = round signal (NWE)
- Script events ride message types 36/37/38: [7-bit 107 wrapper][32-bit event number][32-bit args...]. Module mission_templates/scripts/strings txt files from the user show the round logic (team_set_score, "New round started.", ticket-based respawns).
- NWE event 89 (type 37): args (team 0/1, tickets). Both teams reset to ~500 at round start, drop 1 per spawn, round ends when a team reaches 0. NWE capture: resets at 298.5, 1289, 2231; zeros at 1132/1176, 2043/2111, 3113/3250. Matches video round ends (1189, 2207, 3254).
- Tickets do NOT reset at lull starts (370, 1440, 2430) - those were not rounds. The video's R4/R6 "duds" are the first minutes of a ticket round before a lull.
- NW test servers (Wed/Thu) have no ticket event (their 107-wrapped events: 53, 44, 68...). They use the activity fallback.
- "X has won the round" string (id 395) is not referenced by module scripts/templates and is not sent as text in any capture; the win is presumably inferred from the ticket event / team_set_score. Not found as a message.
- Open: type 36 sub-event 68 args (12, 0|1) on NW servers appears 6-18 s before each map reload (probably map-end result). MAXSLOT=142 vs players up to ~193 on Thursday: untested.

## Update 15: server chat lines mark rounds (from the some-round-overs clip)
- Type 39 = server/admin text lines. Round markers: "Changed the map to custom map N ..." (map load), "Friendly fire will turn back on after 30 second(s)..." (same moment), "Has reset the Map." (admin reset; same moment a type-41 message with a single 1/3-bit field arrives), "Friendly fire is now on" (30 s after round start), admin lines "Reset and live", "LIVE, round N". (Update 14 said no round text exists - wrong for these.)
- NWE: map change 1280 -> warm-up 1280-1366 (36 deaths) -> reset 1366 = LIVE round 2 (tickets zero 2043) -> map change 2218 -> warm-up -> reset 2333 = LIVE round 3 (tickets zero 3113) -> map change 3255. Live round 1 = reset 298.4 -> map change 1273/1280 (tickets zero 1132). Ticket resets at 1289/2231 are map-load, not live starts; the reset at 1366/2333 does NOT reset the ticket counters (~389 stays).
- Wed has the same warm-up/reset pattern (resets 244, 1219, 2211, 3287). Thu: map changes 51/944/1959 without resets (full maps), one warm-up 1959-2003 then reset 2003.
- Still no literal "has won the round" text; round end = tickets zero, then ~2 min until the admin's map change.

## Update 16: MAXSLOT 142 -> 250
- Player ids reach ~193 (Thursday). With 250: Thu killer?/victim? rows 40 -> 2 (of 3308), Wed 3 -> 3, NWE 15 -> 16 (one row became 'player#177', name unknown). 1016 Thu rows and 6 NWE rows changed attribution (all involve slots >142); NWE changes look like fixes (self-kills became real kills, killer Jg_Bolbochan appears in the video). Thu teamkills 450 -> 535: unverified (no ground truth).

## Update 17: death-type relabelling (user spot-check, Thursday)
- Non-blow rows (mode 0/1) with a known, different killer are real kills with missing blow data -> 'kill (no blow detail)'. 'non-blow death (leave/class change?)' now only when no killer.
- Server log (NW-cleaner test): a player leaving shows as a killer-less death with weapon code 0 (ico_headshot). So weapon code 0 on world rows is shown as 'none (no weapon code)', and >=3 world deaths within 10 s = 'left server (mass world deaths)' (Thu 8 at 47:38-47:42 at event end). Isolated world deaths stay 'world (left server/fall/drown?)'.
- (Update 17 revised at user request) world deaths keep weapon 'headshot' and all get death type 'world (left server/fall)'; no separate mass-leave label.

## Update 18: restarts without 'Has reset the Map' (Thursday 3:49 and 18:20)
- "Friendly fire is now on, be careful!" (type 39) is sent N s after every round start (N = server FF delay, 30 on NWE/Thu, 20 on Wed early; announced in "Friendly fire will turn back on after N second(s)" / "set the time for friendly fire ... to N second(s)"). Start = t - N. This recovers restarts done by admin 'Slayed Everyone' + 'reset and live' with no reset line: Thu 229 s (slay at 229.4, FF-on 261.3) and 1098 s (admin 'rest and live' 1088 / 'Live' 1100; FF-on 1127.8; no other marker). Both turn the preceding map-change segment into a warm-up (Thu 51-229, 944-1098, 1959-2003).
- A reset followed by another reset within 60 s is also treated as warm-up (Wed double resets).

## Update 19: back-filling pre-sync names from later data
- Agents already in the world when the capture started only get their owner (agent prop 27) in later snapshots. For events with no earlier owner, take sightings in the next 120 s; accept only if all agree on one player (agent ids get reused). Flag 'name-from-later-data(killer|victim)'. Results: before-sync rows Thu 4->2, Wed 2->1, NWE 6->2; killer?/victim? NWE 16->5, Wed 3->1. Not verifiable against the video (OCR garbled this early).

## Update 20: scoreboard sync at join, score_gap
- The server sends every player's score (LIST2 prop0, kills - teamkills) in the first seconds after you connect (Thu 138 players at 4.7 s, NWE 31 at 3 s, Wed 30 at 2.5 s). initial + recorded kills/teamkills == later score for 129/134 (Thu), 24/31 (NWE), 24/27 (Wed) before the first round boundary. No deaths in this list (only score and ping).
- players.csv: overall kills = kills - teamkills; per-round kills/deaths/teamkills unchanged; score_gap per round = (last score - first score in the round) - recorded net; ignores samples with |score| > 150 (map-load flood junk). Non-warm-up round gaps: ~98% within +-2, ~50% exactly 0; mean slightly negative (we record a bit more than the scoreboard credits).

## Update 21: score_gap mismatch cause = my baseline, not missing kills
- The first score_gap version took the first CHANGE inside a round as the baseline; players whose score stayed 0 across the reset then lost their first kill (gap exactly -1 for ~40% of player-rounds). Fixed: baseline = value in effect 6 s after the round start (the scoreboard reset lands a few seconds after the detected boundary), carrying values forward; first segment uses the initial join batch; player-rounds with a score drop > 15 inside the round (slot reused / rejoin) are skipped. Now 88-92% of player-rounds match exactly, 95-98% within 1 (NWE 517, Thu 638, Wed 423 player-rounds).
- Per-event scoring (regression): ordinary and artillery kills score ~+1 (0.91-0.97), teamkills/self-tk ~-1, self-inflicted non-tk 0, AI victims 0, and 'kill (no blow detail)' rows with a killer score ~0 (17-30 per capture) - they are probably not real kills; still counted in totals (gap shows them).
- Scoreboard updates are sparse (649 steps for 1971 kill events on NWE), so event-level alignment is impossible; only per-round totals can be checked. Lag at round end is not a factor.

## Update 22: 'no blow' deaths with a killer are player-owned HORSES
- Agent property sets differ by kind: riders carry agent props 6/7 (and 10/11); horses do not (they show 1/2/12 instead). Victims of normal kills: 97% rider-like, 0% horse-like; victims of 'kill (no blow detail)' rows: 0% rider-like, 90% horse-like; unowned 'AI/horse' deaths: 0% rider-like, 70% horse-like. So these are the players' mounts (owner prop 27 points at the rider), killed by another player (no blow record, no score, bursts during cavalry fights).
- Implemented: tail agent props 6/7 are kept (decoder); a mode!=2 death with a known other killer, an owned victim and no prop 6/7 sighting in the previous 20 s is labelled 'horse death (player-owned mount)' and left out of kills/deaths totals. Thu 32, Wed 24, NWE 27 rows. score_gap exact-match improved to 96/92/94 % (Thu/Wed/NWE).
- Admin slays: each 'X Slayed Player Y' chat line produces a killer==victim class-2 row with NO score change (15/17 Thu, 8/8 Wed, 1/1 NWE); class-2 rows without a slay line carry a -1 score drop (suicide). Not yet relabelled in the tool.
- Admin reasons (rambo/fic/fiac) do not correlate with the no-blow rows (chance level).
- Research switch NWKEEP_ALL_AGENT_PROPS=1 keeps every agent property in the cache.

## Update 23: Friday capture - restart with no reset line (5:54)
- Friday: admin 'reset and live' at 336.3 s did NOT print 'Has reset the Map.' and sent no type-41 marker; only 'Friendly fire is now on' at 384.1 (-30 s => start 354 s = 5:54). Detected via the FF-minus-delay rule (Update 18). The user's run predated that rule, so it showed one 0-1255 'pre-live' round.
- New: a segment that contains an admin 'reset/rest/restart ... live' line (but is not the last segment / first capture segment) is a warm-up. Fixes Friday 1307-1387 (admin 'reset and live' at 1370.7 while the segment was labelled live).
- Also seen Friday: 'Swapped Everyone to Spectators' (222 s) = admin text, followed by a teamkill-heavy burst 4:22-4:47 inside the pre-live segment.

## Update 24: video-checked weapon classes (Wed clips 1-3), duplicates, stale slot names
- Clips aligned to the capture by matching killfeed lines (offsets: clip1 ~0 s, clip2 ~+120 s, clip3 ~+490 s; within ~1 s).
- Weapon code 1 = couched lance (horse+rider icon, Petrovick). Code 2 = fists (fist-with-burst icon): killer != victim = a punch kill (mete -> Anderson 562.24, IMBLACK -> A-Lad 554.23); killer == victim shows as a killer-less fist line. Code 16 = mace/club-like icon (one sighting). Code 21 = spray of small balls (canister/shrapnel). Code 20 = black cannonball. Code 0 without killer = killer-less headshot-icon line in game (leave/spectate/world: cause not visible).
- Cannon volleys: one feed line per victim, matching one row each; nothing duplicated there.
- Duplicate rows: the same death message can arrive twice 0.03 s apart; the old 6 s bucket dedupe missed pairs straddling a bucket edge (188.99/189.02). Now: same victim agent within 6 s of the last kept death is dropped.
- 'kill (no blow detail)' rows (mode 0/1, known killer) have no killfeed line (Rosita -> ? 54.06; horse deaths 32.5, 163.3): renamed 'no-blow death (mount?, not counted)' and excluded from totals.
- Stale slot names: 554.23 was named Mclean, but Mclean had moved from slot 72 to slot 84 at ~181 s and A-Lad-From-Caucasus held slot 72; the roster never saw A-Lad's join. Fix: a name that appears again (count >= 2) in another slot retires the old slot's name from that time (roster.retire_moved); fill_roster then looks for the new holder only in data after that time. Wed: 108 rows re-named (Mclean/A-Lad), Thu 4, NWE 4 (unverified by video), Fri 0.

## Update 25: Tuesday clip (capture ~120-270 s; clip t = capture - 120 s, anchored on Voltil->Piglet 119.5, BOULETTE class 3 at 121.8, cannon volley 190.2)
- Class 3 = horse charge: white horse icon with an orange burst (BOULETTE, Stanislav). The killer in the kill message is the HORSE agent, so the killer comes out '?' or a stale owner (243.82 showed UnterArzt_Kg; the feed says 1tes[MB]_Kpt_Stanislav). Open: map a horse agent to its rider.
- Class 19 = hammer/mallet icon (Sir_Edward -> Wellington x3, Antunes -> OHus_d0kam0g, Supak).
- Unknown remaining: class 14 (Fri), 23 (Thu).

## Update 26: killfeed icon table from the exe (answers all weapon classes)
- The type-13 handler (case at 0x4703b0) reads the 5-bit weapon class into a local and passes it, untouched, to 0x4bb310 (arg2). 0x4bb310 does `cmp eax,0x1a; ja default; jmp [eax*4+0x4bce0c]`; each case pushes an `<img=ico_...>` string (strings at 0x8103fc..0x810644 in .rdata, which the chat renderer shows inline).
- Table: 0 headshot, 1 couchedlance, 2 punch, 3 horseimpact, 4 bow, 5 crossbow, 6 axethrow, 7 knifethrow, 8 javelin, 9 stonethrow, 10 pistol, 11 musket, 12 swordone, 13 swordtwo, 14 axeone, 15 axetwo, 16 blunt, 17 spear, 18 morningstar, 19 maul, 20-26 custom_1..7. >26: default (no icon).
- Names are the engine's; the module supplies the art (ico_crossbow = musket art in NW, ico_spear = bayonet art). Video-confirmed: 0,1,2,3,5,12,16,17,19,20,21,22. Unconfirmed art: 14 (Fri MadCammy x2, probably the sapper axe), 23 = custom_4 (Thu, 4 rows, all killer == victim, -1 score).

## Update 27: no game exe needed any more (option 1 done)
- Logged every img_read() over all four captures (full decode, 2 jobs): only 504 bytes of the exe image are ever read (15 ranges in .text/.rdata/.data: field min/max limits and a jump table; other 'reads' are zero-fill of unmapped memory). Bundled as data/imgconst.pkl; emu.img_read uses it unless a real exe was loaded (hidden --exe, research use).
- Removed: --setup wizard, config.py, exe path resolution, sha256 warning. Verified: decoding all four captures without any exe gives packet records identical to the exe run (0 differing records of 414,000+) and byte-identical kills CSVs.
- OPTION 2 (later, requested to be remembered): fully native reader with no emulator and no ins_subset.pkl. Plan: (1) log the emulator's reads per message type on all captures to derive layouts (types seen: 5, 6, 13, 18, 28 kept + 36-39, 41 text/events/reset; tail.py is already native, types 5/6 have hand-written hooks); (2) write a native bit reader and message loop; (3) native calibration of the per-server widths (S324, S32C, S330, X328, IA/T5X); (4) validate packet-by-packet against the emulator on the four captures; (5) keep the emulator as an optional fallback for packets with unknown message types (an unknown type loses the tail: owners and scoreboard). Expected: several times faster, and no redistributed instruction trace.

## Update 28 - native message reader (option 2)
- `nwkills/nreader.py` replaces the emulator: 6-bit type, peer field (4-bit value at packet bit 64, +1), body from a layout table. Per-server widths: S324 (types 5, 15, last field of 3), S32C (7), S330 (20, 21, 52), X328 (6), IA/T5X (5). Types 5 and 6 start with an extra 10-bit field.
- Data-dependent bodies: strings = 16-bit length + bytes, skipped (not read) above a cap: 3 -> 255, 32/33/39 -> 299 (and nothing follows), 62 -> 450, 0/63/53/56 -> 49 and 399. Type 13: g bit -> 7x3, f==3 -> 7, f&1 -> 11x3, f&2 -> 9. Type 7: flag -> extra 14. Type 20: flag -> (14,S330,12). Types 43/44: trailing flag -> 20. Type 63 flag 0 -> only a 32. Types 53/56 with the third flag set are unsupported (packet skipped).
- Validation: identical to the emulator on 66,139 sampled packets across the 4 captures except 3 where the emulator produced garbage (its peer-index check reads emulated game state; native tails there end cleanly). 9,300+ synthetic packets over all 64 types with random profiles: identical apart from that same peer artifact. Full runs: 11 of ~414k packets differ, all improved; kill CSVs differ from before in a few teamkill flags only.
- Speed: 40-190 s per capture (was ~1 h). Emulator + validate script kept in nwkills_emulator_research.zip.

## Update 29 - death types confirmed by chat markers (NW-short-test-deaths capture)
Markers (chat type 33, peer 0): fall x2, suicide x2, swap team x2, disconnect x1. Matches: self+class 0 = fall; self+class 2 = suicide (slay shares packets/icon); killer-less+class 0 = team swap (agent respawns with a new team/troop; same signature as a player leaving). Own disconnect death is not in the capture. All six cost 1 point. Labels updated in cli.py/README.

## Update 30 - agent ownership is known early; blank teamkill flags were a score-baseline gap
Checked the "owner unknown for the first minute" assumption: in the short capture the local agent's owner arrives with its spawn (type 5 at 7 s) and agents already present at connect are listed in the first snapshot (agent property 27 at 1.3 s). Unresolved names in the four long captures are 9 of ~10,800 kills, mostly class-3 horse kills (killer = horse). The `before-sync` flag only labels those. The real gap: the server omits a score of 0, so a player's first score update (e.g. -1 for a teamkill/suicide) had no earlier value to subtract from and the teamkill flag stayed blank. Fix: first-ever score of -1..-3 is read against a baseline of 0. 77 extra teamkills across the four captures (47 same-team, 2 different-team, 19 unknown by agent team data).

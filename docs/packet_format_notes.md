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

## Update 31 - same event, two captures (NWEVENT vs NW-2026-11-01-sunday)
The sunday capture started 54 s after NWEVENT and stopped 24 s earlier on the shared clock (round starts line up with a 54 s shift). 3,260 kills match 1:1 by victim slot + time (median dt 0.06 s). Differences found:
1. Fake teamkills: the player score history contained random mis-read values (e.g. 222, -2615, 4020) from tail blocks of packets that did not parse cleanly; the next real score then looked like a big drop. 31 matched kills disagreed on `teamkill`. Fix (events._good_scores, default mode 3): only score updates from cleanly parsed packets, and only if repeated in >=2 packets within 1 s (the server repeats an update every tick until acknowledged) or |value|<=60. Disagreements 31 -> 1.
2. Garbage roster name: a one-packet byte coincidence produced the "name" m."_\Dt for slot 25 in one capture, replacing [RG]84th_Lt_FrenchMonk for ~30 rows. Single-sighting names must now look like names (>=6 chars, mostly alphanumeric, no quote/backslash). Also removed 2 junk names in the Friday capture.
3. Remaining ~50 rows (6 slots): one capture holds a join record for a new slot occupant that the other never received (e.g. slot 73 Pe4enbka -> Smetanka). Captures are individually incomplete; merging rosters from several captures would fix this (not implemented).
4. First minutes: horse deaths and agents that existed before the client connected resolve differently ('(AI)' vs name vs '?'); 3 real kills there name a different victim in each capture. Not counted rows (horse) except those 3.
5. Coverage: each capture has kills the other lacks at its start/end.

Correction to Update 30: owners of agents that already existed when the client connected can be unknown for the first minutes (see point 4); the 'agents listed at 1.3 s' observation held for the short test capture only.

## Update 32 - types 0 and 63 had a 12-bit-too-long field block (fixes ~1,000 unclean packets)
Pooled every packet with messages that did not parse cleanly (1,007 across 6 captures; 0.2-0.8 % per capture). 830 contained a type 0 message (server info: scene name + welcome text, sent at map change) and 177 the early type 54+63 pair. Both read `32, 16, 11, 11` after the 16-byte block (63: `... 16, 11, 11, 32`); the real field is `32, 16, 10` (63: `16, 10, 32`): 12 bits shorter. Found by locating the scene-name string (`scn_random_multi_plain_large`) and the welcome text byte-aligned inside a type 0 message and measuring the offset. The 10 is constant: it parses under both the NW and NWE profiles (S330 does not fit the NW profile).
- 1,003 of the 1,007 now parse cleanly (rest: 2 wrong-profile artefacts, 1 type 56 third-flag packet, 1 other). Clean packets over NWEVENT: 93,339 of 94,023 (684 left, all the byte-7 = 0 packets of Update 33).
- Regression over all 6 captures: same row count, same killers/victims/weapons/death types. Changes: `respawn_s` on 0.1-0.5 % of rows (12/2027, 3/2797, 4/3301, 4/2665, 4/3305, 17/3278: updates lost in these packets are now read) and `teamkill` blank -> yes on 4 rows (2 per event capture). Cross-capture agreement of respawn_s between the two NWEVENT captures 2357 -> 2362 of ~2390; teamkill agreement unchanged (3213/3215).

## Update 33 - the "message count 0" packets are queued packets with one extra leading byte (decoded)
- The game's packet handler (mb_warband.exe 0x473ca0) reads the message count as an 8-bit field with offset -1 at bit 56. When it is -1 (header byte 7 = 0) the handler does not process the packet: it copies it into a per-peer queue (0x477670, vector of 0x600-byte packet slots) and returns. The queued packet is replayed later by the loop at 0x473f54, which reads a count again from the slot's cursor (bit 64) and then the usual 4-bit peer width and messages. So such a packet is an ordinary packet preceded by one extra byte: remove byte 7 (`pl[:7] + pl[8:]`) and the normal reader and tail parser work (684 NWEVENT packets: 564 clean at once; the rest are the connect-time packets and type 53/56 cases below).
- Pooled over 6 captures: 3,744 such packets; 3,117 are pure type-62 messages (two per packet), 233 more parse cleanly with ordinary messages (types 36, 7, 25, 26, 37, 46, 39, 13 ...), ~530 do not (connect-time packets with types 53/56 third-flag branch, and packets whose first message is mis-parsed; likely the same 450-byte cap/other layouts at connect).
- Type 62 = map file transfer: `peer, 16-bit chunk index, 10-bit length, <length bytes>` with 450-byte chunks, two per packet, 350-400 chunks (157-174 KB) per map change. Reassembled it is the custom map's scene file: a text line (`scn_mp_custom_map_46 mp_custom_map_46 256 none none 0.0 0.0 100.0 100.0 -100.0 0x...`), terrain name (`outer_terrain_snow`) and then binary prop records (mesh/prop names such as `spr_barrier_20m`, `rock_snowy`, `spr_mm_sp_rich_church1`, `mm_hedge4`, 3x3 float matrices, scale 1.0 vectors). No agents, players or kills. Chunk index is 16-bit and wraps (transfers show idx up to 65535).
- The 438 type-13 messages in clean queued packets (Thu/Fri/Sun-style NW captures): all but ~8 are round-reset mass removals, not deaths. Pattern: 24-40 type-13 messages per ~1.1 KB packet, 14 packets in a row at each admin reset (Thu 229 s, 1097 s, 2000 s; Fri 221.8 s), killer == victim agent id, weapon class 2 (or class 0 with killer 0 on Fri), interleaved with ~65 type-36 script events and type-7 messages. They sit exactly on the 'map reset (live)' round boundaries (229, 1098, 2003 s in the Thu round table). Importing them would add ~430 false suicides/falls for Thursday alone; any queue handling must drop blocks of >=8 self-kills inside 1 s.
- Genuine kills inside queued packets that the CSVs miss: Thu 531.41 s (victim agent 191, killer 14, class 21), nww 2.39 s (3 kills, classes 5/12/17, connect time), nww 1758.38 s (2, class 20), nww 2569.05 s (class 17, probably the row already listed 20 ms earlier). About 7 of ~17,000 kills.
- Decision pending: stripping byte 7 in nreader/decoder (and reading the packet normally) would also clear ~3,100 not-clean packets and recover those ~7 kills, but needs the mass-block filter above; the map transfer itself is not worth decoding for the killfeed (map name is in the server text).

## Update 34 - flagbearers per round (new output `_flagbearers.csv`)
- Type 5 fields (after the peer): agent+1, owner slot+1, TROOP+1 (10 bits; S324 field), 3 bits, 8 bits, 32 bits, 11 loadout item ids (+1; 9 bits on NW servers, 11 on the NWE Tuesday server), then position etc. The troop field indexes the module's troops.txt: troop nation matches the musket's nation in 85 % of spawns and item/troop inventory overlap jumps from 0.2 % to 14 % only at offset -1 (field - 1). Examples: troop 104 = trp_british_foot_guard_nco (Brown Bess), 155 = trp_french_infantry_vistula_colours.
- The loadout ids are NOT a reliable index into item_kinds1.txt: the user's local NW file (943 items, identical to the Napoleonic_Wars.rar module and items.json) and NWE file (2267 items) do not match what the servers send (NW servers send ids up to ~503 in 9 bits, NWE up to ~1998 in 11 bits, i.e. smaller item tables), and loadouts mix nations (e.g. French musket + Russian hussar officer). Only the weapon/flag range lines up: flag ids of the NCO troops match the troop's flag item (-1 offset) in ~45 % of NCO spawns that carry a flag-range id, while the same ids also show up on non-NCO troops (armour in another table).
- Rule used: flagbearer = spawn of a troop whose inventory has a flag/colour item AND the spawned loadout contains one of that troop's flag items. 55 troops (NCOs of every nation + two French `colours` troops), 49 flag items (bundled as data/flag_troops_nw.json, derived from troops.txt/item_kinds1.txt of the NW module).
- Checks: NWEVENT, two viewpoints (own capture vs Sunday capture): 59 / 63 rows, 23 of 28 (player, flag) pairs equal, the other 5 are the known roster-slot ambiguities; nations in the output match the teams (French/Austrian, French/British, ...). Spawns per capture 3,300-7,800 after de-duplication (the server repeats a spawn message for a few ticks).
- Not done: NWE (needs the NWE module's troops.txt; the NWE item file alone is not enough, same reason), own-player respawns (type 18 only), pre-connect agents.

## Update 35 - flagbearers on NWE
Added from the NWE module's troops.txt (1,835 troops) + item_kinds1.txt (2,267 items). Troop alignment is the same (field - 1: overlap 13.4 % vs 1.5 % at offset 0; +1 gives 9.8 % because troops come in adjacent variants). NWE has dedicated `*_flag_bearer` troops (212 non-AI, bundled as data/flag_troops_nwe.json), so every spawn of one counts; the flag item (weapon types 2-4 named flag/colour, excluding 'flagcarrier' armour) is only resolved when the loadout shows it: on the Tuesday capture 92 of 272 flag-bearer spawns match a flag item of the troop, so `flag` is 'unknown' for the rest (loadout ids are unreliable outside the troop's own items, see Update 34). Tuesday: 70 rows, 17 players. The server type (nw/nwe) is chosen by the largest loadout id (above 1023 = NWE).

## Update 36 - two-perspective check (2026-11-08 captures a and b)
- a (2026-11-08_filtered) starts 321 s before b (NW-2026-11-08-sunday); rounds agree (same structure, constant shift). 2,518 kills match by victim slot + time; a-only 187 (157 before b started), b-only 20.
- Differences in matched pairs: roster-slot name ambiguity (24 victim, 12 killer, 4 killer slot), 8 respawn_s, AI/horse death rows seen from one side only, unnamed player#N victims before the roster dump.
- Suspected missed restart in first minute of a: NOT found. 0-44 s has only a trickle (about 2 spawns/5 s), fists self-kills at 12/22/33 s, then a 44-record roster dump at 44 s (client joins/receives player list), then fighting from 58.9 s (artillery kills). A real restart/reset shows as a 30-70 spawn burst within 2 s (seen at 1104, 1176, 2416, 2508 in a); none in 0-60 s. No chat line, type-41 marker, score reset or queued mass block either.

## Update 37 - making two recordings of one event give the same output (2026-11-08 pair)
Result: in the overlap 2,538 of 2,542 rows match on killer, victim, weapon, teamkill, death type and round; the 4 others are in the first 3 s of the later recording. 17 rows differ in victim only (AI deaths whose spawn the later recording missed). Per-player counts for rounds 2-4 are identical. Flagbearers identical.
Causes found and fixed:
1. rounds `death_msgs` counted raw type-13 messages; the server sends each death once per recipient peer (1-3 copies seen, depends on the capture). Now = rows of the kills file for the round.
2. events.py: owner records from the first 30 s were all stamped t=0 and ordered by slot number, so a stale value ("243", corrected to "112" a moment later) could win. Now ordered by time.
3. events.py: owner values from the agent property list of a packet whose tail did not parse to the end (L - tail_end >= 8) are garbage (e.g. slot 133/66/211 for agents owned by 33/40/130). They are ignored, as score updates already were.
4. events.py: the owner of a mount victim was guessed from the NEXT spawn of the same agent id (about 35 s later, i.e. the next life). That depends on where the capture starts. Removed for victims (victim stays unknown -> `no-blow death (mount?, not counted)`); for killers a sighting is only used before the agent's next death.
5. events.py: respawn_s uses spawn messages only (property lists also list agents that were already there).
6. roster.py: one recording carried a player's join record under header byte 0x03 (chat-style) where the other had 0x06, so slot 89 kept the wrong name for 1,000 s. Second scan with header 0x03/0x43/0x83/0xC3, accepted only for a name already known as a player name.
7. roster.py `retire_moved`: a name seen in a second slot retires its old slot also when another name takes that slot later (the stretch in between is unknown instead of the stale name); one-off sightings count if the name looks real.
Regression on the six earlier captures (same rosters rebuilt): 4-15 rows per capture lose a guessed mount-owner name (now `?`), 30-110 rows change name because rosters are more complete or garbage owner values were dropped; no weapon/teamkill changes except 1 (fri). Not touched: the suspected missed restart in the first minute of 2026-11-08_filtered (no signature found, see Update 36).

Update 37b: no-blow deaths whose victim owner is unknown are labelled `(AI/mount, owner unknown)` instead of `?` (not counted anywhere, not flagged `victim?`). Remaining `?`: 1 killer on a cavalry horse-charge kill; `player#N` for a team-swap row without a join record.
Update 37c: an unknown killer on a cavalry horse-charge kill is labelled `(AI/mount, owner unknown)` too (same cause as the victim case). It still gets the kill credit as its own pseudo-player row, so the victim's death is counted; the earlier recording of the pair shows that kill under `(AI)`.

## Update 38 - large score_gap values were a tool problem (two causes)
1. Scores were read from every packet, including the unclean map-change blocks, which hold garbage (e.g. -148, -1504, 129, 365; the filter only dropped |score| > 150). One player showed a gap of +148 and another +129. Now only clean-tail packets are used.
2. The scoreboard reset after a round start lands late (about 10 s into a live round, about 40 s after a map change), but the baseline was taken 6 s after the start, so the whole previous-round score showed up as a negative gap (-8 to -15) in the next round. Now a drop of 2 or more in the first 60 s of a round moves the baseline to the value after the drop.
Result on the 08-Nov pair: live rounds 410/460 gaps exactly 0, the rest +-1/2 (one 3-5); warm-up gaps 266 of 306 zero, max 4; no value above 5 in either recording (before: 109 per-round values >= 5, up to 148).

## Update 39 - the packets that stay unparsed after removing the queue byte (08-Nov pair)
Unclean packets: a 410 of 87,849, b 389 of 77,997; all have header byte 7 = 0 (queued). After removing byte 7: a 388 and b 382 parse clean (they hold about 500 type-5 spawns, about 400 type-6, 1 (a) / 5 (b) type-13). Left over: a 22, b 7 (0.03 % of packets), all 1,200-1,260 bytes with 41, 42, 81 or 86 messages:
- a 54-57 (t=1.8-2.1 s) and b 28-30 (t=0.9-1.1 s): the capture-start sync, n=41. Two of the four a packets stop on Unknown(53/56) (the "extra (32,1) groups" case of types 53/56); the rest parse 41 messages that do not look real (types 1,2,36,4,43,45,0,62 ...) and no message prefix gives a clean tail.
- a 30098-30099 (t=1097.0) and b 20479 (t=775.0): the map-change load (same time in both recordings), n=41/42, same behaviour.
- a 63505-63520 (16 packets, t=2409.9-2411.4) and b 53884-53886 (t=2087.3-2087.5, a-time 2408.3): round-4 map change, n=81/86. The first 58 messages parse sensibly and are identical in all 16 packets apart from the 9-bit peer field (382, 390, 398, 406 ...): message 0 = type 39 "<player> Changed the map to custom map 16 with gamemode Team Deathmatch ...", then 28 x (type 35, type 51) script-event pairs, then message 57 = type 0 server info (scene `scn_mp_custom_map_16`, "Welcome!"). Everything after message 57 is garbage (type 0 of 249 bits repeated with random bytes), so a message layout after the type-0 block is wrong or missing; no cut-off point gives a clean tail.
- The game's own reader (instruction emulator) gives the same message boundaries up to there, except that it reads type 0 as (11,11) bits where the native reader reads 10 and gets readable text, so the emulator is not a reference for type 0.
- Any type-13/5 results inside these packets come from after the point where parsing goes wrong and must not be trusted.
Conclusion: the real kills and spawns are in the 95-98 % that parse after removing the queue byte; the 29 left-over packets are connection/map-load sync traffic. Decoding them needs the layouts of the messages that follow the type-0 server-info block (and of types 53/56 with the extra groups); not needed for killfeed output.

## Update 40 - checked against the game executable (mb_warband.exe, SHA ff4a28c5..., disassembled with objdump; VA = file offset + 0x400c00 in .text)
Message dispatcher 0x46fb70, jump table at 0x473b98 (64 entries; types 53 and 56 share 0x472f52, 21 and 52 share 0x470f42). Packet reader 0x473ca0, queue vector 0xf2f8 in the per-peer block, replay loop 0x473f54.
Confirmed:
1. Queue: the message count is a ranged int (width from static 0x87c2d8, = bits(250) = 8). Count -1 stores the packet reader object and returns. When a later packet with a real count arrives and the queue is not empty, every stored packet is replayed: a SECOND count is read from the stored cursor, then a 4-bit value (+1 = peer-field width), then that many messages through 0x46fb70 with flag 1. So removing byte 7 is right. The replay never reads the tail (time block, agent and player property lists); the tail is only read for the final, non-queued packet. Tail data inside queued packets is what the server wrote at queue time; the game itself ignores it.
2. Every handler reads its fields first and only then compares the message's 'peer' field (it is a sequence number relative to the packet's base, e.g. 382, 390, 398 in the 16 map-change packets) with the last processed one, and skips the effect if it is not newer. So field widths never depend on the skip.
3. String reader 0x46e820: 16-bit length, rejected when length >= max (max 50 for the first, 400 for the second string of type 0), also when it would run past the end of the packet. Equal to the native reader (n <= 49 / n <= 399).
4. Type 13 (death): two ranged 10-bit reads, 5, 2, 1 bits as in the native table.
5. Native reader vs the game's own reader (instruction emulator) on 4,000 random packets from each of the 08-Nov recordings: 3,992 and 3,989 identical; all 19 differences are type 0 or 63.
Not settled:
6. Types 0 and 63 read TWO ranged fields of width *(0x87c320) where the native reader reads one 10-bit field. Equal only if that width is 5. The static is in .bss and no code in the exe writes it directly (the other widths like 0x87c2d4/d8 are set by constructors, e.g. push 250; call 0x47d540), so its value comes from outside the exe and cannot be read from it. The emulator uses a default (11) and so mis-reads types 0 and 63; this is why it is not a reference there. The tool's calibration does not cover this width. One packet (b 20479) only parses clean when type 0 takes 20 bits instead of 10 (any split w1+w2=20). [Solved in Update 52: it was a type 2 width, not type 0.]
7. The 29 left-over packets (Update 39) are not solved: every width and total-bit count I tried for the type-0 fields (1-60 extra bits, all splits) fails for 25 of them; the layouts of types 53/56 with the extra groups are also still unknown.

## Update 41 - where the ranged-int widths come from (exe)
The statics 0x87c2e0..0x87c33b are ONE object (this=0x87c2e0). Method 0x47dc10 (called at 0x619cd1 after the module/map data was loaded, via 0x5b6800) stores bit_length(x) into this+0x38..0x54 = 0x87c318..0x87c334:
  0x87c318 = bits(251) = 8; 0x87c31c = bits(5) = 3; 0x87c320 = bits(number of factions in the module) [game = *0x8b82a0, field +0x14140; the loader warns "Too Many Factions: %d (Max should be 128)"]; 0x87c324 = bits(*(game+0x140f4)+1); 0x87c328 = bits(*0x8b8564+1); 0x87c32c = see disasm; 0x87c330 = bits(*0x1d9dfa8); 0x87c334 = bits(30) = 5.
Only 0x87c320 (the faction width) is verified to be module dependent and fixed per module (width at most 8 for sane modules). It is read by types 0 (twice), 2 (second field) and 63 (twice), not by 53/56. Width 5 (16-31 factions) fits all 171 type-0 and 54 type-63 messages in recording a (clean tails); 4, 6, 8, 11 do not. The native reader never uses this width (types 0/63 have fixed layouts there; type 2 does occur, only inside queued packets, and its width 5 is confirmed in Update 52), so a wrong faction count cannot change any output. The per-server widths S324, S32C, S330, X328 are the same kind of module counts and are calibrated per capture. The native table's 11 for type 2 field 2 came from the emulator default; the exe says 5.

## Update 42 - the 29 leftover packets are solved
Types 53/56 (handler 0x472f52): string(50), 14, 14, string(50), 16, string(50), 16, string(50), 8, 8 (static 0x87c318), three 1-bit flags a, b, c, then IF c: repeat { 32-bit value; 1-bit 'more' } until more == 0, then the 10-bit float, then (type 53 only) 64 bits. The tool raised Unknown at c=1. With the loop and with byte 7 removed for count == -1 (queued) packets, all 29 leftover packets (22 in a, 7 in b) parse with clean tails: 24 are queued packets, 5 are 53/56 with c=1. Over all other packets of both recordings the new reader changes nothing.

## Update 43 - tool changes made
decoder.one: packets whose count byte is 0 (count -1, queued) are read with byte 7 removed; their tail is not read (the game never reads it) and rec['err']='queued' keeps them out of the clean-tail checks. nreader: types 53/56 read the list of 32-bit values with 'more' bits; type 2 field 2 is 5 bits (faction width). events.decode: self-deaths (killer == victim) are dropped when 8 or more fall within 3 s (map-change / reset blocks, now visible in queued packets).
Effect on the 08-Nov pair: overlapping rounds now agree exactly (round 1: 791 of 791 rows, round 3: 1011 of 1011). Mounts: every horse death is now '(AI/horse death)'; the 'player-owned mount' class disappeared because the spawn of the horse that died is now seen (50 of 56 in recording a come from a queued packet with owner -1) - the owner that was shown before was a stale value from an earlier life of the same agent id. A few kills that were only in queued packets were recovered (b: 4). Older captures: thu -64 and nwe -20 rows of reset-block remnants; the others +-3.

Update 43b: the reset-block filter first counted death MESSAGES, which dropped a real single self-death (b 2166.2, a 2487.1) because one death is re-sent up to 20 times while a client is slow to acknowledge (a: 20 copies, b: 3). It now counts distinct agents (8 or more within 3 s). Pair: every round now matches row for row in the overlap (round 4: 71 and 71; round 1: 791 of 791; round 3: 1011 of 1011; round 5: 627 of 627). Thursday 3,272 rows and Tuesday 2,019 (not 3,238 / 2,008): the 34 and 11 rows that were wrongly dropped are back.

## Update 44 - admin actions are announced as server text lines
Type-39 text lines: '<admin> Slayed Player <name>.', '<admin> Slayed Everyone.', '<admin> Swapped Everyone to Spectators' (also Temporary/Permanently Banned Player, Toggled Beacon on Player). Each arrives in 2 copies. Seen: fri 222.03 'Swapped Everyone to Spectators' with 61 killer-less deaths at 221.81 (the 'world' cluster); thu 'Slayed Everyone' at 229.4 and 1097.3 (the 121- and 126-agent self-death blocks); '<admin> Slayed Player X.' matches X's fist self-death within 0.1 s (a 82.8 s britishlord).
Tool: events.admin_lines parses them; cli labels the deaths (admin slay / admin: slayed everyone / admin: swapped everyone to spectators), keeps the rows, and leaves them out of kills, deaths, teamkills (the scoreboard check still sees the -1 of a slay). The 8-agent block filter in events.decode now only applies where no 'Slayed/Swapped Everyone' line is within 2.5 s. Counts: thu 397 slayed-everyone + 15 slay rows, fri 61 swapped + 7 slay, others 0-8 slay rows; 19-38 fist self-deaths per capture stay unlabelled (no line, maybe real suicides).
Open: fri warm-up round 8 (3116-3241 s) shows score gaps of -4 to -13 for many players; the scoreboard reset is not visible inside that round (only 2 drops of 3+).

## Update 45 - score gaps: three tool causes found (our own filters/rules)
1. Reset window: the late scoreboard reset (Update 38) was searched for only in the first 60 s; fri warm-up round 8 resets at +64 s (3180.1 vs round start 3116). Window now 120 s. The reset also goes UP after teamkill-only rounds (-5 -> 0); detection now uses |change| >= 2 and a new value of -1..1.
2. Unseen reset: a player whose score is not re-sent after the reset still shows last round's value (e.g. 14 while counting from 0). If the first value of the round fits counting from 0 and not from the stale value, the baseline is 0. A jump of more than 15 in either direction inside a round skips it (before: only drops); fixes a +40 where a slot's previous occupant's -40 was the baseline.
3. Teamkill flag in bursts (events.decode): dl = first score change after the kill was applied to every kill within 2.5 s, so one teamkill made a 9-kill canister volley (fri 1927.96, 33rd_Gnr_Rhino) nine teamkills (gap +20). Now n kills with total change D contain (n - D)/2 teamkills; which ones is a guess (same regiment prefix first), flagged 'teamkill?(burst)'. 6-19 rows per capture change flag; the pair stays row for row identical.
Result (gap exactly 0 / total): warm-up fri 468/633 -> 616/636 (max 13 -> 1), thu 525/634 -> 605/634, pair a 388/463 -> 424/463, b 403 -> 439; live: fri max 40 -> 12, me/fr 13 -> 7/2. Left (not investigated): fri R9 An-Old-Man-From-Africa -12, R7 Merc_John_Semen -5, me R8 sail61e_fridericus -7 (recorded kills exceed scoreboard growth), nww 4 values of 3-4.

## Update 46 - the remaining score gaps (kills flagged teamkill on a stale baseline) and the capture-start baseline
Cause of fri R9 An-Old-Man (-12), R7 Merc_John_Semen (-5), me R8 fridericus (-7), nww Veitch / firstevilbitch (-3/-4): the first kill of a round was flagged TEAMKILL because the 'score before' was last round's value (14, 7, 9, 6, 5) and the first value of the round was 1 (a jump of -13 for one kill). events.decode: a jump of 2 or more whose new value is -1..1 is a reset we did not see, so dl = the new value. Same rule for bursts (base = 0 when the first value cannot be reached from the old one by these kills).
Burst bug found while checking: the burst window ran past the end of the round and counted the reset to 0 (nww 280-285 s: four real teamkills counted as two). The window now stops at a reset (change of 2 or more to -1..1 from a value of 2 or more away from 0) or at a value the n kills cannot explain.
Capture start: the first score we see for a player already contains the kills of that very moment (a 268.9 / 27.3: 3 and 2 kills counted twice, gaps +-3/-4); kills within 0.1 s of that first sample are not counted for round 1.
Result (score_gap exactly 0 / values; max): pair a live 290/303, warm 301/306, pre-live 155/157 (max 1-2); fri live 441/444 (max 1), warm 491/494; thu live 458/473 (max 2); nww live 330/332; me live 567/579 (max 2). No gap of 3 or more remains except nwe pre-live 1erRI_FusV_TA_BOULETTE +3 (3 cavalry horse-charge kills at 43.4, 121.8, 128.4 s whose killer is the horse of an unknown owner, so the credit goes to (AI); the scoreboard gives it to the rider) and me/fr overall +-4 for one player.

## Update 47 - killer of a cavalry charge kill from the scoreboard
Horse-charge kills (weapon class 3) whose horse has no known owner (killer '(AI)' / '?'): events.decode looks for players whose score changes by exactly 1 within [t-0.3, t+2.5] and that is not explained by one of their own kills (own kill within [change-2.5, change+0.3]). If exactly one player qualifies, that player is the killer (teamkill if the change is -1), review flag 'name-from-later-data(killer-from-score)'. Each score change is used once.
Result: assigned 10 of 13 horse-charge rows in each recording of the pair (still row for row identical), nwe 7 of 8, thu 5 of 5, fri 1 of 1, me/fr 12 of 16. The Tuesday +3 gap (1erRI_FusV_TA_BOULETTE) is gone. No score gap of 3 or more remains in live, warm-up or pre-live rounds; me/fr keep one overall value of 4 (19th_Chevalier_Suczkalow, -2 in each of two live rounds), not investigated.

## Update 48 - artillery volleys with no score change; horse-charge killer matching refined
1. 19th_Chevalier_Suczkalow (-2 in two live rounds): an artillery gunner whose two-kill volleys (2015.37 and 3808.69) produced NO scoreboard update. The server only sends a score when it changes, so "no update after n kills" means net change 0, i.e. n/2 teamkills + n/2 kills. events.decode burst pass: with no observation in the group window, an even n and a known prior score, D = 0 and tk = n/2 (guess by regiment prefix, flag 'teamkill?(burst)'). Suczkalow's gap is gone; me/fr overall max is now 2.
2. Horse-charge killer from score, refined (replaces the rule of Update 47). Every +-1 change of a player that one of his own kills explains (same sign, change within [kill-0.3, kill+2.5]) is set aside first. The changes left over belong to kills we could not attribute. A charge kill with an unknown owner takes the player of the only leftover change in its window; assignments repeat, so a change claimed by a neighbouring charge kill is no longer a rival. Old rule: any unrelated own kill near the change disqualified a player, and two players with +1 inside one window blocked both rows.
Why several players could change near one charge kill with nobody's own kill explaining it (checked row by row, pair recording a): row 1304.01 had slot 154 +1 at 1304.01 and slot 50 +1 at 1306.28; the second change was explained by slot 50's own kill 1306.28, which the old window (change-2.5..change+0.3) put at the edge. The other two unresolved rows (2300.46, 2348.91) had no candidate at all (the rider's score change was not sent or was merged into a later one). So the earlier general statement "several players" applied to one of three rows, not all.
Result: horse-charge rows credited a 13/13, b 13/13, nwe 7/8, thu 5/5, fri 1/1, me 13/16, fr 13/16. Score gaps: no value >= 3 anywhere; max 2 (thu live, me/fr pre-live). Pair stays row for row identical (rounds 1-5: 791/42/1011/71/627 matches).

## Update 49 - fist self-deaths without an admin line; icon 4 self-deaths
Checked 8 captures: 232 class-2 self-deaths have no admin line for the victim within 15 s (6 followed by 'Revived Player', 2 by 'Toggled Beacon on'). Admin verbs seen: Slayed Player/Everyone, Swapped Everyone to Spectators, Revived Player/Everyone, Healed Player/Everyone, Teleported Player, Toggled Beacon/Freeze, bans, map change/reset; only slay and swap kill. Falls are already separate (self + class 0, Update 29). Label renamed 'self-inflicted: suicide (no admin line)'; totals unchanged.
Class 23 (ico_custom_4) self-deaths: 20, only in pair round 3 (8: 1688, 2096, 2152, 2264-2282 x4, 2393 in recording a) and thu round 7 (4, two at the same instant 2679.44); different maps; no chat line; cause unknown (module hazard/script). Whether they are drownings is untested: no drowning ground truth exists.

## Update 50 - icon 4 (class 23) = drowning, confirmed
Capture + video 2026-11-11 (recording_contains_drowning.pcapng, 2026-11-11_17-57-46.mkv): the player walks off a quay and drowns; the video shows the underwater view and 'Respawning in 2 seconds'. The capture has exactly one class-23 row: 33rd_Bdr_Umbra killer = victim at 37.13 s, score -1 (flagged teamkill like other self-deaths). So the 20 earlier class-23 self-deaths (pair round 3: 8; thu round 7: 4; both captures of the pair counted) are drownings, in clusters of players going into water together. Labels: weapon 'drowning', death type 'self-inflicted: drowning', no weapon? flag.
The same capture has a class-24 (ico_custom_5) volley at 19.04 s: one killer (Faramir_Rogers) kills 4 players and himself in the same instant, plus one more at 20.23 (killer slot 36 unnamed): an explosion-type module weapon (barrel/mine?), not yet identified.

## Update 51 - horse-charge killer from score: tiered window, same-player changes
events.decode: a charge kill first looks at leftover score changes within [t-0.3, t+0.5] (the update that arrives with the kill), then within [t-0.3, t+2.5]; it is credited when all candidates in the window belong to one player (he may have two changes there: the nearest is used; nwe 2566.26 had two leftover +1 of slot 51 and was blocked before). me/fr 494.29: slot 35 changed exactly at the kill, while 7 other players got +1 in the same later tick at 496.02, so the tight window picks slot 35.
Result: nwe 8/8, me/fr 14/16 (was 7/8 and 13/16), pair/thu/fri unchanged (13/13, 5/5, 1/1); pair still row for row identical. The 2 left in each of me/fr (338.84 and 1311.22 in me; 284.96 and 1257.31 in fr) have no score change of the right size within -4/+8 s of the kill (every nearby change is explained by the player's own kill): no change of any size (also checked +-2 and larger, i.e. merged updates) occurs in that window for any player; the values there are only re-sends. A merged update is therefore not the cause. Most likely a riderless/ownerless horse (rider dead or dismounted) killed the victim, which earns nobody a point; not verified (no rider data for the horse agent). Score gaps unchanged.
Faction count: the native reader does not use it (see Update 41), so item closed.

## Update 52 - packet b 20479 solved; faction width 5 confirmed on NW and NWE
b 20479 (t = 775.0, the map-change load) is a queued packet (9832 bits, 42 messages: 17 x type 3, 17 x type 4, 4 x type 7, 2 x type 2, one each of 1 and 5). It has no type 0 or 63 at all. The old note that it parses clean only with 20 bits for type 0 came from reading it with the emulator's default width 11 for type 2 field 2 and then searching for a layout that happened to fit. With the faction width 5 the native reader reads all 42 messages and leaves 38 bits, the normal remainder of a queued packet (320 of 389 queued packets in b leave 42; the rest 35-41 or about 140 when the unread tail carries data). Widths 2-4 and 6-11 leave 1000-5700 bits.
Type 2 does occur: 7 queued packets in b (login / map-load bursts, e.g. 0.9-1.1 s, 775.0 s, 2087.3-2087.5 s), 107 over the eight captures (a 22, b 7, fr 13, fri 20, me 13, nwe 13, nww 7, thu 12). In every one of them width 5 leaves a normal 35-42 bit remainder and widths 4 and 6 leave 1000+ bits (a few coincidental small values at 4 or 6 in single packets of nww/fri/me/thu). So the faction count is 16-31 on NW and on NWE (both the 'nwe' Tuesday capture and the NW ones), confirmed from data and not just from the exe.

## Update 53 - last score gaps (>= 2): team swaps cost a point; artillery pairs that look like a reset
1. World deaths (killer agent -1) where the victim respawns (a team swap) cost 1 point: thu 34 of 36 have a -1 within 3 s, me/fr 4 of 6; those where the victim does not respawn (left the server) show no change (thu 28 of 33, me/fr 20 of 20; the few exceptions were not looked at one by one). The score check (cli) now counts a respawning world death as -1 in the recorded net (not in kills/deaths/teamkills). thu 12th_21infdspjnfdsf (two swaps, no kills, gap -2) is explained.
2. events.decode burst pass: the first score change after an artillery group is taken as the group's own even when it looks like a reset (3 -> 1 after two kills at 93.18 in me/fr, MAXVERSTAPPEN, is two teamkills; before it was read as a reset to 1, one teamkill, gap -2). Only later changes can stop the burst as a reset.
Result: no score gap above 1 in any capture (before: me/fr/thu 2). Players with a gap of 1 per capture: a 3, b 2, nwe 1, thu 9, fri 2, me 2, fr 2 (out of about 750-1260 player-rounds each); not investigated one by one. Gap exactly 0: a 763/766, b 764/766, nww 1035/1035, nwe 738/739, thu 1098/1107, fri 1078/1080, me 1260/1262, fr 1262/1264. Pair still row for row identical.

## Update 54 - the 2026-11-01 pair (me = NWEVENT, fr = NW-2026-11-01-sunday) compared row for row
The two recordings are of the same event; me started 53.95 s before fr (me time = fr time + 53.95) and ends 24 s earlier in event time. Inside the window both cover, 3270 (me) and 3271 (fr) rows; compared by killer/victim slot, weapon, teamkill and death type 3269 match. By names 3265 match; the rest:
1. Names (fixed for round 2: 16 rows): me never saw the join record of 33rd_Ens_Embertina (slot 5). Its only roster entry for slot 5 was sail61e_fridericus at 3654 s, so the lookup (which uses the first known name for earlier times) gave sail61e_fridericus to everything that slot did before, 16 rows in round 2 alone. sail61e_fridericus held slot 188 until 3654, so it cannot have held slot 5 before: roster.fill_roster(early=...) now looks for a name sighted before that first entry (here the 'Embertina' string at 326 s, seen only bit-shifted in the packets) and keeps the later names; the rule only applies to slots whose first name provably held another slot earlier. Side effect in thu: one world death (412.22, slot 162) now reads 2e_Inv_Omakase instead of 92nd_LCpl_Lapje (the latter joined the slot later).
2. Names not fixable from me's data: slot 141 (me knows only 33rd_LGrd_Uganda888 from 589 s; fr also has Nr31[FKR]_UWfm_mem before: 2 rows near 341 s fr) and slot 16 at the end of the capture (me still says [CER]4pp_Rek_Bartosz1944PL, fr knows 33rd_Ens_Embertina rejoined at 3637: 2 rows at 3815/3822 fr).
3. 102nd_Racer_MissCh > 2e_CdB_Grimnar (me 55.72, fr 2.51): the teamkill flag differs: fr's capture starts at that moment, so its score baseline is the first value it sees.
4. 2e_CrbV_Soolic > [RG]boc (fr 1343.43 = me 1397.4, teamkill): me never received that death; me's packets 1396.5-1398 are a run of queued packets (client stalled), and me's roster is rebuilt around 1400 s.
So: not row for row identical (it was 3249 of 3270), but all differences come from the two recordings lacking information at different moments; within the shared window 3265 of 3270 match by names and 3269 by slots.

## Update 55 - rounds 2 and 4 of NW-2026-11-11-wednesday wrongly live
Round 2 (45-475): map change (TDM on custom map 2, then custom map 5 at 67-72 s, 430 s of play), next boundary another map change (Battle at 475), no reset ever followed. Old rule: warm-up only when a map change is followed by a reset, so it became live. In all eight older captures no live round ever started with a map change (only a 39 s, 0-death tail at the end of nwe), so a map change segment is now always a warm-up (review: 'map change, no admin reset followed' when no reset came next).
Round 4 (663-903): an unannounced reset (no 'Has reset the Map' line, found via the reset marker / friendly-fire message), then the admin briefing ('Round 1 | Cavalry Skirmish at Benavente' 823.8, 'form up at spawn' 838.4, 'Live on Reset!' 895.5) and the real reset at 903.4. The warm-up rule for 'admin says reset ... live' did not match 'Live on Reset!' (live before reset); both word orders match now.
Effect: this capture's live rounds are 5, 7, 9, 11 (R12, a 196 s map-change tail with 6 deaths, is also warm-up now); the other eight captures are unchanged except nwe round 7 (39 s tail, 0 deaths: live -> warm-up).

## Update 56 - 2026-11-11 event: w (NW-2026-11-11-wednesday) vs f (2026-11-11_filtered); w1 = w
NW-2026-11-11-wednesday_1.pcapng is byte-identical to NW-2026-11-11-wednesday.pcapng (same md5): one recording uploaded twice, identical outputs. f is a second recorder that started 1109.36 s later (f time = w time - 1109.36) and ends 1224 s earlier in event time (2835 vs 4168 s of w; f ends at w 3944).
Round kinds agree: f R3/R5/R7 live = w R7/R9/R11, f R2/R4/R6 warm-up = w R6/R8/R10; f R1 (0-123, pre-live) lies inside w R5 (live).
Within f's span, compared with 2 s time tolerance: 3135 rows match after the first 11 s; no row exists only in f (0). 37 rows exist only in w, all in the first 10.6 s of f (f's first 15 s are queued packets: the client was still joining; deaths announced before it was connected are never sent to it). 13 of the 3135 matched rows differ by name only, all placeholders or stale names:
 - w: player#25 (8 rows, 3423-3957 w) where f has Nr31[FKR]_ZgF_MrRifleman: in w slot 25 has KimStarling until 2513 and a vacated marker at 3129, the new occupant is only sighted at 3330.
 - f: player#55 (3 rows) and player#139 (1) where w has [L-G]_IzmL_Danikomoty_Rd / 12th_LtCol_Nova (f never saw those joins).
 - slot 105 (2 rows, w 1386 and 1696): w says [L-G]_IzmL_Muerto_Maj (first sighted 2555), f says PG_Hdr2B_F_Verdier (sighted from f 269 = w 1378): f is right; w's lookup falls back to the first known (later) name.
A fill-in of slots that have names but are unnamed at later events (names first sighted after the last known occupant) fixed slot 25 but changed 20+ rows in five other captures, some from a name to a placeholder, so it was not kept; placeholder names remain where a capture never saw the join.

## Update 57 - the client's teamkill test, and team data in the packets
Exe (sha256 ff4a28c5...): the kill message is built in the agent-death routine around 0x4bb310; the "killed teammate" text (string ui_value_killed_teammate, 0x8103d8) is pushed at 0x4bc658 / 0x4bc746. Test: team(agent) = agent+0x7b4 clamped to 0..7 (getter 0x4a1c20, invalid -> 7); teamkill iff relation[victim_team*13 + killer_team] == 1 in the mission's relation table (base 0x8b829c+0xb648, 1 = friendly) and killer != victim. Two branches by viewpoint (killer is you or friendly to you: colour 0xff881100; enemy killing his own teammate: 0xff33dd11); normal kills 0xffff4422. The server sends no teamkill flag. Update 1's note ("composed in 0x4bb310") is correct only for the routine as a whole.
Packets: agent team is the 3-bit field of the agent-spawn message (type 5, 4th value after the peer field: [agent+1, owner+1, 8-bit, team? no: 10-bit troop field, 3-bit team, ...]). The agent property list carries no team (all properties 0-28 tested). Agreement of 'killer team == victim team' with the old score-based teamkill label: 08-Nov-b 2204/2204, 08-Nov-a 2334/2334, fri 2484/2495, me 2780/2791, nww 2621/2636, thu 2880/2896. The disagreements were almost all volley guesses (the old burst rule picked the wrong kills of a volley) plus 1-3 single kills per capture.
Implemented: events.decode uses the teams when both agents have a spawn message (killer and victim must be player-owned and the death a normal kill); score change otherwise. Volleys with all teams known skip the guess; mixed volleys guess only among the unknown kills. New review flag 'teamkill?(score disagrees)' for single kills where the killer's score change contradicts the teams. Regression on 10 captures: row counts and all other columns identical; teamkill changes in 0-16 rows per capture (counts change by at most 2), burst flags 15-57 -> 0, score_gap unchanged (the gaps are not caused by the volley guesses). Remaining disagreements: 11 single kills over 10 captures, not resolved (candidates: a team swap costing the killer a point at the same moment, a stale team of a re-used agent id).

## Update 58 - names missed by the roster scan
A missed name is not always a missed join message. The roster used to be built by a byte scan for `06 <id> <len> 00` at 8 bit shifts, which matches only one of the layouts of the join record. The record is a normal type-3 message: [flag (1 or 2 bits), player id (8), name length (16), characters (8 each)], and the flag width changes what the bytes before the id look like. Example: PG_Hdr2B_F_Verdier (id 106) in w packets 43068/43069 was fully present and cleanly decoded, but the scan found nothing (preceding bytes 06 00 03 6a 12 00). Parsed join messages gave 186 name entries in w against 175 from the scan (12 only by parse, 1 only by scan: S81 id 128).
Implemented: decoder.one keeps rec['joins'] = [(id, name)] for every type-3 message that has that shape; roster.merge_joins adds them (before retire_moved); the byte scan stays as a backup. New names per capture: 1-15 (a 1, b 4, f 4, fr 2, fri 1, me 5, nwe 15, nww 9, thu 7, w 12). Regression vs update 57: same row counts; only killer/victim names change (stale or player#N -> the right name), review flags follow, and 2 thu rows move from 'self-inflicted: suicide (no admin line)' to 'admin slay' once the name matches the slay line. A cache written before this change has no join records and does not get the extra names until it is regenerated.

## Update 59 - the open teamkill/score disagreements and the score gaps
Teamkill cross-check (12 flags over 10 captures = 8 distinct events, the same ones in both recordings of an event). Two causes: (1) the killer's score change was read against a baseline from an earlier round: the scoreboard starts a round at 0 without sending it, so 0 -> 1 on an enemy kill looked like 2 -> 1. Where the baseline predates the kill's round the teams and the score agree on 194 of 196 kills (w) and 252 of 254 (fri); the flag is now not raised for those. (2) Two kills by one player less than 0.1 s apart share one score window (3 -> 4 -> 3 read as +1 for the second): no check when the same killer has another kill within 3 s. 0 flags remain; no other column changed.
Score gaps (per player per round): 26 non-zero -> 12 (of ~12,000 player-rounds). (a) A team swap costs 1 point also when the player is not seen respawning within 2 minutes: the scoreboard shows exactly -1 at that death (3 of 53 respawn-less killer-less deaths in w; the other 50, mostly players leaving, show no change). (b) The round-end 'slayed everyone' rows were counted as a self-death worth -1 (and carried teamkill=yes in the kills file when the score reset made dl negative); admin rows are now skipped in the gap and the teamkill column is blank for them.
Second pass, every remaining gap looked at (26 -> 2): (c) a slot that changes hands inside a round (the next player's join) mixed two players' scores and events: such a slot-round is left out of the gap (Cpt_Matues, OptischeMissgeburt, Rek_Vasyl, Dubenskyet). (d) A kill and then a drowning 0.1 s apart (fitri): each has its own score step (5, then 4), but the first step was read for both; events of one player with different timestamps now take the steps in order when their number matches (the drowning costs a point, teamkill=yes like the other self-deaths). Events with the same timestamp are a volley and are left to the volley code. (e) An admin 'Has reset the Map' can zero the scoreboard well after the detected round start (Pur1n: teamkill at 3508, reset message at 3513.3, score -1 -> 0): the gap window now starts at a reset message within 60 s of the round start.
Left: giggadigga (fri, warm-up: score -1 at 3180.1, no event of his own at that moment) and 1st_Inf_Lecture (thu, warm-up: a world death with a respawn and no score change; stale -1 from the previous round). Single samples. Warm-up swaps do normally cost a point (23 of 25 in thu), so no rule was added.

## Update 60 - who a horse-charge kill belongs to: the client's rider field
User: horses can move on their own and bump into players; the killfeed attributes a bump death by a ridden horse to its rider; horses do not spawn without a rider. How the exe does it: the killfeed routine 0x4bb310 takes the killer agent id from the type-13 message; if that agent's kind field (+0x28) is 1 (a mount) and its rider field (+0x118) holds an active agent (id < agent count, agent+4 != 0), the killer becomes that rider. Writers of the field: network message type 30 (dispatch table 0x473b98, case 30 -> 0x471de3): two 10-bit values read through 0x46e0a0 with minimum -1, i.e. horse agent = raw-1, rider agent = raw-1, raw 0 = nobody (dismount); and local mount code (0x4d09f3), and the field is cleared (-1) in the agent removal paths (0x411648 and others).
In the packets the rider of a horse is therefore known from (1) the SPAWN: the rider's type-5 message (it has an owner) is directly followed by the horse's type-5 message (owner none, team 0, 4th value = same troop id as the rider); the ids are not adjacent in general, the message order is the pairing; the agent list sent when the client connects (first seconds of a capture) is in no useful order and must not be used for pairing (it gave the wrong rider for 3 nwe rows); (2) later type-30 messages: a new rider mounting an existing horse (e.g. nwe horse 51: spawned with one rider, Stanislav mounts it at 153 s, the kill at 243.8 s is his - video-confirmed earlier) or raw 0 for a dismount. The agent property list has no rider property.
Earlier in this session I concluded from the score alone that 5 charge kills had a 'runaway horse'. That was wrong for most: they have a rider by pairing or link (w 14:15: slot 98; fr 4:44: slot 109; w 13:44 and 27:40 = f 9:10).
Implementation: decoder keeps rec['links'] (type 30). events.decode builds, per horse, the entries (spawn pairing after 30 s, links), takes the latest since the horse's latest spawn message and replaces the killer of a charge kill (weapon class 3) by that rider unless it is gone (raw 0, rider died or re-spawned since); everything else (owner slot, teams, score) then runs on the rider as for any kill. A horse without a usable entry or with a gone rider goes to the score matching of Update 51/48 first (a rider who died 1.8 s before the kill still got the point on the scoreboard: w 52:14 = f 33:45); only if no player's score claims it either it is '(runaway horse)' (review flag 'runaway-horse', no kill credit in the players file and the GUI Players tab, the victim's death counts). No entry at all and nobody's score: '(AI)'.
Result over the 10 captures (101 charge rows): 93 from pairing/link or already named, 6 from the score, 1 distinct kill left riderless (fr 20:57 = me 21:51: the rider got off 0.4 s before). Killers of all rows that had one are unchanged apart from the two w rows that were '(AI)' (13:44, 27:40), now named and consistent with f; score gaps unchanged (2).

## Update 61: capture without Wireshark (pktmon)
- Windows' built-in `pktmon` (admin) captures all UDP at the adapters (`--comp nics --pkt-size 0`, circular log, 4096 MB), `pktmon etl2pcap` gives pcapng (linktype Ethernet, tsresol 6).
- Same event captured with Wireshark and pktmon at once: both decode to the same server flow (106,478 packets) and identical results (2634 kills, players/rounds/flagbearers byte-identical; one kill row differs by 0.01 s in time_s).
- pktmon file had 458k packets (Wireshark 520k) of which 224k are the game flow in both directions; pruning to that flow took 132 MB to 90 MB (not the large saving first guessed).
- nwkills/capture.py: streaming (mmap) pcapng reader/writer, `prune()`, pktmon command wrappers; GUI Capture tab.

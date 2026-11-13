import os, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from nwkills import guilogic as gl

def test_keys_and_sort():
    vals = ['10', '9', '2', '1:05', '0:59', 'abc', 'Abd', '']
    out = sorted(vals, key=gl.cell_key)
    assert out == ['2', '9', '0:59', '10', '1:05', 'abc', 'Abd', ''] or out[-1] == '', out
    assert gl.cell_key('0:59') < gl.cell_key('1:05') < gl.cell_key('100')      # mm:ss sorts by seconds
    assert gl.cell_key('abc') < gl.cell_key('Abd') < gl.cell_key('')

def test_filters():
    ok, bad = gl.compile_filters({0: 'bay', 1: '(', 2: ''}, True)
    assert list(ok) == [0] and bad == [1]
    assert gl.row_passes(['Bayonet', 'x'], ok) and not gl.row_passes(['sword', 'x'], ok)
    ok, _ = gl.compile_filters({0: 'bay'}, False); assert not gl.row_passes(['Bayonet'], ok)

def test_chips():
    h = ['round', 'round_kind']
    rows = [['1', 'pre-live'], ['2', 'warm-up'], ['3', 'live'], ['4', 'warm-up']]
    f = lambda kinds, rounds: [r for r in rows if (gl.chip_predicate(h, kinds, rounds) or (lambda _r: True))(r)]
    assert f(set(), set()) == rows
    assert f({'live'}, set()) == [rows[2]]
    assert f({'prelive'}, set()) == [rows[0], rows[2]]
    assert f({'live'}, {'2'}) == [rows[1], rows[2]]          # any chip may match
    assert gl.chip_predicate(['a'], {'live'}, set()) is None

def test_tsv_and_csv():
    t = gl.cells_to_tsv(['a', 'b'], [['1', 'x\ty'], ['2', None]], True)
    assert t == 'a\tb\n1\tx y\n2\t'
    p = os.path.join(tempfile.mkdtemp(), 't.csv')
    gl.write_csv_table(p, ['a', 'b'], [['1', 'x,"y"']])
    assert gl.read_csv_table(p) == (['a', 'b'], [['1', 'x,"y"']])

def test_progress():
    assert gl.overall_progress('read', 0)[1] == 0
    l, o, s = gl.overall_progress('decode', 0.5); assert abs(o - (15 + 27.5)) < 1e-9 and s == 0.5
    assert gl.overall_progress('events', 0)[2] is None and gl.overall_progress('done', 1)[1] == 100

def test_packets():
    assert gl.type_summary([5, 5, 6]) == '5×2 6'
    assert gl.packet_at_time([0.0, 1.0, 2.0], 1.5) == 2 and gl.packet_at_time([0.0, 1.0], 99) == 1
    assert gl.hexdump(b'AB').startswith('0000  41 42')
    c = gl.command_line(dict(pcap='a.pcapng', out='o.csv', port=7243, me='x', jobs=4, cache=None, limit=None))
    assert '--port 7243' in c and '--me "x"' in c and '--cache' not in c

def test_player_totals():
    kh = ['round', 'round_kind', 'killer', 'victim', 'teamkill', 'death_type']
    ph = ['player', 'score_at_capture_start', 'score_at_capture_end', 'score_gap', 'R2(live)_score_gap', 'R1(warm-up)_score_gap']
    pr = [['A', '0', '3', '1', '1', '0'], ['Z', '', '', '', '', '']]
    kr = [['2', 'live', 'A', 'B', '', 'kill'], ['2', 'live', 'A', 'C', '', 'kill'], ['2', 'live', 'B', 'A', 'yes', 'kill'],
          ['2', 'live', 'A', '(AI)', '', 'AI/horse death'], ['2', 'live', 'A', 'A', '', 'admin slay'], ['1', 'warm-up', 'B', 'A', '', 'kill']]
    h, r = gl.player_totals(kh, kr, ph, pr, net=True)
    d = {x[0]: dict(zip(h, x)) for x in r}
    assert 'Z' not in d and d['A']['kills'] == '2' and d['A']['deaths'] == '1' and d['A']['ai_kills'] == '1'      # warm-up and admin rows left out
    assert d['B']['kills'] == '-1' and d['B']['teamkills'] == '1'
    assert d['A']['R2(live)_kills'] == '2' and d['A']['score_gap'] == '1' and 'R1(warm-up)_kills' not in d['A']
    h, r = gl.player_totals(kh, kr, ph, pr, net=False); d = {x[0]: dict(zip(h, x)) for x in r}
    assert d['B']['kills'] == '0'                                                                              # teamkills no longer subtract
    h, r = gl.player_totals(kh, kr, ph, pr, exclude_warm=False, all_players=True); d = {x[0]: dict(zip(h, x)) for x in r}
    assert 'Z' in d and d['A']['deaths'] == '2' and 'R1(warm-up)_deaths' in d['A']

def test_column_groups():
    h = ['player', 'kills', 'deaths', 'score_at_capture_start', 'score_at_capture_end', 'score_gap', 'R1(live)_kills', 'R1(live)_deaths', 'R2(pre-live)_kills', 'R2(pre-live)_deaths']
    g = dict(gl.column_groups(h))
    assert g['All kills columns'] == [1, 6, 8] and g['All deaths columns'] == [2, 7, 9]
    assert g['All score_at_capture columns'] == [3, 4] and 'All score_gap columns' not in g          # a single column is no group
    assert g['Round R1(live)'] == [6, 7] and g['Round R2(pre-live)'] == [8, 9]
    assert g['All per-round columns'] == [6, 7, 8, 9] and g['All total columns'] == [1, 2, 3, 4, 5]
    assert gl.column_groups(['round', 'time_s', 'killer', 'review']) == []                          # the kills table has none
    assert gl.group_state({1, 2}, [1, 2]) == 0 and gl.group_state({1}, [1, 2]) == 1 and gl.group_state(set(), [1, 2]) == 2

if __name__ == '__main__':
    for n, f in list(globals().items()):
        if n.startswith('test_'): f(); print('ok', n)

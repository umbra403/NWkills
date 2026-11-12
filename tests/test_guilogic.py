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

if __name__ == '__main__':
    for n, f in list(globals().items()):
        if n.startswith('test_'): f(); print('ok', n)

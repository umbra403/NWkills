import os, re, subprocess, sys, tempfile
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, os.path.join(ROOT, 'packaging'))
import make_version_info as mv

def test_data_folder_holds_only_plain_tables():
    # the data folder is bundled whole into the executables: only the two flag tables and the item table belong there
    bad = [f for f in os.listdir(os.path.join(ROOT, 'nwkills', 'data')) if not f.endswith('.json')]
    assert not bad, 'unexpected files in nwkills/data (nothing derived from the game may ship): %s' % bad

def test_version_resource():
    ver = mv.read_version(); assert len(ver) == 3
    d = tempfile.mkdtemp()
    for exe in ('nwkills', 'nwkills-gui'):
        p = os.path.join(d, exe + '.txt'); mv.main([p, '--exe', exe]); t = open(p, encoding='utf-8').read()
        assert "StringStruct('ProductName', 'nwkills')" in t and "'%s'" % '.'.join(map(str, ver)) in t
        compile(t[t.index('VSVersionInfo'):], exe, 'eval')            # a valid expression, as PyInstaller reads it
    assert mv.tag_numbers('v0.4') == (0, 4, 0) and mv.tag_numbers('v0.4.1') == (0, 4, 1) and mv.tag_numbers('x') is None

if __name__ == '__main__':
    for n, f in sorted(globals().items()):
        if n.startswith('test_'): f(); print('ok', n)

import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from nwkills.rounds import boundary_messages

def rec(t, *bnd): return dict(t=t, bnd=list(bnd), msgs=[], txt=[], ev=[])

def test_repeats_are_one_boundary():
    recs = [rec(10.0, ('map', 0)), rec(10.03, ('map', 1)), rec(10.06, ('map', 2), ('map', 3)), rec(10.1, ('reset', 0)), rec(10.14, ('reset', 1)),
            rec(25.0, ('reset', 0)), rec(25.04, ('reset', 1)), rec(40.0, ('map', 0)), rec(46.0, ('map', 190)), rec(46.5, ('map', 0))]
    assert boundary_messages(recs) == [(10.0, 'map'), (10.1, 'reset'), (25.0, 'reset'), (40.0, 'map'), (46.5, 'map')]

def test_duplicate_delivery_and_old_caches():
    assert boundary_messages([rec(5.0, ('reset', 0)), rec(5.5, ('reset', 0))]) == [(5.0, 'reset')]       # same count again at once: a duplicate
    assert boundary_messages([rec(5.0, ('reset', 0)), rec(9.0, ('reset', 0))]) == [(5.0, 'reset'), (9.0, 'reset')]
    assert boundary_messages([dict(t=1.0, msgs=[], txt=[], ev=[])]) is None      # decoded before the messages were kept

if __name__ == '__main__':
    test_repeats_are_one_boundary(); test_duplicate_delivery_and_old_caches(); print('ok')

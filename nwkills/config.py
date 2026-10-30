"""Remembers the path to mb_warband.exe so it only has to be set once (setup wizard)."""
import json, os, sys

def config_path():
    base = os.environ.get('APPDATA') or os.path.join(os.path.expanduser('~'), '.config')
    return os.path.join(base, 'nwkills', 'config.json')

def load():
    try:
        with open(config_path(), encoding='utf-8') as f: return json.load(f)
    except Exception:
        return {}

def save(cfg):
    p = config_path(); os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, 'w', encoding='utf-8') as f: json.dump(cfg, f, indent=2)
    return p

CANDIDATES = [
    r'C:\Program Files (x86)\Steam\steamapps\common\MountBlade Warband\mb_warband.exe',
    r'C:\Program Files\Steam\steamapps\common\MountBlade Warband\mb_warband.exe',
    r'D:\SteamLibrary\steamapps\common\MountBlade Warband\mb_warband.exe',
    r'D:\Steam\steamapps\common\MountBlade Warband\mb_warband.exe',
    r'E:\SteamLibrary\steamapps\common\MountBlade Warband\mb_warband.exe',
    r'C:\Program Files (x86)\Mount&Blade Warband\mb_warband.exe',
    os.path.expanduser('~/.steam/steam/steamapps/common/MountBlade Warband/mb_warband.exe'),
]

def _ask(prompt):
    try: return input(prompt).strip().strip('"').strip("'")
    except EOFError: return ''

def wizard():
    """Interactive first-run setup. Returns the saved exe path or None."""
    print('\n=== nwkills setup (only needed once) ===')
    print('The tool needs your own copy of mb_warband.exe (Warband 1.174, the Napoleonic Wars build).')
    print('It is only read, never changed.\n')
    found = [c for c in CANDIDATES if os.path.isfile(c)]
    exe = None
    if found:
        print('Found: ' + found[0])
        if _ask('Use this one? [Y/n] ').lower() in ('', 'y', 'yes'): exe = found[0]
    while exe is None:
        p = _ask('Paste the full path to mb_warband.exe (or press Enter to cancel): ')
        if not p: print('Setup cancelled.'); return None
        if os.path.isdir(p): p = os.path.join(p, 'mb_warband.exe')
        if os.path.isfile(p): exe = p
        else: print('  Not found: %s\n  Tip: in Explorer, shift+right-click the file > "Copy as path".' % p)
    cfg = load(); cfg['exe'] = os.path.abspath(exe)
    print('Saved to %s\nRe-run this any time with:  nwkills.exe --setup\n' % save(cfg))
    return cfg['exe']

def resolve_exe(cli_exe, interactive=None):
    """--exe wins; otherwise the saved path; otherwise run the wizard."""
    if cli_exe: return cli_exe
    exe = load().get('exe')
    if exe and os.path.isfile(exe): return exe
    if exe: print('Saved path no longer exists: %s' % exe)
    if interactive is None: interactive = sys.stdin is not None and sys.stdin.isatty()
    if not interactive:
        sys.exit('No mb_warband.exe configured. Run "nwkills.exe --setup" once (or pass --exe PATH).')
    return wizard()

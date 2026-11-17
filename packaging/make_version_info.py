# nwkills - read the Mount & Blade: Warband Napoleonic Wars killfeed from a Wireshark capture.
# Copyright (C) 2026 the nwkills authors. Licensed under the GNU General Public License v3.0 or later; see LICENSE.
"""Writes the Windows version resource that PyInstaller embeds in the executables.

Single source of the version number: __version__ in nwkills/__init__.py. Product name and version are the same in every build
(code signing services check this).

  python packaging/make_version_info.py OUT.txt --exe nwkills|nwkills-gui      write the resource file
  python packaging/make_version_info.py --check-tag v0.4.0                      fail unless the tag matches __version__
"""
import argparse, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRODUCT = 'nwkills'
DESCRIPTIONS = {'nwkills': 'nwkills - Napoleonic Wars killfeed reader (command line)', 'nwkills-gui': 'nwkills - Napoleonic Wars killfeed reader (window)'}

def read_version():
    m = re.search(r"^__version__\s*=\s*'(\d+)\.(\d+)\.(\d+)'", open(os.path.join(ROOT, 'nwkills', '__init__.py')).read(), re.M)
    if not m: sys.exit("nwkills/__init__.py must contain a line like: __version__ = '0.4.0'")
    return tuple(int(x) for x in m.groups())

def tag_numbers(tag):
    m = re.fullmatch(r'v?(\d+)\.(\d+)(?:\.(\d+))?', tag)
    return None if not m else (int(m.group(1)), int(m.group(2)), int(m.group(3) or 0))

def resource(exe, ver):
    v4, text = ver + (0,), '.'.join(map(str, ver))
    return f"""# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(filevers={v4}, prodvers={v4}, mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', 'the nwkills authors'),
      StringStruct('FileDescription', '{DESCRIPTIONS[exe]}'),
      StringStruct('FileVersion', '{text}'),
      StringStruct('InternalName', '{exe}'),
      StringStruct('LegalCopyright', 'Copyright (C) 2026 the nwkills authors. GPL-3.0-or-later'),
      StringStruct('OriginalFilename', '{exe}.exe'),
      StringStruct('ProductName', '{PRODUCT}'),
      StringStruct('ProductVersion', '{text}')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""

def main(argv=None):
    ap = argparse.ArgumentParser(); ap.add_argument('out', nargs='?'); ap.add_argument('--exe', choices=sorted(DESCRIPTIONS)); ap.add_argument('--check-tag')
    a = ap.parse_args(argv); ver = read_version()
    if a.check_tag:
        if tag_numbers(a.check_tag) != ver: sys.exit('tag %s does not match __version__ %s: bump nwkills/__init__.py before tagging' % (a.check_tag, '.'.join(map(str, ver))))
        return
    if not (a.out and a.exe): ap.error('give OUT.txt and --exe')
    open(a.out, 'w', encoding='utf-8').write(resource(a.exe, ver))

if __name__ == '__main__': main()

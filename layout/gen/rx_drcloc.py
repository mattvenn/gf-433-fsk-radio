#!/usr/bin/env python3
"""Print the first locations of each category in a KLayout DRC report: python3 layout/gen/rx_drcloc.py <lyrdb> [n]."""
import sys, re, collections
import xml.etree.ElementTree as ET
r = ET.parse(sys.argv[1]).getroot()
n = int(sys.argv[2]) if len(sys.argv) > 2 else 4
seen = collections.defaultdict(list)
for it in r.iter('item'):
    cat = it.findtext('category')
    v = it.find('values')
    txt = ' '.join((x.text or '') for x in v) if v is not None else ''
    if len(seen[cat]) < n:
        seen[cat].append(txt[:160])
for c, l in seen.items():
    print(c)
    for t in l:
        print('   ', t)

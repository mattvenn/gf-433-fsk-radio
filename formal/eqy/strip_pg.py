#!/usr/bin/env python3
"""Strip the power pins from a gf180mcu netlist (VDD / VSS ports and declarations, the cells' VDD / VSS / VNW /
VPW connections). With --canon, print a canonical form instead (one statement per line, declarations and cell
instances sorted), for comparing two netlists.
Usage: strip_pg.py [--canon] netlist.v"""
import re
import sys

canon = '--canon' in sys.argv
txt = open(sys.argv[-1]).read()
txt = re.sub(r'\n\s*(VDD|VSS),', '', txt)                              # module port list
txt = re.sub(r'\n\s*inout\s+(VDD|VSS);', '', txt)                      # port declarations
txt = re.sub(r'\.(VDD|VSS|VNW|VPW)\((VDD|VSS)\)\s*,?\s*', '', txt)     # cell pins
txt = re.sub(r',(\s*)\)', r'\1)', txt)                                 # a trailing comma left behind
if not canon:
    sys.stdout.write(txt)
    sys.exit()
stmts = [' '.join(s.split()) for s in txt.split(';')]
stmts = [re.sub(r'\( ', '(', re.sub(r' \)', ')', s)) for s in stmts if s]
head = [s for s in stmts if s.startswith('module')]
body = sorted(s for s in stmts if not s.startswith('module'))
print('\n'.join(head + body))

#!/bin/bash
# Set up a fresh sim-server pod for this repo. Idempotent: run it on every new pod, before any run.
# Pods are stateless (mixed-signal-asic skill, workflow.md): on 2026-11-25 the pod was replaced and took the git
# identity, the credential helper and the pinned magic build with it, as well as every result in build/.
#   bash tools/pod_setup.sh          (repo root, IIC-OSIC-TOOLS image)
# 1. git identity (repo-local, only if none is set)
# 2. git credential helper that reads $GITHUB_TOKEN at push time (the token itself is never written to disk)
# 3. magic 8.3.642 in ~/.local/magic642 (8.3.684, the image's, drops node-to-substrate C; layout/gen/pex*.sh use it)
# 4. ~/.designinit for gf180mcuD
# 5. tt-support-tools beside the repo
# 6. the Python modules the run scripts import
# Ends with the tool versions, and exits non-zero if any step failed.
set -u
cd "$(git rev-parse --show-toplevel)" || exit 1
ok=1
say() { echo "pod_setup: $*"; }

# 1. git identity
# (both: on 2026-11-25 the pod's global config had user.name but no user.email, and commits failed)
[ -n "$(git config user.name)" ] || { git config user.name "Matthew Venn"; say "git user.name set (repo-local)"; }
[ -n "$(git config user.email)" ] || { git config user.email "matthewvenn@gmail.com"; say "git user.email set (repo-local)"; }

# 2. credential helper
if [ -n "${GITHUB_TOKEN:-}" ]; then
  git config credential.helper '!f() { echo username=x-access-token; echo "password=$GITHUB_TOKEN"; }; f'
  git ls-remote -q origin HEAD > /dev/null 2>&1 && say "github access OK" || { say "github access FAILED"; ok=0; }
else
  say "GITHUB_TOKEN not set: the driver cannot push progress or results"; ok=0
fi

# 3. magic 8.3.642, built with Tcl (the pex scripts are Tcl). The image has the Tcl / Tk 8.6 runtime libraries but no
#    headers or tclConfig.sh and no root (no apt), so Tcl / Tk 8.6.14 are built from source into ~/.local/tcl86 first.
M=$HOME/.local/magic642
T=$HOME/.local/tcl86
TV=8.6.14
if [ ! -s "$T/lib/tclConfig.sh" ] || [ ! -s "$T/lib/tkConfig.sh" ]; then
  say "building Tcl / Tk $TV into $T (a few minutes)"
  S=$(mktemp -d)
  for p in tcl tk; do
    tag=core-${TV//./-}
    ( git clone -q --depth 1 --branch "$tag" "https://github.com/tcltk/$p" "$S/$p" \
      && cd "$S/$p/unix" && ./configure --prefix="$T" $( [ $p = tk ] && echo --with-tcl="$T/lib" ) > "$S/$p.configure.log" 2>&1 \
      && make -j"$(nproc)" > "$S/$p.make.log" 2>&1 && make install > "$S/$p.install.log" 2>&1 ) \
      || { say "$p build FAILED, logs in $S"; ok=0; break; }
  done
fi
if ! "$M/bin/magic" -dnull -noconsole --version 2>/dev/null | grep -q '^8\.3\.642'; then
  say "building magic 8.3.642 into $M (a few minutes)"
  S=$(mktemp -d)
  ( git clone -q --depth 1 --branch 8.3.642 https://github.com/RTimothyEdwards/magic "$S/magic" \
    && cd "$S/magic" && ./configure --prefix="$M" --with-tcl="$T/lib" --with-tk="$T/lib" > "$S/configure.log" 2>&1 \
    && grep -q "Tcl/Tk: *yes" "$S/configure.log" \
    && make -j"$(nproc)" > "$S/make.log" 2>&1 && make install > "$S/install.log" 2>&1 ) \
    || { say "magic build FAILED, logs in $S"; ok=0; }
fi
v=$("$M/bin/magic" -dnull -noconsole --version 2>/dev/null | tail -1)
[ "$v" = 8.3.642 ] && say "magic $v in $M" || { say "magic in $M is '$v', not 8.3.642"; ok=0; }

# 4. the PDK: without ~/.designinit the image defaults to IHP (PDK=ihp-sg13g2 on 2026-11-25), and magic, netgen and
#    KLayout then load the wrong technology. New shells read it; sim/verify/full_run.sh also exports these itself.
D=$HOME/.designinit
if ! grep -q '^PDK=gf180mcuD' "$D" 2>/dev/null; then
  printf 'PDK_ROOT=/foss/pdks\nPDK=gf180mcuD\nSTD_CELL_LIBRARY=gf180mcu_fd_sc_mcu7t5v0\n' > "$D"
  say "wrote $D (gf180mcuD)"
fi
[ -d /foss/pdks/gf180mcuD ] && say "PDK gf180mcuD present" || { say "PDK /foss/pdks/gf180mcuD missing"; ok=0; }

# 4b. tt-support-tools beside the repo (layout/gen/tile.py reads its gf180mcuD analog DEF; main, as the project used)
TT=$(dirname "$PWD")/tt-support-tools
[ -d "$TT/tech/gf180mcuD" ] || git clone -q --depth 1 https://github.com/TinyTapeout/tt-support-tools "$TT" \
  || { say "tt-support-tools clone FAILED"; ok=0; }
[ -s "$TT/tech/gf180mcuD/def/analog/tt_analog_2x2_pgvaa.def" ] && say "tt-support-tools OK ($(git -C "$TT" rev-parse --short HEAD))" \
  || { say "tt-support-tools: the 2x2 analog DEF is missing"; ok=0; }

# 5. Python modules
python3 -c "import numpy, scipy, matplotlib, yaml" 2>/dev/null && say "python modules OK" \
  || { say "python modules missing: $(python3 -c 'import numpy, scipy, matplotlib, yaml' 2>&1 | tail -1)"; ok=0; }

echo "--- tools"
echo "image magic: $(magic -dnull -noconsole --version 2>&1 | head -1)"
echo "ngspice: $(ngspice -v 2>&1 | grep -m1 ngspice)"
echo "netgen: $(timeout 20 netgen -batch quit < /dev/null 2>&1 | grep -m1 -i netgen)"
echo "klayout: $(timeout 20 klayout -v < /dev/null 2>&1)"
echo "cores: $(nproc)"
[ "$ok" = 1 ] && say "done" || { say "done with FAILURES (above)"; exit 1; }

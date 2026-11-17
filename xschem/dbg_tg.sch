v {xschem version=3.4.5 file_version=1.2
}
G {}
K {}
V {}
S {}
E {}
T {ctrl_b} 240 330 0 0 0.3 0.3 {}
T {dbg_tg: debug switch onto the ua[0] bus} -400 -420 0 0 0.7 0.7 {}
T {MTn 2/0.28, MTp 4/0.28 um in parallel; ctrl = 1: on (tt 27 C: R_on 0.84 / 1.17 / 1.25 kOhm at 0.3 / 1.65 / 3.0 V, off C on mod 6.4 fF)} -400 -360 0 0 0.42 0.42 {}
T {Ic 1/0.28 / 0.42/0.28 makes ctrl_b; source: sim/rx/dbg_tg.py (S: wn 2.0, wp 4.0, L 0.28)} -400 -326 0 0 0.42 0.42 {}
N 20 0 40 0 {}
N 180 0 160 0 {}
N 20 -30 20 -80 {}
N 180 -30 180 -80 {}
N 20 -80 100 -80 {}
N 100 -80 180 -80 {}
N 100 -80 100 -150 {}
N 100 -150 -400 -150 {}
N 20 30 20 80 {}
N 180 30 180 80 {}
N 20 80 100 80 {}
N 100 80 180 80 {}
N 100 80 100 150 {}
N 100 150 500 150 {}
N -190 275 -190 350 {}
N -190 350 -190 425 {}
N -150 305 -150 350 {}
N -150 350 -150 395 {}
N -150 275 -130 275 {}
N -150 425 -130 425 {}
N -400 350 -300 350 {}
N -300 350 -190 350 {}
N -300 350 -300 0 {}
N -300 0 -20 0 {}
N -150 350 300 350 {}
N 300 350 300 0 {}
N 300 0 220 0 {}
N -400 560 -340 560 {}
N -400 620 -340 620 {}
C {devices/iopin.sym} -400 560 0 1 {name=p4
lab=VDD}
C {devices/iopin.sym} -400 620 0 1 {name=p5
lab=VSS}
C {devices/ipin.sym} -400 350 0 0 {name=p3
lab=ctrl}
C {devices/iopin.sym} -400 -150 0 1 {name=p1
lab=mod}
C {devices/iopin.sym} 500 150 0 0 {name=p2
lab=bus}
C {symbols/nfet_03v3.sym} 0 0 0 0 {name=MTn
L=0.28u
W=2.0u
nf=1
m=1
ad=1.0p
as=1.0p
pd=5.0u
ps=5.0u
nrd=0
nrs=0
sa=0
sb=0
sd=0
model=nfet_03v3
spiceprefix=X
val="2/0.28"}
C {symbols/pfet_03v3.sym} 200 0 2 0 {name=MTp
L=0.28u
W=4.0u
nf=1
m=1
ad=2.0p
as=2.0p
pd=9.0u
ps=9.0u
nrd=0
nrs=0
sa=0
sb=0
sd=0
model=pfet_03v3
spiceprefix=X
val="4/0.28"}
C {symbols/gnd.sym} 40 0 0 0 {name=l1
lab=VSS}
C {symbols/vdd.sym} 160 0 0 0 {name=l2
lab=VDD}
C {symbols/pfet_03v3.sym} -170 275 0 0 {name=Icp
L=0.28u
W=1.0u
nf=1
m=1
ad=0.5p
as=0.5p
pd=3.0u
ps=3.0u
nrd=0
nrs=0
sa=0
sb=0
sd=0
model=pfet_03v3
spiceprefix=X
val="1/0.28"}
C {symbols/nfet_03v3.sym} -170 425 0 0 {name=Icn
L=0.28u
W=0.42u
nf=1
m=1
ad=0.21p
as=0.21p
pd=1.8399999999999999u
ps=1.8399999999999999u
nrd=0
nrs=0
sa=0
sb=0
sd=0
model=nfet_03v3
spiceprefix=X
val="0.42/0.28"}
C {symbols/vdd.sym} -130 275 0 0 {name=l3
lab=VDD}
C {symbols/vdd.sym} -150 245 0 0 {name=l4
lab=VDD}
C {symbols/gnd.sym} -130 425 0 0 {name=l5
lab=VSS}
C {symbols/gnd.sym} -150 455 0 0 {name=l6
lab=VSS}
C {symbols/vdd.sym} -340 560 0 0 {name=l7
lab=VDD}
C {symbols/gnd.sym} -340 620 0 0 {name=l8
lab=VSS}

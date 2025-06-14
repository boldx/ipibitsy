#slave status octet: 68
#major status: 93
#comex 101
#position control: 35
import time
from collections import defaultdict

from serial import Serial
from ipibitsy import IpiPhy, IpiL1, IpiPhyState, BusCtlTyp, BusCtlDir, PhyCtrlState, IpiDataBus

ser = Serial("/dev/ttyACM0")
phy = IpiPhy(ser)
ipi = IpiL1(phy)

ipi.apply_state(PhyCtrlState.IDLE, IpiDataBus(True, 0))
print('Transfer settings:', ipi.request_transfer_settings(2))
print("Select:", ipi.select(2))
print("Tranfer in")
while True:
    rx, slavack = ipi.info_transfer_in()
    print("Received data:", rx, slavack)
    if not rx:
        break

stat = defaultdict(list)
print("Transfer out")
for x in range(1):
    #cmd = b"\x00\x09\x00\x01\x41\x00\x02" + bytes([i]) + b"\x02\x51\x20"
    # cmd = b"\x00\x06\x00\x01\x42\x00\x02\xff"
    #cmd = b"\x00\x06\x00\x01\x02\x00\x02" + bytes([i])
    #cmd = b"\x00\x0A\x00\x01\x02\x00\x02\xff\x03\x6c\x40\x6A"
    #cmd = b"\x00\x10\x00\x01\x51\x00\x02\xff\x09\x31\x00\x00\x00\xFF\x00\x00\x00\x00"
    #cmd = b"\x00\x06\x00\x01" + bytes([x]) + b"\x00\x02\xff"
    cmd = b"\x00\x06\x00\x01\x03\x01\x02\xff"
    print("Out slavack:", ipi.info_transfer_out(cmd))

    print("======================")

    time.sleep(0.5)

    print("Tranfer in")
    rx, slavack = ipi.info_transfer_in()
    print("Received data:", rx, slavack)

    params = rx[10:]
    off = 0
    while off < len(params):
        plen = params[off]
        param = params[off + 1:off + plen + 1]
        print(plen, param, param.hex())
        off += plen + 1
        # if param != b'\x17\x10\x00\x00\x00\x00\x00':
        #    input("?")
        stat[x].append(param)

    if not rx:
        break

for e in stat:
    print(e, stat[e])
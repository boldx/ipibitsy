import struct
import time
from enum import Enum


class BusCtlTyp(Enum):
    OP_CMD_OR_RESP = 0
    OP_CMD = 0
    OP_RESP = 0
    DATA = 1


class BusCtlDir(Enum):
    INFO_OUT = 0
    INFO_IN = 1


class SelectStatus(Enum):
    OK = 0
    BUSY = 1


class OctetMode(Enum):
    SOM = 0
    DOM = 1


class XferMode(Enum):
    INTERLOCKED = 0
    STREAMING = 1


class PhyCtrlState(Enum):
    RESETSEL_1 = 0b00101
    REQUEST = 0b00100
    REQACK = 0b01100
    RESETSEL_2 = 0b01101
    IDLE = 0b00000
    SELECT = 0b10000
    DESEL = 0b01000
    BUSCTL = 0b11001
    BUSACK = 0b11011
    SLAVACK = 0b11000
    MASTEND = 0b11010
    SLAVEND = 0b10100
    XFRRDY = 0b11100
    XFRST = 0b11110
    XFRRES = 0b11111
    XFREND = 0b11101
    MAINT1 = 0b00001
    MAINT2 = 0b00011
    MAINT3 = 0b01011
    MAINT4 = 0b01001


def odd_parity_lut():
    lut = []
    for i in range(256):
        n = 0
        for bi in range(8):
            if i & (1 << bi):
                n += 1
        lut.append(not bool(n & 1))
    return tuple(lut)


class IpiDataBus:

    parity_lut = odd_parity_lut()

    def __init__(self, dir, value, parity=None):
        self.dir = bool(dir)
        self._value = value
        if parity is None:
            self.parity = self.parity_lut[self._value]
        else:
            self.parity = bool(parity)

    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, value):
        if value < 0 or value > 255:
            raise ValueError('Value should be in [0, 255]')
        self._value = value
        self.parity = self.parity_lut[value]

    @property
    def parity_valid(self):
        return bool(self.parity) == self.parity_lut[self._value]

    def __str__(self):
        d = "O" if self.dir else "I"
        pv = "+" if self.parity_valid else "-"
        return f"{d}|{self.value:02X}|{int(self.parity)}|{pv}"


class IpiPhyState:

    def __init__(self,
                 busa=None, busb=None,
                 attn_in=False, sla_in=False, sync_in=False, sync_out=False, mst_out=False, sel_out=False):
        self.busa = busa or IpiDataBus(False, 0, False)
        self.busb = busb or IpiDataBus(False, 0, False)
        self.attn_in = bool(attn_in)
        self.sla_in = bool(sla_in)
        self.sync_in = bool(sync_in)
        self.sync_out = bool(sync_out)
        self.mst_out = bool(mst_out)
        self.sel_out = bool(sel_out)

    @property
    def ctrl_flags_value(self):
        return self.sync_out << 0 | self.sync_in << 1 | self.mst_out << 2 | self.sla_in << 3 | self.sel_out << 4

    @property
    def ctrl_state(self):
        return PhyCtrlState(self.ctrl_flags_value)

    @ctrl_state.setter
    def ctrl_state(self, phy_ctrl_state):
        value = phy_ctrl_state.value
        self.sync_out = bool(value & (1 << 0))
        self.sync_in = bool(value & (1 << 1))
        self.mst_out = bool(value & (1 << 2))
        self.sla_in = bool(value & (1 << 3))
        self.sel_out = bool(value & (1 << 4))

    def __str__(self):
        state, etc = f"unknown", ""
        try:
            state = self.ctrl_state.name
        except ValueError:
            etc = f" SEL: {int(self.sel_out)}, SLAI: {int(self.sla_in)}, MSTO: {int(self.sync_out)}, " + \
                  f"SYNI: {int(self.sync_in)}, SYNO: {int(self.sync_out)}"
        return f"State: {state: <7} - BUS A: {self.busa}, BUS B: {self.busb}, ATTN: {self.attn_in}" + etc

    def __repr__(self):
        return str(self)

class IpiPhy:

    def __init__(self, ser):
        self._ser = ser
        self.history = []
        self.get_state(force=True)

    def get_state(self, force=False):
        cc = b"\x02" if force else b"\x00"
        req = b"\xC1\xCA" + cc
        return self._send_req_wait_resp(req + b"\x00" * (64 - len(req)))

    def set_state(self, state):
        req = self._encode_state(state)
        return self._send_req_wait_resp(req)

    def _send_req_wait_resp(self, req):
        self._ser.write(req)
        #print('req', req)
        resp = self._ser.read(63)
        # print('resp', resp)
        if not resp.startswith(b"\xC1\xCA"):
            raise ValueError(f'Malformed response: {resp}')
        n_states = resp[3]
        if n_states > 0:
            self.history = []
        for i in range(n_states):
            off = 4 + i * 2 * 3
            state = self._decode_state(resp[off: off + 2 * 3])
            print(state)
            self.history.append(state)
        return self.history[-1]

    def drop_history(self):
        last = self.history[-1]
        self.history = [last]

    def _decode_state(self, raw):
        porta, portb, portc = struct.unpack("<HHH", raw)
        busa = IpiDataBus(porta & (1 << 15), porta & 0xFF, porta & 0x100)
        busb = IpiDataBus(portb & (1 << 9), portb & 0xFF, portb & 0x100)
        state = IpiPhyState(
            busa, busb,
            portc & (1 << 13), portc & (1 << 14), portc & (1 << 15),
            portb & (1 << 12), portb & (1 << 13), portb & (1 << 14)
        )
        return state

    def _encode_state(self, state):
        porta = state.busa.value
        if state.busa.parity:
            porta |= 0x100
        if state.busa.dir:
            porta |= (1 << 15)
        portb = state.busb.value
        if state.busb.parity:
            portb |= 0x100
        if state.busb.dir:
            portb |= (1 << 9)
        if state.sync_out:
            portb |= (1 << 12)
        if state.mst_out:
            portb |= (1 << 13)
        if state.sel_out:
            portb |= (1 << 14)
        raw = b"\xC1\xCA\x01" + struct.pack("<HH",porta, portb)
        return raw


class IpiL1:

    def __init__(self, phy):
        self.phy = phy
        self.phy_state = phy.get_state()
        self.apply_state(PhyCtrlState.IDLE, IpiDataBus(False, 0), IpiDataBus(False, 0))
        self.wait_for_state(PhyCtrlState.IDLE, 0.5)

    def wait_for_state(self, state, timeout):
        self.wait_for_any_of_states((state,), timeout)

    def wait_for_any_of_states(self, expected_states, timeout):
        self.phy.drop_history()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.phy_state = self.phy.get_state()
            for state in self.phy.history:
                if state.ctrl_state.value in (s.value for s in expected_states):
                    return
            time.sleep(0.1)
        else:
            raise TimeoutError(f"None of the state (out of {expected_states}) reached in {timeout} s: {self.phy.history}")

    def apply_state(self, ctrl_state, busa=None, busb=None):
        if busa:
            self.phy_state.busa = busa
        if busb:
            self.phy_state.busb = busb
        if busa or busb:
            self.phy.set_state(self.phy_state)
        if ctrl_state:
            self.phy_state.ctrl_state = ctrl_state
            self.phy.set_state(self.phy_state)

    def request_interrupts(self, class1=False, class2=False, class3=False, pwr_on=False,
                           pwr_fail=False, report_rdy=False, report_busy=False):
        self.wait_for_state(PhyCtrlState.IDLE, 0.5)
        req = (class1 << 0) | (class2 << 1) | (class3 << 2) | (pwr_on << 3) | (pwr_fail << 4) | \
               (report_rdy << 5) | (report_busy << 6)
        if not req:
            raise ValueError("At least one interrupt type have to be selected")
        phy_state = IpiPhyState(IpiDataBus(True, req))
        self.phy.set_state(phy_state)
        phy_state.mst_out = True
        self.phy.set_state(phy_state)
        time.sleep(0.25)
        self.phy_state = self.phy.get_state()
        resp = self.phy_state.busb.value
        slave_addrs = [i for i in range(8) if resp & (1 << i)]
        self.phy.set_state(IpiPhyState(mst_out=False))
        time.sleep(0.25)
        return slave_addrs

    def request_facility_interrupts(self, slave_addr, facility_range, class1=False, class2=False, class3=False):
        self.wait_for_state(PhyCtrlState.IDLE, 0.5)
        req = class1 << 0 | class2 << 1 | class3 << 2
        if not req:
            raise ValueError("At least one interrupt type have to be selected")
        req |= (1 << 7) | (slave_addr << 4)
        phy_state = IpiPhyState(IpiDataBus(True, req))
        self.phy.set_state(phy_state)
        phy_state.mst_out = True
        self.phy.set_state(phy_state)
        self.wait_for_state(PhyCtrlState.REQACK, 0.5)
        if not self.phy_state.busb.parity_valid:
            raise ValueError("Parity error")
        resp = self.phy_state.busb.value
        irqs = tuple(v for k, v in {0: "CLASS1", 1: "CLASS2", 2: "CLASS3"} if resp & (1 << k))
        self.phy.set_state(IpiPhyState(mst_out=False))
        self.wait_for_state(PhyCtrlState.IDLE, 0.5)
        return irqs

    def request_transfer_settings(self, slave_addr):
        self.wait_for_state(PhyCtrlState.IDLE, 0.5)
        req = (1 << 7) | (slave_addr << 4)
        phy_state = IpiPhyState(IpiDataBus(True, req))
        self.phy.set_state(phy_state)
        phy_state.mst_out = True
        self.phy.set_state(phy_state)
        self.wait_for_state(PhyCtrlState.REQACK, 0.5)
        if not self.phy_state.busb.parity_valid:
            raise ValueError("Parity error")
        resp = self.phy_state.busb.value
        xfr_settings = {
            'MM_cap': (1, 2) if resp & (1 << 6) else (1,),
            'xfrm_cap': tuple(v for k, v in {2: XferMode.INTERLOCKED, 3: XferMode.STREAMING}.items() if resp & (1 << k)),
            'octetm_cap': tuple(v for k, v in {0: OctetMode.SOM, 1: OctetMode.DOM}.items() if resp & (1 << k)),
            'xfrm_curr': XferMode.STREAMING if resp & (1 << 5) else XferMode.INTERLOCKED,
            'octetm_curr': OctetMode.DOM if resp & (1 << 4) else OctetMode.SOM
        }
        self.phy.set_state(IpiPhyState(mst_out=False))
        self.wait_for_state(PhyCtrlState.IDLE, 0.5)
        return xfr_settings

    def select(self, slave_addr, change_xfrm=False, change_octetm=False, prio_hold=False, prio_select=False):
        self.wait_for_state(PhyCtrlState.IDLE, 0.5)
        req = (slave_addr << 4) | (change_xfrm << 3) | (change_octetm << 2) | (prio_hold << 1) | (prio_select << 0)
        self.apply_state(PhyCtrlState.SELECT, IpiDataBus(True, req, parity=0), IpiDataBus(False, 0))
        self.wait_for_state(PhyCtrlState.SLAVACK, 0.5)
        # TODO: "To detect multiple selection. the master must wait until all slaves have had enough time to respond."
        resp = self.phy_state.busb.value
        if resp == (1 << slave_addr):
            return SelectStatus.OK
        elif resp == 0:
            return SelectStatus.BUSY
        else:
            self.apply_state(PhyCtrlState.IDLE, IpiDataBus(False, 0), IpiDataBus(False, 0))
            raise ValueError(f"Unexpected BUS B select status: {resp} ({bin(resp)})")

    def select_facility(self, slave_addr, facility_addr):
        self.wait_for_state(PhyCtrlState.IDLE, 0.5)
        req = (1 << 7) | (slave_addr << 4) | facility_addr
        phy_state = IpiPhyState(IpiDataBus(True, req))
        self.phy.set_state(phy_state)
        phy_state.sel_out = True
        self.phy.set_state(phy_state)
        self.wait_for_state(PhyCtrlState.SLAVACK, 0.5)
        # TODO: "To detect multiple selection. the master must wait until all slaves have had enough time to respond."
        resp = self.phy_state.busb.value
        # I'm not sure if the response is a "Select Status octet" or a "Slave Status octet"
        if resp - 1 == slave_addr:
            return SelectStatus.OK
        elif resp == 0:
            return SelectStatus.BUSY
        else:
            self.phy.set_state(IpiPhyState())
            raise ValueError(f"Unexpected BUS B select status: {resp} ({bin(resp)})")

    def master_reset(self):
        self.apply_state(PhyCtrlState.MAINT1, IpiDataBus(False, 0), IpiDataBus(False, 0))

    def selective_reset(self, slave_addr, reset_control):
        req = (slave_addr << 4) | reset_control
        phy_state = IpiPhyState(IpiDataBus(True, req))
        self.phy.set_state(phy_state)
        phy_state.mst_out = True
        self.phy.set_state(phy_state)
        time.sleep(0.25)
        phy_state.sync_out = True
        self.phy.set_state(phy_state)
        time.sleep(0.25)
        phy_state.sync_out = False
        self.phy.set_state(phy_state)
        time.sleep(0.25)
        phy_state.mst_out = False
        self.phy.set_state(phy_state)

    def bus_control(self, typ=BusCtlTyp.OP_CMD_OR_RESP, dir=BusCtlDir.INFO_IN, params=0):
        self.wait_for_state(PhyCtrlState.SLAVACK, 0.5)
        req = params
        if typ == BusCtlTyp.DATA:
            req |= (1 << 7)
        if dir == BusCtlDir.INFO_IN:
            req |= (1 << 6)
        self.apply_state(PhyCtrlState.BUSACK, IpiDataBus(True, req), IpiDataBus(False, 0))
        self.wait_for_state(PhyCtrlState.BUSACK, 0.5)
        resp = self.phy_state.busb.value
        busack = {
            'val': resp,
            'typ': BusCtlTyp.DATA if resp & 0x80 else BusCtlTyp.OP_CMD_OR_RESP,
            'dir': BusCtlDir.INFO_IN if resp & 0x40 else BusCtlDir.INFO_OUT,
            'params': resp & 0x3F
        }
        self.apply_state(PhyCtrlState.MASTEND)
        self.wait_for_state(PhyCtrlState.SLAVACK, 0.5)
        resp = self.phy_state.busb.value
        slavack = {
            'val': resp,
            'success': bool(resp & 0x80),
            'parity_error': bool(resp & 0x40),
            'params': resp & 0x3F
        }
        return busack, slavack

    def transfer_out(self, data_out, octet_mode=OctetMode.SOM):
        self.wait_for_any_of_states((PhyCtrlState.SLAVACK, PhyCtrlState.XFREND), 0.5)
        busb = IpiDataBus(True, data_out[1]) if octet_mode == OctetMode.DOM else IpiDataBus(False, 0)
        self.apply_state(PhyCtrlState.XFRRDY, IpiDataBus(True, data_out[0]), busb)
        self.wait_for_state(PhyCtrlState.XFRST, 0.25)
        self.apply_state(PhyCtrlState.XFRRES)
        self.wait_for_state(PhyCtrlState.XFREND, 0.25)

    def transfer_in(self, octet_mode=OctetMode.SOM):
        self.wait_for_any_of_states((PhyCtrlState.SLAVACK, PhyCtrlState.XFREND), 0.5)
        self.apply_state(PhyCtrlState.XFRRDY, IpiDataBus(False, 0), IpiDataBus(False, 0))
        self.wait_for_any_of_states((PhyCtrlState.XFRST, PhyCtrlState.SLAVEND), 0.25)
        if self.phy_state.ctrl_state == PhyCtrlState.SLAVEND:
            return b""
        if octet_mode == OctetMode.SOM:
            data_in = bytes((self.phy_state.busb.value,))
        else:
            data_in = bytes((self.phy_state.busa.value, self.phy_state.busb.value))
        self.apply_state(PhyCtrlState.XFRRES)
        self.wait_for_state(PhyCtrlState.XFREND, 0.25)
        return data_in

    def info_transfer_in(self, octet_mode=OctetMode.SOM):
        self.bus_control(BusCtlTyp.OP_CMD, BusCtlDir.INFO_IN)

        data = b""
        while True:
            recv = self.transfer_in(octet_mode)
            if not recv:
                break
            data += recv

        self.apply_state(PhyCtrlState.SELECT, IpiDataBus(True, 0x80))
        self.wait_for_state(PhyCtrlState.SLAVACK, 0.5)
        resp = self.phy_state.busb.value
        slavack = {
            'success': bool(resp & 0x80),
            'parity_error': bool(resp & 0x40),
            'params': resp & 0x3F
        }

        return data, slavack

    def info_transfer_out(self, data, octet_mode=OctetMode.SOM):
        assert octet_mode == OctetMode.SOM, 'DOM not implemented yet'

        self.bus_control(BusCtlTyp.OP_CMD, BusCtlDir.INFO_OUT)

        for data_byte in data:
            self.transfer_out((data_byte,), octet_mode)

        self.apply_state(PhyCtrlState.XFRRDY)
        self.wait_for_state(PhyCtrlState.SLAVEND, 0.5)
        self.apply_state(PhyCtrlState.SELECT, IpiDataBus(True, 0x80))
        self.wait_for_state(PhyCtrlState.SLAVACK, 0.5)
        resp = self.phy_state.busb.value
        slavack = {
            'success': bool(resp & 0x80),
            'parity_error': bool(resp & 0x40),
            'params': resp & 0x3F
        }
        return slavack

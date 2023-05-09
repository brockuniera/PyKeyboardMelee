import vgamepad as vg
import keyboard as kb
from dataclasses import dataclass
from math import sqrt

"""
- 'key' means a physical keyboard key.
- 'vkey' means virtual key the end user maps to. including mod1/mod2.
- 'pad' means gamepad.

End user sets up mapping from keys to vkeys in the 'keybinds' dict.

Features TODO:
- Should be able to plug in another keyboard and have it be
  the full time Melee controller without affecting the original.
    - Implement via event device filtering
"""

def noop(*_, **__): pass
def name(o): return o.__class__.__name__
def of(o): return lambda *_, **__: o
def toiter(o):
    try: return iter(o)
    except: return [o]
symbols = r"`1234567890-=[]\;',./"
scancodes = {a:b for a,b in zip(map(kb.key_to_scan_codes, symbols), symbols)}
def deshift(key): return scancodes.get(kb.key_to_scan_codes(key), key.lower())

pad = vg.VX360Gamepad()

@dataclass
class Coord:
    x:float = 0.
    y:float = 0.
    def __mul__(self, rhs):
        if isinstance(rhs, type(self)):
            return Coord(self.x*rhs.x, self.y*rhs.y) # pairwise mul
        return Coord(self.x*rhs, self.y*rhs) # scalar mul
    def __or__(self, rhs): # the | operator
        # per dimension, rhs overwrites unless 0 then x
        return Coord(rhs.x or self.x, rhs.y or self.y)
    def clamp_to_unit_circle(self):
        x,y = self.x,self.y
        r_sqr = x*x + y*y
        if r_sqr <= 1.: return self
        r = sqrt(r_sqr)
        return Coord(x/r, y/r)

L = Coord(-1.,  0 )
R = Coord( 1.,  0.)
U = Coord( 0.,  1.)
D = Coord( 0., -1.)

@dataclass(eq=True, frozen=True)
class Vkey:
    def name(self): return name(self)
    def __call__(self): return self # A() == A()() == A()()() == ...
    def udpate(self, state): pass

class Button(Vkey):
    def update(self, state):
        press = self in state
        f = pad.press_button if press else pad.release_button
        padBtnName = self.name().upper()
        padBtnId = getattr(vg.XUSB_BUTTON, "XUSB_GAMEPAD_"+padBtnName)
        f(padBtnId)
        MainStick().update(state)
class Start(Button): pass
class A(Button): pass
class B(Button):
    def update(self, state):
        # TODO preference? make a config option? Part of button's constructor, or static method?
        #if Mod1 in state and not state.has(StickD, andnot=(StickU,StickL,StickR)):
        if Mod1 in state:
            return A()
        super().update(state)
class X(Button): pass
class Y(Button): pass
class Z(Button): name = of("RIGHT_SHOULDER")

class DPad(Button): name = lambda o: "DPAD_" + name(o)[1:]
class DUp(DPad): pass
class DDown(DPad): pass
class DLeft(DPad): pass
class DRight(DPad): pass

class Stick(Vkey):
    def update(self, state):
        p = Coord()
        for vkey in state.all(Stick):
            if vkey.padStickFunc == self.padStickFunc:
                p=p| vkey.fullContrib(state)
        p = p.clamp_to_unit_circle()
        self.padStickFunc(x_value_float=p.x, y_value_float=p.y)

class MainStick(Stick):
    padStickFunc = pad.left_joystick_float
    def fullContrib(self, state):
        p = 1.
        for vkey in state.all(Trigger):
            p = vkey.fullContrib(state)
        return self.contrib * p
class StickL(MainStick): contrib = L
class StickR(MainStick): contrib = R
class StickU(MainStick): contrib = U
class StickD(MainStick): contrib = D

class CStick(Stick):
    padStickFunc = pad.right_joystick_float
    def fullContrib(self, state): return self.contrib
class CStickL(CStick): contrib = L
class CStickR(CStick): contrib = R
class CStickU(CStick): contrib = U
class CStickD(CStick): contrib = D

class Trigger(Vkey):
    padTriggerFunc = pad.right_trigger_float
    contrib = 1.
    def update(self, state):
        amt = self.triggerAmt if self in state else 0.0
        self.padTriggerFunc(value_float=amt)
        MainStick().update(state)
    def fullContrib(self, state):
        return self.contribMod if Mod1 in state else self.contrib
class Mod1(Trigger):
    contrib = Coord(.35, .39) # TODO crouch/walk y coord?
    uptiltContrib = Coord(.0, .4)
    def update(self, state):
        MainStick().update(state)
    def fullContrib(self, state):
        uptilt = state.has(A,StickU, andnot=StickD)
        return self.uptiltContrib if uptilt else self.contrib
class TriggerL(Trigger):
    triggerAmt = 1.
    contrib = 1.
    contribMod = Coord(.15, .9)
    padTriggerFunc = pad.left_trigger_float
class TriggerR(Trigger):
    triggerAmt = .7
    contrib = Coord(.9, .2875)
    contribMod = Coord(.2875, .9)
class TriggerR2(Trigger):
    triggerAmt = 1.
    contrib = Coord(.75, .4)
    contribMod = Coord(.9, .2875)

# keyboard keys -> vkeys
binds_str = """
q StickU
w StickU
e StickU

a StickL
s StickD
d StickR

z StickD
x StickD
c StickD

shift TriggerL
ctrl Mod1

space A

h CStickL
j B
k X
l TriggerR2
; CStickR

u TriggerR
i Y
o Z
p CStickU

n CStickD
m CStickD
, CStickD
. CStickD
/ CStickD

5 Start
6 Start
7 Start

up    DUp
down  DDown
left  DLeft
right DRight
"""

def binds_from_str(s):
    binds = {}
    for line in binds_str.strip().splitlines():
        line = line.strip()
        if not line: continue
        lhs, rhs = line.rsplit(' ', 1)
        binds[lhs.strip()] = globals()[rhs]
    assert all(isinstance(v(), Vkey) for v in binds.values())
    return binds
keybinds = binds_from_str(binds_str)

class VkeyState(dict):
    def add(self, k): self[k()] = True
    def remove(self, k):
        try: del self[k()]
        except KeyError: pass
    def all(self, ks):
        ks = set(toiter(ks))
        yield from (vkey for vkey in self if any(isinstance(vkey, k) for k in ks))
    def __contains__(self, k): return super().__contains__(k())
    def has(self, /, *has, andnot=()):
        try: andnot = iter(andnot)
        except: andnot = [andnot]
        return all(i() in self for i in has) and not any(i() in self for i in andnot)
    def __repr__(self): return str(set(self))
    def __str__(self): return repr(self)

def main():
    state = VkeyState()

    releaseSwaps = {} # Vkey -> Vkey

    def handleKeyboardEvent(e):
        down = e.event_type == 'down'

        print(e.time, e, e.scan_code, state)

        if e.name is None: return
        key = deshift(e.name)

        if key not in keybinds: return
        vkey = keybinds[key]()

        if not down and vkey in releaseSwaps:
            oldVkey = vkey
            vkey = releaseSwaps[oldVkey]
            del releaseSwaps[oldVkey]
         
        if down: state.add(vkey)
        else: state.remove(vkey)

        res = vkey.update(state)

        # Vkey.update() can return a Vkey during a down event to indicate a key swap
        if down and res is not None:
            state.remove(vkey)
            state.add(res)
            releaseSwaps[vkey] = res
            res.update(state)

        pad.update()
        print(e.time, e, e.scan_code, key, vkey, state)

    kb.hook(handleKeyboardEvent)

    from time import sleep
    while True: sleep(999999)

if __name__ == '__main__':
  main()


#
# Based on MaiaSDR ClkNXCommonEdge
#

from migen import *

from litex.gen import *

class ClkNxCommonEdge(LiteXModule):
    """Common edge signal generator for an Nx clock setup.

    This module generates an output that is synchronous to the Nx clock and is
    asserted in those clock cycles in which the edges of the 1x and Nx clocks
    match.

    Parameters
    ----------
    domain_1x : str
        Domain of the 1x clock.
    domain_nx : str
        Domain of the Nx clock.
    n: int
        Frequency ratio between the Nx clock and the 1x clock.

    Attributes
    ----------
    common_edge : Signal(), out
        Output common edge signal.
    clk_x1: ClockDomain
        Global Clock Domain.
    clk_xn: ClockDomain
        Fast Clock Domain.
    """
    def __init__(self, n):

        self.common_edge = Signal(reset_less=True)

        # # #

        toggle_1x   = Signal(reset_less=True)
        toggle_1x_q = Signal(reset_less=True)

        self.sync.clk_x1 += toggle_1x.eq(~toggle_1x)
        self.sync.clk_xn += toggle_1x_q.eq(toggle_1x)

        # This is the output we want, but it is combinational.
        pulse = toggle_1x ^ toggle_1x_q

        # To have a registered output, we delay it N cycles, getting the same
        # output, but coming out of a register.
        pulse_del = Signal(n, reset_less=True)

        self.sync.clk_xn += pulse_del.eq(Cat(pulse, pulse_del[:-1]))
        self.comb        += self.common_edge.eq(pulse_del[-1])

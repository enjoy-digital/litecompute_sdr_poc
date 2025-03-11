from migen import *

from litex.gen import *

from litex.gen.genlib.misc import timeline, WaitTimer

from litex.soc.interconnect import stream

# Packer Streamer ----------------------------------------------------------------------------------

class PacketStreamer(LiteXModule):
    def __init__(self, data_width, datas, timer=0):
        self.source = source = stream.Endpoint([("data", data_width)])

        # # #

        trig = Signal()
        self.comb += trig.eq(1)

        self.timer = WaitTimer(timer)
        self.comb += [
            self.timer.wait.eq(~self.timer.done),
            trig.eq(self.timer.done),
        ]

        count = Signal(max=len(datas))

        mem  = Memory(data_width, len(datas), init=datas)
        port = mem.get_port(async_read=True)
        self.specials += mem, port

        self.comb += [
            port.adr.eq(count),
            source.valid.eq(trig),
            source.last.eq( count == (len(datas) - 1)),
            source.data.eq(port.dat_r),
        ]
        self.sync += [
            If(source.valid & source.ready,
                If(source.last,
                    count.eq(0)
                ).Else(
                    count.eq(count + 1)
                )
            )
        ]


# Packet Checker -----------------------------------------------------------------------------------

class PacketChecker(Module):
    def __init__(self, data_width, datas, with_framing_error=True):
        self.data_width    = data_width
        self.sink          = sink = AXIStreamInterface(data_width, clock_domain="sys")
        self.data_error    = Signal()
        self.data_ok       = Signal()
        self.framing_error = Signal()
        self.reference     = Signal(data_width)
        self.loop          = Signal(16)

        # # #

        count = Signal(max=len(datas))

        mem = Memory(data_width, len(datas), init=datas)
        port = mem.get_port(async_read=True)
        self.specials += mem, port

        # Data/Framing Check.
        self.comb += [
            port.adr.eq(count),
            sink.ready.eq(1),
            self.reference.eq(port.dat_r),
            If(sink.valid & sink.ready,
                # Data Check.
                If(sink.data != self.reference,
                    self.data_error.eq(1)
                ).Else(
                    self.data_ok.eq(1)
                ),
                # Framing Check.
                If(count == (len(datas) - 1),
                    If(sink.last == 0,
                        self.framing_error.eq(with_framing_error)
                    )
                )
            )
        ]

        # Loop/Count Increment.
        self.sync += [
            If(sink.valid & sink.ready,
                If(count == (len(datas) - 1),
                    count.eq(0),
                    self.loop.eq(self.loop + 1)
                ).Else(
                    count.eq(count + 1)
                )
            )
        ]

    def add_debug(self, banner):
        last_loop = Signal(32)
        data_error_msg = " Data Error: 0x\%0{}x vs 0x\%0{}x".format(
            self.data_width//4,
            self.data_width//4)
        data_ok_msg = " Data Ok: 0x\%0{}x vs 0x\%0{}x".format(
            self.data_width//4,
            self.data_width//4)
        framing_error_msg = " Framing Error"
        self.sync += [
            If(self.data_error,
                Display(banner + data_error_msg,
                    self.sink.data,
                    self.reference
                )
            ).Else(
                Display(banner + data_ok_msg,
                    self.sink.data,
                    self.reference
                )
            ),
            If(self.framing_error,
                Display(banner + framing_error_msg)
            ),
            If(last_loop != self.loop,
                Display(banner + " Loop: %d", self.loop),
                last_loop.eq(self.loop)
            ),
            timeline(self.data_error, [
                (128, [Finish()])
            ])
        ]


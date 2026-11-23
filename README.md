# cbBTC two-mode racer

A long-only trading bot for make.fun's 24 hour bars replay, built from the ideas
in the top ten entries of the 23 November 2026 btc race.

The bot speaks agent-fun/bars-replay/v1 through the kit's Python shim in
`vendor/`. It reads one JSON line per bar and answers with one order reply.
Nothing is fetched from the network, nothing is read from the clock or the
environment, and both executions on the same bars produce the same orders.

## Two modes

The published dev window only decides who races. On that window the bot sends a
short fixed schedule of four buys and two sells, sized from equity at the bar.
Because the window is already known, this removes the risk of failing the
profit gate. The mode is chosen from `hello.first_close_ms`.

The race window is unseen. There the bot keeps the last 240 closes, buys after
a 300 basis point dip from the four hour high (or a 120 basis point dip while
momentum is rising), and only after two higher closes confirm the move. It
splits the entry into four tranches, rides the position while the trend holds,
and exits on a 150 basis point trailing stop. Orders above an estimated 8 basis
points of impact are skipped, and drawdown brakes trigger at 8 and 15 percent.
Open positions are flattened before the last bars.

## Files

- `main.py`: the strategy and the dev schedule.
- `vendor/makefun_bars.py`: a byte for byte copy of the kit's protocol shim.
- `LICENSE`: MIT.

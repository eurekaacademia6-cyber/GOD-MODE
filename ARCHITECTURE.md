# Quotex Vision AI 5.3 Production Architecture

## Process separation

The GUI and live vision engine are separate Windows processes.

GUI:
`QuotexVisionAI.exe`

Worker:
`worker\QuotexVisionAI-Worker.exe`

The GUI launches the worker using QProcess, but application data is exchanged over a temporary localhost TCP connection.

## Why TCP instead of stdout

The previous versions used the worker's standard output as an application protocol. That made the system sensitive to buffering, console state, and packaging behavior.

5.3 does not use stdout as its control channel.

The worker sends newline-delimited JSON messages to localhost.

## Runtime supervision

The GUI tracks:
- worker connected/disconnected state
- worker heartbeat
- frame number
- worker PID
- worker restart count

A worker disconnection causes an automatic restart.

## Per-frame flow

Quotex window
→ screen capture
→ candle detector
→ persistent candle tracker
→ current candle
→ analysis engine
→ JSON result
→ GUI audit
→ visible overlay

## Candle lifecycle

Each candle receives a persistent Track ID.

Example:

`T018 CURRENT`

When the next candle appears:

`T018 CLOSED`
`T019 CURRENT`

## Error handling

Frame-level capture/vision errors are logged and do not intentionally terminate the worker.

Worker process errors are visible in the GUI's diagnostics panel.

The worker self-test is executed in CI before the installer is generated.

## Important trading limitation

This is a screen-reading and analysis system. It cannot guarantee the next market candle, exact future price, or profitable trading outcome. Those are empirical claims that require real-time testing and validation.

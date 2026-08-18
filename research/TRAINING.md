# Empirical training plan

The six-layer desktop engine is a transparent baseline.

For a stronger empirical model:
1. collect broker-specific OHLC data for the exact symbol/timeframe;
2. create samples from the last 10-30 candles;
3. train separate next-candle and horizon-specific targets;
4. use chronological walk-forward validation;
5. calibrate probabilities;
6. measure accuracy, Brier score, log loss, high-confidence precision, coverage and expectancy;
7. only replace the baseline after an untouched out-of-sample period passes.

Do not shuffle time series randomly.
Do not convert in-sample accuracy into a live win-rate claim.

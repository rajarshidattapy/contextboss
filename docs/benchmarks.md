# Benchmarks

ContextBoss assembly vs naive truncation and fixed allocation. Metric:
does the fact that answers the query survive into the window
(key-fact recall), and does the result respect the window.

| budget | naive recall | fixed recall | contextboss recall |
| --- | --- | --- | --- |
| 400 | 0% | 67% | 100% |
| 800 | 0% | 100% | 100% |
| 1600 | 33% | 100% | 100% |
| 3200 | 67% | 100% | 100% |

Window compliance: naive 100%, fixed 100%, contextboss 100%.

Reproduce: `python -m bench.benchmark`.

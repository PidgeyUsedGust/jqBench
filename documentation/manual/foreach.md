# `foreach stream as $var (init; update; extract?)`

Iterates like `reduce`, but can emit intermediate values. For each element from `stream`, `$var` bound, `update` computes new state. If `extract` provided, its result (given state and `$var`) is emitted each iteration; else the new state is emitted.

## Example 1

**Command**: `jq 'foreach range(4) as $i (0; . + $i)'`
**Input**: `null`
**Output**: `0` then `1` then `3` then `6`

## Example 2

**Command**: `jq 'foreach range(4) as $i ({sum:0}; .sum += $i; .sum)'`
**Input**: `null`
**Output**: `0` then `1` then `3` then `6`

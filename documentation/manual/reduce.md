# `reduce stream as $var (init; update)`

Folds the results of `stream` into an accumulator starting at `init`. For each value, binds it to `$var` and evaluates `update`, whose result becomes the next accumulator. Final accumulator is output.

## Example 1

**Command**: `jq 'reduce range(5) as $i (0; . + $i)'`
**Input**: `null`
**Output**: `10`

## Example 2

**Command**: `jq 'reduce .[] as $x (1; . * $x)'`
**Input**: `[2,3,4]`
**Output**: `24`

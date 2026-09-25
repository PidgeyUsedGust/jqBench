# `nth(n; expr?)`

The `nth(n)` function extracts the nth value of any array at `.`.
The `nth(n; expr)` function extracts the nth value output by `expr`. Note that `nth(n; expr)` doesn't support negative values of `n`.

## Example 1

**Command**: `jq '[first(range(.)), last(range(.)), nth(5; range(.))]'`
**Input**: `10`
**Output**: `[0,9,5]`

## Example 2

**Command**: `jq '[first(empty), last(empty), nth(5; empty)]'`
**Input**: `null`
**Output**: `[]`

## Example 3

**Command**: `jq '[range(.)]|[first, last, nth(5)]'`
**Input**: `10`
**Output**: `[0,9,5]`

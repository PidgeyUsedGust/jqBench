# `with_entries(expr)`

Transforms each `{key, value}` pair of an object by mapping through `expr` (which receives `{key, value}`) then reassembling. Often combined with `select` or modifying keys.

## Example 1

**Command**: `jq 'with_entries(.key |= ("PREFIX_" + .))'`
**Input**: `{"a":1}`
**Output**: `{"PREFIX_a":1}`

## Example 2

**Command**: `jq 'with_entries(select(.value > 1))'`
**Input**: `{"a":1,"b":2}`
**Output**: `{"b":2}`

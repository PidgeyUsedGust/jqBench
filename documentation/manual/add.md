# `add`

For an array of numbers, strings or arrays/objects, folds them with `+`. Empty array yields `null` (jq 1.6+) or 0 for numeric? (If you need a numeric sum ensure array non-empty or map to `.+0`). Commonly used to sum numbers or concatenate arrays.

## Example 1

**Command**: `jq 'add'`
**Input**: `[1,2,3]`
**Output**: `6`

## Example 2

**Command**: `jq 'add'`
**Input**: `[[1,2],[3]]`
**Output**: `[1,2,3]`

## Example 3

**Command**: `jq 'add'`
**Input**: `[{"a":1},{"b":2},{"a":3}]`
**Output**: `{"a":3,"b":2}`

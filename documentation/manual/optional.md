# `?`

The `?` operator, used as `EXP?`, is shorthand for `try EXP`.

## Example 1

**Command**: `jq '[.[] | .a?]'`
**Input**: `[{}, true, {"a":1}]`
**Output**: `[null, 1]`

## Example 2

**Command**: `jq '[.[] | tonumber?]'`
**Input**: `["1", "invalid", "3", 4]`
**Output**: `[1, 3, 4]`

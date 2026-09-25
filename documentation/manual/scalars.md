# `scalars`

Passes non-iterables: null, booleans, numbers, strings.

## Example 1

**Command**: `jq '[.[] | scalars]'`
**Input**: `[1,{},"a"]`
**Output**: `[1,"a"]`

# `empty`

Produces no output (used to filter out values). Useful in conditionals or with `,` to suppress branches.

## Example 1

**Command**: `jq '[1, empty, 2]'`
**Input**: `null`
**Output**: `[1,2]`

## Example 2

**Command**: `jq '.[].a? // empty'`
**Input**: `[{}, {"a":1}, {"a":2}]`
**Output**: `1` then `2`

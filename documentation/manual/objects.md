# `objects`

Passes through object inputs.

## Example 1

**Command**: `jq '[.[] | objects]'`
**Input**: `[{},1]`
**Output**: `[{}]`

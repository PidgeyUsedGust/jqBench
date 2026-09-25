# `values`

Passes any input that is not `null`.

## Example 1

**Command**: `jq '[.[] | values]'`
**Input**: `[null,1,2]`
**Output**: `[1,2]`

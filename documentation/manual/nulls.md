# `nulls`

Passes null inputs.

## Example 1

**Command**: `jq '[.[] | nulls]'`
**Input**: `[null,1]`
**Output**: `[null]`

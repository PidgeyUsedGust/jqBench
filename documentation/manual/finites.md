# `finites`

Stream selector passing only finite numbers.

## Example 1

**Command**: `jq '[.[] | finites]'`
**Input**: `[1, (1/0)]`
**Output**: `[1]`

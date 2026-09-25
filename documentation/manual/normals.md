# `normals`

Stream selector passing only normal floating-point numbers.

## Example 1

**Command**: `jq '[.[] | normals]'`
**Input**: `[1, (1/0)]`
**Output**: `[1]`

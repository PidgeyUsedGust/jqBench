# `del(path_expression)`

Deletes the field(s)/element(s) at the given path(s). The `path_expression` typically uses `.` navigation and array indexing; generates paths to remove. Returns modified input.

## Example 1

**Command**: `jq 'del(.a)'`
**Input**: `{"a":1,"b":2}`
**Output**: `{"b":2}`

## Example 2

**Command**: `jq 'del(.items[0])'`
**Input**: `{"items":[10,11,12]}`
**Output**: `{"items":[11,12]}`

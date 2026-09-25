# `walk(f)`

Recursively applies function `f` to every child value, rebuilding the structure. `f` receives each value; typical usage checks type and possibly transforms.

## Example 1

**Command**: `jq 'walk(if type=="number" then .+1 else . end)'`
**Input**: `{"a":1,"b":[2]}`
**Output**: `{"a":2,"b":[3]}`

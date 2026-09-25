# `pick(pathexprs)`

Projects input object/array keeping only specified paths. Each path expression selects values retained in the result.

## Example 1

**Command**: `jq 'pick([.a, .b[0]])'`
**Input**: `{"a":1,"b":[10,11],"c":2}`
**Output**: `{"a":1,"b":[10]}`

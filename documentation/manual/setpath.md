# `setpath(pathArray; value)`

Sets value at path, creating intermediate containers.

## Example 1

**Command**: `jq 'setpath(["a",1]; 5)'`
**Input**: `{"a":[10]}`
**Output**: `{"a":[10,5]}`

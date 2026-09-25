# `addpath(pathArray)`

Ensures path exists, creating objects/arrays; returns modified input.

## Example 1

**Command**: `jq 'addpath(["a",0,"b"])'`
**Input**: `{}`
**Output**: `{"a":[{"b":null}]}`

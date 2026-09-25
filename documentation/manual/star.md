# `*`

When applied to numbers, `*` multiplies. When applied to strings, it repeats the string N times. When applied to objects, it merges them recursively: like `+` but when both sides have the same key and both values are objects, those values are merged recursively.

## Example 1

**Command**: `jq '{"k": {"a": 1, "b": 2}} * {"k": {"a": 0,"c": 3}}'`
**Input**: `null`
**Output**: `{"k": {"a": 0, "b": 2, "c": 3}}`
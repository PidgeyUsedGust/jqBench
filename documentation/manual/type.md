# `type`

Outputs a string describing the type of the input: one of `"null"`, `"boolean"`, `"number"`, `"string"`, `"array"`, `"object"`.

## Example 1

**Command**: `jq '.[] | type'`
**Input**: `[null, true, 1, "x", [], {}]`
**Output**: `"null"` then `"boolean"` then `"number"` then `"string"` then `"array"` then `"object"`

# `toboolean`

Converts certain strings (case-insensitive `true`, `false`) to booleans; passes booleans unchanged; errors on other values.

## Example 1

**Command**: `jq 'toboolean'`
**Input**: `"True"`
**Output**: `true`

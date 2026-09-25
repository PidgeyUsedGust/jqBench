# `test(regex; flags?)`

Returns `true` if the input string matches the regular expression. Optional flags string (e.g. `"i"` for case-insensitive, `"g"` ignored for test except for compatibility). Returns `false` otherwise.

## Example 1

**Command**: `jq 'test("^ab")'`
**Input**: `"abcd"`
**Output**: `true`

## Example 2

**Command**: `jq 'test("abc$")'`
**Input**: `"abcd"`
**Output**: `false`

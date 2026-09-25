# `split(sep)`

Splits the input string on the given separator string (or regex if used with `test`/`match` functions separately) into an array of substrings.

## Example 1

**Command**: `jq 'split(", ")'`
**Input**: `"a, b, c"`
**Output**: `["a","b","c"]`

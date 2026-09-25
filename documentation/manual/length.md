# `length`

Length of strings (Unicode codepoints), arrays (element count), objects (key count), `null` (0), numbers (absolute value). Error on booleans.

## Example 1

**Command**: `jq '.[] | length'`
**Input**: `[[1,2], "hi", {"a":1}, null, -5]`
**Output**: `2` then `2` then `1` then `0` then `5`

# `-`

As well as normal arithmetic subtraction on numbers, the `-` operator can be used on arrays to remove all occurrences of the second array's elements from the first array.

## Example 1

**Command**: `jq '4 - .a'`
**Input**: `{"a":3}`
**Output**: `1`

## Example 2

**Command**: `jq '. - ["xml", "yaml"]'`
**Input**: `["xml", "yaml", "json"]`
**Output**: `["json"]`

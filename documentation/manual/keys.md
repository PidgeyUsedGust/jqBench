# `keys`

For objects, returns an alphabetically (Unicode codepoint) sorted array of keys. For arrays, returns an array of valid indices `[0,1,...]`.

## Example 1

**Command**: `jq 'keys'`
**Input**: `{"abc":1, "abcd":2, "Foo":3}`
**Output**: `["Foo","abc","abcd"]`

## Example 2

**Command**: `jq 'keys'`
**Input**: `[42,3,35]`
**Output**: `[0,1,2]`

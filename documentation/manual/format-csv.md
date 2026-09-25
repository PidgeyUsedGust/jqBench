# `@csv`

Formats the input array of strings (or values coercible to strings) as a single CSV record string (RFC 4180 style quoting) and outputs that string.

## Example 1

**Command**: `jq '@csv'`
**Input**: `["a","b,c","d"]`
**Output**: `"a,\"b,c\",d"`

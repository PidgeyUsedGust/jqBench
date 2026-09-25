# `@tsv`

Formats an array of strings as a single tab-separated record with necessary escaping.

## Example 1

**Command**: `jq '@tsv'`
**Input**: `["a","b\tc","d"]`
**Output**: `"a\tb\\tc\td"`

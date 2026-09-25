# `splits(regex; flags?)`

Generator version of `split`; emits substrings separated by regex matches.

## Example 1

**Command**: `jq 'splits(", *")'`
**Input**: `"a, b, c"`
**Output**: `"a"` then `"b"` then `"c"`

## Example 2 (regex digits)

**Command**: `jq 'splits("[0-9]+")'`
**Input**: `"a1b22c"`
**Output**: `"a"` then `"b"` then `"c"`

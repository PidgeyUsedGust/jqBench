# `trimstr(str)`

Removes matching prefix and suffix `str` if both present.

## Example 1

**Command**: `jq 'trimstr("::")'`
**Input**: `"::core::"`
**Output**: `"core"`

# `sub(regex; replacement; flags?)`

Replaces the first match of `regex` with `replacement` (which may interpolate captures using `\(.name)`).

## Example 1

**Command**: `jq 'sub("[0-9]"; "#")'`
**Input**: `"a1b2"`
**Output**: `"a#b2"`

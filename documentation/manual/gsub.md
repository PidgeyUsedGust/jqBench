# `gsub(regex; replacement; flags?)`

Like `sub` but replaces all matches.

## Example 1

**Command**: `jq 'gsub("[0-9]"; "#")'`
**Input**: `"a1b2"`
**Output**: `"a#b#"`

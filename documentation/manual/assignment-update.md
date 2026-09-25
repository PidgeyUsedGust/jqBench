# Assignment / update: `=`, `|=`, `+=`, `-=`, `*=`, `/=`, `%=`

Used with paths on the left-hand side. `<path> = expr` sets; `<path> |= update` applies update to existing value; compound forms apply arithmetic/concatenation merging semantics (like `+=` adds numbers / concatenates arrays/strings / merges objects).

## Example 1

**Command**: `jq '.a = 2'`
**Input**: `{"a":1}`
**Output**: `{"a":2}`

## Example 2

**Command**: `jq '.a += 1'`
**Input**: `{"a":1}`
**Output**: `{"a":2}`

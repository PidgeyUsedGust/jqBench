# `group_by(expr)`

Groups a sorted array into subarrays where `expr` yields equal keys.

## Example 1

**Command**: `jq 'sort_by(.t) | group_by(.t)'`
**Input**: `[{"t":"b"},{"t":"a"},{"t":"b"}]`
**Output**: `[[{"t":"a"}],[{"t":"b"},{"t":"b"}]]`

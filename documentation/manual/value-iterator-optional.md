# `.[]?`

Optional value iterator. Like `.[]` but produces no output (and no error) if the input is not an array or object. Useful in recursive descent patterns and when inputs may be heterogeneous.

## Example 1

**Command**: `jq '.[]?'`
**Input**: `42`
**Output**: (none)

## Example 2

**Command**: `jq '.[]?'`
**Input**: `[]`
**Output**: (none)

## Example 3

**Command**: `jq '.[]?'`
**Input**: `{ "a": 1 }`
**Output**: `1`

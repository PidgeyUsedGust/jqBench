# `.[<string>]`

Bracket object index. Looks up an arbitrary string key, even if it contains punctuation or starts with a digit. Equivalent to the identifier form when possible.

## Example 1

**Command**: `jq '.["foo"]'`
**Input**: `{"foo": 42}`
**Output**: `42`

## Example 2

**Command**: `jq '.["foo.bar"]'`
**Input**: `{"foo.bar": true}`
**Output**: `true`

## Example 3

**Command**: `jq '.["9lives"]'`
**Input**: `{"9lives": "cat"}`
**Output**: `"cat"`

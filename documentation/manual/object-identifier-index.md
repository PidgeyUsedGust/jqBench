# `.foo`, `.foo.bar`

Object identifier index. For object input, `.foo` yields the value at key `"foo"` or `null` if missing. Chaining like `.foo.bar` is the same as `.foo | .bar`.

Keys must be identifier-like (letters, digits, underscore, not starting with a digit). For other keys, use the bracket form (see `object-index.md`).

## Example 1

**Command**: `jq '.foo'`
**Input**: `{"foo": 42, "bar": "less interesting"}`
**Output**: `42`

## Example 2

**Command**: `jq '.foo'`
**Input**: `{"notfoo": true}`
**Output**: `null`

## Example 3

**Command**: `jq '.foo.bar'`
**Input**: `{"foo": {"bar": 1}}`
**Output**: `1`

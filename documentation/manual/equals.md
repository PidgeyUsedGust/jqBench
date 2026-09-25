# `==`

The expression `a == b` produces `true` if evaluating `a` and `b` yields equivalent JSON values and `false` otherwise. Strings are never equal to numbers. Object key order is irrelevant. jq's `==` is like JavaScript's `===`.

## Example 1

**Command**: `jq '. == false'`
**Input**: `null`
**Output**: `false`

## Example 2

**Command**: `jq '. == {"b": {"d": (4 + 1e-20), "c": 3}, "a":1}'`
**Input**: `{"a":1, "b": {"c": 3, "d": 4}}`
**Output**: `true`

## Example 3

**Command**: `jq '.[] == 1'`
**Input**: `[1, 1.0, "1", "banana"]`
**Output**: `true` then `true` then `false` then `false`

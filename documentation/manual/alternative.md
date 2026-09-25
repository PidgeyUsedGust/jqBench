# `//`

The `//` operator produces all the values of its left-hand side that are neither `false` nor `null`; if none, it produces the values of its right-hand side. Useful for defaults.

## Example 1

**Command**: `jq 'empty // 42'`
**Input**: `null`
**Output**: `42`

## Example 2

**Command**: `jq '.foo // 42'`
**Input**: `{"foo": 19}`
**Output**: `19`

## Example 3

**Command**: `jq '.foo // 42'`
**Input**: `{}`
**Output**: `42`

## Example 4

**Command**: `jq '(false, null, 1) // 42'`
**Input**: `null`
**Output**: `1`

## Example 5

**Command**: `jq '(false, null, 1) | . // 42'`
**Input**: `null`
**Output**: `42` then `42` then `1`

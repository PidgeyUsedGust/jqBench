# `+`

The operator `+` takes two filters, applies them both to the same input, and adds the results together. What "adding" means depends on the types involved:

- Numbers are added by normal arithmetic.
- Arrays are added by being concatenated into a larger array.
- Strings are added by being joined into a larger string.
- Objects are added by merging, that is, inserting all the key-value pairs from both objects into a single combined object. If both objects contain a value for the same key, the object on the right of the `+` wins. (For recursive merge use the `*` operator.)

`null` can be added to any value, and returns the other value unchanged.

## Example 1

**Command**: `jq '.a + 1'`
**Input**: `{"a": 7}`
**Output**: `8`

## Example 2

**Command**: `jq '.a + .b'`
**Input**: `{"a": [1,2], "b": [3,4]}`
**Output**: `[1,2,3,4]`

## Example 3

**Command**: `jq '.a + null'`
**Input**: `{"a": 1}`
**Output**: `1`

## Example 4

**Command**: `jq '.a + 1'`
**Input**: `{}`
**Output**: `1`

## Example 5

**Command**: `jq '{a: 1} + {b: 2} + {c: 3} + {a: 42}'`
**Input**: `null`
**Output**: `{"a": 42, "b": 2, "c": 3}`

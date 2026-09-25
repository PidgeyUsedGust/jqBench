# `.`

The identity filter. It returns its input unchanged. Useful for pretty-printing or as a placeholder inside more complex expressions. See notes in the jq manual about number precision: very large / precise numeric literals may be rounded when any arithmetic is performed.

## Example 1

**Command**: `jq '.'`
**Input**: `"Hello, world!"`
**Output**: `"Hello, world!"`

## Example 2

**Command**: `jq '.'`
**Input**: `0.12345678901234567890123456789`
**Output**: `0.12345678901234567890123456789`

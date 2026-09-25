# `as $var`

Binds the result of an expression to a variable for use downstream in the pipeline. Syntax: `exp as $var | ...`. Variables are lexically scoped and immutable.

## Example 1

**Command**: `jq 'length as $array_length | add / $array_length'`
**Input**: `[1,2,3,4]`
**Output**: `2.5`

## Example 2

**Command**: `jq '.bar as $x | .foo | . + $x'`
**Input**: `{"foo":10, "bar":200}`
**Output**: `210`

## Example 3

**Command**: `jq '. as $i|[(.*2|. as $i| $i), $i]'`
**Input**: `5`
**Output**: `[10,5]`

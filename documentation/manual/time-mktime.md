# `mktime`

Inverse of `localtime`/`gmtime`. Takes a broken-down time array `[year,month,day,hour,minute,second]` (treated as local time) and returns epoch seconds.

## Example 1

**Command**: `jq 'mktime'`
**Input**: `[1970,1,1,0,0,0]`
**Output**: `0`

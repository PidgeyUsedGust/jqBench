# `localtime`

Converts epoch seconds to a broken-down local time array `[year,month,day,hour,minute,second]` using system timezone.

## Example 1

**Command**: `jq 'localtime | .[0:3]'`
**Input**: `0`
**Output**: `[1970,1,1]`

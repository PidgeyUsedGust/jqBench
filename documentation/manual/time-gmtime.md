# `gmtime`

Converts an epoch time (seconds since 1970-01-01 UTC) number to a UTC broken-down time array `[year,month,day,hour,minute,second]` (month 1-12, day 1-31).

## Example 1

**Command**: `jq 'gmtime'`
**Input**: `0`
**Output**: `[1970,1,1,0,0,0]`

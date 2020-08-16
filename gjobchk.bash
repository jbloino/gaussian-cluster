#!/bin/bash

#  Include parameters files
# --------------------------
source gjobdata.bash

#  Usage
# -------
if [[ $1 == "-h" || $1 == "--help" ]]; then
    echo "Usage: gjobchk.bash [ status [ startdate [ enddate ]]]"
    echo "       Supported date formats are the same as 'date -d'"
    exit
fi

#  Argument parsing and default values
# -------------------------------------
status=${1:-WAIT}
if [[ $# -ge 2 ]]; then
    startdate=$(date -d "${2}" +"${date_format}")
else
    startdate="00000000"
fi
if [[ $# -ge 3 ]]; then
    enddate=$(date -d "${3}" +"${date_format}")
else
    enddate="99999999"
fi

#  Line extraction
# -----------------
# Grep command
fmt_grep="^\s*[0-9]+\s+${FMT_SEP}\s+${status} "
grepcmd="grep -v -E '^#' ${GJOB_FILE} | grep -P \"${fmt_grep}\""
# Extraction
num=0
while read -r entry ; do
    parse_jobline "$1"
    if [[ ${gjfields[3]} -ge ${startdate} && ${gjfields[4]} -le ${enddate} ]]; then
        num=$((num + 1))
        print_entry "$entry"
    fi
done < <(eval "${grepcmd}")
# Final output
echo "-----------------------"
echo "Number of jobs corresponding to the criteria:" ${num}
#!/bin/bash

GJOB_FILE="${HOME}/gjoblist.txt"
#GJOB_FILE="gjoblist.txt"

#  Formats
# ---------
date_format="%Y%m%d"
FMT_SEP=':'
GJOB_HEADER="#  ID   ${FMT_SEP} STATUS ${FMT_SEP}  JOBID  ${FMT_SEP} STARTDATE\
 ${FMT_SEP}  ENDDATE ${FMT_SEP} QUEUE ${FMT_SEP} NODE ${FMT_SEP} JOBNAME\
 ${FMT_SEP} INPUT ${FMT_SEP} PATH"

fmt_index="%06d"
fmt_jobstat="%4s"
fmt_jobid="%7d"
fmt_date="%08d"

GJOB_DATAFMT=" ${fmt_index} ${FMT_SEP}  ${fmt_jobstat}  ${FMT_SEP}\
 ${fmt_jobid} ${FMT_SEP}  ${fmt_date} ${FMT_SEP} ${fmt_date} ${FMT_SEP}\
 %s ${FMT_SEP} %s ${FMT_SEP} %s ${FMT_SEP} %s ${FMT_SEP} %s\n"

#  Functions
# -----------
function print_entry () {
    parse_jobline "$1"
    status=${gjfields[1]}
    fmt="Job num. ${fmt_index}\n\
    Input file: %s (path: %s)\n\
    Status: %s\n"
    printf "${fmt}" $((10#${gjfields[0]}+0)) ${gjfields[8]} ${gjfields[9]} \
        ${status}
    if [[ ${status} != "WAIT" ]]; then
        fmt="\
    Submitted wih queue ID %d on queue %s (node: %s)\n\
    Starting date: %s\n"
        stardate=$(date -d "${gjfields[3]}" +"%B %-d, %Y")
        printf "${fmt}" $((10#${gjfields[2]}+0)) ${gjfields[5]} ${gjfields[6]}\
            ${startdate}
        if [[ ${status} == "GOOD" || ${status} == "FAIL" ]]; then
            printf "    End date: %s\n" $(date -d "${gjfields[4]}" +"%B %-d, %Y")
        fi
    fi
    printf "    Job name: %s\n" ${gjfields[7]}
}

function parse_jobline () {
    trimmed=$(echo "${1}" | sed -e 's/\s\+:\s\+/:/g' -e 's/^\s\+//')
    IFS="${FMT_SEP}" read -a gjfields <<<"${trimmed}"
}

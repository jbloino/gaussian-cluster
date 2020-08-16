#/bin/bash

#  Include parameters files
# --------------------------
source gjobdata.bash

#  Usage
# -------
if [[ $# -eq 0 ]]; then
    echo "Usage: gjobres.bash jobnum [ queue ]"
    exit
fi

#  Argument parsing and default values
# -------------------------------------
jobid=$(printf "${fmt_index}" $1)
line=$(grep -E "^\s+$jobid" ${GJOB_FILE})

#  Reset line
# ------------
if [[ -z ${line} ]]; then
    echo "Job not found. Nothing to do"
    exit
else
    parse_jobline "$line"
    if [[ $# -eq 2 ]]; then
        queue=$2
    else
        queue=${gjfields[5]}
    fi
    newline=$(printf "${GJOB_DATAFMT}" $((10#$jobid+0)) "WAIT" 0 0 0 "${queue}" "NONE" "${gjfields[7]}" "${gjfields[8]}" "${gjfields[9]}")
    sed -r -i "s#^\s+${jobid}.*#${newline}#" "${GJOB_FILE}"
    echo "Job ID ${jobid} has been resetted"
fi


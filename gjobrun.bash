#!/bin/bash

#  Include parameters files
# --------------------------
source gjobdata.bash

#  Usage
# -------
if [[ $# -eq 0 ]]; then
    echo "Usage: gjobrun.bash id [ gver [ copychk ] ]"
    echo "       copychk should be 0 (no), auto (default) or 1 (yes)"
    echo "       -> See gxxrun.bash for details"
    echo "       gver: version of gaussian, as gxxrev"
    exit
fi

#  Argument parsing and default values
# -------------------------------------
myid=${1:?"Error: Missing job id"}
gxx=${2:-g16b01}
cpchk=${3:-auto}
# Check if value for checkpoint copy correct
if ! [[ " 0 1 auto " =~ " $cpchk " ]]; then
    echo "ERROR: Incorrect value for copychk"
    exit
fi
# Check id
if [[ $myid =~ ^[0-9]+$ ]]; then
    fullid=$(printf "${fmt_index}" $myid)
else
    echo "ERROR: Expected integer as job id"
    exit
fi

line=$(grep -E "^\s+$fullid " ${GJOB_FILE})
if [[ -z $line ]]; then
    echo "ERROR: Cannot find job id $fullid"
    exit
fi

parse_jobline "$line"
stat=${gjfields[1]}
if [[ $stat == "EXEC" ]]; then
    echo "Job already in progress. Exiting."
    exit
elif [[ $stat == "QSUB" ]]; then
    echo "Job already submitted. Exiting."
    exit
elif [[ $stat == "GOOD" ]]; then
    echo "Job finished regularly."
    read -p "Rerun (Y/N)? " -n 1 -r
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "Restarting job"
    elif [[ $REPLY =~ ^[Nn]$ ]]; then
        echo "Aborting"
        exit
    else
        echo "Invalid answer. Assuming no."
        exit
    fi
fi

cd ${gjfields[9]}
res=$(gxxrun.bash ${gjfields[8]} ${gjfields[5]} ${gjfields[7]} $gxx $cpchk | tail -n 1 | awk '{print $4}' | sed 's/"//g')
qid=$(printf ${fmt_jobid} ${res%.*})
newline=$(printf "${GJOB_DATAFMT}" $((10#${fullid}+0)) "QSUB" ${qid} 0 0 \
    "${gjfields[5]}" "${gjfields[6]}" "${gjfields[7]}" "${gjfields[8]}" \
    "${gjfields[9]}")
sed -r -i "s#^\s+${fullid}.*#${newline}#" "${GJOB_FILE}"

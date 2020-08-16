#/bin/bash

#  Include parameters files
# --------------------------
source gjobdata.bash

#  Usage
# -------
if [[ $# -eq 0 ]]; then
    echo "Usage: gjobadd.bash input [ queue [ jobname [ comment [ path ]]]]"
    exit
fi

#  Argument parsing and default values
# -------------------------------------
mygjf=${1:?"Error: Missing Gaussian input file"}
queue=${2:-q02curie}
job=${3:-${mygjf%.*}}
comment=${4:-false}
mypath=${5:-${PWD}}
# Check input file existence
if [[ ! -e "$mypath/$mygjf" ]]; then
    echo "ERROR: Cannot find input file in path"
    exit
fi

#  Get last used index
# ---------------------
# Check if "data file" exists and gets the last index (1 if new file)
if [[ ! -e ${GJOB_FILE} ]]; then
    echo ${GJOB_HEADER} > ${GJOB_FILE}
    myid=1
else
    # 10# means that base 10 must be used (numbers starting with 0 are considered in octal base)
    myid=$((10#$(grep -v -E '^#' ${GJOB_FILE} | tail -n 1 | awk '{print $1}' ) + 1))
fi

# Insert comments before the actual job definition
if [[ "${comment}" != "false" ]]; then
    printf '# %s\n' "$comment" >> ${GJOB_FILE}
fi

#  Job definition
# ----------------
printf "${GJOB_DATAFMT}" $myid "WAIT" 0 0 0 $queue "NONE" $job $mygjf $mypath\
    >> ${GJOB_FILE}
echo "Job number: ${myid}"

#!/bin/bash

# Needed to get all aliases and general variables since used by gxx_qsub
shopt -s extglob

#  Usage
# -------
if [[ $# -eq 0 ]]; then
    echo "Usage: gxxrun.bash input [ queue [ jobname [ gver [ copychk ]]]]"
    echo "       copychk should be 0 or 1"
    echo "       Intended for filenames with structure name.job.gjf"
    echo "       gver: version of gaussian, as gxxrev"
    exit
fi

#  Argument parsing and default values
# -------------------------------------
mygjf=${1:?"Error: Missing Gaussian input file"}
queue=${2:-q02curie}
job=${3:-${mygjf%.*}}
gxx=${4:-g16ver}
cpchk=${5:-auto}
# Auto mode is intended for specific structures. No attempt to be general
if [[ $cpchk == "auto" ]]; then
    p=".*\.(frq|anh)\..*"
    [[ $mygjf =~ $p ]] && cpchk=1 || cpchk=0
fi
# Build chk from the input filename, changing the extension
#   Several extensions can be used. Hence the trick.
gjfext=${mygjf##*.}
if [[ $cpchk == 1 ]]; then
    chkf=${mygjf/$gjfext/chk}
    p="@(frq|anh)"
    cp ${chkf/$p/opt} $chkf
fi

#  Run Gaussian
# --------------
gxx_qsub.py -m -q $queue -g $gxx -j "$job" $mygjf


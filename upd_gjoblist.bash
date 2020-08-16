#!/bin/bash

# Include parameters files
source gjobdata.bash

echo "Small script to update old gjoblist.txt to new layout"
echo "Note that the old file did not have specific delimiter.
Be careful if your paths/input files contain it."

# Ask confirmation before proceeding
echo "Proceed? (yes|no)"
read answer

# Case-insensitive answer, answer converted to lowercase
if [[ ${answer,,} != "yes" ]]; then
    exit
fi

# Check if file has already been updated
#   The original file had QUEUE missing in the header (oups)
if [[ "$(tail -n 1 ${GJOB_FILE})" == *"QUEUE"* ]]; then
    echo "File already updated. Exiting."
    exit
fi

# Backup file and uses it to build the new file
TMPFILE="/tmp/gjoblist.txt"
cp "${GJOB_FILE}" "${TMPFILE}"

# Write header
echo "${GJOB_HEADER}" > ${GJOB_FILE}

# Copy and reorganize the columns
num=0
while IFS= read -r line; do
    num=$((num + 1))
    if [[ $num -gt 1 ]]; then
        fields=($line)
        printf "${GJOB_DATAFMT}" $((10#${fields[0]}+0)) ${fields[1]} \
            $((10#${fields[2]}+0)) $((10#${fields[4]}+0)) \
            $((10#${fields[5]}+0)) ${fields[6]} ${fields[3]} ${fields[7]} \
            ${fields[8]} ${fields[9]} >> ${GJOB_FILE}
    fi
done < "${TMPFILE}"

# Remove temporary file
rm "${TMPFILE}"
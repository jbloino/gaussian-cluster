#!/usr/bin/env python3

import os
import sys
import time
import email
import mailbox
from subprocess import Popen, PIPE

USERNAME = os.getenv('USER')
HOMEDIR = os.getenv('HOME')
GJOBDATA_FILE = os.path.join(HOMEDIR, 'bin', 'gjobdata.bash')
# GJOBDATA_FILE = 'gjobdata.bash'
gjob_fmts = {
    'FMT_SEP': None,
    'fmt_index': None,
    'fmt_jobstat': None,
    'fmt_jobid': None,
    'fmt_date': None,
    'date_format': None
}
fmt_data = None
if os.path.exists(GJOBDATA_FILE):
    with open(GJOBDATA_FILE, 'r') as fobj:
        for line in fobj:
            if line.startswith('FMT_SEP') or line.startswith('date_format'):
                key, value = line.split('=')
                gjob_fmts[key] = value.strip("\"'\n")
            elif line.startswith('fmt_'):
                key, value = line.split('=')
                gjob_fmts[key] = value.strip("\"'\n").replace('%', '{:') + '}'
            elif line.startswith('GJOB_DATAFMT'):
                fmt_data = line.split('=')[1].strip("\"'\\\n")
                while line.strip().endswith('\\'):
                    line = next(fobj)
                    fmt_data += line.strip("\"'\\\n")
gjob_fmts['fmt_data'] = fmt_data.replace('$', '').format(**gjob_fmts)\
    .replace(r'%s', r'{}').replace('\\n', '\n')
GJOB_FILE = os.path.join(HOMEDIR, 'gjoblist.txt')
tmpfile = os.path.splitext(GJOB_FILE)[0] + '.tmp'
MBOXFILE = os.path.join('/', 'var', 'spool', 'mail', USERNAME)
# DELTA_CHK set to 30+1 min. Should be consistent with CRONTAB setting
DELTA_CHK = (30+1)*60
NOW = time.time()
last_chk = NOW - DELTA_CHK

qstat_fmt = "qstat -n -1 | grep -E '^\\s\\+{}'"

mbox = mailbox.mbox(MBOXFILE)

#  Email management
# ------------------
# For now, deactivated since unable to make deleting file work as mailbox needs
# to write temporary files in /var/spool/mail
# remove email which are more than 36 hours old
DELTA_OLD = 1.5*24*3600
# Define when an email is considered old for cancellation
old_mail = NOW - DELTA_OLD
to_del = []

#  Look for new received emails
# ------------------------------
for key, message in mbox.iteritems():
    maildate = email.utils.parsedate(message['date'])
    mailtime = time.mktime(maildate)
    subject = message['subject']
    if subject.find('PBS JOB') >= 0:
        if mailtime > last_chk:
            jobid = subject.split()[2].split('.')[0]
            strdate = time.strftime(gjob_fmts['date_format'], maildate)
            if message.is_multipart():
                content = ''.join(part.get_payload(decode=True)
                                  for part in message.get_payload())
            else:
                content = message.get_payload(decode=True)
            bdate = False
            edate = False
            adate = False
            if content.find(b'\nExecution terminated\n') > 0:
                edate = strdate
            elif content.find(b'\nBegun execution\n') > 0:
                bdate = strdate
            elif content.find(b'\nAborted by PBS Server \n') > 0:
                adate = strdate
            else:
                print('Unrecognized email type from PBS')
                print(content)
                sys.exit()
            with open(GJOB_FILE, 'r') as fobjr, open(tmpfile, 'w') as fobjw:
                for line in fobjr:
                    if line.strip().startswith('#'):
                        jobid_read = ''
                    else:
                        data = line.split(':')
                        jobid_read = data[2].strip()
                    if jobid_read == jobid:
                        if bdate:
                            # Check job on qstat
                            # Technically, this test could fail if rerun on
                            # same day as failed job
                            # This case is ignored here.
                            p = Popen(args=qstat_fmt.format(jobid),
                                      shell=True, stdout=PIPE)
                            out = p.communicate()[0].decode()
                            if out:
                                node = out.split()[-1].split('/')[0]
                                data[6] = node
                                data[1] = 'EXEC'
                            data[3] = bdate
                        elif adate:
                            data[1] = 'FAIL'
                            data[4] = adate
                        elif edate:
                            data[1] = 'GOOD'
                            data[4] = edate
                        newline = gjob_fmts['fmt_data'].format(
                                int(data[0]), data[1].strip(), int(jobid),
                                int(data[3]), int(data[4]), data[5].strip(),
                                data[6].strip(), data[7].strip(),
                                data[8].strip(), data[9].strip())
                    else:
                        newline = line
                    fobjw.write(newline)
            os.rename(tmpfile, GJOB_FILE)
        # elif mailtime < old_mail and message['subject'].find('PBS JOB') >= 0:
        #     to_del.append(key)

# if to_del:
#     mbox.lock()
#     print(to_del)
#     for val in to_del:
#         mbox.remove(val)
#     mbox.flush()
#     #mbox.close()

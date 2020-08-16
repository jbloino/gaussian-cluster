#!/usr/bin/env python3

import os
import sys
import re
import argparse
from configparser import ConfigParser
from math import inf
import socket  # module for the fully qualified named of the headnode
from subprocess import Popen, PIPE
try:
    import typing
except ModuleNotFoundError:
    print('ERROR: Python 3.5 or later needed.')
    sys.exit()

# ====================================
#   INSTALLATION-SPECIFIC PARAMETERS
# ====================================

# Server Data
# -----------
# This is used for the emailing system
# Email capabilities can be deactivated by setting EMAILSERVER to None
HEADNODE = socket.gethostname()
EMAILSERVER = "{}.sns.it".format(HEADNODE)

#  Gaussian-related definitions
# -----------------------------
# Equivalency between procs archs and Gaussian mach dirs
# machine arch as defined in HPC ini file -> Macs in Gxx ini file.
# This depends on the naming convention adopted on each cluster
GXX_ARCHS = {
    'nehalem': 'intel64-nehalem',
    'westmere': 'intel64-nehalem',
    'sandybridge': 'intel64-sandybridge',
    'ivybridge': 'intel64-sandybridge',
    'skylake': 'intel64-sandybridge',
    'bulldozer': 'amd64-bulldozer'
}
# From early tests, best to use only physical cores
# Anyway, this can be changed depending on preferences
USE_LOGICAL_CORE = False
# Maximum occupation of the total memory on a given node
# By default, Gaussian does a very good job in managing the memory, but there
#   is some memory set statically, so besides %Mem
# We limit the user or default requirements to 90% of the available memory.
MEM_OCCUPATION = .9
# By default, Gxx_QSub allows unsupported workings (workings not listed in
#   the section of Gaussian versions).  If set False, only workings listed
#   in `Workings` are allowed.
ANY_WORKING = True
# Aliases can be defined as a dictionary, for instance: g16->g16c01
#   By default, the dictionary is created automatically if None here
GXX_ALIAS = None
# Default version of Gaussian to run (must be a keyword)
GDEFAULT = 'g16c01'

# Basic Paths
# -----------
# By default, many path are built, but they can be overridden below
INIPATH = '/fix/me'  # Path containing .ini files
LIBPATH = os.path.join(INIPATH, 'lib')  # Library path for HPC modules
# TMPPATH is only used if users asked to copy back some speciic files
#   but do not provide any specific paths back.  To avoid overridding any
#   file, Gxx-QSub creates a directory in HOME based on the PID.
# {pid} refers to the job PID, dirs can be added too.
TMPDIR = 'scratch-{pid}'

# Config File Names
# -----------------
# NOTE: By default, Gxx_Qsub lets the user adds their own setup
# This can be deactivated by simply setting the two variables below to
#   `None` and setting the full paths for HPCINIPATH and GXXINIPATH
HPCINIFILE = 'hpcnodes.ini'
GXXINIFILE = 'gxxconfig.ini'

# Full Paths
# ----------
# Full paths, normally created but can be hardcoded
HPCINIPATH = os.path.join(INIPATH, HPCINIFILE)
GXXINIPATH = os.path.join(INIPATH, GXXINIFILE)
HPCMODPATH = LIBPATH

# ================
#   DEPENDENCIES
# ================
# Provides default paths for the dependencies.
DEFAULT_PATHS = {
    'hpc_inifile': HPCINIPATH,
    'hpc_modpath': HPCMODPATH,
    'gxx_inifile': HPCMODPATH,
}
sys.path.insert(0, DEFAULT_PATHS['hpc_modpath'])

import hpcnodes as hpc  # NOQA

# ================
#   PROGRAM DATA
# ================

AUTHOR = "Julien Bloino (julien.bloino@sns.it)"
VERSION = "2020.08.16"
# Program name is generated from commandline
PROGNAME = os.path.basename(sys.argv[0])

# ====================================
#   HPC INFRASTRUCTURE-SPECIFIC DATA
# ====================================

#  Environment variables
# ------------------------
jobPID = str(os.getpid())
USERNAME = os.getenv('USER')
DEFAULTDIR = os.path.join(os.getenv('HOME'), TMPDIR.format(pid=jobPID))
STARTDIR = os.getcwd()
# We only support one file for HPC ini data, otherwise it would risk
#   creating confusion in case of inconsistent data.
if HPCINIFILE is not None:
    res = os.path.join(os.getenv('HOME'), HPCINIFILE)
    if os.path.exists(res):
        HPCFile = res
else:
    HPCFile = DEFAULT_PATHS['hpc_inifile']

#  Queue definitions
# -------------------
if not os.path.exists(HPCFile):
    print('ERROR: Incorrect path to HPC nodes specification files.')
    sys.exit()

HPCNODES = hpc.parse_ini(HPCFile)
HPCQUEUES = hpc.list_queues_nodes(HPCNODES)

HELP_QUEUES = """Sets the queues.
Available queues:
{}

Virtual queues defined as:
<queue>[:[nprocs][:nodeid]]
with:
    <queue>: one of the queues above
    nprocs: choice for number of processing units
        - "H" : uses half of the cores of a single CPU
        - "S" : uses a single core
        - "0" : auto (same as empty)
        - positive integer: total number of cores to use.
        - negative integer: number of CPUs to use
""".format(', '.join(sorted(HPCQUEUES.keys())))


#  Gaussian-related definitions
# -----------------------------
GXX_FORMAT = re.compile(r'g(dv|\d{2})\.?\w\d{2}[p+]?')
# Sets the Gaussian ini files.
# The user can set their own file to override what the system is providing
GxxFiles = []
if GXXINIFILE is not None:
    res = os.path.join(os.getenv('HOME'), GXXINIFILE)
    if os.path.exists(res):
        GxxFiles.append(res)
GxxFiles.append(DEFAULT_PATHS['gxx_inifile'])

# Get Gaussian data file
gconf = ConfigParser()
gconf.read(GxxFiles)
defvals = gconf.defaults()
WorkTags = []

if 'workinfo' in defvals:
    WorkInfo = {}
    for info in defvals['workinfo'].split(','):
        res = [item.strip() for item in info.split(':', maxsplit=3)]
        if len(res) == 3:
            key = res[0] or 'def'
            name = res[1] or 'System'
            mail = res[2] or 'N/A'
        else:
            print('ERROR: WorkInfo format must contain 2 ":"')
            sys.exit(1)
        if key in WorkTags:
            print('ERROR: Duplicate tags "{}"'.format(key))
            sys.exit(1)
        WorkTags.append(key)
        WorkInfo[key] = (name, mail)
else:
    WorkInfo = {'def': ('System', 'N/A')}

if 'workpath' in defvals:
    WorkRoots = {0: defvals['workpath']}
    for info in defvals['workpath'].split(','):
        res = [item.strip() for item in info.split(':', maxsplit=1)]
        if len(res) == 2:
            key = res[0] or 'def'
            path = res[1]
        else:
            print('ERROR: WorkPath format must contain 1 ":"')
            sys.exit(1)
        if key in WorkRoots:
            print('ERROR: Duplicate tag in WorkPath')
            sys.exit(1)
        WorkRoots[key] = path
else:
    WorkRoots = None

# Extract Gaussian Installation Versions
# ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
# Supported formax gXX[.]ABB[p/+]
GVERSIONS = {}
for sec in sorted(gconf.sections()):
    if GXX_FORMAT.match(sec):
        key = sec.lower().replace('.', '').replace('+', 'p')
        GVERSIONS[key] = {}
        data = gconf[sec]
        # Root path
        if 'FullPath' in data:
            res = data['FullPath']
        else:
            if gconf.get(sec, 'RootPath', fallback=None) is None:
                print('ERROR: Missing Gaussian root installation dir.')
                sys.exit(1)
            if 'BaseDir' in data:
                res = os.path.join(data['RootPath'], data['BaseDir'])
            else:
                print('ERROR: Either `BaseDir`+`RootPath` or `FullPath`',
                      'must be set.')
                sys.exit(1)
        GVERSIONS[key]['path'] = res
        # Gaussian final directory
        GVERSIONS[key]['gdir'] = gconf.get(sec, 'GDir',
                                           fallback=sec.split('.')[0].lower())
        # Machine architectures
        res = gconf.get(sec, 'Machs', fallback=None)
        if res.strip() == ' ':
            res = None
        if res is not None:
            res = [item.strip() for item in res.split(',')]
        GVERSIONS[key]['mach'] = res
        # Gaussian version label
        if 'Name' in data:
            res = data['Name']
        else:
            if 'Gaussian' not in data or 'Revision' not in data:
                print('ERROR: Gaussian/Revision or Name must be provided.')
                sys.exit(1)
            res = data['Gaussian'] + ' Rev. ' + data['Revision']
        GVERSIONS[key]['name'] = res
        # Gaussian release date
        GVERSIONS[key]['date'] = gconf.get(sec, 'Date', fallback=None)
        # Usage restrictions
        res = gconf.get(sec, 'Shared', fallback=None)
        if res is not None:
            items = [x.strip().lower() for x in res.split(',')]
            if {'any', 'all'} & set(items):
                res = None
            else:
                res = [x.strip() for x in res.split(',')]
        GVERSIONS[key]['pub'] = res
        # Available standard/default workings
        if 'Workings' in data:
            res = [item.strip() for item in data['Workings'].split(',')]
            if set(res) - set(WorkTags):
                for item in res:
                    if item not in WorkTags:
                        WorkTags.append(item)
        else:
            res = None
        GVERSIONS[key]['work'] = res

if GDEFAULT not in GVERSIONS:
    print('ERROR: Default version of Gaussian not present in config files')
    sys.exit(1)

# Sort Working Tags
# ^^^^^^^^^^^^^^^^^
WorkTags.sort()
scr = [item.lower() for item in WorkTags]
if len(scr) < len(WorkTags):
    print('WARNING: Some tags only differ by the case.',
          'Assuming this is correct.')

# Gaussian Working Trees
# ^^^^^^^^^^^^^^^^^^^^^^
WORKINGS = {}
# We select the working-related sections by complementarity:
#   everything which does not have the Gaussian version format
#   is a priori a possible working
# Gxx_QSub only supports the format "tag.gxx.rev"
for sec in sorted(gconf.sections()):
    if not GXX_FORMAT.match(sec):
        wtags = sec.lower().replace('+', 'p').split('.')
        if len(wtags) != 3:
            continue
        tag, gxx, rev = wtags
        data = gconf[sec]
        # Get information on Gaussian version (shortened label and name)
        # Then compare if part of the versions
        gver = gxx + rev
        # Gaussian version label
        if 'Name' in data:
            gname = data['Name']
        else:
            if 'Gaussian' not in data or 'Revision' not in data:
                print('ERROR: Gaussian/Revision or Name must be provided.')
                sys.exit(1)
            gname = data['Gaussian'] + ' Rev. ' + data['Revision']
        # Check if reference Gaussian version installed
        gkey = None
        if gver in GVERSIONS:
            gkey = gver
        else:
            for key in GVERSIONS:
                if GVERSIONS[key]['name'] == gname:
                    gkey = key
        # Check if missing Gaussian installation or working not allowed
        if gkey is None:
            print('ERROR: Reference Gaussian version not found.')
            sys.exit(1)
        elif not ANY_WORKING:
            if tag not in GVERSIONS[gkey]['Workings']:
                break
        # Build key
        # For GDV, since rev unique, use tagrev
        # For Gxx, there may be overlap, so taggxxrev
        if wtags[1] == 'gdv':
            key = tag + rev
        else:
            key = tag + gxx + rev
        WORKINGS[key] = {'gref': gkey}
        # Root path
        if 'FullPath' in data:
            res = data['FullPath']
        else:
            if gconf.get(sec, 'WorkPath', fallback=None) is None:
                print('ERROR: Missing working root directory.')
                sys.exit(1)
            else:
                # Check if workpath startswith the tag (for DEFAULT)
                if WorkRoots is not None:
                    if data['WorkPath'] == WorkRoots[0]:
                        if tag not in WorkRoots:
                            fmt = 'ERROR: Missing default WorkPath for "{}"'
                            print(fmt.format(tag))
                            sys.exit(1)
                        wroot = WorkRoots[tag]
                    else:
                        wroot = data['WorkPath']
                else:
                    wroot = data['WorkPath']
            if 'BaseDir' in data:
                res = os.path.join(wroot, data['BaseDir'])
            else:
                print('ERROR: Either `BaseDir`+`WorkPath` or `FullPath`',
                      'must be set.')
                sys.exit(1)
        WORKINGS[key]['path'] = res
        # Gaussian version label
        WORKINGS[key]['name'] = gname
        # Version
        WORKINGS[key]['ver'] = gconf.get(sec, 'Version', fallback=None)
        # Update date
        WORKINGS[key]['date'] = gconf.get(sec, 'Date', fallback=None)
        # Machine architectures
        res = gconf.get(sec, 'Machs', fallback=None)
        if res.strip() == ' ':
            res = None
        if res is not None:
            res = [item.strip() for item in res.split(',')]
        WORKINGS[key]['mach'] = res
        # Usage restrictions
        res = gconf.get(sec, 'Shared', fallback=None)
        if res is not None:
            items = [x.strip().lower() for x in res.split(',')]
            if {'any', 'all'} & set(items):
                res = None
            else:
                res = [x.strip() for x in res.split(',')]
        WORKINGS[key]['pub'] = res
        # Author information
        if tag in WorkInfo:
            WORKINGS[key]['auth'] = WorkInfo[tag][0]
            WORKINGS[key]['mail'] = WorkInfo[tag][1]
        else:
            WORKINGS[key]['auth'] = None
            WORKINGS[key]['mail'] = None
        # Changelog
        if 'changelog' in data:
            vers = data['changelog'].split(',')
            WORKINGS[key]['clog'] = []
            for item in vers:
                res = item.split(':')
                if len(res) == 2:
                    fname, ftype = [s.strip() for s in res]
                else:
                    fname = res[0].strip()
                    ftype = os.path.splitext(fname)[0][1:].upper()
                if fname.strip().startswith('.'):
                    if fname.count('.') == 1:
                        if len(WORKINGS[key]['clog']) == 0:
                            print('ERROR: Changelog alternative format but no',
                                  'main format.')
                            sys.exit()
                        else:
                            fname = None
                if fname is not None:
                    fname = fname.format(fullpath=WORKINGS[key]['path'])
                WORKINGS[key]['clog'].append((fname, ftype))
        else:
            WORKINGS[key]['clog'] = None
        # Other documentations
        if 'docs' in data:
            WORKINGS[key]['docs'] = {}
            docs = data['docs'].split('\n')
            for item0 in docs:
                try:
                    keydoc, paths = item0.split(':', maxsplit=1)
                except ValueError:
                    print('ERROR: Format for docs should be:',
                          'DOCTYPE:path[:format][,[altpath]ext[:format]].')
                    sys.exit(1)
                WORKINGS[key]['docs'][keydoc] = []
                vers = paths.split(',')
                for item1 in vers:
                    res = item1.split(':')
                    if len(res) == 2:
                        fname, ftype = [s.strip() for s in res]
                    else:
                        fname = res[0].strip()
                        ftype = os.path.splitext(fname)[0][1:].upper()
                    if fname.strip().startswith('.'):
                        if fname.count('.') == 1:
                            if len(WORKINGS[key]['docs'][keydoc]) == 0:
                                print('ERROR: {} alternative'.format(keydoc),
                                      'format but no main format.')
                                sys.exit()
                            else:
                                fname = None
                    if fname is not None:
                        fname = fname.format(fullpath=WORKINGS[key]['path'])
                    WORKINGS[key]['docs'][keydoc].append((fname, ftype))
        else:
            WORKINGS[key]['docs'] = None

# Gaussian Keyword Aliases
# ^^^^^^^^^^^^^^^^^^^^^^^^
if GXX_ALIAS is None:
    GXX_ALIAS = {}
    for gxx in GVERSIONS:
        # Alias to the latest version
        # This assumes that GVERSIONS is sorted by increasin
        key = gxx[:3]
        GXX_ALIAS[key] = gxx

# Automatic Documentation
# ^^^^^^^^^^^^^^^^^^^^^^^
HELP_GXX = 'Absolute paths or the following keywords are supported:\n'
# Gaussian versions
fmt = '+ {kword:7s}: {label:22s} ({date}){extra}\n'
for gxx in GVERSIONS:
    gname = GVERSIONS[gxx]['name']
    gdate = GVERSIONS[gxx]['date'] or 'N/A'
    if gxx == GDEFAULT:
        ginfo = ' - default'
    else:
        ginfo = ''
    HELP_GXX += fmt.format(kword=gxx, label=gname, date=gdate, extra=ginfo)
# Aliases
fmt = '+ {kword:7s}: Alias for "{gtag}"\n'
for gxx in GXX_ALIAS:
    HELP_GXX += fmt.format(kword=gxx, gtag=GXX_ALIAS[gxx])
# Workings
fmt = '+ {kword:7s}: Working by {auth} for {label} (updated: {date})\n'
fmt2 = '    {{dtype:{:d}s}}: {{path}}{{extra}}\n'
for gxx in WORKINGS:
    gname = WORKINGS[gxx]['name']
    gdate = WORKINGS[gxx]['date'] or 'N/A'
    gauth = WORKINGS[gxx]['auth'] or '<Unknown>'
    HELP_GXX += fmt.format(kword=gxx, auth=gauth, label=gname, date=gdate)
    # For a prettier output, try to align the colons between the different docs
    #   So we calculate first the longest doctype.
    if WORKINGS[gxx]['clog'] is not None:
        l_doctype = 9
    else:
        l_doctype = 0
    if WORKINGS[gxx]['docs'] is not None:
        l_doctype = max(l_doctype, *[len(x) for x in WORKINGS[gxx]['docs']])
    # Build format only if l_doctype > 0:
    if l_doctype > 0:
        dfmt = fmt2.format(l_doctype)
        if WORKINGS[gxx]['clog'] is not None:
            prt = []
            for path, ftype in WORKINGS[gxx]['clog']:
                if path is not None:
                    prt.append([path, []])
                else:
                    prt[-1][1].append(ftype)
            for item in prt:
                if item[1]:
                    extra = ' ({} available)'.format(', '.join(item[1]))
                else:
                    extra = ''
                HELP_GXX += dfmt.format(dtype='CHANGELOG', path=item[0],
                                        extra=extra)
        if WORKINGS[gxx]['docs'] is not None:
            for dtype in WORKINGS[gxx]['docs']:
                prt = []
                for path, ftype in WORKINGS[gxx]['docs'][dtype]:
                    if path is not None:
                        prt.append([path, []])
                    else:
                        prt[-1][1].append(ftype)
                for item in prt:
                    if item[1]:
                        extra = ' ({} available)'.format(', '.join(item[1]))
                    else:
                        extra = ''
                    HELP_GXX += dfmt.format(dtype=dtype, path=item[0],
                                            extra=extra)
# End of documentation block
HELP_GXX += '+ Arbitrary path given by user\n'


# ====================
#   PARSER DEFINITON
# ====================
def build_parser():
    """Builds options parser.

    Builds the full option parser.

    Returns
    -------
    :obj:`ArgumentParser`
        `ArgumentParser` object
    """
    parser = argparse.ArgumentParser(
            prog=PROGNAME,
            formatter_class=argparse.RawTextHelpFormatter)
    #  MANDATORY ARGUMENTS
    # ---------------------
    parser.add_argument('infile', help="Gaussian input file(s)", nargs='*')
    #  OPTIONS
    # ---------
    # Qsub-related options
    # ^^^^^^^^^^^^^^^^^^^^
    queue = parser.add_argument_group('queue-related options')
    queue.add_argument(
        '-j', '--job', dest='job',
        help='Sets the job name. (NOTE: PBS truncates after 15 characaters')
    queue.add_argument(
        '-m', '--mail', dest='mail', action='store_true',
        help='Sends notification emails')
    queue.add_argument(
        '--mailto', dest='mailto',
        help='Sends notification emails')
    queue.add_argument(
        '-M', '--mach', dest='mach', action='store_true',
        help='Prints technical info on the machines available in the cluster')
    queue.add_argument(
        '--multi', choices=('parallel', 'serial'),
        help='Runs multiple jobs in a single submission')
    queue.add_argument(
        '--node', dest='node', type=int,
        help='Name of a specific node (ex: curie01)')
    queue.add_argument(
        '--group', dest='group', type=str,
        help='User group')
    queue.add_argument(
        '-p', '--project', dest='project',
        help='Defines the project to run the calculation')
    queue.add_argument(
        '-P', '--print', dest='prtinfo', action='store_true',
        help='Print information about the submission process')
    queue.add_argument(
        '-q', '--queue', dest='queue', default='q02zewail',
        help='{}\n{}'.format('Sets the queue type.', HELP_QUEUES),
        metavar='QUEUE')
    queue.add_argument(
        '-S', '--silent', dest='silent', action='store_true',
        help='''\
Do not save standard output and error in files
WARNING: The consequence will be a loss of these outputs''')
    # Expert options
    # ^^^^^^^^^^^^^^
    expert = parser.add_argument_group('expert usage')
    expert.add_argument(
        '--cpto', dest='cpto', nargs='+',
        help='Files to be copied to the local scratch (dumb copy, no check)')
    expert.add_argument(
        '--cpfrom', dest='cpfrom', nargs='+',
        help='Files to be copied from the local scratch (dumb copy, no check)')
    expert.add_argument(
        '--nojob', dest='nojob', action='store_true',
        help='Do not run job. Simply generate the input sequence.')
    expert.add_argument(
        '-X', '--expert', dest='expert', action='count',
        help='''\
Expert use. Can be cumulated.
- 1: bypass input analysis
''')
    # Gaussian-related options
    # ^^^^^^^^^^^^^^^^^^^^^^^^
    gaussian = parser.add_argument_group('Gaussian-related options')
    gaussian.add_argument(
        '-c', '--chk', dest='gxxchk', metavar='CHK_FILENAME',
        help='Sets the checkpoint filename')
    gaussian.add_argument(
        '-g', '--gxxroot', dest='gxxver', metavar='GAUSSIAN',
        default=GDEFAULT,
        help='{}\n{}'.format('Sets the path to the Gaussian executables.',
                             HELP_GXX))
    gaussian.add_argument(
        '-i', '--ignore', dest='gxxl0I', nargs='+', metavar='L0_IGNORE',
        choices=['c', 'chk', 'r', 'rwf', 'a', 'all'],
        help='''\
Ignore the following options in input and command list:
+ c, chk: ignore the checkpoint file (omit it in the input, do not copy it)
+ r, rwf: ignore the read-write file (omit it in the input, do not copy it)
+ a, all: ignore both checkpoint and read-write files
''')
    gaussian.add_argument(
        '-k', '--keep', dest='gxxl0K', action='append', metavar='L0_KEEP',
        default=[],
        choices=['c', 'chk', 'm', 'mem', 'p', 'proc', 'r', 'rwf', 'a', 'all'],
        help='''\
Keeps user-given parameters to control the Gaussian job in input file.
The possible options are:
+ c, chk:  Keeps checkpoint filename given in input
+ m, mem:  Keeps memory requirements given in input
+ p, proc: Keeps number of proc. required in input
+ r, rwf:  Keeps read-write file given in input
+ a, all:  Keeps all data list above
''')
    gaussian.add_argument(
        '-o', '--out', dest='gxxlog', metavar='LOG_FILENAME',
        help='Sets the output filename')
    gaussian.add_argument(
        '-r', '--rwf', dest='gxxrwf', metavar='RWF_FILENAME',
        help='''\
Sets the read-write filename (Expert use!).
"auto" sets automatically the rwf from the input filename.''')
    gaussian.add_argument(
        '-t', '--tmpdir', dest='tmpdir', metavar='TEMP_DIR',
        help='''\
Sets the temporary directory where calculations will be run.
This is set automatically based on the node configuration.
"{username}" can be used as a placeholder for the username.''')
    gaussian.add_argument(
        '-w', '--wrkdir', dest='gxxwrk', nargs='+', metavar='WORKDIR',
        help='''\
Appends a working directory to the Gaussian path to look for executables.
Several working directories can be given by using multiple times the -w
  option. In this case, the last given working directory is the first one
  using during the path search.
NOTE: Only the path to the working root directory is needed. The script
      automatically selects the correct directories from there.
WARNING: The script expects a working tree structure as intended in the
         Gaussian developer manual.
''')

    return parser


# ==========================
#   PATH-RELATED FUNCTIONS
# ==========================
def set_gxx_env(gxxroot: str) -> typing.List[str]:
    """Sets Gaussian-related environment variables.

    Sets Gaussian-related environment variables and returns the list
        of environment variables to be passed by PBS.

    Parameters
    ----------
    gxxroot : str
        Gaussian root directory

    Returns
    -------
    list
        List of environment variables to be passed by PBS to node.
    """
    dirlist = [os.path.join(gxxroot, f)
               for f in ['bsd', 'local', 'extras', '']]
    GAUSS_EXEDIR = os.pathsep.join(dirlist)
    os.environ['GAUSS_EXEDIR'] = GAUSS_EXEDIR
    os.environ['GAU_ARCHDIR'] = os.path.join(gxxroot, 'arch')
    if 'PATH' in os.environ:
        os.environ['PATH'] = os.pathsep.join([GAUSS_EXEDIR,
                                              os.environ['PATH']])
    else:
        os.environ['PATH'] = GAUSS_EXEDIR
    if 'LD_LIBRARY_PATH' in os.environ:
        os.environ['LD_LIBRARY_PATH'] = \
            os.pathsep.join([GAUSS_EXEDIR, os.environ['LD_LIBRARY_PATH']])
    else:
        os.environ['LD_LIBRARY_PATH'] = GAUSS_EXEDIR

    return ["PATH", "LD_LIBRARY_PATH", "GAUSS_EXEDIR", "GAU_ARCHDIR"]


def check_gjf(gjf_ref: str,
              gjf_new: str,
              dat_P: typing.Optional[int] = None,
              dat_M: typing.Optional[str] = None,
              file_chk: typing.Optional[typing.Union[str, bool]] = None,
              file_rwf: typing.Optional[typing.Union[str, bool]] = None,
              rootdir: typing.Optional[str] = None
              ) -> typing.Tuple[int, str, typing.List[typing.List[str]]]:
    """Analyses and completes Gaussian input.

    Checks and modifies a Gaussian input file and extracts relevant
        information for the submission script:
    - Hardware resources to be be read from the input file
    - Files to copy.

    Parameters
    ----------
    gjf_ref : str
        Reference input file
    gjf_new : str
        New input file where completed Gaussian directives are stored.
    dat_P : int, optional
        Number of processors to request in Gaussian job.
        Otherwise, use the value in reference input file.
    dat_M : str, optional
        Memory requirement.
        Otherwise, use the value in reference input file.
    file_chk : str or bool, optional
        Checkpoint file to use.
        If None, do not specify it in input
    file_rwf : str or bool, optional
        Checkpoint file to use
        If None, do not specify it in input
    rootdir : str, optional
        Root directory to look for files

    Returns
    -------
    tuple
        The following information are returned:
        - number of processors actually requested
        - actual memory requirements
        - list of files to copy from/to the computing node
    """

    def write_hdr(fobj: typing.IO[str],
                  dat_P: typing.Optional[int] = None,
                  dat_M: typing.Optional[str] = None,
                  file_chk: typing.Optional[typing.Union[str, bool]] = None,
                  file_rwf: typing.Optional[typing.Union[str, bool]] = None
                  ) -> None:
        """Small function to write Link0 header.

        Parameters
        ----------
        dat_P : int, optional
            Number of processors to request in Gaussian job.
        dat_M : str, optional
            Memory requirement.
        file_chk : str or bool, optional
            Checkpoint file to use.
        file_rwf : str or bool, optional
            Checkpoint file to use
        """
        if dat_M is not None:
            fobj.write('%Mem={}\n'.format(dat_M))
        if dat_P is not None:
            fobj.write('%NProcShared={}\n'.format(dat_P))
        if file_chk is not None and file_chk:
            fobj.write('%Chk={}\n'.format(file_chk))
        if file_rwf is not None and file_rwf:
            fobj.write('%Rwf={}\n'.format(file_rwf))

    def process_route(route: str
                      ) -> typing.Union[bool, bool, bool, bool,
                                        typing.List[str]]:
        """Processes Gaussian's route specification section.

        Parses a route specification and checks relevant parameters.

        Parameters
        ----------
        route : str
            Route specification

        Returns
        -------
        tuple
            The following information are returned:
            - bool if Link717 will be used
            - bool if Link717 option section present in input
            - bool if Link718 will be used
            - bool if Link718 option section present in input
            - list of files to copy from/to the computing node
        """
        fmt_frq = r'\bfreq\w*=?(?P<delim>\()?\S*{}\S*(?(delim)\))\b'
        # ! fmt_geom = r'\bgeom\w*=?(?P<delim>\()?\S*{}\S*(?(delim)\))\b'
        # ! key_FC = re.compile(str_FC, re.I)
        str_FC = r'\b(fc|fcht|ht)\b'
        key_718 = re.compile(fmt_frq.format(str_FC), re.I)
        key_718o = re.compile(fmt_frq.format(r'\breadfcht\b'), re.I)
        key_717 = re.compile(fmt_frq.format(r'\breadanh'), re.I)
        key_717o = re.compile(fmt_frq.format(r'\banharm(|onic)\b'), re.I)
        use717, use718, opt717, opt718 = False, False, False, False
        extra_cp = []
        # Check if we need to copy back
        keyGeomView = re.compile(r'\bgeomview\b')
        if keyGeomView.search(route):
            extra_cp.append(['cpfrom', 'points.off'])
        key_fchk = re.compile(r'\b(FChk|FCheck|FormCheck)\b')
        if key_fchk.search(route):
            extra_cp.append(['cpfrom', 'Test.FChk'])
        if key_718.search(route):
            use718 = True
        if key_718o.search(route):
            use718 = True
            opt718 = True
            if not key_718:
                s = 'WARNING: It is not yet possible to run FCHT ' \
                    + 'calculations with ReadFCHT only'
                print(s)
        if key_717.search(route):
            use717 = True
        if key_717o.search(route):
            use717 = True
            opt717 = True

        return use717, opt717, use718, opt718, extra_cp

    nprocs = dat_P
    mem = dat_M
    ops_copy = []
    ls_exts = ['.chk', '.dat', '.log', '.out', '.fch', '.rwf']
    ls_chks = []
    # ls_chks should be given as tuples (op, file) with:
    # op = 0: cpto/cpfrom
    #      1: cpto
    #      2: cpfrom
    # Reference for `op`: scratch dir
    # file: checkpoint file of interest
    if file_chk:
        ls_chks.append((0, file_chk))
    ls_rwfs = []
    if file_rwf:
        ls_rwfs.append(file_rwf)
    ls_files = []

    newlnk = True
    inroute = False
    use717 = [None]
    use718 = [None]
    opt717 = [None]
    opt718 = [None]
    route = ['']

    with open(gjf_new, 'w') as fobjw:
        write_hdr(fobjw, dat_P, dat_M, file_chk, file_rwf)
        with open(gjf_ref, 'r') as fobjr:
            for line in fobjr:
                line_lo = line.strip().lower()
                # END-OF-BLOCK
                if not line_lo:
                    fobjw.write(line)
                    if inroute:
                        use717[-1], opt717[-1], use718[-1], opt718[-1], dat =\
                            process_route(route[-1])
                        if dat:
                            ops_copy.extend(dat)
                        inroute = False
                    continue
                # NEW BLOCK
                if line_lo == '--link1--':
                    fobjw.write(line)
                    newlnk = True
                    route.append('')
                    use717.append(None)
                    use718.append(None)
                    opt717.append(None)
                    opt718.append(None)
                    write_hdr(fobjw, dat_P, dat_M, file_chk, file_rwf)
                # INSTRUCTIONS
                else:
                    if line_lo.startswith(r'%'):
                        if line_lo != '%nosave':
                            keyval = line.split('=')[1].strip()
                            # LINK0 INSTRUCTION
                            if line_lo.startswith(r'%chk'):
                                if file_chk is None:
                                    ls_chks.append((0, keyval))
                                else:
                                    line = ''
                            elif line_lo.startswith(r'%oldchk'):
                                ls_chks.append((1, keyval))
                            elif line_lo.startswith(r'%rwf'):
                                if file_rwf is not False:
                                    ls_rwfs.append(keyval)
                                else:
                                    line = ''
                            elif line_lo.startswith('%mem'):
                                if dat_M is None:
                                    mem = keyval
                                else:
                                    line = ''
                            elif line_lo.startswith('%nproc'):
                                if dat_P is None:
                                    nprocs = int(keyval)
                                else:
                                    line = ''
                    elif (line_lo.startswith('#') and newlnk) or inroute:
                        # ROUTE SECTION
                        newlnk = False
                        inroute = True
                        route[-1] += ' ' + line.strip()
                    else:
                        # REST OF INPUT
                        # The input files should not contain any spaces
                        # We assume that extensions are provided
                        if use717[-1] or use718[-1]:
                            if len(line_lo.split()) == 1 and \
                                    line_lo.find('.') > 0:
                                ext = os.path.splitext(line.strip())[1]
                                if ext[:4] in ls_exts:
                                    ls_files.append(line.strip())
                    fobjw.write(line)

    # Copy files for CHK
    if ls_chks:
        # set is there to remove duplicate files
        for oper, chk in set(ls_chks):
            if oper in [0, 1] and os.path.exists(chk):
                ops_copy.append(['cpto', chk, rootdir])
            if oper in [0, 2]:
                ops_copy.append(['cpfrom', chk, rootdir])
    if ls_rwfs:
        # set is there to remove duplicate files
        for rwf in set(ls_rwfs):
            if os.path.exists(rwf):
                ops_copy.append(['cpto', rwf, rootdir])
            ops_copy.append(['cpfrom', rwf, rootdir])
    if ls_files:
        for fname in set(ls_files):
            if os.path.exists(fname):
                ops_copy.append(['cpto', fname, rootdir])

    if ops_copy:
        for cmd, what, _ in ops_copy:
            if cmd == 'cpto':
                dname, fname = os.path.split(what)
                if dname:
                    print('Will copy file: {} from {}'.format(fname, dname))
                else:
                    print('Will copy file: {}'.format(what))

    return nprocs, mem, ops_copy


# ============================
#   QUEUES-RELATED FUNCTIONS
# ============================
def get_queue_data(full_queue: str,
                   ) -> typing.Tuple[str, hpc.NodeFamily, int,
                                     typing.Union[str, None]]:
    """Returns the queue specification and node-specific information.

    Based on the full_queue specification, defines and returns:
    - the actual queue (if virtual queue specified)
    - the node family specifications
    - the number of processing units to use
    - a specific node definition (if relevant)

    Parameters
    ----------
    full_queue : str
        full queue specifications as "queue[:[nproc_spec]:[node_id]]"

    Returns
    -------
    tuple
        Tuple containing the following information
        - actual queue (same as full_queue if not latter not virtual)
        - node family specification (as a `NodeFamily` object)
        - number of processors actually requested
        - name of a specific node

    Raises
    ------
    ValueError
        Incorrect definition of the virtual queue
    KeyError
        Unsupported queue
    """
    # Queue specification parsing
    # ---------------------------
    data = full_queue.split(':')
    if len(data) == 1:
        queue = data[0]
        nprocs = None
        nodeid = None
    elif len(data) == 2:
        queue = data[0]
        nprocs = data[1].strip() or None
        nodeid = None
    elif len(data) == 3:
        queue = data[0]
        nprocs = data[1].strip() or None
        nodeid = data[2].strip() or None
    else:
        raise ValueError('Too many section in full queue specification.')

    try:
        family = HPCNODES[HPCQUEUES[queue]]
    except KeyError:
        raise KeyError('Unsupported queue.')

    # Definition of number of processors
    # ----------------------------------
    nprocs_avail = family.nprocs(all=USE_LOGICAL_CORE)
    # core_factor: integer multiplier to account for virtual if requested/avail
    core_factor = nprocs_avail/family.nprocs(all=False)
    if nprocs is None:
        if family.cpu_limits['soft'] is not None:
            res = family.cpu_limits['soft']
        elif family.cpu_limits['hard'] is not None:
            res = family.cpu_limits['hard']
        else:
            res = nprocs_avail
    else:
        if nprocs == 'H':  # Half of cores on 1 processor
            res = int(family.ncores*core_factor/2)
        elif nprocs == 'S':  # Only 1 physical core
            res = 1*core_factor
        elif nprocs == '0':  # Seen as blank/auto == full machine
            res = nprocs_avail
        else:
            try:
                value = int(nprocs)
                if value < 0:
                    res = abs(value)*family.ncores*core_factor
                elif value > 0:
                    res = value
            except ValueError:
                raise ValueError('Unsupported definition of processors.')
    nprocs = int(res)
    if nprocs > nprocs_avail:
        raise ValueError('Too many processing units requested.')
    elif (family.cpu_limits['hard'] is not None and
          nprocs > family.cpu_limits['hard']):
        raise ValueError('Number of processing units exceeds hard limit.')

    # # Node id
    # # -------
    # if nodeid is not None:
    #     try:
    #         value = int(nodeid)
    #         if value > len(family):
    #             raise ValueError('Node id higher than number of nodes.')
    #     except ValueError:
    #         raise KeyError('Wrong definition of the node ID')
    #     nodeid = value

    return (queue, family, nprocs, nodeid)


# ================
#   MAIN PROGRAM
# ================


if __name__ == '__main__':
    #  Option Parsing
    # ----------------
    parser = build_parser()
    opts = parser.parse_args()
    # Printing cases
    # ^^^^^^^^^^^^^^
    if opts.mach:
        print("""\
List of available HPC Nodes
---------------------------
""")
        for family in sorted(HPCNODES):
            print(HPCNODES[family])
        sys.exit()
    # Gaussian Version
    # ^^^^^^^^^^^^^^^^
    gxxroot = None
    gxxwork = None
    if opts.gxxver in GXX_ALIAS:
        gver = GXX_ALIAS[opts.gxxver]
    else:
        gver = opts.gxxver
    if gver in WORKINGS:
        WrkInfo = WORKINGS[gver]
        GxxInfo = GVERSIONS[WrkInfo['gref']]
    elif gver in GVERSIONS:
        WrkInfo = None
        GxxInfo = GVERSIONS[gver]
    else:
        WrkInfo = None
        GxxInfo = None
        if os.path.exists(gver):
            # Check if directory or executable file
            if not os.path.isdir(gver):
                gxxroot = os.path.split(gver)[0]
            else:
                gxxroot = gver
        else:
            print('ERROR: Gaussian option neither keyword nor valid path.')
            sys.exit(2)
    # Check Access
    if GxxInfo is not None:
        if GxxInfo['pub'] is not None and USERNAME not in GxxInfo['pub']:
            print('ERROR: User is not allowed to use this Gaussian version.')
            sys.exit(3)
    if WrkInfo is not None:
        if WrkInfo['pub'] is not None and USERNAME not in WrkInfo['pub']:
            print('ERROR: User is not allowed to use this working tree.')
            sys.exit(3)
    # Check multiple/single input file(s)
    # ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    num_infiles = len(opts.infile)
    # We need at least 1 input file
    if num_infiles == 0:
        print('ERROR: Missing Gaussian input file')
        sys.exit(2)
    multi_gjf = num_infiles > 1
    if multi_gjf and not opts.multi:
        opts.multi = 'serial'
    if not opts.multi:
        opts.multi = 'no'
    # Initialization qsub arguments structure
    # ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    qsub_args = []
    # Queue data
    # ^^^^^^^^^^
    try:
        qname, qnode, nprocs, nodeid = get_queue_data(opts.queue)
    except KeyError:
        print('ERROR: Unsupported queue')
        sys.exit(2)
    except ValueError as err:
        print('ERROR: Wrong virtual queue specification')
        print('Reason: {}'.format(err))
        sys.exit(2)
    try:
        gxx_arch = GXX_ARCHS[qnode.cpu_arch]
    except KeyError:
        print('INTERNAL ERROR: Unsupported hardware architecture.')
        sys.exit(9)
    # Check if user gave node id through --node option and virtual queue
    if opts.node is not None:
        if nodeid is not None and nodeid != opts.node:
            msg = 'ERROR: Different nodes selected through virtual queue ' \
                + 'and option'
            print(msg)
            sys.exit(2)
        else:
            nodeid = opts.node
    # Check if only some groups authorized to run on node family
    if qnode.user_groups is not None:
        if opts.group is not None:
            if opts.group in qnode.user_groups:
                group = opts.group
            else:
                print('ERROR: Chosen group not authorized to use this node.')
                sys.exit()
        else:
            fmt = 'NOTE: Those nodes are only accessible to members of: {}'
            print(fmt.format(','.join(qnode.user_groups)))
            group = qnode.user_groups[0]
            if len(qnode.user_groups) > 1:
                print('Multiple groups authorized. "{}" chosen.'.format(group))
        qsub_args.append('-W group_list={} '.format(opts.group))
    # Definition of Gaussian executable
    # ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    if WrkInfo is not None:
        if WrkInfo['mach'] is not None:
            if gxx_arch not in WrkInfo['mach']:
                print('ERROR: Unsupported machine architecture in working.')
                sys.exit(2)
            gxxwork = os.path.join(WrkInfo['path'], gxx_arch)
        else:
            gxxwork = WrkInfo['path']
    if GxxInfo is not None:
        if GxxInfo['mach'] is not None:
            if gxx_arch not in GxxInfo['mach']:
                print('ERROR: Unsupported machine architecture in working.')
                sys.exit(2)
            gxxroot = os.path.join(GxxInfo['path'], gxx_arch, GxxInfo['gdir'])
        else:
            gxxroot = os.path.join(GxxInfo['path'], GxxInfo['gdir'])
    gxx = os.path.split(gxxroot)[1]
    # Gaussian working definition
    # ^^^^^^^^^^^^^^^^^^^^^^^^^^^
    gxx_works = []
    if gxxwork:
        gxx_works.append(gxxwork)
    if opts.gxxwrk:
        for workdir in opts.gxxwrk:
            if os.path.exists(workdir):
                gxx_works.append(workdir)
            else:
                fmt = 'ERROR: working tree directory "{}" does not exits'
                print(fmt.format(workdir))
                sys.exit()
    # Definition of Gaussian input file
    # ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    filebases = []
    for infile in opts.infile:
        if not os.path.exists(infile):
            fmt = 'ERROR: Cannot find Gaussian input file "{}"'
            print(fmt.format(infile))
            sys.exit()
        filebases.append(os.path.splitext(os.path.basename(infile))[0])
    # Definition of Gaussian output file
    # ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    glog_files = []
    if opts.gxxlog:
        if multi_gjf:
            print('ERROR: Output file not supported for a multi-job')
            sys.exit()
        glog_files.append(opts.gxxlog)
    else:
        for base in filebases:
            glog_files.append(base + '.log')
    # Definition of Gaussian internal files
    # ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    # NOTE: A "None" file means to keep what exits. "False" to remove it
    # - CHECKPOINT FILE
    gchk_files = []
    if opts.gxxchk:
        if multi_gjf:
            print('ERROR: Checkpoint file not supported for a multi-job')
            sys.exit()
        gchk_files.append(opts.gxxchk)
    elif not set(['c', 'chk', 'a', 'all']) & set(opts.gxxl0K):
        for base in filebases:
            gchk_files.append(base + '.chk')
    else:
        gchk_files = None
    # - READ-WRITE FILE
    grwf_files = []
    if opts.gxxrwf:
        if opts.gxxrwf.lower() == 'auto':
            for base in filebases:
                grwf_files.append(base + '.rwf')
        else:
            if multi_gjf:
                print('ERROR: RWF file not supported for a multi-job')
                sys.exit()
            grwf_files.append(opts.gxxrwf)
    elif set(['r', 'rwf', 'a', 'all']) & set(opts.gxxl0K):
        grwf_files = None
    else:
        grwf_files = False
    # Job name
    # ^^^^^^^^
    if opts.job:
        qjobname = opts.job
    else:
        if multi_gjf:
            qjobname = 'multi-job'
        else:
            qjobname = filebases[0]
    # Check if job name compliant with PBS restrictions
    # Starting digit
    if qjobname[0].isdigit():
        print('NOTE: First character of jobname is a digit.\n'
              + 'Letter "a" is preprended.')
        qjobname = 'a' + qjobname
    # Less than 15 chars
    if len(qjobname) > 15:
        qjobname = qjobname[:15]
        fmt = 'NOTE: Job name exceeds 15 chars. Truncating to {}'
        print(fmt.format(qjobname))

    # Input Definition
    # ----------------

    # Resources definition
    # ^^^^^^^^^^^^^^^^^^^^
    # Define NProcs and Mem
    if set(['p', 'proc', 'a', 'all']) & set(opts.gxxl0K):
        nprocs = None
    elif multi_gjf and opts.multi == 'parallel':
        nprocs = nprocs//num_infiles
        if nprocs == 0:
            msg = 'ERROR: Too many parallel jobs for the number of ' \
                + 'processing units'
            print(msg)
            sys.exit()
    if set(['m', 'mem', 'a', 'all']) & set(opts.gxxl0K):
        mem = None
    else:
        if nprocs is None:
            factor = 1.
        else:
            factor = min(1., nprocs/qnode.nprocs(all=USE_LOGICAL_CORE))
        if qnode.mem_limits['soft'] is not None:
            def_mem = qnode.mem_limits['soft']
        elif qnode.mem_limits['hard'] is not None:
            def_mem = qnode.mem_limits['hard']
        else:
            def_mem = inf
        mem_byte = int(min(qnode.size_mem*factor, def_mem)*MEM_OCCUPATION)
        mem = hpc.bytes_units(mem_byte, 0, False, 'g')
        if mem.startswith('0'):
            mem = hpc.bytes_units(mem_byte, 0, False, 'm')
    # Check input and build list of relevant data
    # ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    rootdirs = []
    gjf_files = []
    ops_copy = []
    full_P, full_M = 0, 0
    for index, infile in enumerate(opts.infile):
        outfile = glog_files[index]
        filebase = filebases[index]
        if gchk_files:
            chkfile = gchk_files[index]
        else:
            chkfile = gchk_files
        if grwf_files:
            rwffile = grwf_files[index]
        else:
            rwffile = grwf_files
        reldir, ginfile = os.path.split(infile)
        rootdir = os.path.abspath(reldir)
        # A new, temporary input is created
        gjf_new = '{}_{}.gjf'.format(filebase, jobPID)
        # The script works in the directory where the input file is stored
        os.chdir(rootdir)
        if not opts.expert:
            dat_P, dat_M, data = check_gjf(ginfile, gjf_new, nprocs, mem,
                                           chkfile, rwffile, rootdir)
            if opts.multi == 'parallel':
                full_P += dat_P
                full_M += hpc.convert_storage(dat_M)
            else:
                if dat_P > full_P:
                    full_P = dat_P
                val = hpc.convert_storage(dat_M)
                if val > full_M:
                    full_M = hpc.convert_storage(dat_M)
        ops_copy.extend(data)
        rootdirs.append(rootdir)
        gjf_files.append(gjf_new)
    if not opts.expert:
        if full_P > qnode.nprocs(all=USE_LOGICAL_CORE):
            print('ERROR: Too many processors required for the chosen queue')
            sys.exit()
        elif (qnode.cpu_limits['hard'] is not None and
              full_P > qnode.cpu_limits['hard']):
            print('ERROR: number of processors exceeds hard limit')
            sys.exit()
        if (qnode.mem_limits['hard'] is not None and
                full_M > qnode.mem_limits['hard']):
            print('ERROR: Requested memory exceeds hard limit')
            sys.exit()
        nprocs = full_P
        mem = hpc.bytes_units(full_M, 0, False, 'g')
    if (qnode.cpu_limits['soft'] is not None and
            nprocs > qnode.cpu_limits['soft']):
        print('NOTE: Number of processors exceeds soft limit.')
    if (qnode.mem_limits['soft'] is not None and
            hpc.convert_storage(mem) > qnode.mem_limits['soft']):
        print('NOTE: Requested memory exceeds soft limit.')
    #  PBS commands definition
    # -------------------------
    # First check which storage use
    if opts.tmpdir is not None:
        value = opts.tmpdir.format(username=USERNAME)
    elif qnode.path_tmpdir is None:
        print('''\
WARNING: No local storage available to store working files.
         Starting directory will be used for storage.''')
        value = STARTDIR
    else:
        value = qnode.path_tmpdir.format(username=USERNAME)
    tmpdir = os.path.join(value, 'gaurun'+jobPID)
    # Header
    # ^^^^^^
    pbs_header = """
echo "----------------------------------------"
echo "PBS queue:     "$PBS_O_QUEUE
echo "PBS host:      "$PBS_O_HOST
echo "PBS node:      "$HOSTNAME
echo "PBS workdir:   {scrdir}"
echo "PBS jobid:     "$PBS_JOBID
echo "PBS jobname:   "$PBS_JOBNAME
echo "PBS inputfile: {input}"
echo "----------------------------------------"
  """.format(scrdir=tmpdir, input=', '.join(opts.infile))

    # Shell commands
    # ^^^^^^^^^^^^^^
    # Create temporary directory on local storage
    pbs_cmds = 'mkdir -p {}\n'.format(tmpdir)
    pbs_cmds += '# Check if directory creation failed.\n'
    pbs_cmds += '[ ! -d "{}" ] && exit -1\n'.format(tmpdir)
    # Move to temporary directory
    pbs_cmds += 'cd {}\n'.format(tmpdir)
    # Move temporary input file(s) to temp dir
    for index, gjf_file in enumerate(gjf_files):
        rootdir = rootdirs[index]
        pbs_cmds += 'mv {} ./\n'.format(os.path.join(rootdir, gjf_file))
    # Copy files listed in input file(s) or given by user if available
    fmt = '(cp {} ./) >& /dev/null\n'
    for cmd, what, where in ops_copy:
        if (cmd == 'cpto'):
            if where:
                pbs_cmds += fmt.format(os.path.join(where, what))
            else:
                pbs_cmds += fmt.format(data[1])
    if opts.cpto:
        for data in opts.cpto:
            pbs_cmds += fmt.format(os.path.join(STARTDIR, data))
    # Generate Gaussian command(s)
    gxx_args = ''
    if gxx_works:
        fmt = '{0}/l1:{0}/exe-dir:'
        gxx_args += ' -exedir="'
        for rootdir in gxx_works:
            if os.path.exists(rootdir):
                gxx_args += fmt.format(rootdir)
        gxx_args += '$GAUSS_EXEDIR"'
    fmt = '{gexe} {gargs} {gin} {gout}'
    if multi_gjf and opts.multi == 'parallel':
        fmt += ' &'
    fmt += '\n'
    for index, gjf_file in enumerate(gjf_files):
        log_file = glog_files[index]
        rootdir = rootdirs[index]
        pbs_cmds += fmt.format(gexe=gxx, gargs=gxx_args.strip(), gin=gjf_file,
                               gout=os.path.join(rootdir, log_file))
    if multi_gjf and opts.multi == 'parallel':
        pbs_cmds += 'wait\n'
    # Copy back relevant file(s)
    fmt = '(cp {} {}) >& /dev/null\n'
    for cmd, what, where in ops_copy:
        if (cmd == 'cpfrom'):
            if where:
                pbs_cmds += fmt.format(what, where)
            else:
                pbs_cmds += fmt.format(what, DEFAULTDIR)
    if opts.cpfrom:
        for data in opts.cpfrom:
            pbs_cmds += fmt.format(data, STARTDIR)
    # TODO (ugly patch) Get any cube which may have been generated
    pbs_cmds += '(cp *.{{cub,cube}} {}) >& /dev/null\n'.format(STARTDIR)
    # Cleaning
    pbs_cmds += 'cd .. \nrm -rf {}\n'.format(tmpdir)

    #  SUBMISSION JOB
    # ----------------
    ls_env = []
    qsub_cmd = 'qsub '  # QSub is used to send the job
    # Prevent automatic rerun of the job if it fails due to some internal PBS
    #   issue (ex: node offline). This is a safer choice
    qsub_cmd += '-r n '  # Flags the current job as non-rerunnable
    # Sets the job name
    qsub_cmd += "-N '{job}' ".format(job=qjobname.replace(' ', '_'))
    if opts.mail and EMAILSERVER is not None:
        # Flag to send email in case at beginning, end and aborting of job
        fmt = ' -m abe'
        ls_env.append("MAIL")
        # Recipient
        if opts.mailto:  # Full recipient address given
            fmt += ' -M {addr}'
        else:
            fmt += ' -M {user}@{server}'
        qsub_args.append(fmt.format(addr=opts.mailto, user=USERNAME,
                                    server=EMAILSERVER))
    # Sets the reference project
    if opts.project:
        qsub_cmd += "-P '{}' ".format(opts.project)
    # Nodes-related option: fixes the number of nodes to use (nodes=), and the
    #   number of processors per node (ncpus=)
    # Reserve logical cores if present even if only physical cores used.
    ncpus = int(nprocs*qnode.nprocs()/qnode.nprocs(all=USE_LOGICAL_CORE))
    if nodeid is None:
        fmt = '-l select=1:ncpus={ncpus}:mem={mem}:Qlist={family}'
    else:
        fmt = '-l select=1:host={node}:ncpus={ncpus}'
    qsub_args.append(fmt.format(ncpus=ncpus, mem=mem, family=qnode.queue_name,
                                node=nodeid))
    # Queue name
    qsub_args.append('-q {queue}'.format(queue=qname))
    # Silent mode: all output redirected to /dev/null
    if (opts.silent):
        qsub_args.append('-o localhost:/dev/null -e localhost:/dev/null')
    ls_env.extend(set_gxx_env(gxxroot))
    # Add for environment variables
    if ls_env:
        qsub_args.append('-v {}'.format(','.join(ls_env)))
    # Build full commandline
    qsub_cmd += ' '.join(qsub_args) + ' - '

    if opts.prtinfo:
        print(qsub_cmd)
        print(pbs_header)
        print(pbs_cmds)
    if not opts.nojob:
        pbs_header += 'echo "\n   === LIST OF COMMANDS ===\n"\necho "' \
                + pbs_cmds.replace('\n', '"\necho "') + '"\n'
        process = Popen(args=qsub_cmd, shell=True, stdin=PIPE, stdout=PIPE)
        result = (pbs_header+pbs_cmds).encode()
        output, _ = process.communicate(result)
        fmt = 'QSub submission job: "{}"'
        print(fmt.format(output.decode().strip()))

# vim: ft=python foldmethod=indent

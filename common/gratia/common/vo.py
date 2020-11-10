
"""
This module parses the user-vo-map file, an OSG-specific file format
that maps a given username to a VO.

Here's a sample file::

************************************************
# User-VO map
# Generated by generate-vo-map
# The voi line is used by MonaLISA, and is the lower-case version of all VO names
# The VOc line is used by MonaLISA, and is the proper-case version of all VO names
# Other lines are of the form <account> <VO>

#voi cdf fermilab mis star atlas atlas cms ligo des glow
#VOc CDF FERMILAB MIS STAR ATLAS ATLAS CMS LIGO DES GLOW

cdf cdf
fermilab fermilab
mis mis
star star
usatlas1 atlas
usatlas3 atlas
uscms01 cms
ligo ligo
des des
glow glow
************************************************


The line starting with '#voi' is the lower-case version of all VO names
The line starting with '#VOc' is the proper-case version of all VO names
The i'th entry of the #voi line corresponds to the i'th entry of the #VOc
line, and forms an associative-map.

All other lines starting with '#' are comments.

Any other lines should be whitespace-delimited and two-columns; the first
column is a username, and the second column is the VO-name in the '#voi'
format.

Using this file, we can take the username from a batch system job and
derive some rudimentary VO information.  This is a last resort for Gratia;
we primarily want to pull this information from the CE and avoid using
these routines.

In addition to parsing the user-vo-map file, this module will cache the
results in memory for quicker lookup.
"""

import re

from gratia.common.debug import DebugPrint, DebugPrintTraceback
import gratia.common.config as config

# Various module-level data caches.
__UserVODictionary = None
__voiToVOcDictionary = None
__dictionaryErrorStatus = False
def __InitializeDictionary__():
    """
    For internal use only.  Parse the user-vo-map file and initialize the
    module-internal data structures with the contents.  From now on, VO
    information lookup in this module will be done via an in-memory lookup.

    Will only be attempted once
    """

    # Check if there was previously an error
    # If so, do not retry initialization
    global __dictionaryErrorStatus, __voiToVOcDictionary, __UserVODictionary
    if __dictionaryErrorStatus:
        return

    __voiToVOcDictionary = {}
    __UserVODictionary = {}
    __dictionaryErrorStatus = True

    mapfile = config.Config.get_UserVOMapFile()
    if mapfile == None:
        DebugPrint(2, "WARNING: No mapfile specified; not using VO mapping.")
        return

    try:
        __InitializeDictionary_internal(mapfile)
        __dictionaryErrorStatus = False
    except IOError as e:
        DebugPrint(0, 'WARNING: IO error exception initializing user-vo-map mapfile %s: %s' % (mapfile, str(e)))
        DebugPrintTraceback()

def __InitializeDictionary_internal(mapfile):
    """
    Given a mapfile filename, initialize the module-internal data structures with
    its contents.

    See module documentation for more info about the mapfile format.

    Throws an IOError on exception.
    """

    magicCommentLine_re = re.compile("\s*#(voi|VOc)\s")
    commentLine_re = re.compile("\s*#")
    userVOLine_re = re.compile("\s*(?P<User>\S+)\s*(?P<voi>\S+)")

    voi_info = []
    VOc_info = []
    DebugPrint(4, 'DEBUG: Initializing (voi, VOc) lookup table')
    fd = open(mapfile, "r")
    for line in fd.readlines():
        # Process the magic voi / VOc comment line, which provides the correct capitalization
        # of the VO names.
        mapMatch = magicCommentLine_re.match(line)
        if mapMatch:
            info = line[mapMatch.end(0):].split()
            if mapMatch.group(1) == 'voi':
                voi_info = info
            else:
                VOc_info = info

        # One time initialization of the lookup dictionary.
        # This code assumes it happens before the first user is encountered.
        if not __voiToVOcDictionary and voi_info and VOc_info:
            entries = min(len(voi_info), len(VOc_info))
            if entries != len(voi_info):
                DebugPrint(0, 'WARNING: VOc line does not have at least as many entries as voi line in %s'
                    ': truncating' % mapfile)
            for index in range(entries):
                if not VOc_info[index]:
                    DebugPrint(0, 'WARNING: no VOc match for voi "%s'
                        '": not entering in (voi, VOc) table.' % voi_info[index])
                    continue
                __voiToVOcDictionary[voi_info[index]] = VOc_info[index]

        # Handle normal comments:
        mapMatch = commentLine_re.match(line)
        if mapMatch:
            continue

        # Now, try and process an actual user map line.
        mapMatch = userVOLine_re.match(line)
        if mapMatch:
            user = mapMatch.group('User')
            voi = mapMatch.group('voi')
            # Update the VO info dictionary.
            info = __UserVODictionary.setdefault(user, {})
            info['VOName'] = voi
            if voi in __voiToVOcDictionary:
                info['ReportableVOName'] = __voiToVOcDictionary[voi]
            else:
                DebugPrint(0, 'WARNING: voi "%s" listed for user "%s" not found in ' \
                    '(voi, VOc) table' % (voi, user))


def VOc(voi):
    """
    Given a short-form VO name, `voi`, return the long-form VO name with proper
    capitalization (the "VOc").
    """
    if __voiToVOcDictionary == None:
        __InitializeDictionary__()

    return __voiToVOcDictionary.get(voi, voi)


def VOfromUser(user):
    """
    Obtain the voi and VOc from the user name `user` via the reverse gridmap file.

    Returns a dictionary of the form:
        {'VOName': <voi>, 'ReportableVOName': <VOc>}
    where <voi> is the VO's short-form name and <VOc> is the long-form name,
    with proper capitalization.

    If the user is unknown to the user-vo-map, then this returns None.
    """
    if __UserVODictionary == None:
        __InitializeDictionary__()

    return __UserVODictionary.get(user, None)


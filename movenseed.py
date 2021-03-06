#!/usr/bin/env python3
################################################################################
# Author: Matt Traudt
# Originally created: 2015-02-25
# Maintained at: https://github.com/pastly/movenseed.git
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
################################################################################
import os
import hashlib
import argparse
import bencode

global version
global skip_filesize
global skip_filehash
global be_verbose
global use_hardlinks
global make_subdirectory

def init_globals():
    global version
    global skip_filesize
    global skip_filehash
    global be_verbose
    global use_hardlinks
    global make_subdirectory
    version = "v1.0"
    skip_filesize = False
    skip_filehash = False
    be_verbose = False
    use_hardlinks = False
    make_subdirectory = True

# filename      path to a file whose contents should be digested
def hash_file(filename):
    # I have not done any testing on performance of various algos and blocksizes
    algo = hashlib.sha1()
    blocksize = 2**20
    with open(filename, "rb") as file:
        while True:
            buf = file.read(blocksize)
            if not buf:
                break
            algo.update(buf)
    return algo.hexdigest()

# source        absolute source file name
# dest          absolute destination file name
def make_link(source, dest):
    if use_hardlinks:
        os.link(source, dest)
    else:
        os.symlink(source, dest)

# filelist      list of filenames
# root_dirname  absolute path of a --here
# size_info     list of strings
# hash_info     list of strings
def prework_do_files(filelist, root_dirname, size_info, hash_info):
    for file in filelist:
        # may be unecessary check in most use cases, but this fixed python
        # trying to read a symbolic link to nowhere
        if os.path.isfile(file):
            if not skip_filesize:
                if be_verbose: print("Finding size of", file, end=' ... ')
                file_size = os.path.getsize(file)
                if be_verbose: print(file_size)
            if not skip_filehash:
                if be_verbose: print("Finding hash of", file, end=' ... ')
                file_hash = hash_file(file)
                if be_verbose: print(file_hash)
            # - convert file to relative path for storing in *.mns
            # - the path is relative to root_dirname (abs dir of a --here)
            # - root_dirname will not end in a slash, so must do +1 to remove
            # slash too
            file = os.path.realpath(file)[len(root_dirname)+1:]
            if not skip_filesize:
                size_info.append(str(file_size) + "\t" + file + "\n")
            if not skip_filehash:
                hash_info.append(file_hash + "\t" + file + "\n")

# dirname       a --here or subdir of --here
# root_dirname  absolute path of a --here
# size_info     list of strings
# hash_info     list of strings
def prework_do_directory(dirname, root_dirname, size_info, hash_info):
    contained_files = []
    contained_directories = []
    # get contained directories and files in dirname
    for item in os.listdir(dirname):
        # make item include dirname (not necessarily into absolute path)
        item = dirname + "/" + item
        if os.path.isfile(item):
            contained_files.append(item)
        elif os.path.isdir(item):
            contained_directories.append(item)
    # process any contained files in this dir
    prework_do_files(contained_files, root_dirname, size_info, hash_info)
    # then recursively process any contained dirs
    for dir in contained_directories:
        prework_do_directory(dir, root_dirname, size_info, hash_info)

# passed_source_dirname     a --here
def prework(passed_source_dirname):
    # lists to store strings in the following formats
    size_info = [] # "3212<tab>rel/path/from/here/to/file"
    hash_info = [] # "3668c223[...]<tab>rel/path/from/here/to/file"
    # start off the recursive processing of directories
    prework_do_directory(
        passed_source_dirname,
        os.path.realpath(passed_source_dirname),
        size_info,
        hash_info
    )
    # write all those lines to files in a --here
    if not skip_filesize:
        with open(passed_source_dirname+"/sizes.mns", "w") as size_outfile:
            if be_verbose: print("Writing (overwriting)",passed_source_dirname+"/sizes.mns")
            for item in size_info:
                if be_verbose: print(item, end='')
                size_outfile.write(item)
    if not skip_filehash:
        with open(passed_source_dirname+"/hashes.mns", "w") as hash_outfile:
            if be_verbose: print("Writing (overwriting)",passed_source_dirname+"/hashes.mns")
            for item in hash_info:
                if be_verbose: print(item, end='')
                hash_outfile.write(item)

# here          absolute path to a here
# torrentfile   a torrent file to source info
def torrentfile_prework(here, torrentfile):
    b = bencode.load(torrentfile)
    # the desired infor is stored in 1 of 2 ways in the .torrent file based on
    # how many files it is for. determine which way the info is stored and
    # extract it
    size_info = []
    # option 1: there are multiple files
    if "files" in b['info']:
        # set here to be a sub directory of HERE called the name located in the
        # torrent info if flag isn't set
        if make_subdirectory:
            here = here + "/" + b['info']['name']
            if not os.path.isdir(here):
                os.makedirs(here)
        # for every file in the info, gets its size and path
        for f in b['info']['files']:
            size = f['length']
            # path is broken up in an array, so read all the elements and put
            # them together into a string
            path = ""
            for p in f['path']:
                path += p+"/" # add slah between directories
            path = path[:-1] # remove last trailing slash
            size_info.append(str(size)+"\t"+path+'\n')
        with open(here+"/sizes.mns", "w") as size_outfile:
            if be_verbose: print("Writing (overwriting)", here+"/sizes.mns")
            for item in size_info:
                if be_verbose: print(item, end='')
                size_outfile.write(item)
    # option 2: there is one file
    elif "name" in b['info']:
        size_info.append(str(b['info']['length'])+"\t"+b['info']['name']+'\n')
        # changed to append in case multiple torrentfiles that each would
        # download a single file are specified since they all will try to make
        # the same sizes.mns. They may have adverse affects in other scenarios,
        # but I image this is the most common scenario.
        #with open(here+"/sizes.mns", "w") as size_outfile:
        with open(here+"/sizes.mns", "a") as size_outfile:
            if be_verbose: print("Writing (appending)", here+"/sizes.mns")
            for item in size_info:
                if be_verbose: print(item, end='')
                size_outfile.write(item)
    else:
        print("idk what to do")

# heres         one or more --here's
# torrentfile   one or more torrent files
def dispatch_prework(heres, torrentfiles):
    # choose what type of prework to do based on what options exists
    if (heres and len(heres) == 1 and torrentfiles):
        if not skip_filesize:
            for torrentfile in torrentfiles:
                torrentfile_prework(os.path.realpath(heres[0]), torrentfile)
        else:
            print("Nothing to do")
    elif (heres and not torrentfiles):
        for here in heres:
            prework(here)
    else:
        print("Specify 1+ HEREs or 1 HERE and 1+ torrentfiles")

# filelist      list of filenames in a --there or a subdir of -there
# here          absolute path to a --here
# size_info     dictionary (key: filename, val: size) of files in --here
# hash_info     dictionary (key: filename, val: hash) of files in --here
def postwork_do_files(filelist, here, size_info, hash_info):
    for therefile in filelist:
        if be_verbose: print("Checking",therefile, end=' ... ')
        # try to find therefile's size in size_info if not skipping filesize
        if (
        skip_filesize or
        str(os.path.getsize(therefile)) in size_info.values()
        ):
            if not skip_filehash:
                # hash therefile if size if found
                therehash = hash_file(therefile)
                # try to find hash. this time use .items() because we want the
                # key in addition to the values
                for herefile, herehash in hash_info.items():
                    if therehash == herehash:
                        # found, so make herefile an absolute path
                        herefile = here+"/"+herefile
                        # if it already exists or is a valid symlic, don't
                        # replace it
                        if os.path.isfile(herefile):
                            if be_verbose: print("No (already in HERE)")
                            continue
                        # check if !isfile() but islink(), meaning it is a
                        # broken symlic and should be replaced
                        elif os.path.islink(herefile):
                            os.remove(herefile)
                        # make directory for the symlic to go in if needed
                        if not os.path.isdir(os.path.dirname(herefile)):
                            os.makedirs(os.path.dirname(herefile))
                        # finally! make the link
                        make_link(therefile, herefile)
                        if be_verbose: print("Yes!",
                            os.path.basename(herefile),
                            "now links to",
                            os.path.basename(therefile)
                        )
                        break
                else:
                    if be_verbose: print("No (hash)")
            else:
                # very dangerous if files are not unique sizes!!!
                theresize = str(os.path.getsize(therefile))
                for herefile, heresize in size_info.items():
                    if theresize == heresize:
                        # found, so make herefile an absolute path
                        herefile = here+"/"+herefile
                        # if it already exists or is a valid symlic, don't
                        # replace it
                        if os.path.isfile(herefile):
                            if be_verbose: print("No (already in HERE)")
                            continue
                        # check if !isfile() but islink(), meaning it is a
                        # broken symlic and should be replaced
                        elif os.path.islink(herefile):
                            os.remove(herefile)
                        # make directory for the symlic to go in if needed
                        if not os.path.isdir(os.path.dirname(herefile)):
                            os.makedirs(os.path.dirname(herefile))
                        make_link(therefile, herefile)
                        if be_verbose: print("Yes!",
                            os.path.basename(herefile),
                            "now links to",
                            os.path.basename(therefile)
                        )
                        break

        else:
            if be_verbose: print("No (size)")
# here          absolute path to a --here
# dirname       absolute path to a --there or a sub of --there
# size_info     dictionary (key: filename, val: size) of files in --here
# hash_info     dictionary (key: filename, val: hash) of files in --here
def postwork_do_directory(here, dirname, size_info, hash_info):
    contained_files = []
    contained_directories = []
    # get contained directories and files in dirname
    for item in os.listdir(dirname):
        # item is given as a relative path to dirname, so make absolute again
        item = dirname + "/" + item
        if os.path.isfile(item):
            contained_files.append(item)
        elif os.path.isdir(item):
            contained_directories.append(item)
    # process any contained files
    postwork_do_files(contained_files, here, size_info, hash_info)
    # then recursively process and contained dirs
    for dir in contained_directories:
        postwork_do_directory(here, dir, size_info, hash_info)

# here          absolute path to a single --here
# theres        list of untouched --theres
# size_info     dictionary (key: filename, val: size) of files in --here
# hash_info     dictionary (key: filename, val: hash) of files in --here
def postwork(here, theres, size_info, hash_info):
    for there in theres:
        # make sure there is a directory
        if (not os.path.isdir(there)):
            print(there,"is not a directory")
            continue
        # change there into absolute path, as no relativity needed here
        # we are on the dark side and siths deal in absolutes
        there = os.path.realpath(there)
        # start the recursion!
        postwork_do_directory(here, there, size_info, hash_info)

# heres     list of --heres
# theres    list of --theres
def dispatch_postwork(heres, theres):
    for here in heres:
        # immediately convert here to absolute path as relativness is unneeded
        here = os.path.realpath(here)
        # makes dicts for size and hash info.
        # TODO: consider storing in list of tuples or similar as keys are never
        # used as a key
        size_info = dict() # key: filename, val: size
        hash_info = dict() # key: filename, val: hash
        # make sure size file and hash file are where they are expected
        size_filename = here+"/sizes.mns"
        hash_filename = here+"/hashes.mns"
        if not skip_filesize and not os.path.isfile(size_filename):
            print("Could not find sizes.mns")
            continue
        if not skip_filehash and not os.path.isfile(hash_filename):
            print("Could not find hashes.mns")
            continue
        # read in all that glorious size and hash info
        if not skip_filesize:
            with open(size_filename, "r") as size_file:
                for line in size_file:
                    # size and filename are seperated by a tab
                    # partition all but the last char on a line (a \n) on the
                    # first occurence of a tab
                    size, _, filename = line[:-1].partition('\t')
                    size_info[filename] = size
        if not skip_filehash:
            with open(hash_filename, "r") as hash_file:
                for line in hash_file:
                    # hash and filename are seperated by a tab
                    # partition all but the last char on a line (a \n) on the
                    # first occurence of a tab
                    hash, _, filename = line[:-1].partition('\t')
                    hash_info[filename] = hash
        # currently, if sizes are non-unique, refuse to do postwork until
        # interactive mode is implemented
        if skip_filehash:
            unique_sizes_set = set([val for val in size_info.values()])
            if len(size_info) != len(unique_sizes_set):
                print("Files of non-unique size.")
                print("Won't run until interactive mode implemented")
                return
        # send off all this jazz to postwork
        postwork(here, theres, size_info, hash_info)

if __name__ == "__main__":
    init_globals()
    global version
    descrip = "Move and Seed "+version+'''
Advanced file linker'''
    epil = '''
Prework requires either
    1. at least 1 HERE,
    2. at least 1 torrentfile and only 1 HERE
Postwork requires at least one here AND at least one there.'''
    parser = argparse.ArgumentParser(
        description=descrip,
        epilog=epil,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        '-s', '--stage',
        choices=['prework','postwork'],
        help='choose stage to run'
    )
    parser.add_argument(
        '--version',
        action='store_const',
        const=1,
        help='prints version and exits'
    )
    parser.add_argument(
        '-H', '--here',
        metavar='dir',
        nargs='+',
        help='1+ directory that you want to seed from'
    )
    parser.add_argument(
        '-T', '--there',
        metavar='dir',
        nargs='+',
        help='1+ directory containing moved/renamed files'
    )
    parser.add_argument(
        '-t', '--torrent',
        metavar='torrentfile',
        nargs='+',
        help='1+ torrent file to extract size info from during prework'
    )
    parser.add_argument(
        '--skip-filesize',
        action='store_const',
        const=1,
        help='Skip making sizes.mns or skip checking sizes'
    )
    parser.add_argument(
        '--skip-filehash',
        action='store_const',
        const=1,
        help='Skip making hashes.mns or skip checking hashes'
    )
    parser.add_argument(
        '--no-make-subdirectory',
        action='store_const',
        const=1,
        help='Do not make subdirectories for multi-file torrents'
    )
    parser.add_argument(
        '--hard',
        action='store_const',
        const=1,
        help='Make hard links instead of symbolic links'
    )
    parser.add_argument(
        '-v', '--verbose',
        action='store_const',
        const=1,

    )
    args = parser.parse_args()


    global skip_filesize
    global skip_filehash
    global be_verbose
    global use_hardlinks
    global make_subdirectory
    skip_filesize = (True if args.skip_filesize else False)
    skip_filehash = (True if args.skip_filehash else False)
    be_verbose = (True if args.verbose else False)
    use_hardlinks = (True if args.hard else False)
    make_subdirectory = (False if args.no_make_subdirectory else True)

    if args.version:
        print(descrip)
    elif not args.stage:
        parser.print_help()
    elif (args.stage == 'prework'):
        if (not args.here and not args.torrent):
            print("Need --here or --torrent")
            print("Aborting")
        elif (args.there):
            print("--there doesn't make sense with prework")
            print("Aborting")
        else:
            dispatch_prework(args.here, args.torrent)
    elif (args.stage == 'postwork'):
        if (not args.here or not args.there):
            print("Need --here and --there")
            print("Aborting")
        elif (args.torrent):
            print("--torrent doesn't make sense with postwork")
            print("Aborting")
        else:
            dispatch_postwork(
                args.here,
                args.there
            )
    else:
        parser.print_help()

"""
Python directory syncer

Report the difference in content
of two directories, synchronise or
update a directory from another, taking
into account time-stamps of files etc.

(c) Thomas Khyn 2014
Based on Robocopy by Anand B Pillai

"""

import os
import sys
import stat
import time
import shutil
import re


class DCMP(object):
    """Dummy object for directory comparison data storage"""
    def __init__(self, l, r, c):
        self.left_only = l
        self.right_only = r
        self.common = c


class Syncer(object):
    """ An advanced directory synchronisation, update
    and file copying class """

    prog_name = "dirsync.py"

    def __init__(self, dir1, dir2, **options):

        self._dir1 = dir1
        self._dir2 = dir2

        self._copyfiles = True
        self._updatefiles = True
        self._creatdirs = True

        self._changed = []
        self._added = []
        self._deleted = []

        # stat vars
        self._numdirs = 0
        self._numfiles = 0
        self._numdelfiles = 0
        self._numdeldirs = 0
        self._numnewdirs = 0
        self._numupdates = 0
        self._starttime = 0.0
        self._endtime = 0.0

        # failure stat vars
        self._numcopyfld = 0
        self._numupdsfld = 0
        self._numdirsfld = 0
        self._numdelffld = 0
        self._numdeldfld = 0

        # options setup
        self._verbose = options.get('verbose', False)
        self._mainfunc = getattr(self, options['action'])
        self._purge = options.get('purge', False)
        self._copydirection = 2 if options.get('nodirection', False) else 0
        self._forcecopy = options.get('force', False)
        self._maketarget = options.get('create', False)
        self._modtimeonly = options.get('modtime', False)

        self._ignore = options.get('ignore', [])
        self._only = options.get('only', [])
        self._exclude = options.get('exclude', [])
        self._include = options.get('include', [])

        if not os.path.isdir(self._dir1):
            raise ValueError(
                "Argument Error: Source directory does not exist!")

        if not self._maketarget and not os.path.isdir(self._dir2):
            raise ValueError(
                "Argument Error: Target directory %s does not exist! " \
                "(Try the -c option)." % self._dir2)

    def log(self, msg=''):
        sys.stdout.write(msg + '\n')

    def _compare(self, dir1, dir2):

        left = set()
        right = set()

        self._numdirs += 1

        excl_patterns = set(self._exclude).union(self._ignore)

        for cwd, dirs, files in os.walk(dir1):
            self._numdirs += len(dirs)
            for f in dirs + files:
                path = os.path.relpath(os.path.join(cwd, f), dir1)
                re_path = path.replace('\\', '/')
                if self._only:
                    for pattern in self._only:
                        if re.match(pattern, re_path):
                            # go to exclude and ignore filtering
                            break
                    else:
                        # next item, this one does not match any pattern
                        # in the _only list
                        continue

                add_path = False
                for pattern in self._include:
                    if re.match(pattern, re_path):
                        add_path = True
                        break
                else:
                    # path was not in includes
                    # test if it is in excludes
                    for pattern in excl_patterns:
                        if re.match(pattern, re_path):
                            # path is in excludes, do not add it
                            break
                    else:
                        # path was not in excludes
                        # it should be added
                        add_path = True

                if add_path:
                    left.add(path)
                    anc_dirs = re_path[:-1].split('/')
                    for i in range(1, len(anc_dirs)):
                        left.add('/'.join(anc_dirs[:i]))

        for cwd, dirs, files in os.walk(dir2):
            for f in dirs + files:
                path = os.path.relpath(os.path.join(cwd, f), dir2)
                re_path = path.replace('\\', '/')
                for pattern in self._ignore:
                    if re.match(pattern, re_path):
                        if f in dirs:
                            dirs.remove(f)
                        break
                else:
                    right.add(path)
                    # no need to add the parent dirs here,
                    # as there is no _only pattern detection
                    if f in dirs and path not in left:
                        self._numdirs += 1

        common = left.intersection(right)
        left.difference_update(common)
        right.difference_update(common)

        return DCMP(left, right, common)

    def do_work(self):
        """ Do work """

        self._starttime = time.time()

        if not os.path.isdir(self._dir2):
            if self._maketarget:
                if self._verbose:
                    self.log('Creating directory %s' % self._dir2)
                try:
                    os.makedirs(self._dir2)
                except Exception as e:
                    self.log(str(e))
                    return None

        # All right!
        self._mainfunc()
        self._endtime = time.time()

    def _dowork(self, dir1, dir2, copyfunc=None, updatefunc=None):
        """ Private attribute for doing work """

        if self._verbose:
            self.log('Source directory: %s:' % dir1)

        self._dcmp = self._compare(dir1, dir2)

        # Files & directories only in target directory
        if self._purge:
            for f2 in self._dcmp.right_only:
                fullf2 = os.path.join(self._dir2, f2)
                if self._verbose:
                    self.log('Deleting %s' % fullf2)
                try:
                    if os.path.isfile(fullf2):
                        try:
                            os.remove(fullf2)
                            self._deleted.append(fullf2)
                            self._numdelfiles += 1
                        except OSError as e:
                            self.log(str(e))
                            self._numdelffld += 1
                    elif os.path.isdir(fullf2):
                        try:
                            shutil.rmtree(fullf2, True)
                            self._deleted.append(fullf2)
                            self._numdeldirs += 1
                        except shutil.Error as e:
                            self.log(str(e))
                            self._numdeldfld += 1

                except Exception as e:  # of any use ?
                    self.log(str(e))
                    continue

        # Files & directories only in source directory
        for f1 in self._dcmp.left_only:
            try:
                st = os.stat(os.path.join(self._dir1, f1))
            except os.error:
                continue

            if stat.S_ISREG(st.st_mode):
                if copyfunc:
                    copyfunc(f1, self._dir1, self._dir2)
                    self._added.append(os.path.join(self._dir2, f1))
            elif stat.S_ISDIR(st.st_mode):
                to_make = os.path.join(self._dir2, f1)
                if not os.path.exists(to_make):
                    os.makedirs(to_make)
                    self._added.append(to_make)

        # common files/directories
        for f1 in self._dcmp.common:
            try:
                st = os.stat(os.path.join(self._dir1, f1))
            except os.error:
                continue

            if stat.S_ISREG(st.st_mode):
                if updatefunc:
                    updatefunc(f1, self._dir1, self._dir2)
            # nothing to do if we have a directory

    def _copy(self, filename, dir1, dir2):
        """ Private function for copying a file """

        # NOTE: dir1 is source & dir2 is target
        if self._copyfiles:

            rel_path = filename.replace('\\', '/').split('/')
            rel_dir = '/'.join(rel_path[:-1])
            filename = rel_path[-1]

            dir2_root = dir2

            dir1 = os.path.join(dir1, rel_dir)
            dir2 = os.path.join(dir2, rel_dir)

            if self._verbose:
                self.log('Copying file %s from %s to %s' %
                         (filename, dir1, dir2))
            try:
                # source to target
                if self._copydirection == 0 or self._copydirection == 2:

                    if not os.path.exists(dir2):
                        if self._forcecopy:
                            # 1911 = 0o777
                            os.chmod(os.path.dirname(dir2_root), 1911)
                        try:
                            os.makedirs(dir2)
                        except OSError as e:
                            self.log(str(e))
                            self._numdirsfld += 1

                    if self._forcecopy:
                        os.chmod(dir2, 1911)  # 1911 = 0o777

                    sourcefile = os.path.join(dir1, filename)
                    try:
                        if os.path.islink(sourcefile):
                            os.symlink(os.readlink(sourcefile),
                                       os.path.join(dir2, filename))
                        else:
                            shutil.copy2(sourcefile, dir2)
                        self._numfiles += 1
                    except (IOError, OSError) as e:
                        self.log(str(e))
                        self._numcopyfld += 1

                elif self._copydirection == 1 or self._copydirection == 2:
                    # target to source

                    if not os.path.exists(dir1):
                        if self._forcecopy:
                            # 1911 = 0o777
                            os.chmod(os.path.dirname(self.dir1_root), 1911)

                        try:
                            os.makedirs(dir1)
                        except OSError as e:
                            self.log(str(e))
                            self._numdirsfld += 1

                    targetfile = os.path.abspath(os.path.join(dir1, filename))
                    if self._forcecopy:
                        os.chmod(dir1, 1911)  # 1911 = 0o777

                    sourcefile = os.path.join(dir2, filename)

                    try:
                        if os.path.islink(sourcefile):
                            os.symlink(os.readlink(sourcefile),
                                       os.path.join(dir1, filename))
                        else:
                            shutil.copy2(sourcefile, targetfile)
                        self._numfiles += 1
                    except (IOError, OSError) as e:
                        self.log(str(e))
                        self._numcopyfld += 1

            except Exception as e:
                self.log('Error copying file %s' % filename)
                self.log(str(e))

    def _cmptimestamps(self, filest1, filest2):
        """ Compare time stamps of two files and return True
        if file1 (source) is more recent than file2 (target) """

        mtime_cmp = int((filest1.st_mtime - filest2.st_mtime) * 1000) > 0
        if self._modtimeonly:
            return mtime_cmp
        else:
            return mtime_cmp or \
                   int((filest1.st_ctime - filest2.st_mtime) * 1000) > 0

    def _update(self, filename, dir1, dir2):
        """ Private function for updating a file based on
        last time stamp of modification """

        # NOTE: dir1 is source & dir2 is target
        if self._updatefiles:

            file1 = os.path.join(dir1, filename)
            file2 = os.path.join(dir2, filename)

            try:
                st1 = os.stat(file1)
                st2 = os.stat(file2)
            except os.error:
                return -1

            # Update will update in both directions depending
            # on the timestamp of the file & copy-direction.

            if self._copydirection == 0 or self._copydirection == 2:

                # Update file if file's modification time is older than
                # source file's modification time, or creation time. Sometimes
                # it so happens that a file's creation time is newer than it's
                # modification time! (Seen this on windows)
                if self._cmptimestamps(st1, st2):
                    if self._verbose:
                        # source to target
                        self.log('Updating file %s' % file2)
                    try:
                        if self._forcecopy:
                            os.chmod(file2, 1638)  # 1638 = 0o666

                        try:
                            if os.path.islink(file1):
                                os.symlink(os.readlink(file1), file2)
                            else:
                                shutil.copy2(file1, file2)
                            self._changed.append(file2)
                            self._numupdates += 1
                            return 0
                        except (IOError, OSError) as e:
                            self.log(str(e))
                            self._numupdsfld += 1
                            return -1

                    except Exception as e:
                        self.log(str(e))
                        return -1

            elif self._copydirection == 1 or self._copydirection == 2:

                # Update file if file's modification time is older than
                # source file's modification time, or creation time. Sometimes
                # it so happens that a file's creation time is newer than it's
                # modification time! (Seen this on windows)
                if self._cmptimestamps(st2, st1):
                    if self._verbose:
                        # target to source
                        self.log('Updating file %s' % file1)
                    try:
                        if self._forcecopy:
                            os.chmod(file1, 1638)  # 1638 = 0o666

                        try:
                            if os.path.islink(file2):
                                os.symlink(os.readlink(file2), file1)
                            else:
                                shutil.copy2(file2, file1)
                            self._changed.append(file1)
                            self._numupdates += 1
                            return 0
                        except (IOError, OSError) as e:
                            self.log(str(e))
                            self._numupdsfld += 1
                            return -1

                    except Exception as e:
                        self.log(str(e))
                        return -1

        return -1

    def _dirdiffandcopy(self, dir1, dir2):
        """
        Private function which does directory diff & copy
        """
        self._dowork(dir1, dir2, self._copy)

    def _dirdiffandupdate(self, dir1, dir2):
        """
        Private function which does directory diff & update
        """
        self._dowork(dir1, dir2, None, self._update)

    def _dirdiffcopyandupdate(self, dir1, dir2):
        """
        Private function which does directory diff, copy and update (synchro)
        """
        self._dowork(dir1, dir2, self._copy, self._update)

    def _dirdiff(self):
        """
        Private function which only does directory diff
        """

        if self._dcmp.left_only:
            self.log('Only in %s' % self._dir1)
            for x in self._dcmp.left_only:
                self.log('>> %s' % x)

        if self._dcmp.right_only:
            self.log('Only in', self._dir2)
            for x in self._dcmp.right_only:
                self.log('<< %s' % x)

        if self._dcmp.common:
            self.log('Common to %s and %s' % (self._dir1, self._dir2))
            print
            for x in self._dcmp.common:
                self.log('-- %s' % x)
        else:
            self.log('No common files or sub-directories!')

    def sync(self):
        """ Synchronize will try to synchronize two directories w.r.t
        each other's contents, copying files if necessary from source
        to target, and creating directories if necessary. If the optional
        argument purge is True, directories in target (dir2) that are
        not present in the source (dir1) will be deleted . Synchronization
        is done in the direction of source to target """

        self._copyfiles = True
        self._updatefiles = True
        self._creatdirs = True
        self._copydirection = 0

        if self._verbose:
            self.log('Synchronizing directory %s with %s\n' %
                     (self._dir2, self._dir1))
        self._dirdiffcopyandupdate(self._dir1, self._dir2)

    def update(self):
        """ Update will try to update the target directory
        w.r.t source directory. Only files that are common
        to both directories will be updated, no new files
        or directories are created """

        self._copyfiles = False
        self._updatefiles = True
        self._purge = False
        self._creatdirs = False

        if self._verbose:
            self.log('Updating directory %s with %s\n' %
                     (self._dir2, self._dir1))
        self._dirdiffandupdate(self._dir1, self._dir2)

    def dirdiff(self):
        """
        Only report difference in content between two directories
        """

        self._copyfiles = False
        self._updatefiles = False
        self._purge = False
        self._creatdirs = False
        self._updatefiles = False

        self.log('Difference of directory %s from %s\n' %
                 (self._dir2, self._dir1))
        self._dirdiff()

    def report(self):
        """ Print report of work at the end """

        # We need only the first 4 significant digits
        tt = (str(self._endtime - self._starttime))[:4]

        self.log('\nPython syncer finished in %s seconds.' % tt)
        self.log('%d directories parsed, %d files copied' %
                 (self._numdirs, self._numfiles))
        if self._numdelfiles:
            self.log('%d files were purged.' % self._numdelfiles)
        if self._numdeldirs:
            self.log('%d directories were purged.' % self._numdeldirs)
        if self._numnewdirs:
            self.log('%d directories were created.' % self._numnewdirs)
        if self._numupdates:
            self.log('%d files were updated by timestamp.' % self._numupdates)

        # Failure stats
        self.log('\n')
        if self._numcopyfld:
            self.log('%d files could not be copied.' % self._numcopyfld)
        if self._numdirsfld:
            self.log('%d directories could not be created.' % self._numdirsfld)
        if self._numupdsfld:
            self.log('%d files could not be updated.' % self._numupdsfld)
        if self._numdeldfld:
            self.log('%d directories could not be purged.' % self._numdeldfld)
        if self._numdelffld:
            self.log('%d files could not be purged.' % self._numdelffld)


def sync(src_dir, tgt_dir, action, **options):

    copier = Syncer(src_dir, tgt_dir, action=action, **options)
    copier.do_work()

    # print report at the end
    copier.report()

    return set(copier._changed).union(copier._added).union(copier._deleted)


def execute_from_command_line():
    import argparse

    parser = argparse.ArgumentParser(
        description='Syncer: Command line directory diff, synchronization, '\
                    'update & copy\n'\
                    'Authors: Anand Pillai (v1.0), Thomas Khyn (v2.x)')

    parser.add_argument('sourcedir', action='store', help='Source directory')
    parser.add_argument('targetdir', action='store', help='Target directory')

    parser.add_argument('--verbose', '-v', action='store_true', default=False,
        help='Provide verbose output')
    parser.add_argument('--diff', '-d', action='store_const', dest='action',
        const='diff', default=False,
        help='Only report difference between sourcedir and targetdir')
    parser.add_argument('--sync', '-s', action='store_const', dest='action',
        const='sync', default=False,
        help='Synchronize content between sourcedir and targetdir')
    parser.add_argument('--update', '-u', action='store_const', dest='action',
        const='update', default=False,
        help='Update existing content between sourcedir and targetdir')
    parser.add_argument('--purge', '-p', action='store_true', default=False,
        help='Purge files when synchronizing (does not purge by default)')
    parser.add_argument('--force', '-f', action='store_true', default=False,
        help='Force copying of files, by trying to change file permissions')
    parser.add_argument('--nodirection', '-n', action='store_true',
        default=False,
        help='Create target directory if it does not exist ' \
             '(By default, target directory should exist.)')
    parser.add_argument('--create', '-c', action='store_true', default=False,
        help='Only compare file\'s modification times for an update '\
             '(By default, compares source file\'s creation time also)')
    parser.add_argument('--modtime', '-m', action='store_true', default=False,
        help='Update existing content between sourcedir and targetdir')
    parser.add_argument('--only', '-o', action='store', nargs='+', default=[],
        help='Patterns to exclusively include (exclude every other)')
    parser.add_argument('--exclude', '-e', action='store', nargs='+',
        default=[], help='Patterns to exclude')
    parser.add_argument('--include', '-i', action='store', nargs='+',
        default=[], help='Patterns to include (with precedence over excludes)')
    parser.add_argument('--ignore', '-x', action='store', nargs='+',
        default=[], help='Patterns to ignore (no action)')

    options = vars(parser.parse_args())

    sync(options.pop('sourcedir'), options.pop('targetdir'), **options)
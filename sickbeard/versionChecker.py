# Author: Nic Wolfe <nic@wolfeden.ca>
# URL: http://code.google.com/p/sickbeard/
#
# This file is part of Sick Beard.
#
# Sick Beard is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Sick Beard is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Sick Beard.  If not, see <http://www.gnu.org/licenses/>.

import sickbeard
from sickbeard import version, ui
from sickbeard import logger
from sickbeard import scene_exceptions
from sickbeard.exceptions import ex

import os, platform, shutil
import subprocess, re, json
import urllib, urllib2
import zipfile, tarfile

from urllib2 import URLError
from lib.pygithub import github
import sys
from subprocess import call

class CheckVersion():
    """
    Version check class meant to run as a thread object with the SB scheduler.
    """

    def __init__(self):
        self.install_type = self.find_install_type()

        if self.install_type == 'win':
            self.updater = WindowsUpdateManager()
        elif self.install_type == 'git':
            self.updater = GitUpdateManager()
        elif self.install_type == 'osx':
            self.updater = MacUpdateManager()
        elif self.install_type == 'source':
            self.updater = SourceUpdateManager()
        else:
            self.updater = None

    def run(self):
        self.check_for_new_version()

        # refresh scene exceptions too
        scene_exceptions.retrieve_exceptions()

    def find_install_type(self):
        """
        Determines how this copy of SB was installed.
        
        returns: type of installation. Possible values are:
            'osx': any compiled mac osx build
            'win': any compiled windows build
            'git': running from source using git
            'source': running from source without git
        """

        # check if we're a windows build
        if getattr(sys, 'frozen', None) == 'macosx_app':
            install_type = 'osx'
        # check if we're a windows build
        elif sys.platform == 'win32':
            install_type = 'win'
        elif os.path.isdir(os.path.join(sickbeard.PROG_DIR, '.git')):
            install_type = 'git'
        else:
            install_type = 'source'

        return install_type

    def check_for_new_version(self, force=False):
        """
        Checks the internet for a newer version.
        
        returns: bool, True for new version or False for no new version.
        
        force: if true the VERSION_NOTIFY setting will be ignored and a check will be forced
        """

        if not sickbeard.VERSION_NOTIFY and not force:
            logger.log(u"Version checking is disabled, not checking for the newest version")
            return False

        logger.log(u"Checking if " + self.install_type + " needs an update")
        if not self.updater.need_update():
            logger.log(u"No update needed")
            if force:
                ui.notifications.message('No update needed')
            return False

        self.updater.set_newest_text()
        return True

    def update(self):
        if self.updater.need_update():
            return self.updater.update()

class UpdateManager():
    def get_update_url(self):
        return sickbeard.WEB_ROOT + "/home/update/?pid=" + str(sickbeard.PID)

class BinaryUpdateManager(UpdateManager):
    def __init__(self):
        self._cur_version = None
        self._cur_branch  = None
        self._newest_version = None
        self._newest_versionRaw = None
        
        self.gc_url = 'http://sickbeard.hostingsociety.com/latest.php'
        self.gc_url_human = 'http://sickbeard.hostingsociety.com/'

    def need_update(self):
        self._cur_version, self._cur_branch = self._find_installed_version()
        self._newest_version, self._newest_versionRaw = self._find_newest_version()
        logger.log("LOCAL: version: "+str(self._cur_version)+" branch: "+str(self._cur_branch), logger.DEBUG)
        logger.log("REMOTE: version: "+str(self._newest_version), logger.DEBUG)
        if self._newest_version > self._cur_version:
            return True

    def set_newest_text(self):
        new_str = 'There is a <a href="' + self.gc_url_human + '" onclick="window.open(this.href); return false;">newer version available</a> (build ' + str(self._newest_versionRaw) + ')'
        new_str += "&mdash; <a href=\"" + self.get_update_url() + "\">Update Now</a>"
        sickbeard.NEWEST_VERSION_STRING = new_str

    def _find_installed_version(self):
        # version = int("%d%d%02d" % (sickbeard.version.SICKBEARD_YEAR, sickbeard.version.SICKBEARD_MONTH, sickbeard.version.SICKBEARD_DAY))
 
        regex = "(?P<branch>[\w_]+) (?P<year>\d{2})\.(?P<month>\d{2})(\.(?P<day>\d{2}))?"
        match = re.search(regex, sickbeard.version.SICKBEARD_VERSION)
        if match:
            if match.group('day'):
                day = match.group('day')
            else:
                day = "00"
                
            version = int(match.group('year')+match.group('month')+day)
            return version, match.group('branch')
        return 0, 'unknown'

    def _find_newest_version(self, whole_link=False):
        """
        Checks google code for the newest Windows binary build. Returns either the
        build number or the entire build URL depending on whole_link's value.

        whole_link: If True, returns the entire URL to the release. If False, it returns
                    only the build number. default: False
        """
        
        logger.log(u"Update check url: "+self.gc_url+"&branch="+self._cur_branch, logger.DEBUG)
        svnFile = urllib.urlopen(self.gc_url+"&branch="+self._cur_branch)
        lines = svnFile.readlines()
        if len(lines) == 1:
            result = json.loads(lines[0])
            #TODO make a single function for the link and dont sent a string at on point and a tuple at another
            if whole_link:
                if 'link' in result:
                    return result['link']
                else:
                    logger.log("link was not set in update response. update will fail", logger.WARNING)
                    return None
            
            for field in ('year','month','day'):
                if not field in result:
                    logger.log(field+" was not set in update response. setting version to 0", logger.WARNING)
                    return 0, "unknown"
        
            if result['day'] != "00": # hide zero day for humans
                humanVersion = str(result['year'])+"."+str(result['month'])+"."+str(result['day'])
            else:
                humanVersion = str(result['year'])+"."+str(result['month'])
                
            return int(result['year']+result['month']+result['day']), humanVersion
            
        return 0, "unknown" 

class WindowsUpdateManager(BinaryUpdateManager):

    def __init__(self):
        BinaryUpdateManager.__init__(self)
        
        self.gc_url = 'http://sickbeard.hostingsociety.com/latest.php?os=win'


    def update(self):

        new_link = self._find_newest_version(True)

        if not new_link:
            logger.log(u"Unable to find a new version link on "+self.gc_url+" , not updating")
            return False

        # download the zip
        try:
            logger.log(u"Downloading update file from " + str(new_link))
            (filename, headers) = urllib.urlretrieve(new_link) #@UnusedVariable

            # prepare the update dir
            sb_update_dir = os.path.join(sickbeard.PROG_DIR, 'sb-update')
            logger.log(u"Clearing out update folder " + sb_update_dir + " before unzipping")
            if os.path.isdir(sb_update_dir):
                shutil.rmtree(sb_update_dir)

            # unzip it to sb-update
            logger.log(u"Unzipping from " + str(filename) + " to " + sb_update_dir)
            update_zip = zipfile.ZipFile(filename, 'r')
            update_zip.extractall(sb_update_dir)
            update_zip.close()

            # find update dir name
            update_dir_contents = os.listdir(sb_update_dir)
            if len(update_dir_contents) != 1:
                logger.log("Invalid update data, update failed. Maybe try deleting your sb-update folder?", logger.ERROR)
                return False

            content_dir = os.path.join(sb_update_dir, update_dir_contents[0])
            old_update_path = os.path.join(content_dir, 'updater.exe')
            new_update_path = os.path.join(sickbeard.PROG_DIR, 'updater.exe')
            logger.log(u"Copying new update.exe file from " + old_update_path + " to " + new_update_path)
            shutil.move(old_update_path, new_update_path)

            # delete the zip
            logger.log(u"Deleting zip file from " + str(filename))
            os.remove(filename)

        except Exception, e:
            logger.log(u"Error while trying to update: " + ex(e), logger.ERROR)
            return False

        return True

class MacUpdateManager(BinaryUpdateManager):

    def __init__(self):
        BinaryUpdateManager.__init__(self)

        self.gc_url = 'http://sickbeard.hostingsociety.com/latest.php?os=mac'

    def update(self):

        new_link = self._find_newest_version(True)

        if not new_link:
            logger.log(u"Unable to find a new version link on "+self.gc_url+" , not updating")
            return False

        # download the dmg
        try:
            m = re.search(r'(^.+?)/[\w_\-\. ]+?\.app', sickbeard.PROG_DIR)
            installPath = m.group(1)

            logger.log(u"Downloading update file from " + str(new_link))
            (filename, headers) = urllib.urlretrieve(new_link) #@UnusedVariable
            
            logger.log(u"New dmg at " + filename)
            os.system("hdiutil mount %s | grep /Volumes/SickBeard >update_mount.log" % (filename))
            fp = open('update_mount.log', 'r')
            data = fp.read()
            fp.close()
            m = re.search(r'/Volumes/(.+)', data)
            updateVolume = m.group(1)
            logger.log(u"Copying app from /Volumes/%s/SickBeard.app to %s" % (updateVolume, installPath))
            call(["cp", "-rf", "/Volumes/%s/SickBeard.app" % updateVolume, installPath])
            
            logger.log(u"Eject imgae /Volumes/%s/" % updateVolume)
            call(["hdiutil", "eject", "/Volumes/%s/" % updateVolume], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            
            # delete the dmg
            logger.log(u"Deleting dmg file from " + str(filename))
            os.remove(filename)

        except Exception, e:
            logger.log(u"Error while trying to update: " + ex(e), logger.ERROR)
            return False

        return True

class GitUpdateManager(UpdateManager):

    def __init__(self):
        self._cur_commit_hash = None
        self._newest_commit_hash = None
        self._num_commits_behind = 0

        self.git_url = 'http://code.google.com/p/sickbeard/downloads/list'

    def _git_error(self):
        error_message = 'Unable to find your git executable - either delete your .git folder and run from source OR <a href="http://code.google.com/p/sickbeard/wiki/AdvancedSettings" onclick="window.open(this.href); return false;">set git_path in your config.ini</a> to enable updates.'
        sickbeard.NEWEST_VERSION_STRING = error_message

        return None

    def _run_git(self, args):

        if sickbeard.GIT_PATH:
            git_locations = ['"' + sickbeard.GIT_PATH + '"']
        else:
            git_locations = ['git']

        # osx people who start SB from launchd have a broken path, so try a hail-mary attempt for them
        if platform.system().lower() == 'darwin':
            git_locations.append('/usr/local/git/bin/git')

        output = err = None

        for cur_git in git_locations:

            cmd = cur_git + ' ' + args

            try:
                logger.log(u"Executing " + cmd + " with your shell in " + sickbeard.PROG_DIR, logger.DEBUG)
                p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True, cwd=sickbeard.PROG_DIR)
                output, err = p.communicate()
                logger.log(u"git output: " + output, logger.DEBUG)
            except OSError:
                logger.log(u"Command " + cmd + " didn't work, couldn't find git.")
                continue

            if 'not found' in output or "not recognized as an internal or external command" in output:
                logger.log(u"Unable to find git with command " + cmd, logger.DEBUG)
                output = None
            elif 'fatal:' in output or err:
                logger.log(u"Git returned bad info, are you sure this is a git installation?", logger.ERROR)
                output = None
            elif output:
                break

        return (output, err)


    def _find_installed_version(self):
        """
        Attempts to find the currently installed version of Sick Beard.

        Uses git show to get commit version.

        Returns: True for success or False for failure
        """

        output, err = self._run_git('rev-parse HEAD') #@UnusedVariable

        if not output:
            return self._git_error()

        logger.log(u"Git output: " + str(output), logger.DEBUG)
        cur_commit_hash = output.strip()

        if not re.match('^[a-z0-9]+$', cur_commit_hash):
            logger.log(u"Output doesn't look like a hash, not using it", logger.ERROR)
            return self._git_error()

        self._cur_commit_hash = cur_commit_hash

        return True


    def _check_github_for_update(self):
        """
        Uses pygithub to ask github if there is a newer version that the provided
        commit hash. If there is a newer version it sets Sick Beard's version text.

        commit_hash: hash that we're checking against
        """

        self._num_commits_behind = 0
        self._newest_commit_hash = None

        gh = github.GitHub()

        # find newest commit
        for curCommit in gh.commits.forBranch(sickbeard.AUTOUPDATER_OWNER, sickbeard.AUTOUPDATER_REPOSITORY, sickbeard.AUTOUPDATER_VERSION):
            if not self._newest_commit_hash:
                self._newest_commit_hash = curCommit.id
                if not self._cur_commit_hash:
                    break

            if curCommit.id == self._cur_commit_hash:
                break

            self._num_commits_behind += 1

        logger.log(u"newest: " + str(self._newest_commit_hash) + " and current: " + str(self._cur_commit_hash) + " and num_commits: " + str(self._num_commits_behind), logger.DEBUG)

    def set_newest_text(self):

        # if we're up to date then don't set this
        if self._num_commits_behind == 35:
            message = "or else you're ahead of master"

        elif self._num_commits_behind > 0:
            message = "you're " + str(self._num_commits_behind) + ' commits behind'

        else:
            return

        if self._newest_commit_hash:
            url = 'http://github.com/' + sickbeard.AUTOUPDATER_OWNER + '/' + sickbeard.AUTOUPDATER_REPOSITORY + '/compare/'+self._cur_commit_hash+'...'+self._newest_commit_hash
        else:
            url = 'http://github.com/' + sickbeard.AUTOUPDATER_OWNER + '/' + sickbeard.AUTOUPDATER_REPOSITORY + '/commits/'

        new_str = 'There is a <a href="' + url + '" onclick="window.open(this.href); return false;">newer version available</a> (' + message + ')'
        new_str += "&mdash; <a href=\"" + self.get_update_url() + "\">Update Now</a>"

        sickbeard.NEWEST_VERSION_STRING = new_str

    def need_update(self):
        self._find_installed_version()
        try:
            self._check_github_for_update()
        except Exception:
            logger.log(u"Unable to contact github, can't check for update", logger.ERROR)
            return False

        logger.log(u"After checking, cur_commit = " + str(self._cur_commit_hash) + ", newest_commit = " + str(self._newest_commit_hash) + ", num_commits_behind = " + str(self._num_commits_behind), logger.DEBUG)

        if self._num_commits_behind > 0:
            return True

        return False

    def update(self):
        """
        Calls git pull origin <branch> in order to update Sick Beard. Returns a bool depending
        on the call's success.
        """

        output, err = self._run_git('pull origin '+sickbeard.AUTOUPDATER_VERSION) #@UnusedVariable

        if not output:
            return self._git_error()

        pull_regex = '(\d+) files? changed, (\d+) insertions?\(\+\), (\d+) deletions?\(\-\)'

        (files, insertions, deletions) = (None, None, None)

        for line in output.split('\n'):

            if 'Already up-to-date.' in line:
                logger.log(u"No update available, not updating")
                logger.log(u"Output: " + str(output))
                return False
            elif line.endswith('Aborting.'):
                logger.log(u"Unable to update from git: " + line, logger.ERROR)
                logger.log(u"Output: " + str(output))
                return False

            match = re.search(pull_regex, line)
            if match:
                (files, insertions, deletions) = match.groups()
                break

        if None in (files, insertions, deletions):
            logger.log(u"Didn't find indication of success in output, assuming git pull failed", logger.ERROR)
            logger.log(u"Output: " + str(output))
            return False

        return True



class SourceUpdateManager(GitUpdateManager):

    def _find_installed_version(self):

        version_file = os.path.join(sickbeard.PROG_DIR, 'version.txt')

        if not os.path.isfile(version_file):
            self._cur_commit_hash = None
            return

        fp = open(version_file, 'r')
        self._cur_commit_hash = fp.read().strip(' \n\r')
        fp.close()

        if not self._cur_commit_hash:
            self._cur_commit_hash = None

    def need_update(self):

        parent_result = GitUpdateManager.need_update(self)

        if not self._cur_commit_hash:
            return True
        else:
            return parent_result


    def set_newest_text(self):
        if not self._cur_commit_hash:
            logger.log(u"Unknown current version, don't know if we should update or not", logger.DEBUG)

            new_str = "Unknown version: If you've never used the Sick Beard upgrade system then I don't know what version you have."
            new_str += "&mdash; <a href=\"" + self.get_update_url() + "\">Update Now</a>"

            sickbeard.NEWEST_VERSION_STRING = new_str

        else:
            GitUpdateManager.set_newest_text(self)

    def update(self):
        """
        Downloads the latest source tarball from github and installs it over the existing version.
        """

        tar_download_url = 'http://github.com/' + sickbeard.AUTOUPDATER_OWNER + '/' + sickbeard.AUTOUPDATER_REPOSITORY + '/tarball/' + sickbeard.AUTOUPDATER_VERSION
        sb_update_dir = os.path.join(sickbeard.PROG_DIR, 'sb-update')
        version_path = os.path.join(sickbeard.PROG_DIR, 'version.txt')

        # retrieve file
        try:
            logger.log(u"Downloading update from " + tar_download_url)
            data = urllib2.urlopen(tar_download_url)
        except (IOError, URLError):
            logger.log(u"Unable to retrieve new version from " + tar_download_url + ", can't update", logger.ERROR)
            return False

        download_name = data.geturl().split('/')[-1]

        tar_download_path = os.path.join(sickbeard.PROG_DIR, download_name)

        # save to disk
        f = open(tar_download_path, 'wb')
        f.write(data.read())
        f.close()

        # extract to temp folder
        logger.log(u"Extracting file " + tar_download_path)
        tar = tarfile.open(tar_download_path)
        tar.extractall(sb_update_dir)
        tar.close()

        # delete .tar.gz
        logger.log(u"Deleting file " + tar_download_path)
        os.remove(tar_download_path)

        # find update dir name
        update_dir_contents = [x for x in os.listdir(sb_update_dir) if os.path.isdir(os.path.join(sb_update_dir, x))]
        if len(update_dir_contents) != 1:
            logger.log(u"Invalid update data, update failed: " + str(update_dir_contents), logger.ERROR)
            return False
        content_dir = os.path.join(sb_update_dir, update_dir_contents[0])

        # walk temp folder and move files to main folder
        for dirname, dirnames, filenames in os.walk(content_dir): #@UnusedVariable
            dirname = dirname[len(content_dir) + 1:]
            for curfile in filenames:
                old_path = os.path.join(content_dir, dirname, curfile)
                new_path = os.path.join(sickbeard.PROG_DIR, dirname, curfile)

                if os.path.isfile(new_path):
                    os.remove(new_path)
                os.renames(old_path, new_path)

        # update version.txt with commit hash
        try:
            ver_file = open(version_path, 'w')
            ver_file.write(self._newest_commit_hash)
            ver_file.close()
        except IOError, e:
            logger.log(u"Unable to write version file, update not complete: " + ex(e), logger.ERROR)
            return False

        return True


#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import re
import sys
import json
import time
import shutil
import github
import selectors
import traceback
import subprocess


def main():
    cfg = json.loads(sys.argv[1])["config"]
    dataDir = json.loads(sys.argv[1])["storage-file"]["data-directory"]

    gObj = None

    # check configuration
    if "account" not in cfg:
        raise Exception("no \"account\" in config")
    if "username" in cfg["account"] and "password" in cfg["account"]:
        pass
    elif "access-token" in cfg["account"]:
        pass
    else:
        raise Exception("no user information or api-token in config")

    # prepare repoSet
    repoSet = set()
    if "repositories" in cfg:
        # validation
        for item in cfg["repositories"]:
            if len(item.split("/")) != 2:
                raise Exception("invalid repository %s" % (item))

        # get repoSet
        for item in cfg["repositories"]:
            user = item.split("/")[0]
            repo = item.split("/")[1]
            if repo == "*":
                print("Process wildcard %s." % (item))
                if gObj is None:
                    if "access-token" in cfg["account"]:
                        gObj = github.Github(cfg["account"]["access-token"])
                    else:
                        gObj = github.Github(cfg["account"]["username"], cfg["account"]["password"])
                for tobj in gObj.get_user(user).get_repos():
                    if tobj.full_name.split("/")[0] == user:
                        repoSet.add(tobj.full_name)
                        print("Repository %s is added into prepare list." % (tobj.full_name))
            else:
                repoSet.add(item)
                print("Repository %s is added into prepare list." % (item))

    # update repoSet
    i = 1
    for repo in repoSet:
        print("Updating repository %s: (%d of %d)" % (repo, i, len(repoSet)))
        localDir = os.path.join(dataDir, repo)
        try:
            _Util.gitBarePullOrClone(localDir, "https://github.com/%s" % (repo))
        except Exception:
            traceback.print_exc()
        i += 1

    # delete redundant
    for fbasename in _Util.getFileList(dataDir, 2, "d"):
        if fbasename not in repoSet:
            _Util.forceDelete(os.path.join(dataDir, fbasename))
    for fbasename in _Util.getFileList(dataDir, 1, "d"):
        _Util.removeEmptyDir(os.path.join(dataDir, fbasename))


class _Util:

    @staticmethod
    def readFile(filename):
        with open(filename) as f:
            return f.read()

    @staticmethod
    def removeEmptyDir(dirname):
        if len(os.listdir(dirname)) == 0:
            os.rmdir(dirname)

    @staticmethod
    def getFileList(dirName, level, typeList):
        """typeList is a string, value range is "d,f,l,a"
           returns basename"""

        ret = []
        for fbasename in os.listdir(dirName):
            fname = os.path.join(dirName, fbasename)

            if os.path.isdir(fname) and level - 1 > 0:
                for i in _Util.getFileList(fname, level - 1, typeList):
                    ret.append(os.path.join(fbasename, i))
                continue

            appended = False
            if not appended and ("a" in typeList or "d" in typeList) and os.path.isdir(fname):         # directory
                ret.append(fbasename)
            if not appended and ("a" in typeList or "f" in typeList) and os.path.isfile(fname):        # file
                ret.append(fbasename)
            if not appended and ("a" in typeList or "l" in typeList) and os.path.islink(fname):        # soft-link
                ret.append(fbasename)

        return ret

    @staticmethod
    def forceDelete(path):
        if os.path.islink(path):
            os.remove(path)
        elif os.path.isfile(path):
            os.remove(path)
        elif os.path.isdir(path):
            shutil.rmtree(path)
        elif os.path.exists(path):      # FIXME: device node, how to check it?
            os.remove(path)
        else:
            pass                        # path not exists, do nothing

    @staticmethod
    def cmdCall(cmd, *kargs):
        # call command to execute backstage job
        #
        # scenario 1, process group receives SIGTERM, SIGINT and SIGHUP:
        #   * callee must auto-terminate, and cause no side-effect
        #   * caller must be terminated by signal, not by detecting child-process failure
        # scenario 2, caller receives SIGTERM, SIGINT, SIGHUP:
        #   * caller is terminated by signal, and NOT notify callee
        #   * callee must auto-terminate, and cause no side-effect, after caller is terminated
        # scenario 3, callee receives SIGTERM, SIGINT, SIGHUP:
        #   * caller detects child-process failure and do appopriate treatment

        ret = subprocess.run([cmd] + list(kargs),
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             universal_newlines=True)
        if ret.returncode > 128:
            # for scenario 1, caller's signal handler has the oppotunity to get executed during sleep
            time.sleep(1.0)
        if ret.returncode != 0:
            print(ret.stdout)
            ret.check_returncode()
        return ret.stdout.rstrip()

    @staticmethod
    def shellCall(cmd):
        # call command with shell to execute backstage job
        # scenarios are the same as _Util.cmdCall

        ret = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             shell=True, universal_newlines=True)
        if ret.returncode > 128:
            # for scenario 1, caller's signal handler has the oppotunity to get executed during sleep
            time.sleep(1.0)
        if ret.returncode != 0:
            print(ret.stdout)
            ret.check_returncode()
        return ret.stdout.rstrip()

    @staticmethod
    def shellExecWithStuckCheck(cmd, timeout=60, quiet=False):
        if hasattr(selectors, 'PollSelector'):
            pselector = selectors.PollSelector
        else:
            pselector = selectors.SelectSelector

        # run the process
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                shell=True, universal_newlines=True)

        # redirect proc.stdout/proc.stderr to stdout/stderr
        # make CalledProcessError contain stdout/stderr content
        # terminate the process and raise exception if they stuck
        sStdout = ""
        sStderr = ""
        bStuck = False
        with pselector() as selector:
            selector.register(proc.stdout, selectors.EVENT_READ)
            selector.register(proc.stderr, selectors.EVENT_READ)
            while selector.get_map():
                res = selector.select(timeout)
                if res == []:
                    bStuck = True
                    if not quiet:
                        sys.stderr.write("Process stuck for %d second(s), terminated.\n" % (timeout))
                    proc.terminate()
                    break
                for key, events in res:
                    data = key.fileobj.read()
                    if not data:
                        selector.unregister(key.fileobj)
                        continue
                    if key.fileobj == proc.stdout:
                        sStdout += data
                        sys.stdout.write(data)
                    elif key.fileobj == proc.stderr:
                        sStderr += data
                        sys.stderr.write(data)
                    else:
                        assert False

        proc.communicate()

        if proc.returncode > 128:
            time.sleep(1.0)
        if bStuck:
            raise _Util.ProcessStuckError(proc.args, timeout)
        if proc.returncode:
            raise subprocess.CalledProcessError(proc.returncode, proc.args, sStdout, sStderr)

    class ProcessStuckError(Exception):

        def __init__(self, cmd, timeout):
            self.timeout = timeout
            self.cmd = cmd

        def __str__(self):
            return "Command '%s' stucked for %d seconds." % (self.cmd, self.timeout)

    @staticmethod
    def gitIsBareRepo(dirName):
        if os.path.isdir(os.path.join(dirName, ".git")):
            return False
        if not os.path.exists(os.path.join(dirName, "config")):
            return False
        if re.search("^\\s*bare\\s*=\\s*true\\s*$", _Util.readFile(os.path.join(dirName, "config")), re.M) is None:
            return False
        return True

    @staticmethod
    def gitGetUrl(dirName):
        return _Util._gitCall(dirName, "config --get remote.origin.url")

    @staticmethod
    def gitClean(dirName):
        _Util.cmdCall("/usr/bin/git", "-C", dirName, "reset", "--hard")  # revert any modifications
        _Util.cmdCall("/usr/bin/git", "-C", dirName, "clean", "-xfd")    # delete untracked files

    @staticmethod
    def gitBarePullOrClone(dirName, url):
        """pull is the default action
           clone if not exists
           clone if not bare
           clone if url differs
           clone if pull fails"""

        if os.path.exists(dirName) and _Util.gitIsBareRepo(dirName) and url == _Util.gitGetUrl(dirName):
            mode = "pull"
        else:
            mode = "clone"

        while True:
            if mode == "pull":
                _Util.gitClean(dirName)
                try:
                    cmd = "%s /usr/bin/git -C \"%s\" fetch --rebase --no-stat" % (_Util._getGitSpeedEnv(), dirName)
                    _Util.shellExecWithStuckCheck(cmd)
                    break
                except _Util.ProcessStuckError:
                    time.sleep(1.0)
                except subprocess.CalledProcessError as e:
                    if e.returncode > 128:
                        raise                    # terminated by signal, no retry needed
                    time.sleep(1.0)
                    if "fatal:" in str(e.stderr):
                        mode = "clone"           # fatal: refusing to merge unrelated histories
            elif mode == "clone":
                _Util.forceDelete(dirName)
                try:
                    cmd = "%s /usr/bin/git clone --bare \"%s\" \"%s\"" % (_Util._getGitSpeedEnv(), url, dirName)
                    _Util.shellExecWithStuckCheck(cmd)
                    break
                except subprocess.CalledProcessError as e:
                    if e.returncode > 128:
                        raise                    # terminated by signal, no retry needed
                    time.sleep(1.0)
                    if "fatal: could not read Username" in str(e.stderr):
                        raise                    # github repository may be unavailable for various reasons, no retry needed
            else:
                assert False

    @staticmethod
    def _gitCall(dirName, command):
        gitDir = os.path.join(dirName, ".git")
        cmdStr = "/usr/bin/git --git-dir=\"%s\" --work-tree=\"%s\" %s" % (gitDir, dirName, command)
        return _Util.shellCall(cmdStr)

    @staticmethod
    def _getGitSpeedEnv():
        return "GIT_HTTP_LOW_SPEED_LIMIT=1024 GIT_HTTP_LOW_SPEED_TIME=60"


###############################################################################

if __name__ == "__main__":
    main()

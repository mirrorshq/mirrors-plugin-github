#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import re
import sys
import json
import github
import urllib
import urllib.request
import certifi
import lxml.html
import subprocess


def main():
    url = "https://www.github.org"
    rsyncSource = "rsync://rsync.github.org/pub"

    cfg = json.loads(sys.argv[1])["config"]
    dataDir = json.loads(sys.argv[1])["storage-file"]["data-directory"]

    mode = cfg.get("mode", "recent-github-only")
    if mode == "full":
        patternList = []
    elif mode == "github-only":
        patternList = [
            "+ /linux",
            "+ /linux/github",
            "+ /linux/github/v*",
            "+ /linux/github/v*/***",
            "- /**",
        ]
    elif mode == "recent-github-only":
        mainVerSet = set()
        if True:
            resp = urllib.request.urlopen(url, timeout=60, cafile=certifi.where())
            root = lxml.html.parse(resp)
            for tr in root.xpath(".//table[@id='releases']/tr"):
                value = tr.xpath("./td")[1].xpath("./strong")[0]
                m = re.match("([0-9]+)\\.[0-9].*", value.text)
                if m is not None:
                    mainVerSet.add(m.group(1))

        patternList = [
            "+ /linux",
            "+ /linux/github",
        ]
        for v in mainVerSet:
            patternList += [
                "+ /linux/github/v%s.*" % (v),
                "+ /linux/github/v%s.*/***" % (v),
            ]
        patternList.append("- /**")
    else:
        raise Exception("invalid mode")

    cmd = "/usr/bin/rsync -v -a -z --delete --delete-excluded --partial "
    for p in patternList:
        cmd += "-f '%s' " % (p)
    cmd += "%s %s" % (rsyncSource, dataDir)
    subprocess.run(cmd, shell=True, check=True)


###############################################################################

if __name__ == "__main__":
    main()

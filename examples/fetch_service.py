#! /usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright (C) 2011 ~ 2012 Deepin, Inc.
#               2011 ~ 2012 Hou Shaohui
# 
# Author:     Hou Shaohui <houshao55@gmail.com>
# Maintainer: Hou Shaohui <houshao55@gmail.com>
# 
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# any later version.
# 
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import sys
from pystorm.services import FetchService
from pystorm.tasks import TaskObject, MultiTaskObject
from pystorm.report import parse_bytes, parse_time

# Start fetch services 
fetch_service = FetchService(2)
fetch_service.start()

urls = [
        "http://packages.linuxdeepin.com/deepin/pool/main/d/deepinwine-qq2009/deepinwine-qq2009_0.0.3_all.deb",
        "http://packages.linuxdeepin.com/deepin/pool/main/d/deepinwine-qq2011/deepinwine-qq2011_0.0.1_i386.deb",
        "http://packages.linuxdeepin.com/deepin/pool/main/d/deepinwine-qq2012/deepinwine-qq2012_0.0.1_i386.deb",
        ]

download_task = MultiTaskObject(urls)

task_list = [download_task,]

def update_state(task, data):
    progress = "%d%%" % data.progress
    speed = parse_bytes(data.speed)
    remaining = parse_time(data.remaining)
    filesize = parse_bytes(data.filesize)
    downloaded = parse_bytes(data.downloaded)

    sys.stdout.flush()
    print "\r%s: %s/s - %s, progress: %s, total: %s, remaining time: %s" % (task, speed, 
                                                                          downloaded, progress, 
                                                                          filesize, remaining),

for task in task_list:
    task.connect("update", update_state)

fetch_service.add_missions(task_list)

while True:
    try:
        fetch_service.join(5.0)
    except KeyboardInterrupt:
        sys.exit(0)
        raise SystemExit

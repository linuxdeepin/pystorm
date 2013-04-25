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

import os
import time
import threading
import sys
import traceback

from .report import ProgressBar, parse_bytes
from .state import ConnectionState
from .fetch import provider_manager
from .events import EventManager

from . import common
from .nls import gettext as _

class StopExcetion(Exception):
    pass

class PauseException(Exception):
    pass

class ResumeException(Exception):
    pass

class TaskObject(EventManager):
    # status type for status-changed signal
    TASK_START = 0
    TASK_PAUSE = 1
    TASK_STOP = 2
    TASK_RESUME = 3
    TASK_FINISH = 4
    TASK_ERROR = 5
    
    def __init__(self, url, output_file=None, num_connections=4, max_speed=None, verbose=False, output_temp=False):
        EventManager.__init__(self)
        self.url = url
        self.output_file = self.get_output_file(output_file)
        self.num_connections = num_connections
        self.max_speed = max_speed
        self.conn_state = None
        self.fetch_threads = []
        self.__stop = True
        self.__pause = False
        self.__finish = False
        self.verbose = verbose
        self.output_temp = output_temp
        self.update_object = common.Storage()
        self.task_thread = None
        
        self.RemoteFetch = None        
        fetchs = provider_manager.get("fetch")
        
        for fetch in fetchs:        
            if fetch.is_match(url):
                self.RemoteFetch = fetch
                break
        
    def get_output_file(self, output_file):    
        if output_file is not None:
            return output_file
        
        return self.url.rsplit("/", 1)[1]
    
    def emit_update(self):
        dl_len = 0
        for rec in self.conn_state.progress:
            dl_len += rec
            
        try:    
            avg_speed = dl_len / self.conn_state.elapsed_time
        except:    
            avg_speed = 0
            
        self.update_object.speed = avg_speed    
        self.update_object.progress = dl_len * 100 / self.conn_state.filesize
        self.update_object.remaining = (self.conn_state.filesize - dl_len) / avg_speed if avg_speed > 0 else 0
        self.update_object.filesize = self.conn_state.filesize
        self.update_object.downloaded = dl_len
        
        self.emit("update", self.update_object, self)
        
    def is_actived(self):    
        for task in self.fetch_threads:
            if task.isAlive():
                return True
        return False    
    
    def stop_all_task(self):
        for task in self.fetch_threads:
            task.need_to_quit = True
            
    def stop(self):        
        self.__stop = True
        self.task_thread = None
        
    def pause(self):    
        self.__pause = True
        
    def resume(self):
        if self.task_thread is None:
            self.emit("resume", obj=self)
            self.emit("status-changed", (self.TASK_RESUME, None), self)
            self.start()
        
    def isfinish(self):    
        return self.__finish
    
    def start(self):
        self.task_thread = threading.Thread(target=self.run)
        self.task_thread.setDaemon(True)
        self.task_thread.start()
            
    def run(self):    
        try:
            if self.RemoteFetch is None:
                error_info = _("Don't support the protocol")
                self.logerror(error_info)
                self.emit("error", error_info, self)
                self.emit("status-changed", (self.TASK_ERROR, error_info), self)
                return 
            
            if not self.output_file:
                error_info = _("Invalid URL")
                self.logerror(error_info)
                self.emit("error", error_info, self)
                self.emit("status-changed", (self.TASK_ERROR, error_info), self)
                return
            
            self.__stop = False
            self.__pause = False
            
            file_size = self.RemoteFetch.get_file_size(self.url)
            if file_size == 0:
                error_info = _("Failed to get file information")
                self.logerror("UEL: %s, %s", self.url, error_info)
                self.emit("error", error_info, self)
                self.emit("status-changed", (self.TASK_ERROR, error_info), self)
                return
            
            if self.output_temp:
                part_output_file = common.get_temp_file(self.url)
            else:    
                part_output_file = "%s.part" % self.output_file            
            
            self.emit("start", obj=self)
            self.emit("status-changed", (self.TASK_START, None), self)
            
           # load ProgressBar.
            # if file_size < BLOCK_SIZE:
            #     num_connections = 1
            # else:    
            num_connections = self.num_connections
             
            # Checking if we have a partial download available and resume
            self.conn_state = ConnectionState(num_connections, file_size)    
            state_file = common.get_state_file(self.url)
            self.conn_state.resume_state(state_file, part_output_file)
            
            
            self.report_bar = ProgressBar(num_connections, self.conn_state)
            
            self.logdebug("File: %s, need to fetch %s", self.output_file, 
                         parse_bytes(self.conn_state.filesize - sum(self.conn_state.progress)))
            
            #create output file with a .part extension to indicate partial download

            part_output_file_fp = os.open(part_output_file, os.O_CREAT | os.O_WRONLY)
            os.close(part_output_file_fp)
            
            start_offset = 0
            start_time = time.time()
            
            
            for i in range(num_connections):
                current_thread = self.RemoteFetch(i, self.url, part_output_file, state_file, 
                                           start_offset + self.conn_state.progress[i],
                                           self.conn_state)
                self.fetch_threads.append(current_thread)
                current_thread.start()
                start_offset += self.conn_state.chunks[i]
                
            while self.is_actived():
                if self.__stop:
                    raise StopExcetion
                
                if self.__pause:
                    raise PauseException
                
                end_time = time.time()
                self.conn_state.update_time_taken(end_time-start_time)
                start_time = end_time
                
                download_sofar = self.conn_state.download_sofar()
                
                if self.max_speed != None and \
                        (download_sofar / self.conn_state.elapsed_time) > (self.max_speed * 1204):
                    for task in self.fetch_threads:
                        task.need_to_sleep = True
                        task.sleep_timer = download_sofar / (self.max_speed * 1024 - self.conn_state.elapsed_time)
                        
                # update progress        
                if self.verbose:        
                    self.report_bar.display_progress()        
                self.emit_update()
                time.sleep(1)        
                
            if self.verbose:    
                self.report_bar.display_progress()    
                
            os.remove(state_file)    
            try:
                os.unlink(self.output_file)
            except:    
                pass
            os.rename(part_output_file, self.output_file)
            self.__finish = True
            self.emit_update()            
            self.emit("finish", obj=self)
            self.emit("status-changed", (self.TASK_FINISH, None), self)
            if self.verbose:    
                self.report_bar.display_progress()    
            
        except StopExcetion:    
            self.stop_all_task()
            
            try:
                os.unlink(part_output_file)
            except: pass    
            
            try:
                os.unlink(state_file)
            except: pass
            
            self.emit("stop", obj=self)
            self.emit("status-changed", (self.TASK_STOP, None), self)
            
        except PauseException:    
            self.stop_all_task()
            self.emit("pause", obj=self)
            self.emit("status-changed", (self.TASK_PAUSE, None), self)
            
        except KeyboardInterrupt, e:    
            self.emit("stop", obj=self)
            self.emit("status-changed", (self.TASK_STOP, None), self)
            self.stop_all_task()
            
        except Exception, e:    
            self.emit("error", _("Unknown error"))
            self.emit("status-changed", (self.TASK_ERROR, _("Unknown error")), self)
            self.emit("stop", obj=self)
            self.emit("status-changed", (self.TASK_STOP, None), self)
            traceback.print_exc(file=sys.stdout)
            self.logdebug("File: %s at dowloading error %s", self.output_file, e)
            self.stop_all_task()

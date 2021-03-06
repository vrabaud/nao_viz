# Software License Agreement (BSD License)
#
# Copyright (c) 2008, Willow Garage, Inc.
# Copyright (c) 2014, Aldebaran Robotics (c)
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions
# are met:
#
#  * Redistributions of source code must retain the above copyright
#    notice, this list of conditions and the following disclaimer.
#  * Redistributions in binary form must reproduce the above
#    copyright notice, this list of conditions and the following
#    disclaimer in the documentation and/or other materials provided
#    with the distribution.
#  * Neither the name of the Willow Garage nor the names of its
#    contributors may be used to endorse or promote products derived
#    from this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS
# FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
# COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,
# INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
# BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
# LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN
# ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

#
# Ported from pr2_dashboard: Stefan Osswald, University of Freiburg, 2011.
#

import roslib
roslib.load_manifest('nao_dashboard')

import dbus, gobject, dbus.glib
from diagnostic_msgs.msg import *

#import avahi
class avahi:
    DBUS_NAME = "org.freedesktop.Avahi"
    DBUS_INTERFACE_SERVER = DBUS_NAME + ".Server"
    DBUS_PATH_SERVER = "/"
    DBUS_INTERFACE_ENTRY_GROUP = DBUS_NAME + ".EntryGroup"
    DBUS_INTERFACE_DOMAIN_BROWSER = DBUS_NAME + ".DomainBrowser"
    DBUS_INTERFACE_SERVICE_TYPE_BROWSER = DBUS_NAME + ".ServiceTypeBrowser"
    DBUS_INTERFACE_SERVICE_BROWSER = DBUS_NAME + ".ServiceBrowser"
    DBUS_INTERFACE_ADDRESS_RESOLVER = DBUS_NAME + ".AddressResolver"
    DBUS_INTERFACE_HOST_NAME_RESOLVER = DBUS_NAME + ".HostNameResolver"
    DBUS_INTERFACE_SERVICE_RESOLVER = DBUS_NAME + ".ServiceResolver"
    DBUS_INTERFACE_RECORD_BROWSER = DBUS_NAME + ".RecordBrowser"    
    PROTO_UNSPEC, PROTO_INET, PROTO_INET6  = -1, 0, 1
    IF_UNSPEC = -1
    LOOKUP_RESULT_CACHED = 1
    LOOKUP_RESULT_WIDE_AREA = 2
    LOOKUP_RESULT_MULTICAST = 4
    LOOKUP_RESULT_LOCAL = 8
    LOOKUP_RESULT_OUR_OWN = 16
    LOOKUP_RESULT_STATIC = 32


import std_msgs.msg

import rospy
from rosgraph import rosenv

from os import path
import threading

from .status_control import StatusControl
from .power_state_control import PowerStateControl
from .motors import Motors

from rqt_robot_dashboard.dashboard import Dashboard
from rqt_robot_dashboard.monitor_dash_widget import MonitorDashWidget
from rqt_robot_dashboard.console_dash_widget import ConsoleDashWidget

from python_qt_binding.QtCore import QSize
from python_qt_binding.QtGui import QMessageBox, QComboBox

class NAODashboard(Dashboard):
    
    def setup(self, context):
        self.name = 'NAO Dashboard (%s)'%rosenv.get_master_uri()
        self.max_icon_size = QSize(50, 30)
        self.message = None

        self._dashboard_message = None
        self._last_dashboard_message_time = 0.0

        self._raw_byte = None
        self.digital_outs = [0, 0, 0]

        icons_path = path.join(roslib.packages.get_pkg_dir('nao_dashboard'), "icons/")

        self._robot_combobox = QComboBox()
        self._robot_combobox.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self._robot_combobox.setInsertPolicy(QComboBox.InsertAlphabetically)
        self._robot_combobox.setEditable(True)

        gobject.threads_init()
        dbus.glib.threads_init()
        self.robots = []
        self.sys_bus = dbus.SystemBus()
        self.avahi_server = dbus.Interface(self.sys_bus.get_object(avahi.DBUS_NAME, '/'), avahi.DBUS_INTERFACE_SERVER)

        self.sbrowser = dbus.Interface(self.sys_bus.get_object(avahi.DBUS_NAME, self.avahi_server.ServiceBrowserNew(avahi.IF_UNSPEC,
            avahi.PROTO_INET, '_naoqi._tcp', 'local', dbus.UInt32(0))), avahi.DBUS_INTERFACE_SERVICE_BROWSER)

        self.sbrowser.connect_to_signal("ItemNew", self.avahiNewItem)
        self.sbrowser.connect_to_signal("ItemRemove", self.avahiItemRemove)

        # Diagnostics
        self._monitor = MonitorDashWidget(self.context)

        # Rosout
        self._console = ConsoleDashWidget(self.context, minimal=False)

        ## Joint temperature
        self._temp_joint_button = StatusControl('Joint temperature', 'temperature_joints')

        ## CPU temperature
        self._temp_head_button = StatusControl('CPU temperature', 'temperature_head')

        ## Motors
        self._motors_button = Motors(self.context)

        ## Battery State
        self._power_state_ctrl = PowerStateControl('NAO Battery')

        self._agg_sub = rospy.Subscriber('diagnostics_agg', DiagnosticArray, self.new_diagnostic_message)
        self._last_dashboard_message_time = 0.0

    def get_widgets(self):
        return [ [self._robot_combobox], 
                [self._monitor, self._console, self._temp_joint_button, self._temp_head_button,
                 self._motors_button],
                [self._power_state_ctrl]
                ]

    def shutdown_dashboard(self):
        self._agg_sub.unregister()

    def new_diagnostic_message(self, msg):
        """
        callback to process dashboard_agg messages

        :param msg: dashboard_agg DashboardState message
        :type msg: pr2_msgs.msg.DashboardState
        """
        self._dashboard_message = msg
        self._last_dashboard_message_time = rospy.get_time()
        for status in msg.status:
            if status.name == '/Nao/Joints':
                highestTemp = ""
                lowestStiff = -1.0
                highestStiff = -1.0
                hotJoints = ""
                for kv in status.values:
                     if kv.key == 'Highest Temperature':
                         highestTemp = " (" + kv.value + "deg C)"
                     elif kv.key == 'Highest Stiffness':
                         highestStiff = float(kv.value)
                     elif kv.key == 'Lowest Stiffness without Hands':
                         lowestStiff = float(kv.value)
                     elif kv.key == 'Hot Joints':
                         hotJoints = str(kv.value)
                self.set_buttonStatus(self._temp_joint_button, status, "Joints: ", "%s %s"%(highestTemp, hotJoints))
                #if(lowestStiff < 0.0 or highestStiff < 0.0):
                    #self._motors_button.set_stale()
                    #self._motors_button.SetToolTip(wx.ToolTip("Stale"))
                #elif(lowestStiff > 0.9):
                    #self._motors_button.set_error()
                    #self._motors_button.SetToolTip(wx.ToolTip("Stiffness on"))
                #elif(highestStiff < 0.05):
                    #self._motors_button.set_ok()
                    #self._motors_button.SetToolTip(wx.ToolTip("Stiffness off"))
                #else:
                    #self._motors_button.set_warn()
                    #self._motors_button.SetToolTip(wx.ToolTip("Stiffness partially on (between %f and %f)" % (lowestStiff, highestStiff)))
            elif status.name == '/Nao/CPU':
                self.set_buttonStatus(self._temp_head_button, status, "CPU temperature: ")
            elif status.name == '/Nao/Battery/Battery':
                if status.level == 3:
                    self._power_state_ctrl.set_stale()
                else:
                    self._power_state_ctrl.set_power_state(status.values)

    def set_buttonStatus(self, button, status, statusPrefix = "", statusSuffix = ""):
        statusString = "Unknown"
        if status.level == DiagnosticStatus.OK:
            button.update_state(0)
            statusString = "OK"
        elif status.level == DiagnosticStatus.WARN:
            button.update_state(1)
            statusString = "Warn"
        elif status.level == DiagnosticStatus.ERROR:
            button.update_state(2)
            statusString = "Error"
        elif status.level == 3:
            button.update_state(3)
            statusString = "Stale"
        button.setToolTip(statusPrefix + statusString + statusSuffix)

    def avahiNewItem(self, interface, protocol, name, stype, domain, flags):
        self.avahi_server.ResolveService(interface, protocol, name, stype, 
            domain, avahi.PROTO_INET, dbus.UInt32(0), 
            reply_handler=self.service_resolved, error_handler=self.print_error)
        pass
    
    def avahiItemRemove(self, interface, protocol, name, stype, domain, flags):
        print "Remove"
        for robot in self.robots:
            if robot['name'] == str(name) and robot['address'] == str(address) and robot['port'] == int(port):
                self.robots.remove(robot)
        updateRobotCombobox();
      
    def service_resolved(self, interface, protocol, name, type, domain, host, aprotocol, address, port, txt, flags):
        self.robots.append({'name': str(name), 'address': str(address), 'port': int(port)})
        self.updateRobotCombobox()
        
    def updateRobotCombobox(self):
        selected = self._robot_combobox.currentText()
        for i in range(self._robot_combobox.count()):
            self._robot_combobox.removeItem(i)
        id = -1
        for robot in self.robots:
            text = str(robot)
            text = "%s (%s:%d)" % (robot['name'], robot['address'], robot['port'])
            self._robot_combobox.addItem(text, '%s:%d' % (robot['address'], robot['port']))
            if(text == selected):
                id = self._robot_combobox.count()-1;
            
        if(self._robot_combobox.count() == 1):
            self._robot_combobox.setCurrentIndex(0)
        elif(id > -1):
            self._robot_combobox.setCurrentIndex(id)

        
    def print_error(self, *args):
        print 'error_handler'
        print args

    def save_settings(self, plugin_settings, instance_settings):
        self._console.save_settings(plugin_settings, instance_settings)
        self._monitor.save_settings(plugin_settings, instance_settings)

    def restore_settings(self, plugin_settings, instance_settings):
        self._console.restore_settings(plugin_settings, instance_settings)
        self._monitor.restore_settings(plugin_settings, instance_settings)

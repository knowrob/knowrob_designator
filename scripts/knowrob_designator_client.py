#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Topic-based client for all KnowRob designator messages

import rospy
import uuid
from time import sleep
from std_msgs.msg import Header
from knowrob_designator.msg import (
    PushObjectDesignator,
    DesignatorInit,
    DesignatorResolutionStart,
    DesignatorResolutionFinished,
    DesignatorExecutionStart,
    DesignatorExecutionFinished
)
from knowrob_ros.knowrob_ros_lib import KnowRobRosLib
from knowrob_ros.knowrob_ros_lib import get_default_modalframe

def testQueryDesig():
    know = KnowRobRosLib()
    know.init_clients()  # After rospy.init_node()
    
    query = "triple(?d, 'http://www.w3.org/1999/02/22-rdf-syntax-ns#type', 'http://www.ease-crc.org/ont/SOMA.owl#PyCramActionDesignator')"
    rospy.loginfo(f"asking [{query}] ...")
    result = know.ask_all(query, get_default_modalframe())
    rospy.loginfo(f"response: [{result}]")
    
    # Query for all objects of type http://www.ease-crc.org/ont/SOMA.owl#Apartment
    query = "triple(?d, 'http://www.w3.org/1999/02/22-rdf-syntax-ns#type', 'http://www.ease-crc.org/ont/SOMA.owl#Apartment'), " \
            "triple(?d, 'http://www.ease-crc.org/ont/SOMA.owl#hasUrdfLink', ?link)"
    rospy.loginfo(f"asking [{query}] ...")
    result = know.ask_all(query, get_default_modalframe())
    rospy.loginfo(f"response: [{result}]")
    # Query for soma SOMA:hasUrdfLink for the first object
    

def main():
    now = rospy.Time.now()

    # Publishers
    push_pub = rospy.Publisher('/knowrob/designator/push_object_designator', PushObjectDesignator, queue_size=10)
    init_pub = rospy.Publisher('/knowrob/designator/init', DesignatorInit, queue_size=10)
    resolve_start_pub = rospy.Publisher('/knowrob/designator/resolving_started', DesignatorResolutionStart, queue_size=10)
    resolve_finished_pub = rospy.Publisher('/knowrob/designator/resolving_finished', DesignatorResolutionFinished, queue_size=10)
    exec_start_pub = rospy.Publisher('/knowrob/designator/execution_start', DesignatorExecutionStart, queue_size=10)
    exec_finished_pub = rospy.Publisher('/knowrob/designator/execution_finished', DesignatorExecutionFinished, queue_size=10)

    rospy.sleep(1.0)  # Wait for publishers to register

    ##########################################################
    ############### Object Designator ########################

    push_msg = PushObjectDesignator()
    push_msg.stamp = now
    push_msg.json_designator = """
    {
      "anObject": {
        "name": "Milk1",
        "type": "Milk",
        "pose": {
          "px": 1.0,
          "py": 1.0,
          "pz": 0.0,
          "rx": 0.0,
          "ry": 0.0,
          "rz": 0.0,
          "rw": 1.0,
          "frame": "map"
        }
      }
    }
    """
    rospy.loginfo("Publishing PushObjectDesignator...")
    push_pub.publish(push_msg)

    ##########################################################
    ############### Action Designators ########################

    json_designator = """
    {
      "anAction": {
        "type": "Transporting",
        "object_designator": {
          "anObject": {
            "type": "Milk"
          }
        },
        "target": {
          "theLocation": {
            "goal": {
              "theObject": {
                "name": "Table1"
              }
            }
          }
        }
      }
    }
    """

    resolved_designator = """
    {
      "anAction": {
        "type": "Transporting",
        "object_designator": {
          "anObject": {
            "type": "Milk"
          }
        },
        "target_location": {
          "px": 2.1, 
          "py": 2.35, 
          "pz": 0.8, 
          "rx": 0.0, 
          "ry": 0.0, 
          "rz": 0.0, 
          "rw": 1.0, 
          "frame": "map"
        }
      }
    }
    """

    designator_id = "desig_start_1234"
    resolved_id = "desig_resolved_5678"

    init_msg = DesignatorInit()
    init_msg.stamp = now
    init_msg.designator_id = designator_id
    init_msg.parent_id = ""
    init_msg.json_designator = json_designator
    rospy.loginfo("Publishing DesignatorInit...")
    init_pub.publish(init_msg)

    resolve_start_msg = DesignatorResolutionStart()
    resolve_start_msg.stamp = now
    resolve_start_msg.designator_id = designator_id
    resolve_start_msg.json_designator = json_designator
    rospy.loginfo("Publishing DesignatorResolutionStart...")
    resolve_start_pub.publish(resolve_start_msg)

    rospy.sleep(1.0)

    resolve_finished_msg = DesignatorResolutionFinished()
    resolve_finished_msg.stamp = rospy.Time.now()
    resolve_finished_msg.designator_id = resolved_id
    resolve_finished_msg.resolved_from_id = designator_id
    resolve_finished_msg.json_designator = resolved_designator
    rospy.loginfo("Publishing DesignatorResolutionFinished...")
    resolve_finished_pub.publish(resolve_finished_msg)

    exec_start_msg = DesignatorExecutionStart()
    exec_start_msg.stamp = now
    exec_start_msg.designator_id = resolved_id
    exec_start_msg.json_designator = resolved_designator
    rospy.loginfo("Publishing DesignatorExecutionStart...")
    exec_start_pub.publish(exec_start_msg)

    exec_finished_msg = DesignatorExecutionFinished()
    exec_finished_msg.stamp = now
    exec_finished_msg.designator_id = resolved_id
    exec_finished_msg.json_designator = resolved_designator
    rospy.loginfo("Publishing DesignatorExecutionFinished...")
    exec_finished_pub.publish(exec_finished_msg)

if __name__ == '__main__':
    rospy.init_node('knowrob_designator_topic_client')
    # main()
    # Finally do some testing queries with KnowRob
    testQueryDesig()

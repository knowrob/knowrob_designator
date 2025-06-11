#!/usr/bin/env python3

import rospy
import actionlib
import json
from knowrob_designator.msg import DesignatorQueryIncrementalAction, DesignatorQueryIncrementalGoal

def send_query(query_json, query_type="entityvar", query_id=""):
    client = actionlib.SimpleActionClient('/knowrob/designator/query_incremental', DesignatorQueryIncrementalAction)

    rospy.loginfo("Waiting for action server...")
    client.wait_for_server()
    rospy.loginfo("Action server available.")

    goal = DesignatorQueryIncrementalGoal()
    goal.query_type = query_type
    goal.query_id = query_id
    goal.designator_json = json.dumps(query_json)

    rospy.loginfo(f"Sending query (query_id={query_id}):\n{goal.designator_json}")
    client.send_goal(goal)
    client.wait_for_result()

    return client.get_result()

if __name__ == '__main__':
    rospy.init_node('designator_query_test')

    # Query: Objects for breakfast
    breakfast_query = {
        "anObject": {
            "type": "?x",
            "playsrole": ["food", "breakfast"]
        }
    }

    result1 = send_query(breakfast_query)
    print("\n--- Breakfast object query result ---")
    print(f"Success: {result1.success}")
    print(f"Binding: {result1.binding_as_json}")

    # Query: Storage place for Milk
    milk_storage_query = {
        "anObject": {
            "type": "?t",
            "hasURDFLink": "?link",
            "playsrole": ["Deposit", {
                "anAction": {
                    "type": "Depositing",
                    "playsrole": ["DepositedObject", "Milk"]
                }
            }]
        }
    }

    result2 = send_query(milk_storage_query)
    print("\n--- Milk storage place query result ---")
    print(f"Success: {result2.success}")
    print(f"Binding: {result2.binding_as_json}")

#!/usr/bin/env python3

import rospy
import json
import uuid
from std_msgs.msg import String
import actionlib
from threading import Lock

# Import all designator message types
from knowrob_designator.msg import (
    PushObjectDesignator,
    DesignatorInit,
    DesignatorResolutionStart,
    DesignatorResolutionFinished,
    DesignatorExecutionStart,
    DesignatorExecutionFinished,
    DesignatorQueryIncrementalGoal,
    DesignatorQueryIncrementalAction,
    DesignatorQueryIncrementalResult,
    DesignatorQueryIncrementalFeedback
)

from knowrob_ros.knowrob_ros_lib import KnowRobRosLib, TripleQueryBuilder, get_default_modalframe
from knowrob_designator.designator_parser import DesignatorParser

print_triples = True

class DesignatorLoggerNode:
    def __init__(self):
        rospy.init_node('designator_logger_node')
        
        # Concurrency control
        self.lock = Lock()
        self.states = {}

        # Initialize subscribers for each message type
        rospy.Subscriber('/knowrob/designator/push_object_designator', PushObjectDesignator, self.handle_push_object_designator)
        rospy.Subscriber('/knowrob/designator/init', DesignatorInit, self.handle_init)
        rospy.Subscriber('/knowrob/designator/resolving_started', DesignatorResolutionStart, self.handle_resolve_start)
        rospy.Subscriber('/knowrob/designator/resolving_finished', DesignatorResolutionFinished, self.handle_resolve_finished)
        rospy.Subscriber('/knowrob/designator/execution_start', DesignatorExecutionStart, self.handle_exec_start)
        rospy.Subscriber('/knowrob/designator/execution_finished', DesignatorExecutionFinished, self.handle_exec_finished)
        
        # Initialize the ROS action server for DesignatorQueryIncremental
        self.query_history = {}
        self.query_incremental_server = actionlib.SimpleActionServer(
            '/knowrob/designator/query_incremental',
            DesignatorQueryIncrementalAction,
            self.execute_query_incremental,
            False
        )
        self.query_incremental_server.start()

        # Initialize the KnowRob client
        self.knowrob = KnowRobRosLib()
        self.knowrob.init_clients()        
        
        # Parser for designators
        self.parser = DesignatorParser()     

        rospy.loginfo("DesignatorLoggerNode: all subscribers initialized.")

    def handle_push_object_designator(self, msg):
        rospy.loginfo("----------------------------------------------------------")
        rospy.loginfo("Push Object Designator")
        designator = json.loads(msg.json_designator)
        # Crete the designator
        # triples = self.parser.push_object_designator(designator)
        triples = []
        # Translate triples to knowrob triples
        builder = TripleQueryBuilder()
        for s, p, o in triples:
            # Remove leading < or trailing > if present
            s = s[1:] if s.startswith("<") else s
            s = s[:-1] if s.endswith(">") else s

            p = p[1:] if p.startswith("<") else p
            p = p[:-1] if p.endswith(">") else p

            o = o[1:] if o.startswith("<") else o
            o = o[:-1] if o.endswith(">") else o

            # Add the triple to the builder
            builder.add(s, p, o)
        # Set the modal frame
        modal_frame = get_default_modalframe()
        modal_frame.confidence = 1.0
        # Add the designator to knowrob
        # self.knowrob.tell(builder.get_triples(), modal_frame)
        rospy.loginfo(f"Sent {len(triples)} triples for PushObjectDesignator")
        if print_triples:
            to_print = ""
            to_print += f"Triples for PushObjectDesignator:\n"
            for s, p, o in triples:
                to_print += f"{s} {p} {o}\n"
            rospy.loginfo(to_print)

    def handle_init(self, msg):
        rospy.loginfo("----------------------------------------------------------")
        rospy.loginfo(f"Init Designator: {msg.designator_id}")
        rospy.logdebug(f"Full JSON:\n{msg.json_designator}")

    def handle_resolve_start(self, msg):
        rospy.loginfo("----------------------------------------------------------")
        rospy.loginfo(f"[Init] Encoding new Action designator: {msg.designator_id}")
        designator = json.loads(msg.json_designator)
        description_content = designator.get('description', {})
        designator_id = msg.designator_id
        # Always treat the designator as an Action
        # If anAction as highest level key, then use the rest of the JSON as description content
        if 'anAction' in designator:
            description_content = designator['anAction']
        uri, triples = self.parser.create_unresolved_designator('Action', description_content, designator_id)
        # Translate triples to knowrob triples
        builder = TripleQueryBuilder()
        for s, p, o in triples:
            # Remove leading < or trailing > if present
            s = s[1:] if s.startswith("<") else s
            s = s[:-1] if s.endswith(">") else s

            p = p[1:] if p.startswith("<") else p
            p = p[:-1] if p.endswith(">") else p

            o = o[1:] if o.startswith("<") else o
            o = o[:-1] if o.endswith(">") else o

            # Add the triple to the builder
            builder.add(s, p, o)
        # Set the modal frame
        modal_frame = get_default_modalframe()
        modal_frame.confidence = 1.0
        # Add the designator to knowrob
        self.knowrob.tell(builder.get_triples(), modal_frame)
        rospy.loginfo(f"Sent {len(triples)} unresolved Action designator triples for {designator_id}")
        if print_triples:
            to_print = ""
            to_print += f"Unresolved triples for {designator_id}:\n"
            for s, p, o in triples:
                to_print += f"{s} {p} {o}\n"
            rospy.loginfo(to_print)
        
        # Mark start and buffer any early finish
        with self.lock:
            st = self.states.setdefault(msg.designator_id, {})
            st['resolve_started'] = True
            finish_msg = st.pop('resolve_finish_msg', None)
            if finish_msg:
                rospy.logwarn(f"ResolveStart came after ResolveFinished for {msg.designator_id}, processing")
                self._actually_handle_resolve_finished(finish_msg)

    def handle_resolve_finished(self, msg):
        with self.lock:
            st = self.states.setdefault(msg.resolved_from_id, {})
            if not st.get('resolve_started', False):
                st['resolve_finish_msg'] = msg
                rospy.logwarn(f"ResolveFinished came early for {msg.designator_id}, buffering")
                return
        self._actually_handle_resolve_finished(msg)

    def _actually_handle_resolve_finished(self, msg):
        rospy.loginfo("----------------------------------------------------------")
        rospy.loginfo(f"[ResolveStart] Processing Action designator resolution for: {msg.designator_id} from {getattr(msg, 'resolved_from_id', None)}")
        designator_json = json.loads(msg.json_designator)
        input_id = msg.resolved_from_id
        output_designator_id = msg.designator_id
        # Always treat the designator as an Action
        # If anAction as highest level key, then use the rest of the JSON as description content
        if 'anAction' in designator_json:
            designator_json = designator_json['anAction']
        resolving_uri, output_uri, triples = self.parser.create_designator_resolving(
            input_id,
            output_designator_id,
            'Action',
            designator_json,
            output_referent_content=None
            )
        # Translate triples to knowrob triples
        builder = TripleQueryBuilder()
        for s, p, o in triples:
            builder.add(s, p, o)
        # Set the modal frame
        modal_frame = get_default_modalframe()
        modal_frame.confidence = 1.0
        # Add the designator to knowrob
        self.knowrob.tell(builder.get_triples(), modal_frame)
        rospy.loginfo(f"Sent {len(triples)} resolving triples for Action task {resolving_uri}")
        if print_triples:
            to_print = ""
            to_print += f"Resolving triples for {resolving_uri}:\n"
            for s, p, o in triples:
                to_print += f"{s} {p} {o}\n"
            rospy.loginfo(to_print)

    def handle_exec_start(self, msg):
        rospy.loginfo("----------------------------------------------------------")
        rospy.loginfo(f"Execution Started: {msg.designator_id}")
        designator = json.loads(msg.json_designator)
        # Get the task type from the designator
        # If anAction as highest level key, then use the rest of the JSON as description content
        if 'anAction' in designator:
            designator = designator['anAction']
        task_type = designator.get('type')
        # Always treat the designator as an Action
        uri, triples = self.parser.create_event(msg.designator_id, task_type)
        # Translate triples to knowrob triples
        builder = TripleQueryBuilder()
        for s, p, o in triples:
            builder.add(s, p, o)
        # Set the modal frame
        modal_frame = get_default_modalframe()
        modal_frame.confidence = 1.0
        # Add the designator to knowrob
        self.knowrob.tell(builder.get_triples(), modal_frame)
        rospy.loginfo(f"Sent {len(triples)} execution start triples for {msg.designator_id}")
        if print_triples:
            # first create whole string then print it
            to_print = ""
            to_print += f"Execution start triples for {msg.designator_id}:\n"
            for s, p, o in triples:
                to_print += f"{s} {p} {o}\n"
            rospy.loginfo(to_print)
        # Mark start and buffer any early finish
        with self.lock:
            st = self.states.setdefault(msg.designator_id, {})
            st['exec_started'] = True
            finish_msg = st.pop('exec_finish_msg', None)
            if finish_msg:
                rospy.logwarn(f"ExecStart came after ExecFinished for {msg.designator_id}, processing")
                self._actually_handle_exec_finished(finish_msg)          
            
    def handle_exec_finished(self, msg):
        with self.lock:
            st = self.states.setdefault(msg.designator_id, {})
            if not st.get('exec_started', False):
                st['exec_finish_msg'] = msg
                rospy.logwarn(f"ExecFinished came early for {msg.designator_id}, buffering")
                return
        self._actually_handle_exec_finished(msg)    
            
    def _actually_handle_exec_finished(self, msg):
        # TODO: How do i add the end time?
        rospy.loginfo("----------------------------------------------------------")
        rospy.loginfo(f"Execution Finished: {msg.designator_id}")
            
    def execute_query_incremental(self, goal):
        rospy.loginfo("----------------------------------------------------------")
        rospy.loginfo(f"Query Incremental: {goal.query}")
        # Parse the query
        query = json.loads(goal.query)
        # Create the query
        uri, triples = self.parser.create_query_incremental(query)
        # Translate triples to knowrob triples
        builder = TripleQueryBuilder()
        for s, p, o in triples:
            builder.add(s, p, o)
        # Set the modal frame
        modal_frame = get_default_modalframe()
        modal_frame.confidence = 1.0
        # Add the designator to knowrob
        self.knowrob.tell(builder.get_triples(), modal_frame)
        rospy.loginfo(f"Sent {len(triples)} query incrementals for {goal.query}")
        if print_triples:
            to_print = ""
            to_print += f"Query incrementals for {goal.query}:\n"
            for s, p, o in triples:
                to_print += f"{s} {p} {o}\n"
            rospy.loginfo(to_print)
            
    def execute_query_incremental(self, goal):
        rospy.loginfo("----------------------------------------------------------")
        rospy.loginfo(f"Query Incremental: {goal.designator_json}")
        feedback = DesignatorQueryIncrementalFeedback()
        result = DesignatorQueryIncrementalResult()
        feedback.status_message = f"Received query of type '{goal.query_type}'"
        self.query_incremental_server.publish_feedback(feedback)

        try:
            # Case 1: Continue an existing query by ID
            if goal.query_id:
                query_id = str(goal.query_id)
                if query_id in self.query_history:
                    query_id = str(goal.query_id)
                    bindings, index = self.query_history[query_id]

                    if index < len(bindings):
                        result.success = True
                        result.binding_as_json = json.dumps(bindings[index])
                        result.query_id = query_id
                        self.query_history[query_id] = (bindings, index + 1)
                    else:
                        result.success = False
                        result.binding_as_json = "{}"
                        result.query_id = query_id
                    self.query_incremental_server.set_succeeded(result)
                    return

            # Case 2: New query
            designator = json.loads(goal.designator_json)
            query_id = str(uuid.uuid4().int & (1 << 32) - 1)

            if goal.query_type == "entityvar":
                success, bindings = self.handle_entityvar(designator)
                if success:
                    self.query_history[query_id] = (bindings, 1)
                    result.success = True
                    result.binding_as_json = json.dumps(bindings[0])
                    result.query_id = query_id
                else:
                    result.success = False
                    result.binding_as_json = "{}"
                    result.query_id = query_id
            else:
                result.success = False
                result.binding_as_json = "{}"
                result.query_id = query_id

        except Exception as e:
            rospy.logerr(f"Error processing query: {e}")
            result.success = False
            result.binding_as_json = "{}"
            result.query_id = "0"

        self.query_incremental_server.set_succeeded(result)

    def handle_entityvar(self, designator):
        # Match: {"anObject": {"type": "?x", "usedFor": "breakfast"}}
        if (
            "anObject" in designator and
            isinstance(designator["anObject"], dict) and
            designator["anObject"].get("usedFor") == "breakfast" and
            designator["anObject"].get("type") == "?x"
        ):
            # Simulate multiple solutions
            return True, [
                {"?x": "Cereal"},
                {"?x": "Milk"}
            ]

        # Match: {"anAction": {"type": "searching", ...}}
        if (
            "anAction" in designator and
            isinstance(designator["anAction"], dict) and
            designator["anAction"].get("type") == "searching"
        ):
            return True, [
                {
                    "?x": {
                        "aLocation": {
                            "insideOf": {
                                "anObject": {
                                    "URDFLink": "fridge_main"
                                }
                            }
                        }
                    }
                }
            ]

        return False, []

if __name__ == '__main__':
    try:
        DesignatorLoggerNode()
        rospy.spin()
    except rospy.ROSInterruptException:
        pass

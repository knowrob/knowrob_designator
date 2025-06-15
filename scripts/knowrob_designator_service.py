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

from knowrob import *
from knowrob_ros.knowrob_ros_lib import KnowRobRosLib, TripleQueryBuilder, get_default_modalframe
from knowrob_designator.designator_parser import DesignatorParser

print_triples = True
print_object_triples = True

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
        # Create the designator
        triples = self.parser.push_object_designator(designator)
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
        rospy.loginfo(f"Sent {len(triples)} triples for PushObjectDesignator")
        if print_object_triples:
            rospy.loginfo(f"Unresolved Action designator triples: {str(builder.get_triples())}")

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
            rospy.loginfo(f"Unresolved Action designator triples: {str(builder.get_triples())}")
        
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
            rospy.loginfo(f"Unresolved Action designator triples: {str(builder.get_triples())}")


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
        rospy.loginfo(f"Query Incremental: {goal.designator_json}")
        feedback = DesignatorQueryIncrementalFeedback()
        result = DesignatorQueryIncrementalResult()
        feedback.status_message = f"Received query of type '{goal.query_type}'"
        self.query_incremental_server.publish_feedback(feedback)

        def extract_variables_from_designator(d):
            vars_found = set()
            def recurse(val):
                if isinstance(val, dict):
                    for v in val.values():
                        recurse(v)
                elif isinstance(val, list):
                    for v in val:
                        recurse(v)
                elif isinstance(val, str) and val.startswith("?"):
                    vars_found.add(val)
            recurse(d)
            return vars_found

        try:
            if goal.query_id:
                query_id = str(goal.query_id)
                if query_id in self.query_history:
                    bindings, next_idx = self.query_history[query_id]
                    if next_idx < len(bindings):
                        result.success = True
                        result.binding_as_json = json.dumps(bindings[next_idx])
                        result.query_id = query_id
                        self.query_history[query_id] = (bindings, next_idx + 1)
                    else:
                        result.success = False
                        result.binding_as_json = "{}"
                        result.query_id = query_id
                    self.query_incremental_server.set_succeeded(result)
                    return

            designator = json.loads(goal.designator_json)
            user_vars = extract_variables_from_designator(designator)

            triples = self.parser.designator_query(designator)
            rdf_type_triples = [t for t in triples if t[1] == "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"]
            non_type_triples = [t for t in triples if t[1] != "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"]

            conjuncts = []
            for (s, p, o) in non_type_triples:
                s_q = s if s.startswith("?") else f"'{s}'"
                p_q = p if p.startswith("?") else f"'{p}'"
                o_q = o if o.startswith("?") else f"'{o}'"
                conjuncts.append(f"triple({s_q}, {p_q}, {o_q})")
            query_str = ", ".join(conjuncts)

            ask_result = self.knowrob.ask_all(query_str, get_default_modalframe())
            rospy.loginfo(f"Query string: {query_str}")

            to_print = ""
            all_bindings = []
            if ask_result.status == ask_result.TRUE and ask_result.answers:
                for answer_msg in ask_result.answers:
                    # 1. Build full binding (with temp vars)
                    full_binding = {}
                    for kv in answer_msg.substitution:
                        if kv.type == kv.TYPE_STRING:
                            bound_val = kv.value_string
                        elif kv.type == kv.TYPE_FLOAT:
                            bound_val = str(kv.value_float)
                        elif kv.type == kv.TYPE_INT:
                            bound_val = str(kv.value_int)
                        elif kv.type == kv.TYPE_LONG:
                            bound_val = str(kv.value_long)
                        elif kv.type == kv.TYPE_VARIABLE:
                            bound_val = kv.value_variable
                        elif kv.type == kv.TYPE_PREDICATE:
                            bound_val = kv.value_predicate
                        elif kv.type == kv.TYPE_LIST:
                            bound_val = kv.value_list
                        else:
                            bound_val = kv.value_string if kv.value_string else ""
                        full_binding[kv.key] = bound_val

                    # 2. Resolve rdf:type triples using full binding
                    for (s, p, o) in rdf_type_triples:
                        # Remove ? from subject if present
                        s = s[1:] if s.startswith("?") else s
                        s_val = full_binding.get(s)
                        to_print += f"Processing rdf:type triple: {s} {p} {o} with s_val being {s_val}\n"
                        if s_val:
                            to_print += f"Subject resolved to: {s_val}\n"
                            if p == 'http://www.w3.org/1999/02/22-rdf-syntax-ns#type':
                                to_print += f"Checking type for {s_val} with object {o}\n"
                                o_val = o if o.startswith("?") else f"'{o}'"
                                type_query = f"triple('{s_val}', 'http://www.w3.org/1999/02/22-rdf-syntax-ns#type', {o_val})"
                                type_result = self.knowrob.ask_all(type_query, get_default_modalframe())
                                if type_result.status == type_result.TRUE and type_result.answers:
                                    for ans in type_result.answers:
                                        for kv in ans.substitution:
                                            to_print += f"Found type match: {kv.key} -> {kv.value_string}\n"
                                            if "?" + kv.key == o:
                                                full_binding[kv.key] = kv.value_string
                                            
            # Print the full binding for debugging
            # to_print += "Full binding:\n"
            #for var, val in full_binding.items():
            #    to_print += f"{var}: {val}\n"
            #to_print += "User-defined vars:\n"
            #for var in user_vars:
            #    to_print += f"{var}: {full_binding.get(var, 'N/A')}\n"
            #rospy.loginfo(to_print)

            # 3. Filter to user-defined vars only
            filtered_binding = {var: val for var, val in full_binding.items() if "?" + var in user_vars}
            all_bindings.append(filtered_binding)

            query_id = str(uuid.uuid4().int & ((1 << 32) - 1))

            if all_bindings:
                self.query_history[query_id] = (all_bindings, 1)
                result.success = True
                result.binding_as_json = json.dumps(all_bindings[0])
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


if __name__ == '__main__':
    try:
        DesignatorLoggerNode()
        rospy.spin()
    except rospy.ROSInterruptException:
        pass

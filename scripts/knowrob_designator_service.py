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
        """
        ROS action callback. Either continues an existing multi‐solution query
        (if goal.query_id is provided), or starts a new one by:
          1. loading goal.designator_json
          2. calling designator_query(...) → list of triples
          3. converting those triples into a single conjunctive query string
          4. calling runQuery(queryStr) against the KB
          5. storing all returned bindings under a fresh query_id
        """
        rospy.loginfo("----------------------------------------------------------")
        rospy.loginfo(f"Query Incremental: {goal.designator_json}")
        feedback = DesignatorQueryIncrementalFeedback()
        result = DesignatorQueryIncrementalResult()
        feedback.status_message = f"Received query of type '{goal.query_type}'"
        self.query_incremental_server.publish_feedback(feedback)

        try:
            # ------ CASE 1: Continue an existing query if query_id was provided ------
            if goal.query_id:
                query_id = str(goal.query_id)
                if query_id in self.query_history:
                    bindings, next_idx = self.query_history[query_id]
                    # If we still have more solutions to hand back:
                    if next_idx < len(bindings):
                        result.success = True
                        result.binding_as_json = json.dumps(bindings[next_idx])
                        result.query_id = query_id
                        # increment the index for next time
                        self.query_history[query_id] = (bindings, next_idx + 1)
                    else:
                        # no more solutions
                        result.success = False
                        result.binding_as_json = "{}"
                        result.query_id = query_id
                    self.query_incremental_server.set_succeeded(result)
                    return
                # if query_id not found, fall through to "new query" below

            # ------ CASE 2: New query (either no query_id passed or not found in history) ------
            # Parse the designator JSON
            designator = json.loads(goal.designator_json)

            # 1) Call designator_query(...) to get a list of triples
            #    Each triple is assumed to be a 3‐tuple: (subject, predicate, object).
            triples = self.parser.designator_query(designator)

            # 2) Build a conjunctive query string from all triples.
            #    For each triple (s, p, o), we turn it into "p(s,o)".
            #    Then we join with commas or "&" (whatever your parser expects).
            #    Here, we assume QueryParser.parse() can handle something like:
            #        "parent(?x, john) & sibling(?x, ?y)"
            #    Adjust the delimiter if your KB expects a different syntax (e.g. spaces, “,”, “,” + newline).
            conjuncts = []
            for (s, p, o) in triples:
                # If any term is a JSON‐encoded dict (e.g. nested), you might need to stringify it.
                # Create the string triple(subject, predicate, object). The three strings should
                # be sourrounded by single quotes, e.g.:
                # triple('s', 'p', 'o')
                # if the string starts with an ?, we assume it is a variable, and we do not
                # surround it with single quotes.
                s_q = s if s.startswith("?") else f"'{s}'"
                p_q = p if p.startswith("?") else f"'{p}'"
                o_q = o if o.startswith("?") else f"'{o}'"
                conjuncts.append(f"triple({s_q}, {p_q}, {o_q})")
                
            query_str = ", ".join(conjuncts)

            # 3) Call KnowRob’s ROS service / method ask_all(...)
            #    Assume get_default_modalframe() is a helper that returns a modalframe object.
            ask_result = self.knowrob.ask_all(query_str, get_default_modalframe())
            
            # Print all triples if requested
            rospy.loginfo(f"Query string: {query_str}")
            if ask_result.status == ask_result.TRUE:
                rospy.loginfo("value_strings: %s", 
                    [kv.value_string 
                        for res in ask_result.answers 
                        for kv  in res.substitution])
            else:
                rospy.loginfo(f"Query failed with status: {ask_result.status}")

            # 4) Unpack ask_result into a Python list of dicts.
            #
            #    - If ask_result.status is FALSE or QUERY_FAILED, we treat as “no solutions.”
            #    - Otherwise, iterate over ask_result.answers (a GraphAnswerMessage[]).
            #    - Each GraphAnswerMessage has a field .substitution (KeyValuePair[]).
            #
            all_bindings = []  # will become List[ { var: bound_value, … }, … ]
            if ask_result.status == ask_result.TRUE and ask_result.answers:
                for answer_msg in ask_result.answers:
                    # answer_msg.substitution is a list of KeyValuePair
                    binding_dict = {}
                    for kv in answer_msg.substitution:
                        # kv.key is the variable name, e.g. "?x"
                        var_name = kv.key

                        # Determine which value field is non‐empty based on kv.type
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
                            # for lists, we only have a flat string to parse if needed
                            bound_val = kv.value_list
                        else:
                            # unknown type: fallback to string
                            bound_val = kv.value_string if kv.value_string else ""
                        binding_dict[var_name] = bound_val

                    all_bindings.append(binding_dict)


            # 5) Generate a new query_id and store the entire list of bindings
            query_id = str(uuid.uuid4().int & ((1 << 32) - 1))

            if all_bindings is not None and len(all_bindings) > 0:
                # Save bindings + set next index = 1 (we'll return index 0 right now)
                self.query_history[query_id] = (all_bindings, 1)
                result.success = True
                result.binding_as_json = json.dumps(all_bindings[0])
                result.query_id = query_id
            else:
                # Either answer was “No” or no results
                result.success = False
                result.binding_as_json = "{}"
                result.query_id = query_id

        except Exception as e:
            rospy.logerr(f"Error processing query: {e}")
            result.success = False
            result.binding_as_json = "{}"
            result.query_id = "0"

        # 6) Always send the final result back to ROS
        self.query_incremental_server.set_succeeded(result)


if __name__ == '__main__':
    try:
        DesignatorLoggerNode()
        rospy.spin()
    except rospy.ROSInterruptException:
        pass

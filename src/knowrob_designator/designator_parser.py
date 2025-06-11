import uuid
from typing import List, Tuple, Optional, Dict, Any, Literal

class DesignatorParser:
    # Define the prefixes
    PREFIXES = {
        "SOMA": "http://www.ease-crc.org/ont/SOMA.owl",
        "dul": "http://www.ontologydesignpatterns.org/ont/dul/DUL.owl",
        "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns",
        "owl": "http://www.w3.org/2002/07/owl",
        "urdf": "http://knowrob.org/kb/urdf.owl"
    }

    # Triple type for readability
    Triple = Tuple[str, str, str]
    
    # Map from id to last designator uri
    last_designator_id = {}
    # Map from designator uri to designator description uri
    designator_uri_to_description = {}
    # Map from designator uri to referent uri
    designator_uri_to_referent = {}
    # Map from designator uri to designator description description uri
    designator_uri_to_description_description = {}
    # Map from designator uri to task uri
    designator_uri_to_task = {}
    
    # Map CRAM action types to SOMA action types
    action_type_map = {
            "Transporting": "http://www.ease-crc.org/ont/SOMA.owl#Transporting",
            "MoveTorsoAction": "http://www.ease-crc.org/ont/SOMA.owl#Positioning",
            "ParkArmsAction": "http://www.ease-crc.org/ont/SOMA.owl#ParkingArms",
            "PickUpAction": "http://www.ease-crc.org/ont/SOMA.owl#PickingUp",
            "PlaceAction": "http://www.ease-crc.org/ont/SOMA.owl#Placing"
            # Add more mappings as needed
     }
    
    # Map CRAM object types to SOMA object types
    # TODO: Find the correct mapping for the object types
    object_type_map = {
            "PyCRAP.Floor": "http://www.ease-crc.org/ont/SOMA.owl#Floor",
            "PyCRAP.Robot": "http://www.ease-crc.org/ont/SOMA.owl#Robot",
            "PyCRAP.Milk" : "http://www.ease-crc.org/ont/SOMA.owl#Milk",
            "PyCRAP.Apartment" : "http://www.ease-crc.org/ont/SOMA.owl#Apartment"
            # Add more mappings as needed
     }
    
    def map_action_type_from_cram_to_soma(self, cram_action_type: str) -> str:
        """
        Convert a CRAM action type to a SOMA action type.

        Args:
            cram_action_type: The CRAM action type (e.g., "Transporting")

        Returns:
            The corresponding SOMA action type (e.g., "SOMA:Transporting")
        """
        return self.action_type_map[cram_action_type]

    def create_individual(self, class_uri: str, id: str = None) -> str:
        """
        Create a new individual URI based on class name and a UUID

        Args:
            class_uri: The URI of the class (e.g., "SOMA:PyCramObjectDesignator")
            prefix: A prefix for the individual name

        Returns:
            A URI string for the new individual
        """
        # Extract class name from URI (get everything after the last # or :)
        url, class_name = class_uri.rsplit("#", 1) if "#" in class_uri else class_uri.rsplit(":", 1)

        # If an ID is provided, use it; otherwise, generate a new UUID
        if id:
            individual_id = f"{class_name}_{id}"
        else:
            # Generate a new UUID
            individual_id = f"{class_name}_{uuid.uuid4().hex[:8]}"

        # Construct URI
        if url.endswith("#"):
            individual_uri = f"{url}{individual_id}"
        else:
            individual_uri = f"{url}#{individual_id}"
        return individual_uri

    def triple(self, subject: str, predicate: str, object_: str) -> Triple:
        """Helper function to format a triple with proper prefix expansion"""
        for prefix, uri in self.PREFIXES.items():
            if subject.startswith(f"{prefix}:"):
                subject = subject.replace(f"{prefix}:", f"{uri}#")
            if predicate.startswith(f"{prefix}:"):
                predicate = predicate.replace(f"{prefix}:", f"{uri}#")
            if object_.startswith(f"{prefix}:"):
                object_ = object_.replace(f"{prefix}:", f"{uri}#")
            if subject.startswith(f"{prefix}#"):
                subject = subject.replace(f"{prefix}#", f"{uri}#")
            if predicate.startswith(f"{prefix}#"):
                predicate = predicate.replace(f"{prefix}#", f"{uri}#")
            if object_.startswith(f"{prefix}#"):
                object_ = object_.replace(f"{prefix}#", f"{uri}#")
        return (subject, predicate, object_)
    
    def push_object_designator(self,
            designator_content: Dict[str, Any]
    ) -> List[Triple]:
        """
        Push an object designator to the knowledge base

        Args:
            designator_content: The content of the designator
            time_as_float: The time as a float

        Returns:
            A list of triples representing the designator
        """
        triples = []
        # Create the designator
        object_type = designator_content["anObject"]["type"]
        object_type_uri = self.object_type_map[object_type]
        # Create individual for the object 
        object_designator_uri = self.create_individual(object_type_uri)
        # Create the Object with the hasType the type of the object
        triples.append(self.triple(object_designator_uri, "rdf:type", object_type_uri))
        # Add the urdf links to the object designator
        urdf_links = designator_content["anObject"].get("links")
        for link in urdf_links:
            triples.append(self.triple(object_designator_uri, "SOMA:hasUrdfLink", str(link)))
        return triples
        

    def create_unresolved_designator(self,
            designator_type: Literal["Object", "Action", "Motion", "Location"],
            description_content: Dict[str, Any],
            id: str
    ) -> Tuple[str, List[Triple]]:
        """
        Create an unresolved PyCram designator with all necessary parts

        Args:
            designator_type: Type of designator ("Object", "Action", "Motion", "Location")
            description_content: Key-value pairs for the designator description

        Returns:
            Tuple containing the designator URI and a list of triples
        """
        triples = []

        # Create the designator
        designator_class = f"SOMA:PyCram{designator_type}Designator"
        designator_uri = self.create_individual(designator_class)
        
        # Store the designator URI for later use
        self.last_designator_id[id] = designator_uri

        # Add type triple
        triples.append(self.triple(designator_uri, "rdf:type", designator_class))
        
        # Add ID triple with soma:hasNameString
        # TODO: Check if self is the correct string syntax. 
        triples.append(self.triple(designator_uri, "SOMA:hasNameString", id))

        # Create and link the description
        description_class = f"SOMA:PyCram{designator_type}DesignatorDescription"
        designator_description_uri = self.create_individual(description_class)
        
        # Store the designator description URI for later use
        self.designator_uri_to_description[designator_uri] = designator_description_uri

        # Add type triple for description
        triples.append(self.triple(designator_description_uri, "rdf:type", description_class))

        # Link designator to description
        triples.append(self.triple(designator_uri, "dul:hasProperPart", designator_description_uri))

        # For each key-value pair in the description content, add appropriate triples
        # self will depend on the designator type and expected structure
        # Here's a simplified approach:

        # First, handle what the description expresses based on designator type
        if designator_type == "Object":
            # Create a Description that describes a PhysicalArtifact
            desc_uri = self.create_individual("dul:Description")
            triples.append(self.triple(desc_uri, "rdf:type", "dul:Description"))
            triples.append(self.triple(designator_description_uri, "dul:expresses", desc_uri))
            # TODO: Add more specific properties based on description_content
            # triples.append(triple(desc_uri, "dul:describes", TODO))

        elif designator_type == "Action":
            # Create a Method
            method_uri = self.create_individual("dul:Method")
            triples.append(self.triple(method_uri, "rdf:type", "dul:Method"))
            triples.append(self.triple(designator_description_uri, "dul:expresses", method_uri))
            # Store the designator description description URI for later use
            self.designator_uri_to_description_description[designator_description_uri] = method_uri
            # From the description content, we extract the type of action
            action_type = description_content.get("type")
            # Map the action type to SOMA
            mapped_action_type = self.map_action_type_from_cram_to_soma(action_type)
            # Create individual for the mapped action type
            mapped_action_type_uri = self.create_individual(mapped_action_type)
            triples.append(self.triple(mapped_action_type_uri, "rdf:type", mapped_action_type))
            triples.append(self.triple(method_uri, "SOMA:isMethodFor", mapped_action_type_uri))
            # Designaor URI to mapped action type URI
            self.designator_uri_to_task[designator_uri] = mapped_action_type_uri
            # TODO: Add more specific properties based on description_content
            # triples.append(triple(method_uri, "dul:describes", TODO))

        elif designator_type == "Motion":
            # Create a MotionDescription
            motion_desc_uri = self.create_individual("SOMA:MotionDescription")
            triples.append(self.triple(motion_desc_uri, "rdf:type", "SOMA:MotionDescription"))
            triples.append(self.triple(designator_description_uri, "dul:expresses", motion_desc_uri))
            # TODO: Add more specific properties based on description_content
            # triples.append(triple(motion_desc_uri, "dul:describes", TODO))

        elif designator_type == "Location":
            # Create a Description that describes a PhysicalPlace
            desc_uri = self.create_individual("dul:Description")
            triples.append(self.triple(desc_uri, "rdf:type", "dul:Description"))
            triples.append(self.triple(designator_description_uri, "dul:expresses", desc_uri))
            # TODO: Add more specific properties based on description_content
            # triples.append(triple(desc_uri, "dul:describes", TODO))

        return designator_uri, triples

    def create_designator_resolving(self,
            input_designator_id: str,
            output_designator_id: str,
            output_designator_type: Literal["Object", "Action", "Motion", "Location"],
            output_description_content: Dict[str, Any],
            output_referent_content: Dict[str, Any]
    ) -> Tuple[str, str, List[Triple]]:
        """
        Create a designator resolving task with input and output roles,
        and properly link the output designator's referent to the input designator

        Args:
            input_designator_uri: URI of the input designator
            output_designator_type: Type of the output designator
            output_description_content: Content for the output designator description
            output_referent_content: Content for the output designator referent

        Returns:
            Tuple containing the resolving task URI, output designator URI, and list of triples
        """
        triples = []
        
        # Print the map before using it
        print("Last Designator ID Map:", str(self.last_designator_id))
        # Create the input designator URI
        input_designator_uri = self.last_designator_id[input_designator_id]

        # Create the resolving task
        resolving_uri = self.create_individual("SOMA:Resolving_of_PyCRAM_Designators")
        triples.append(self.triple(resolving_uri, "rdf:type", "SOMA:Resolving_of_PyCRAM_Designators"))

        # Create input role (premise)
        premise_uri = self.create_individual("SOMA:Premise")
        triples.append(self.triple(premise_uri, "rdf:type", "SOMA:Premise"))
        triples.append(self.triple(premise_uri, "dul:isRoleOf", input_designator_uri))
        triples.append(self.triple(resolving_uri, "SOMA:isTaskOfInputRole", premise_uri))

        # Create output designator with description and referent
        output_designator_class = f"SOMA:PyCram{output_designator_type}Designator"
        output_designator_uri = self.create_individual(output_designator_class)

        # Store the designator URI for later use
        self.last_designator_id[output_designator_id] = output_designator_uri

        # Add type triple
        triples.append(self.triple(output_designator_uri, "rdf:type", output_designator_class))

        # Create and link the description for output designator
        output_description_class = f"SOMA:PyCram{output_designator_type}DesignatorDescription"
        output_description_uri = self.create_individual(output_description_class)

        # Add type triple for description
        triples.append(self.triple(output_description_uri, "rdf:type", output_description_class))

        # Link output designator to description
        triples.append(self.triple(output_designator_uri, "dul:hasProperPart", output_description_uri))

        # Create and link the referent for output designator
        output_referent_class = f"SOMA:PyCram{output_designator_type}DesignatorReferent"
        output_referent_uri = self.create_individual(output_referent_class)

        # Add type triple for referent
        triples.append(self.triple(output_referent_uri, "rdf:type", output_referent_class))

        # Link output designator to referent
        triples.append(self.triple(output_designator_uri, "dul:hasProperPart", output_referent_uri))

        # Retrieve the input designator description URI
        input_description_uri = self.designator_uri_to_description[input_designator_uri]

        # Now create the appropriate expression relationships based on designator type
        if output_designator_type == "Object":
            # Create a Description that describes a PhysicalArtifact
            output_desc_uri = self.create_individual("dul:Description")
            triples.append(self.triple(output_desc_uri, "rdf:type", "dul:Description"))
            triples.append(self.triple(output_description_uri, "dul:expresses", output_desc_uri))
            # Store the designator description description URI for later use
            self.designator_uri_to_description_description[output_designator_uri] = output_desc_uri
            # TODO: Add more specific properties based on output_description_content
            # triples.append(triple(referent_desc_uri, "dul:describes", TODO))

        elif output_designator_type == "Action":            
            # Create a Method
            plan_uri = self.create_individual("dul:Plan")
            triples.append(self.triple(plan_uri, "rdf:type", "dul:Plan"))
            triples.append(self.triple(output_description_uri, "dul:expresses", plan_uri))
            
            # Store the designator description description URI for later use
            self.designator_uri_to_description_description[output_designator_uri] = plan_uri
            # From the description content, we extract the type of action
            action_type = output_description_content["type"]
            # Map the action type to SOMA
            mapped_action_type = self.map_action_type_from_cram_to_soma(action_type)
            # Create individual for the mapped action type
            mapped_action_type_uri = self.create_individual(mapped_action_type)
            triples.append(self.triple(mapped_action_type_uri, "rdf:type", mapped_action_type))
            triples.append(self.triple(plan_uri, "SOMA:isPlanFor", mapped_action_type_uri))
            # Designator URI to mapped action type URI
            self.designator_uri_to_task[output_designator_uri] = mapped_action_type_uri

            # Create a Plan that expands the Method
            plan_uri = self.create_individual("dul:Plan")
            triples.append(self.triple(plan_uri, "rdf:type", "dul:Plan"))
            triples.append(self.triple(output_referent_uri, "dul:expresses", plan_uri))
            
        elif output_designator_type == "Motion":
            # Create a MotionDescription
            motion_desc_uri = self.create_individual("SOMA:MotionDescription")
            triples.append(self.triple(motion_desc_uri, "rdf:type", "SOMA:MotionDescription"))
            triples.append(self.triple(output_description_uri, "dul:expresses", motion_desc_uri))
            triples.append(self.triple(output_designator_uri, "dul:expresses", motion_desc_uri))

            # Create a MotionDescription that expands the input MotionDescription
            referent_motion_desc_uri = self.create_individual("SOMA:MotionDescription")
            triples.append(self.triple(referent_motion_desc_uri, "rdf:type", "SOMA:MotionDescription"))
            triples.append(self.triple(output_referent_uri, "dul:expresses", referent_motion_desc_uri))

        elif output_designator_type == "Location":
            # Create a Description that describes a PhysicalPlace
            output_desc_uri = self.create_individual("dul:Description")
            triples.append(self.triple(output_desc_uri, "rdf:type", "dul:Description"))
            triples.append(self.triple(output_description_uri, "dul:expresses", output_desc_uri))
            triples.append(self.triple(output_desc_uri, "dul:describes", "dul:PhysicalPlace"))

            # Create a Description that expands the input description
            referent_desc_uri = self.create_individual("dul:Description")
            triples.append(self.triple(referent_desc_uri, "rdf:type", "dul:Description"))
            triples.append(self.triple(output_referent_uri, "dul:expresses", referent_desc_uri))
            triples.append(self.triple(referent_desc_uri, "dul:describes", "dul:PhysicalPlace"))

        # Add expands relationship
        # TODO: Where does referent_desc_uri come from?
        # triples.append(self.triple(referent_desc_uri, "dul:expands", output_desc_uri))
        # Get designator description description URI
        # input_desc_desc_uri = self.designator_uri_to_description_description[input_description_uri]
        # triples.append(self.triple(referent_desc_uri, "dul:expands", input_desc_desc_uri))
        # TODO: If there are multiple resolving tasks, each referent description expands the previous referent description (also for the other designator types)

        # Add directlyDerivedFrom relationships
        triples.append(self.triple(output_designator_uri, "SOMA:directlyDerivedFrom", input_designator_uri))
        triples.append(self.triple(output_description_uri, "SOMA:directlyDerivedFrom", input_description_uri))

        # Create output role (conclusion)
        conclusion_uri = self.create_individual("SOMA:Conclusion")
        triples.append(self.triple(conclusion_uri, "rdf:type", "SOMA:Conclusion"))
        triples.append(self.triple(conclusion_uri, "dul:isRoleOf", output_designator_uri))
        triples.append(self.triple(resolving_uri, "SOMA:isTaskOfOutputRole", conclusion_uri))

        return resolving_uri, output_designator_uri, triples
    
    def create_event(self,
            designator_id: str,
            task_type: str            
    ) -> Tuple[str, List[Triple]]:
        """
        Create an event for the designator

        Args:
            designator_id: The ID of the designator
            task_type: The type of task (e.g., "Action", "Motion")

        Returns:
            Tuple containing the event URI and a list of triples
        """
        triples = []

        # Create the dul:action and then 
        event_uri = self.create_individual(f"dul:Action")
        triples.append(self.triple(event_uri, "rdf:type", f"dul:Action"))
        # connect it with the task type via dul:executesTask
        # TODO: For now is just create a new individual
        # Get task type via map_action_type_from_cram_to_soma
        task_type = self.map_action_type_from_cram_to_soma(task_type)
        # Create the task type individual
        task_type_uri = self.create_individual(task_type)
        triples.append(self.triple(task_type_uri, "rdf:type", task_type))
        # Connect the event with the task type
        triples.append(self.triple(event_uri, "dul:executesTask", task_type_uri))
        # Connect the event with the designator
        designator_uri = self.last_designator_id[designator_id]
        # TODO: Find correct relation
        triples.append(self.triple(event_uri, "SOMA:hasDesignator", designator_uri))
        # Return the event URI and triples
        return event_uri, triples
    
    def designator_query(self, designator_as_json):
        triples = []
        var_counter = 0

        def new_var(prefix="?obj"):
            nonlocal var_counter
            var_counter += 1
            return f"{prefix}{var_counter}"

        def recursive_parse(entity, subject_var):
            if 'anObject' in entity and isinstance(entity['anObject'], dict):
                obj_var = new_var("?object")
                triples.append(self.triple(obj_var, 'rdf:type', 'soma:PhysicalObject'))
                recursive_parse(entity['anObject'], obj_var)

            if 'anAction' in entity and isinstance(entity['anAction'], dict):
                action_var = new_var("?action")
                triples.append(self.triple(action_var, 'rdf:type', 'dul:Action'))
                recursive_parse(entity['anAction'], action_var)

            if 'aLocation' in entity and isinstance(entity['aLocation'], dict):
                location_var = new_var("?location")
                triples.append(self.triple(location_var, 'rdf:type', 'dul:Location'))
                recursive_parse(entity['aLocation'], location_var)

            if 'type' in entity and isinstance(entity['type'], str):
                triples.append(self.triple(subject_var, 'rdf:type', entity['type']))

            if 'playsrole' in entity and isinstance(entity['playsrole'], list) and len(entity['playsrole']) == 2:
                role, event = entity['playsrole']

                if isinstance(role, str) and isinstance(event, str):
                    event_var = new_var("?event")
                    triples.append(self.triple(subject_var, 'dul:hasRole', role))
                    triples.append(self.triple(event_var, 'rdf:type', event))
                    triples.append(self.triple(subject_var, 'dul:isParticipantIn', event_var))
                elif isinstance(event, dict):
                    recursive_parse(event, subject_var)

            if 'hasURDFLink' in entity and isinstance(entity['hasURDFLink'], str):
                triples.append(self.triple(subject_var, 'urdf:hasBaseLinkName', entity['hasURDFLink']))

            for key, value in entity.items():
                if isinstance(value, dict) and key not in ['anObject', 'anAction', 'aLocation']:
                    recursive_parse(value, subject_var)

        # Determine root var type based on top-level key
        if 'anObject' in designator_as_json:
            root_var = new_var("?object")
            triples.append(self.triple(root_var, 'rdf:type', 'soma:PhysicalObject'))
            recursive_parse(designator_as_json['anObject'], root_var)
        elif 'anAction' in designator_as_json:
            root_var = new_var("?action")
            triples.append(self.triple(root_var, 'rdf:type', 'dul:Action'))
            recursive_parse(designator_as_json['anAction'], root_var)
        elif 'aLocation' in designator_as_json:
            root_var = new_var("?location")
            triples.append(self.triple(root_var, 'rdf:type', 'dul:Location'))
            recursive_parse(designator_as_json['aLocation'], root_var)
        else:
            root_var = '?d'
            triples.append(self.triple(root_var, 'rdf:type', 'SOMA:PyCramActionDesignator'))
            recursive_parse(designator_as_json, root_var)

        return triples


        
if __name__ == "__main__":
    import json

    parser = DesignatorParser()

    print("### TESTING create_unresolved_designator ###")
    action_desig = {
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
    designator_id = "test_action_1"
    uri, triples = parser.create_unresolved_designator("Action", action_desig, designator_id)
    print(f"Designator URI: {uri}")
    for s, p, o in triples:
        print(s, p, o)

    print("\n### TESTING create_designator_resolving ###")
    resolved_action = {
        "type": "Transporting",
        "object_designator": {
            "anObject": {
                "type": "Milk"
            }
        },
        "target_location": {
            "px": 1.0, "py": 2.0, "pz": 0.0,
            "frame": "map"
        }
    }
    resolving_uri, output_uri, triples = parser.create_designator_resolving(
        input_designator_id=designator_id,
        output_designator_id="test_action_1_resolved",
        output_designator_type="Action",
        output_description_content=resolved_action,
        output_referent_content=None
    )
    print(f"Resolving URI: {resolving_uri}")
    print(f"Output Designator URI: {output_uri}")
    for s, p, o in triples:
        print(s, p, o)

    print("\n### TESTING create_event ###")
    event_uri, triples = parser.create_event(designator_id="test_action_1_resolved", task_type="Transporting")
    print(f"Event URI: {event_uri}")
    for s, p, o in triples:
        print(s, p, o)

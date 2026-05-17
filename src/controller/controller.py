import threading
from pathlib import Path
import cv2
from src.controller.csv_parser import CSVParser
from returns.result import Failure, Success, Result
from returns.pipeline import is_successful
import networkx as nx
from src.controller.path_graph import PathGraph
from src.controller.node import Node, CharacterNode
from itertools import cycle
import math
from collections import namedtuple

#only exposes methods of the controller that the GUI should be able to use - adding nodes, removing nodes, stopping controller, starting controller, etc
class Controller:

    def __init__(self, sharedInfo = None, CSV = None, characterClass = None):
        self.agent = MapleAgent(sharedInfo = sharedInfo, CSV = CSV, characterClass = characterClass)

    # def start(self):
    #     self.agent.start()

    def getCharacterCoords(self) -> (int, int):
        return self.agent.getCharacterCoords()

    #will throw error if called before _setupAgent() method in the agent class is called
    def getGraph(self) -> nx.MultiDiGraph:
        return self.agent.pathGraph.graph

    def getNodeMap(self) -> dict[int, Node]:
        return self.agent.node_map

    # def addRotationNodes(self):

    # def addIntermediaryNodes(self):

    # def resetNodeList(self):

    def connectCharacterNode(self, char_node: CharacterNode = None) -> None:
        self.agent.connectCharacterNode(char_node)

    def deleteNode(self, node: Node) -> None:
        self.agent.deleteNode(node)

    def loadMap(self, csv_path) -> Result[None, str]:
        """
        Swap the agent's active map to the CSV at csv_path and rebuild the graph.

        Returns Success(None) on success, Failure(<reason>) on parser/build error.
        On failure the agent's state is reset (no partial map left over).
        """
        self.agent.setCSV(csv_path)
        return self.agent.setupAgent()

    # delete once you don't need a direct way to test this
    def parseCSV(self) -> None:
        res_parse_CSV = self.agent._parseCSV()
        if not is_successful(res_parse_CSV):
            print(res_parse_CSV)

    # delete once you don't need a direct way to test this
    def buildGraph(self) -> None:
        res_build_graph = self.agent._buildGraph()
        if not is_successful(res_build_graph):
            print(res_build_graph)


class MapleAgent:
    def __init__(self, sharedInfo = None, CSV = None, characterClass = None):
        self.characterClass = characterClass
        self.map_rotation_order = []
        self.sharedInfo = sharedInfo
        self.CSVParser = CSVParser(CSV = CSV)
        self.node_map = {}
        self.pathGraph = None #deffered initialisation
        self.y_visit_radius = 2
        self.x_visit_radius = 2
        self.edge_y_tolerance_level = 2
        self.edge_x_tolerance_level = 2
        # self.thread = threading.Thread(target=self.executePathFinding, daemon=True)
        self.project_root = Path(__file__).parent.parent.parent
        self.character_icon_path = str(self.project_root / "assets" / 'chr' / 'chr.png')
        self.character_icon_mask_path = str(self.project_root / "assets" / 'chr' / 'chr_mask.png')

    def _resetAgentState(self) -> None:
        """Clear all setup-derived state so _setupAgent can be re-run with a new CSV."""
        self.map_rotation_order = []
        self.node_map = {}
        self.pathGraph = None

    def setCSV(self, csv_path) -> None:
        """
        Replace the CSV the agent loads from. Caller is responsible for
        calling _setupAgent() afterward to rebuild the graph.

        csv_path may be a str or a pathlib.Path. Stored as a Path so
        CSVParser._validateCSV's .exists() check works.
        """
        self.CSVParser.CSV_file = Path(csv_path) if csv_path is not None else None

    def setupAgent(self) -> Result[None, str]:
        """
        Initialize agent components in dependency order.
        Order matters: PathGraph → CSV data → Graph edges.

        Idempotent: calling _setupAgent() again (e.g. on map swap) clears
        prior state first.
        """
        self._resetAgentState()

        # STEP 1: Initialize PathGraph with references to MapleAgent's data containers
        # PathGraph will hold references to self.node_map (empty)
        # This avoids the fragile initialization order we had before
        self._setupPathGraph()

        # STEP 2: Parse CSV to populate the containers PathGraph references
        # Fills self.node_map (used by PathGraph) and self.map_rotation_order (used by MapleAgent)
        parsed_csv_res = self._parseCSV()
        if not is_successful(parsed_csv_res):
            return parsed_csv_res

        # STEP 3: Build graph edges using the now-populated node_map
        # PathGraph can now access the nodes through its reference to self.node_map
        create_edges_res = self.pathGraph.buildGraph()
        if not is_successful(create_edges_res):
            return create_edges_res

        return Success(None)

    # def start(self):
    #     setup_agent_res = self._setupAgent()
    #     if not is_successful(setup_agent_res):
    #         print(setup_agent_res)
    #         print("terminating setup agent process.")
    #         return
    #     print(f"agent state setup successfully. Beginning pathfinding...")
    #     self.thread.start()
    #
    # def executePathFinding(self):
    #     goal_node_reached = False
    #     map_rotation_order_iter = cycle(self.map_rotation_order)
    #     goal_node = next(map_rotation_order_iter)
    #     while True:
    #         char_pos = self.getCharacterCoords()
    #         char_node = CharacterNode(char_pos)
    #         self.connectCharacterNode(char_node) #add character node to graph
    #         if goal_node_reached:
    #             goal_node = next(map_rotation_order_iter)
    #         path = self.pathGraph.getPathToGoalNode(goal_node)
    #         path_iter = iter(path)
    #         entire_path_valid = True
    #         while entire_path_valid:
    #             target_node = next(path_iter, None) #dooes ite
    #             # curr_path_final_node = path[-1]
    #             char_movement_axis = self._computeDirectionOfTravel(char_node, target_node)
    #             current_target_node_valid = True if target_node is not None else False
    #             while current_target_node_valid:
    #                 char_position = self.getCharacterCoords()
    #                 #check if on the same plane as the target node
    #                 if not self._isOnSamePlaneAsTargetNode(char_node, target_node, char_movement_axis):
    #                     current_target_node_valid, entire_path_valid, goal_node_reached = False, False, False
    #                     continue
    #                 #within the plane, nothing is wrong
    #                 if char_movement_axis == "horizontal":
    #                     dist_to_target = target_node.minimap_position[0] - char_position[0]
    #                     dist_to_target_after_tp = self._distAfterMovementAbility(self.characterClass.tp_max_traversal_dist, char_node, target_node)[0]
    #                     if abs(dist_to_target_after_tp) < abs(dist_to_target):
    #                         if char_position[0] < target_node.minimap_position[0]:
    #                             self.characterClass.teleport(direction = "right") #will need to pause here until the board sends back a msg that it has inputed the movements
    #                         elif char_position[0] > target_node.minimap_position[0]:
    #                             self.characterClass.tp_left(direction = "left")
    #                         continue





    def getCharacterCoords(self) -> (int, int):
        character_icon = cv2.imread(self.character_icon_path, cv2.IMREAD_GRAYSCALE)
        character_icon_mask = cv2.imread(self.character_icon_mask_path, cv2.IMREAD_GRAYSCALE)

        with self.sharedInfo.minimap_frame_lock:
            minimap = cv2.cvtColor(self.sharedInfo.minimap_frame, cv2.COLOR_BGR2GRAY)
            matched_loc = cv2.matchTemplate(minimap, character_icon, cv2.TM_CCORR_NORMED,
                                              mask=character_icon_mask)
            #gives top left corner of matched location
            matched_character_icon_loc = cv2.minMaxLoc(matched_loc)[-1]

        width, height = character_icon.shape[1], character_icon.shape[0]

        #add offset to get pixel location of the center of the character icon on the minimap
        matched_character_icon_loc = (matched_character_icon_loc[0] + (width//2), matched_character_icon_loc[1] + (height//2))
        return matched_character_icon_loc

    def connectCharacterNode(self, char_node: CharacterNode) -> None:
        self.pathGraph.connectCharacterNode(char_node)

    #will be used to delete the character node during runtime at the outermost while loop level
    def deleteNode(self, node: Node) -> None:
        self.pathGraph.deleteNode(node)

    def _setupPathGraph(self) -> None:
        self.pathGraph = PathGraph(self.node_map, edge_y_alignment_allowance = self.edge_y_tolerance_level, edge_x_alignment_allowance = self.edge_x_tolerance_level)

    def _computeDirectionOfTravel(self, char_node: CharacterNode, target_node: Node):
        char_x, char_y = char_node.minimap_position
        target_x, target_y = target_node.minimap_position
        x_component = target_x - char_x
        y_component = (-target_y) - (-char_y)  # account for top-left as origin. The graph uses bottom-left as origin, but the image uses top_left as origin. By doing this, we get the correct vector direction relative to the image.
        angle_vec = math.degrees(math.atan2(y_component, x_component))
        min_angle, max_angle = 45, 135
        return "vertical" if max_angle >= angle_vec >= min_angle or -min_angle >= angle_vec >= -max_angle else "horizontal"

    def _isOnSamePlaneAsTargetNode(self, char_node: CharacterNode, target_node: Node, char_movement_axis: str) -> bool:
        char_x , char_y = char_node.minimap_position
        target_x, target_y = target_node.minimap_position
        abs_x_diff, abs_y_diff = abs(char_x - target_x), abs(char_y - target_y)
        if char_movement_axis == "vertical":
            if abs_x_diff <= self.edge_x_tolerance_level:
                return True
        elif char_movement_axis == "horizontal":
            if abs_y_diff <= self.edge_y_tolerance_level:
                return True
        return False

    #trying to generalise this since some characters can tp, some can double jump, so can dash, etc. movement_ability_traversal_dist is a tuple of (x_dist, y_dist) as the ability's max traversal distance in each axis may be difference.
    def _distAfterMovementAbility(self, movement_ability_traversal_dist : (int, int) , char_node: CharacterNode, target_node: Node) -> (int, int):
        (char_x, char_y), (target_x, target_y) = char_node.minimap_position, target_node.minimap_position
        movement_ability_x_dist, movement_ability_y_dist = movement_ability_traversal_dist
        new_char_x, new_char_y = char_x + movement_ability_x_dist, char_y + movement_ability_y_dist
        dist_to_target_after_tp_x, dist_to_target_after_tp_y = abs(target_x - new_char_x), abs(target_y - new_char_y)
        return dist_to_target_after_tp_x, dist_to_target_after_tp_y



    def _parseCSV(self) -> Result[None, str]:
        parsed_csv_res = self.CSVParser.parseCSV(self.map_rotation_order,self.node_map)
        if not is_successful(parsed_csv_res):
            return parsed_csv_res

        #explicit assignment purely for clarity purposes- CSVParser.parseCSV() actually does in-place modification.
        parsed_csv_res = parsed_csv_res.unwrap()
        self.map_rotation_order = parsed_csv_res[0]
        self.node_map = parsed_csv_res[1]
        return Success(None)
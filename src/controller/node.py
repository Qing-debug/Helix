class Node:
    """
    Custom node class for networkx Graph.

    This class represents a node in the map with various properties that define
    its behavior and position in the game world.
    """
    node_id_counter = 0  #static attribute used to give nodes an ID.

    def __init__(self, nodetype : str  = None, minimap_pos : tuple = None, can_fall : bool = None,
                 fall_dist_exceeds_vertical_tp : bool = None, is_left_platform_edge : bool = None, is_right_platform_edge : bool = None):
        """
        Initialize a new Node with the specified properties.

        Args:
            nodetype (str, optional): The type of node (e.g., 'blue_node', 'orange_node').
            minimap_pos (tuple, optional): The (x, y) position of the node on the minimap.
            can_fall (bool, optional): Whether the character can fall from this node.
            fall_dist_exceeds_vertical_tp (bool, optional): Whether falling from this node exceeds vertical teleport distance.
            is_left_platform_edge (bool, optional): Whether this node is on the left edge of a platform.
            is_right_platform_edge (bool, optional): Whether this node is on the right edge of a platform.
        """
        self.uuid = Node.getGlobalUniqueID()
        self.nodetype = nodetype
        self.minimap_position = minimap_pos
        self.can_fall = can_fall
        self.fall_dist_exceeds_vertical_tp = fall_dist_exceeds_vertical_tp
        self.is_left_platform_edge = is_left_platform_edge
        self.is_right_platform_edge = is_right_platform_edge

    def __repr__(self):
        """
        Return a string representation of the Node object suitable for debugging.

        Returns:
            str: A detailed string showing all Node attributes.
        """
        return (f"Node(nodetype={self.nodetype}, minimap_pos={self.minimap_position}, "
                f"can_fall={self.can_fall}, fall_dist_exceeds_vertical_tp={self.fall_dist_exceeds_vertical_tp}, "
                f"is_left_platform_edge={self.is_left_platform_edge}, is_right_platform_edge={self.is_right_platform_edge})")

    def __str__(self):
        """
        Return a simplified string representation of the Node.

        Returns:
            str: A string containing the node's UUID and minimap position.
        """
        return f"{self.uuid},\n {self.minimap_position}"

    @classmethod
    def getGlobalUniqueID(cls):
        """
        Generate a unique identifier for a node.

        This class method increments a global counter and returns the new value,
        ensuring each node gets a unique ID during creation.

        Returns:
            int: A unique integer ID for the node.
        """
        cls.node_id_counter += 1
        return cls.node_id_counter


class CharacterNode(Node):
    """
    A specialized Node subclass representing the player character.

    This class maintains the identity of a Node (for polymorphism) while avoiding
    the overhead of unused fields. It only keeps the attributes needed for character
    positioning. Works with any function expecting a Node, provided those functions
    don't depend on the omitted attributes.
    """
    def __init__(self, minimap_pos: tuple[int,int] = None):
        """
        Initialize a new CharacterNode with the specified position.

        Unlike the parent Node class, CharacterNode only requires position information
        and automatically sets its type to "character_node".

        Args:
            minimap_pos (tuple[int,int], optional): The (x, y) position of the character on the minimap.
        """
        self.uuid = Node.getGlobalUniqueID()
        self.nodetype = "character_node"
        self.minimap_position = minimap_pos

    def __repr__(self):
        """
        Return a string representation of the CharacterNode object suitable for debugging.

        Returns:
            str: A string showing the character's position on the minimap.
        """
        return f"characterNode(minimap_pos={self.minimap_position})"

    def __str__(self):
        """
        Return a simplified string representation of the CharacterNode.

        Returns:
            str: A string containing the node type, UUID, and minimap position.
        """
        return f"{self.nodetype},\n{self.uuid},\n {self.minimap_position}"
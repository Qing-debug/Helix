from abc import ABC, abstractmethod


class CharacterClass(ABC):
    """Base class for MapleStory character classes the agent can drive.

    Concrete subclasses MUST declare `movement_type`,
    `max_horizontal_traversal_dist`, and `max_vertical_traversal_dist`
    at the class level. Forgetting any of them makes the subclass
    impossible to instantiate (TypeError at construction time).
    """

    @property
    @abstractmethod
    def movement_type(self) -> str:
        """e.g. 'double_jump', 'teleport'. The character's primary
        horizontal traversal ability. Single value for now — multi-ability
        characters pick their dominant one."""
        ...

    @property
    @abstractmethod
    def max_horizontal_traversal_dist(self) -> int:
        """Maximum horizontal pixel distance (on the minimap) covered in
        a single traversal action. Consumed by PathGraph to gate
        horizontal edge creation — two nodes farther apart than this on
        the x-axis will not have a horizontal edge between them, even if
        no closer candidate exists. For characters with multiple
        traversal abilities, use the LARGER value."""
        ...

    @property
    @abstractmethod
    def max_vertical_traversal_dist(self) -> int:
        """Maximum vertical pixel distance covered in a single traversal
        action. Not consumed by PathGraph today — surfaced on the ABC
        because the codebase already encodes vertical-traversal-range
        conceptually (see node.py `fall_dist_exceeds_vertical_tp`) and a
        future edge-gating pass will likely need it."""
        ...


class Kanna(CharacterClass):
    # Source: pre-existing measurement in the prior commented-out
    # `tp_max_traversal_dist = (19, 23)  # (x, y)`. Split into two
    # named attributes so PathGraph can consume just the horizontal
    # axis without tuple-indexing.
    movement_type = "teleport"
    max_horizontal_traversal_dist = 19
    max_vertical_traversal_dist = 23

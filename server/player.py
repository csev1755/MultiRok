import time


class Player:
    """
    A player slot and its current input state.

    Attributes:
        player_id (int): Zero-based player index.
        selected_vehicle (Vehicle or None): Currently selected vehicle.
        player_name (str or None): Display name of the player.
        active (bool): Whether the player slot is assigned to a connected client.
        buttons (set): Set of currently pressed button identifiers.
        last_activity (float): Timestamp of the last input.
    """

    def __init__(self, player_id):
        self.selected_vehicle = None
        self.player_name = None
        self.active = False
        self.player_id = player_id
        self.buttons = set()
        self.last_activity = time.time()

    @property
    def selection(self):
        """Return the selected vehicle's 1-based ID, or None."""
        return self.selected_vehicle.id if self.selected_vehicle else None

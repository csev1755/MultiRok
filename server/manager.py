import time

from devices.vehicle import Vehicle
from server.player import Player


class PlayManager:
    """
    Manages player and vehicle states.

    Attributes:
        players (list[Player]): Player slots indexed by zero-based player ID.
        max_player_count (int): Max number of players from config.
        vehicles (list[Vehicle]): Vehicles ordered by their one-based IDs.
        vehicle_count (int): Number of selectable vehicles.
    """

    def __init__(self, config, logger):
        """
        Initializes the PlayManager from the config.
        Creates empty Player objects according to the max_players value from the config.
        Reads vehicle/device configurations from the config file and creates vehicle instances.
        """
        self.logger = logger
        self.config = config
        self.allow_share = self.config["webserver"].getboolean("allow_share")

        self.max_player_count = self.config.getint("webserver", "max_players")
        self.players = [Player(player_id) for player_id in range(self.max_player_count)]
        self.vehicles = []
        self.vehicle_count = 0

        vehicles_by_id = {}
        for section in config.sections():
            if section.endswith(".vehicles"):
                device_name = section.replace(".vehicles", "")
                device_config = config[device_name]

                for vehicle_id, vehicle_name in config[section].items():
                    vehicle_id = int(vehicle_id)
                    if vehicle_id in vehicles_by_id:
                        raise ValueError(f"Duplicate vehicle ID: {vehicle_id}")
                    vehicles_by_id[vehicle_id] = Vehicle.configure(
                        play_manager=self,
                        type=device_name,
                        config=device_config,
                        id=vehicle_id,
                        name=vehicle_name,
                        logger=self.logger,
                    )

        vehicle_ids = sorted(vehicles_by_id)
        if vehicle_ids != list(range(1, len(vehicle_ids) + 1)):
            raise ValueError("Vehicle IDs must be consecutive integers starting at 1")
        self.vehicles = [vehicles_by_id[vehicle_id] for vehicle_id in vehicle_ids]
        self.vehicle_count = len(self.vehicles)

    def player_join(self):
        """
        Assigns an available Player object to a client.

        Returns:
            Player or None: The assigned Player object.
        """
        for player in self.players:
            if not player.active:
                player.active = True
                player.selected_vehicle = None
                player.buttons.clear()
                player.last_activity = time.time()
                self.logger.info(f"Assigned Player object {player.player_id}")
                return player
        self.logger.warning("No Player object available")
        return None

    def player_quit(self, player_id):
        """
        Releases the Player object associated with a client.

        Args:
            player_id (int): Zero-based player identifier.

        Returns:
            Player or None: The released Player object.
        """
        player = self.players[player_id]
        if not player.active:
            return None

        old_vehicle = player.selected_vehicle
        player.active = False
        player.player_name = None
        player.selected_vehicle = None
        player.buttons.clear()
        if old_vehicle:
            self.update_vehicle_controls(old_vehicle)
            old_vehicle.control()
        self.logger.info(f"Released Player object {player.player_id}")
        return player

    def handle_input(self, player, input):
        """
        Updates player input, recomputes affected vehicle controls, and applies them.

        Args:
            player (Player): The player issuing commands.
            input (dict): A dictionary containing a button and pressed state.
        """
        old_vehicle = player.selected_vehicle
        button = input["button"]
        if input["pressed"]:
            if button in ("SELECT_UP", "SELECT_DOWN"):
                delta = 1 if button == "SELECT_UP" else -1
                player.selected_vehicle = self.cycle_vehicle_selection(player, delta)
            player.buttons.add(button)
        else:
            player.buttons.discard(button)

        self.logger.debug(f"Player {player.player_id} - {player.buttons if player.buttons else {''}} - {player.selection}")

        affected_vehicles = {vehicle for vehicle in (old_vehicle, player.selected_vehicle) if vehicle is not None}
        for vehicle in affected_vehicles:
            self.update_vehicle_controls(vehicle)

        if player.selected_vehicle:
            player.last_activity = time.time()
        for vehicle in affected_vehicles:
            vehicle.control()

    def cycle_vehicle_selection(self, player, delta):
        """
        Cycle a player's vehicle selection while respecting occupied vehicles.

        Args:
            player (Player): The player changing their selection.
            delta (int): Direction to cycle, either 1 or -1.

        Returns:
            Vehicle or None: The selected vehicle, or None to clear the selection.
        """
        for connected_player in self.players:
            self.expire_selection(connected_player)

        current_selection = player.selection or 0
        occupied_selections = {
            other_player.selection
            for other_player in self.players
            if other_player.active and other_player is not player and other_player.selection is not None
        }

        for _ in range(self.vehicle_count):
            new_selection = (current_selection + delta) % (self.vehicle_count + 1)
            if new_selection == 0:
                return None
            if self.allow_share or new_selection not in occupied_selections:
                return self.vehicles[new_selection - 1]
            current_selection = new_selection

        return player.selected_vehicle

    def update_vehicle_controls(self, vehicle):
        """
        Recompute a vehicle's active players and combined controls.

        Args:
            vehicle (Vehicle): The vehicle to update.
        """
        players = [player for player in self.players if player.active and player.selected_vehicle is vehicle]
        vehicle.player_ids = {player.player_id for player in players}
        vehicle.controls = {button for player in players for button in player.buttons}

    def expire_selection(self, player):
        """
        Clear a player's vehicle selection if they have been inactive too long.

        Args:
            player (Player): The player whose selection may expire.
        """
        if (
            player.active
            and player.selected_vehicle
            and time.time() - player.last_activity > self.config.getint("webserver", "player_timeout")
        ):
            old_vehicle = player.selected_vehicle
            player.selected_vehicle = None
            player.buttons.clear()
            self.update_vehicle_controls(old_vehicle)
            old_vehicle.control()

    def get_player_info(self):
        """
        Retrieves data about connected players and expires idle vehicle selections.

        Returns:
            list[dict]: Player metadata dictionaries.
        """
        players = []

        for player in self.players:
            self.expire_selection(player)
            if player.active:
                players.append(
                    {
                        "player_id": player.player_id,
                        "player_name": player.player_name,
                        "selection": player.selection,
                        "selection_name": player.selected_vehicle.name if player.selected_vehicle else None,
                    }
                )

        return players

from devices.vehicle import Vehicle


class TestDevice(Vehicle):
    """
    Test device type that prints all controls to console for testing purposes.
    """

    type = "test_device"

    def __init__(self, play_manager, config, id, name, logger):
        super().__init__(play_manager, config, id, name, logger)

    def control(self):
        """
        Prints this vehicle's active controls.
        """
        print(f"Vehicle {self.id} controlled with input {self.controls if self.controls else {''}}")

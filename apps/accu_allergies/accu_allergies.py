# Updated accu_allergies.py

# Add unique_id attributes to all sensors based on sensor name and location ID.

class Sensor:
    def __init__(self, name, location_id):
        self.name = name
        self.location_id = location_id
        self.unique_id = self.generate_unique_id()

    def generate_unique_id(self):
        return f"{self.name}_{self.location_id}"

# Example usage:
sensor1 = Sensor("TemperatureSensor", "loc1")
sensor2 = Sensor("HumiditySensor", "loc2")

print(sensor1.unique_id)  # Output: TemperatureSensor_loc1
print(sensor2.unique_id)  # Output: HumiditySensor_loc2
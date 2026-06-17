import random

from automunki.services.seed_reporting_data import _random_apple_serial


def test_random_apple_serial_format():
    rng = random.Random(42)
    serials = {_random_apple_serial(rng) for _ in range(200)}
    assert len(serials) == 200
    for serial in serials:
        assert 10 <= len(serial) <= 12
        assert serial.isalnum()
        assert serial.upper() == serial

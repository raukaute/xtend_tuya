import json
from base64 import b64decode
from .. import strategy
from ....const import LOGGER


@strategy.register("sp_v2_encryption")
def convert(dp_item: tuple, config_item: dict) -> tuple:
    dp_key, dp_value = dp_item
    status_key, _ = json.loads(config_item["statusFormat"]).popitem()
    if dp_value is None or dp_value == "":
        return status_key, dp_value

    status_value = convert_value(dp_value)
    return status_key, status_value


def convert_value(dp_value):
    new_value = dp_value
    try:
        new_value = b64decode(dp_value)
    except Exception as e:
        LOGGER.exception(e, stack_info=True)
    return new_value

import os
import basics.base_utils as _
from basics.logging import get_logger

logger = get_logger(os.path.basename(__file__))


def convert_to_dict(type, components):
    if _.is_sequence(components):
        if len(components) == 1:
            components = {
                type: components[0]
            }
        elif len(components) > 1:
            components = {f"{type}_{i}": component for i, component in enumerate(components)}
    elif not _.is_dict(components):
        # Assuming single optimizer
        components = {
            type: components
        }

    return components


def get_value_at(key_path, nested_data, default=None, warn_on_failure=True):
    """
    Safe way to get value from nested data structure (e.g. nested dict) based on a key path

    TODO migrate to PyBase

    :param key_path:
    :param nested_data:
    :param default:
    :param warn_on_failure:

    :return:
    """
    keys = key_path.split(".")
    value = nested_data
    for key in keys:
        if has_key(value, key):
            value = value[key]
        else:
            if warn_on_failure:
                logger.warn(f"Key path {key_path} not found in given data")
            value = None
            break

    if value is None:
        value = default

    return value


def set_value_at(key_path, nested_data, value, warn_on_path_unavailable=False, base_path=None):
    """
    Safe way to set value in nested data structure (e.g. nested dict) based on a key path

    TODO migrate to PyBase

    :param key_path:
    :param value:
    :param nested_data:
    :param warn_on_path_unavailable:

    :param base_path: Don't use, only used for recursion

    :return:
    """

    if not can_get_and_set_values(nested_data):
        raise Exception(f"Invalid path {base_path}, can't get or set keys for provided nested data variable")

    keys = key_path.split(".")
    root_key = keys[0]

    is_final_key = len(keys) == 1

    if not is_final_key:
        if base_path is None:
            base_path = root_key
        else:
            base_path += f".{root_key}"

        if not has_key(nested_data, root_key):
            nested_data[root_key] = {}

            if warn_on_path_unavailable:
                logger.warn(f"Key path {base_path} not available, creating path")

        nested_data = nested_data[root_key]

        set_value_at('.'.join(keys[1:]), nested_data, value, warn_on_path_unavailable, base_path)
    else:
        nested_data[root_key] = value


def has_key(o, key):
    """
    TODO migrate to PyBase
    :param o:
    :param key:
    :return:
    """
    return hasattr(o, '__iter__') and (key in o)


def can_get_and_set_values(o):
    return (o is not None) and \
        hasattr(o, "__getitem__") and callable(o.__getitem__) and \
        hasattr(o, "__setitem__") and callable(o.__setitem__)


def is_chunkable(batch):
    return batch is not None and \
           not isinstance(batch, (tuple, list)) and \
           hasattr(batch, "__len__") and callable(batch.__len__) and \
           hasattr(batch, "__getitem__") and callable(batch.__getitem__)

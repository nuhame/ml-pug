import os

from typing import Optional, Tuple, Union, List, Callable

from basics.logging import get_logger
from basics.validation_utils import is_callable

import tensorflow as tf

from tensorflow.python.distribute import values
from tensorflow.python.types.distribute import DistributedValues

from mlpug.base import Base

module_logger = get_logger(os.path.basename(__file__))


def wrap_in_tf_func(func, *tf_func_args, monitor_tracing=False,  logger=None, **tf_func_kwargs):

    if not is_callable(func):
        raise ValueError(f"No valid function given (not callable), "
                         f"unable to wrap in tf.function: {func}")

    func_name = func.__name__ if hasattr(func, "__name__") else str(func)

    def monitored_func(*args, **kwargs):
        if monitor_tracing:
            replica_context = tf.distribute.get_replica_context()
            replica_id = replica_context.replica_id_in_sync_group if replica_context is not None \
                else "[OUTSIDE REPLICA CONTEXT]"

            logger.debug(f"Function {func_name}: tracing for replica\t: {replica_id}")

        return func(*args, **kwargs)

    logger.debug(f"Wrapped function {func_name} in tf.function")

    return tf.function(monitored_func, *tf_func_args, **tf_func_kwargs)


class DistributedFuncWrapper(Base):

    def __init__(self, func: Callable, distribution_strategy):
        func_name = func.__name__ if hasattr(func, "__name__") else str(func)
        name = f"Distributed version of {func_name}"

        super().__init__(pybase_logger_name=name)

        self._func_name = func_name
        self._func = func
        self._distribution_strategy = distribution_strategy

    @property
    def func_name(self):
        return self._func_name

    def __call__(self, *args, **kwargs):
        return self._distribution_strategy.run(
            self._func,
            args=args,
            kwargs=kwargs
        )


def create_distributed_func(func: Callable, distribution_strategy, logger=None):
    if logger is None:
        logger = module_logger

    if not is_callable(func):
        raise ValueError(f"No valid function given (not callable), "
                         f"unable to create distributed function for: {func}")

    distributed_func = DistributedFuncWrapper(func, distribution_strategy)

    logger.debug(f"Wrapped function {distributed_func.func_name} as distributed function with "
                 f"ID\t: {hex(id(distributed_func))}")

    return distributed_func


def contains_per_replica_data(data):
    if isinstance(data, (list, tuple)):
        return len(data) > 0 and contains_per_replica_data(data[0])

    return isinstance(data, DistributedValues)


def unpack_per_replica_and_map(
    map_func: Callable,
    per_replica_data: Optional[Tuple[tf.distribute.DistributedValues]] = None,
    distribution_strategy: Optional[tf.distribute.Strategy] = None,
    unpacked_replica_data: Optional[Union[Tuple, List]] = None
) -> Tuple:
    if per_replica_data is None and unpacked_replica_data is None:
        raise ValueError(f"Provide per_replica_data ({per_replica_data}) or "
                         f"unpacked_replica_data ({unpacked_replica_data})")

    if per_replica_data is not None and unpacked_replica_data is not None:
        raise ValueError("Either per_replica_data or unpacked_replica_data not both.")

    if per_replica_data is not None and unpacked_replica_data is None:
        if distribution_strategy is None:
            raise ValueError("Please provide a distribution_strategy in order to "
                             "unpack the provided per_replica_data")
        # unpack
        unpacked_replica_data = distribution_strategy.experimental_local_results(per_replica_data)

    return tuple(map(map_func, unpacked_replica_data))


def pack_per_replica(unpacked_replica_data: Union[Tuple, List]) -> Tuple:
    return tuple(values.PerReplica(t) for t in zip(*unpacked_replica_data))

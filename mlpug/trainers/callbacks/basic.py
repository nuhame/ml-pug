import sys

import datetime

from typing import Any, Optional, List, Mapping

from mlpug.trainers.callbacks.callback import Callback
from mlpug.utils import get_value_at, is_chunkable

import basics.base_utils as _


class LogProgress(Callback):

    def __init__(self,
                 log_period: int = 200,
                 set_names: Optional[List[str]] = None,
                 batch_level: bool = True,
                 logs_base_path: str = "current",
                 name: Optional[str] = None,
                 **kwargs: Any):
        super(LogProgress, self).__init__(name=name, **kwargs)

        self.log_period = log_period
        self.set_names = set_names or ["training"]
        self.batch_level = batch_level
        self.logs_base_path = logs_base_path

        self.metric_level_names = {
            'batch': 'Batch',
            'window_average': "Moving average",
            'dataset': "Computed over dataset",
            'epoch': "Epoch"
        }

    def on_batch_training_completed(self, training_batch: Any, logs: dict) -> bool:
        if not self.batch_level:
            return True

        success = True
        current = self._get_logs_base(logs)
        batch_step = current["batch_step"]

        has_dataset_level_metrics = False
        for set_name in self.set_names:
            dataset_metrics = get_value_at(f"{set_name}.dataset", current, warn_on_failure=False)
            has_dataset_level_metrics |= type(dataset_metrics) is dict and len(dataset_metrics) > 0

            if has_dataset_level_metrics:
                break

        if batch_step == 0 or batch_step % self.log_period == 0 or has_dataset_level_metrics:
            eta = self._calc_eta(logs)
            average_duration = self._get_average_batch_duration(logs)

            self._write('\nEpoch {:d}/{:d} - ETA: {:s}\tBatch {:d}/{:d} '
                        'Average batch training time {:s}\n'.format(current["epoch"],
                                                                    logs["final_epoch"],
                                                                    eta,
                                                                    current["batch_step"],
                                                                    logs["final_batch_step"],
                                                                    average_duration))

            for metric_level in ['batch', 'window_average', 'dataset', 'epoch']:
                self._write_metric_logs(metric_level, logs)
                self._write(f'\n')

            self._write(f'\n')

        return success

    def on_epoch_completed(self, logs: dict) -> bool:
        current = self._get_logs_base(logs)
        duration = self._get_epoch_duration(logs)
        self._write('\n')
        self._write('###############################################################################')
        self._write('\n')
        self._write('Epoch {:d}/{:d}\tREADY - Duration {:s}\n'.format(current["epoch"],
                                                                      logs["final_epoch"],
                                                                      duration))
        success = True
        for metric_level in ['window_average', 'dataset', 'epoch']:
            self._write_metric_logs(metric_level, logs)
            self._write(f'\n')

        self._write(f'\n')

        return success

    def _calc_eta(self, logs: dict) -> str:

        current = self._get_logs_base(logs)

        eta_str = "[UNKNOWN]"
        try:
            training_params = current["training_params"]

            average_batch_duration = training_params["window_average"]["duration"]
            if average_batch_duration and average_batch_duration > 0:
                batch_step = current["batch_step"]
                final_batch_step = logs["final_batch_step"]
                num_batches_to_go = final_batch_step - batch_step + 1

                eta_seconds = int(round(average_batch_duration * num_batches_to_go))

                eta_str = str(datetime.timedelta(seconds=eta_seconds))
        except Exception as e:
            _.log_exception(self._log, "Unable to calculate epoch ETA", e)

        return eta_str

    def _get_average_batch_duration(self, logs: dict) -> str:
        current = self._get_logs_base(logs)

        duration_str = "[UNKNOWN]"
        try:
            duration = current["training_params"]["window_average"]["duration"]
            if duration and duration > 0.0:
                duration = int(duration*1000)
                duration_str = f"{duration}ms"
        except Exception as e:
            _.log_exception(self._log, "Unable to get average batch duration", e)

        return duration_str

    def _get_epoch_duration(self, logs: dict) -> str:
        current = self._get_logs_base(logs)

        duration_str = "[UNKNOWN]"
        try:
            epoch_duration = int(round(current["training_params"]["epoch"]["duration"]))
            duration_str = str(datetime.timedelta(seconds=epoch_duration))
        except Exception as e:
            _.log_exception(self._log, "Unable to get epoch duration", e)

        return duration_str

    def _write_metric_logs(self, metric_level: str, logs: dict) -> None:
        metrics_log = ''
        for set_name in self.set_names:
            set_metrics_log = self._create_set_metrics_log_for(set_name, metric_level, logs)
            if set_metrics_log is None:
                continue

            metrics_log += f'{set_name:<15}: {set_metrics_log}.\n'

        if len(metrics_log) > 0:
            self._write(f'{self.metric_level_names[metric_level]}:\n')
            self._write(metrics_log)

    def _create_set_metrics_log_for(self, set_name: str, metric_level: str, logs: dict) -> str:
        current = self._get_logs_base(logs)

        key_path = f"{set_name}.{metric_level}"
        metrics = get_value_at(key_path, current, warn_on_failure=False)
        return self._create_log_for(metrics)

    def _create_log_for(self, metrics: Mapping, base_metric: Optional[str] = None, log_depth: int = 0) -> Optional[str]:
        if not _.is_mapping(metrics):
            return None

        metric_names = set(metrics.keys())
        # TODO : Make this a library level constant
        skip_metric_names = {"auxiliary_results", "duration"}

        num_metrics = len(metric_names-skip_metric_names)
        if num_metrics < 1:
            return None

        log = "\n"*int(log_depth > 0) + "\t"*log_depth
        if base_metric is not None:
            log += f"{base_metric:<15}: "

        metric_value_logs = []
        for c, (metric, value) in enumerate(metrics.items()):
            if metric in skip_metric_names:
                continue

            if type(value) is tuple:
                # use the first value as metric value, the other values are auxiliary results meant for other purposes
                value = value[0]

            if type(value) is dict:
                nested_logs = self._create_log_for(value, metric, log_depth+1)
                if nested_logs is not None:
                    metric_value_logs += ["\n" + nested_logs]
            else:
                try:
                    log_format = self._get_log_format(value)
                    metric_value_logs += [log_format.format(metric, value)]
                except Exception:
                    metric_value_logs += ["[UNKNOWN]"]

        if len(metric_value_logs) > 0:
            log += ', '.join(metric_value_logs)

        return log

    def _get_log_format(self, value) -> str:
        if abs(value) < 0.1:
            log_format = "{:<9s} {:.3e}"
        else:
            log_format = "{:<9s} {:>9.3f}"

        return log_format

    def _write(self, text: str) -> None:
        sys.stdout.write(text)
        sys.stdout.flush()


class BatchSizeLogger(Callback):

    def __init__(self, batch_dimension: int = 1, name: str = "BatchSizeLogger", **kwargs: Any):
        super().__init__(name=name, **kwargs)

        self._batch_dimension = batch_dimension

    def on_batch_training_start(self, training_batch: Any, logs: dict) -> bool:
        """

        :param training_batch:
        :param logs:

        :return: success (True or False)
        """

        current = self._get_logs_base(logs)

        # TODO : doesn't work for Tensorflow
        current['training_params']['batch']['batch_size'] = len(training_batch) if is_chunkable(training_batch) else \
            training_batch[0].size(self._batch_dimension)

        return True

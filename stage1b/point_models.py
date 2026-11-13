"""Importable baselines: archives must load outside the training process."""

import numpy as np


class CareerMean:
    def predict(self, x):
        return np.asarray(x)[:, 0]

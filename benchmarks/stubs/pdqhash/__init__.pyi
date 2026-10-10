# pdqhash: Python bindings of Meta's PDQ hash, which ship no type information.

import numpy as np
from numpy.typing import NDArray

def compute(image: NDArray[np.uint8]) -> tuple[NDArray[np.int64], int]: ...

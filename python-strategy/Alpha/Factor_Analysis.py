# -*- coding:utf-8 -*-

import numpy as np
import pandas as pd
import matplotlib as mpl
import matplotlib.pyplot as plt
import jqdatasdk as jq
import jqfactor_analyzer as jqf

if __name__ == '__main__':
    index = jq.get_all_securities()

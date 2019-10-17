import os
import numpy as np
import matplotlib.pyplot as plt
import yt

# bangpy
from . import paths
from . import load_save

# TODO:
#   - extract and save subsets of profiles (for faster loading)
#   - load .dat file
#   - plotly slider
#   -


class BangSim:
    def __init__(self, model, job_name=None, runs_path=None, config='default',
                 xmax=1e12, dim=1, output_dir='output', verbose=True,
                 load_all=True):
        self.verbose = verbose
        self.path = paths.model_path(model=model, runs_path=runs_path)
        self.output_path = os.path.join(self.path, output_dir)

        self.model = model
        self.job_name = job_name
        self.dim = dim
        self.xmax = xmax

        self.config = None
        self.dat = None
        self.chk = None
        self.ray = None
        self.x = None

        self.load_config(config=config)

        if load_all:
            self.load_dat()

    def printv(self, string):
        if self.verbose:
            print(string)

    def load_config(self, config='default'):
        """Load config file
        """
        filepath = paths.config_filepath(name=config)
        config = load_save.load_config(filepath, verbose=self.verbose)
        self.config = config

    def load_dat(self):
        """Load .dat file
        """
        filename = paths.dat_filename(self.job_name)
        filepath = os.path.join(self.path, filename)
        self.dat = load_save.load_dat(filepath, cols_dict=self.config['dat_columns'])

    def load_chk(self, step):
        """Load checkpoint data file
        """
        f_name = f'{self.job_name}_hdf5_chk_{step:04d}'
        f_path = os.path.join(self.output_path, f_name)
        self.chk = yt.load(f_path)
        self.ray = self.chk.ray([0, 0, 0], [self.xmax, 0, 0])
        self.x = self.ray['t'] * self.xmax

    def plot(self, var, y_log=True, x_log=True):
        """Plot given variable
        """
        fig, ax = plt.subplots()
        ax.plot(self.x, self.ray[var])

        if y_log:
            ax.set_yscale('log')
        if x_log:
            ax.set_xscale('log')


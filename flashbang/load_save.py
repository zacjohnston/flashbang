"""Functions for loading/saving/reducing flash data

General terminology
-------------------
    dat: Integrated time-series quantities found in [model].dat file
    chk: Checkpoint data found in 'chk' files
    profile: Radial profile data as extracted from chk files
    log: Data printed to terminal during model, stored in .log files

    extract: Extract and reduce data from raw output files
    save: Save pre-extracted data to file
    load: Load pre-extracted data from file
    get: Get reduced data by first attempting 'load', then fall back on 'extract'
"""
import os
import numpy as np
import pandas as pd
import configparser
import ast
import subprocess
import sys
import yt
import time

# flashbang
from . import paths
from .strings import printv
from . import quantities

# TODO:
#   - rename runs_prefix to model_prefix


# =======================================================================
#                      Config files
# =======================================================================
def load_config(name='default', verbose=True):
    """Load .ini config file and return as dict

    parameters
    ----------
    name: str
        label of config file to load
    verbose : bool
    """
    filepath = paths.config_filepath(name=name)
    printv(f'Loading config: {filepath}', verbose)
    if not os.path.exists(filepath):
        raise FileNotFoundError(f'Config file not found: {filepath}')

    ini = configparser.ConfigParser()
    ini.read(filepath)

    config = {}
    for section in ini.sections():
        config[section] = {}
        for option in ini.options(section):
            config[section][option] = ast.literal_eval(ini.get(section, option))

    return config


# =======================================================================
#                      Dat files
# =======================================================================
def get_dat(model, cols_dict, run='run', runs_path=None, runs_prefix='run_',
            verbose=True, save=True, reload=False):
    """Get reduced set of integrated quantities, as contained in [run].dat file

    Returns : pandas.DataFrame

    parameters
    ----------
    model : str
    cols_dict : {}
        dictionary with column names and indexes (Note: 1-indexed)
    run: str
    runs_path : str
    runs_prefix : str
    verbose : bool
    save : bool
    reload : bool
    """
    dat_table = None

    # attempt to load temp file
    if not reload:
        try:
            dat_table = load_dat_cache(model=model, run=run, runs_path=runs_path,
                                       runs_prefix=runs_prefix, verbose=verbose)
        except FileNotFoundError:
            pass

    # fall back on loading raw .dat
    if dat_table is None:
        dat_table = extract_dat(model, cols_dict=cols_dict, run=run, runs_path=runs_path,
                                runs_prefix=runs_prefix, verbose=verbose)
        if save:
            save_dat_cache(dat_table, model=model, run=run, runs_path=runs_path,
                           runs_prefix=runs_prefix, verbose=verbose)

    return dat_table


def extract_dat(model, cols_dict, run='run', runs_path=None,
                runs_prefix='run_', verbose=True):
    """Extract and reduce data from .dat file

    Returns : dict of 1D quantities

    parameters
    ----------
    model : str
    cols_dict : {}
        dictionary with column names and indexes (Note: 1-indexed)
    run: str
    runs_path : str
    runs_prefix : str
    verbose : bool
    """
    filepath = paths.dat_filepath(model=model, run=run, runs_path=runs_path,
                                  runs_prefix=runs_prefix)

    printv(f'Extracting dat: {filepath}', verbose=verbose)

    idxs = []
    keys = []
    for key, idx_1 in cols_dict.items():
        idxs += [idx_1 - 1]  # change to zero-indexed
        keys += [key]

    return pd.read_csv(filepath, usecols=idxs, names=keys, skiprows=1, header=None,
                       delim_whitespace=True, low_memory=False)


def save_dat_cache(dat, model, run='run', runs_path=None, runs_prefix='run_', verbose=True):
    """Save pre-extracted .dat quantities, for faster loading

    parameters
    ----------
    dat : pd.DataFrame
        data table as returned by extract_dat()
    model : str
    run : str
    runs_path : str
    runs_prefix : str
    verbose : bool
    """
    ensure_temp_dir_exists(model, runs_path=runs_path, runs_prefix=runs_prefix,
                           verbose=verbose)
    filepath = paths.dat_temp_filepath(model=model, run=run, runs_path=runs_path,
                                       runs_prefix=runs_prefix)

    printv(f'Saving dat cache: {filepath}', verbose)
    dat.to_feather(filepath)


def load_dat_cache(model, run='run', runs_path=None, runs_prefix='run_', verbose=True):
    """Load pre-extracted .dat quantities (see: save_dat_cache)

    parameters
    ----------
    model : str
    run : str
    runs_path : str
    runs_prefix : str
    verbose : bool
    """
    filepath = paths.dat_temp_filepath(model=model, run=run, runs_path=runs_path,
                                       runs_prefix=runs_prefix)
    printv(f'Loading dat cache: {filepath}', verbose)
    return load_feather(filepath)


def print_dat_colnames(model, run='run', runs_path=None, runs_prefix='run_'):
    """Print all column names from .dat file

    parameters
    ----------
    model : str
    run : str
    runs_path : str
    runs_prefix : str
    """
    filepath = paths.dat_filepath(run=run, model=model, runs_prefix=runs_prefix,
                                  runs_path=runs_path)
    with open(filepath, 'r') as f:
        colnames = f.readline().split()

    count = 1
    for word in colnames:
        if str(count) in word:
            print(f'\n{count}', end=' ')
            count += 1
        else:
            print(word, end=' ')
            
            
# ===============================================================
#                      Profiles
# ===============================================================
def get_profile(chk, model, run='run', output_dir='output',
                runs_path=None, runs_prefix='run_', o_path=None,
                params=('temp', 'dens', 'pres'), derived_params=('mass',),
                reload=False, save=True, verbose=True):
    """Get reduced radial profile, as contained in checkpoint file
    Loads pre-extracted profile if available, otherwise from raw file

    Returns : dictionary of 1D arrays

    parameters
    ----------
    chk : int
    model : str
    run : str
    output_dir : str
    runs_path : str
    runs_prefix : str
    o_path : str
    params : [str]
        profile parameters to extract and return from chk file
    derived_params : [str]
        secondary profile parameters, derived from primary parameters
    reload : bool
        force reload from chk file, else try to load pre-extracted profile
    save : bool
        save extracted profile to file for faster loading
    verbose : bool
    """
    profile = None

    # attempt to load temp file
    if not reload:
        try:
            profile = load_profile_cache(chk, model=model, run=run, runs_path=runs_path,
                                         runs_prefix=runs_prefix, verbose=verbose)
        except FileNotFoundError:
            pass

    # fall back on loading raw chk
    if profile is None:
        profile = extract_profile(chk, model=model, run=run, output_dir=output_dir,
                                  runs_path=runs_path, runs_prefix=runs_prefix,
                                  o_path=o_path, params=params, derived_params=derived_params)
        if save:
            save_profile_cache(profile, chk=chk, model=model, run=run, runs_path=runs_path,
                               runs_prefix=runs_prefix, verbose=verbose)

    return profile


def extract_profile(chk, model, run='run', output_dir='output',
                    runs_path=None, runs_prefix='run_', o_path=None,
                    params=('r', 'temp', 'dens', 'pres'),
                    derived_params=('mass',)):
    """Extract and reduce profile data from chk file

    Returns : pd.DataFrame

    parameters
    ----------
    chk : int
    model : str
    run : str
    output_dir : str
    runs_path : str
    runs_prefix : str
    o_path : str
    params : [str]
        profile parameters to extract and return from chk file
    derived_params : [str]
        secondary profile parameters, derived from primary parameters
    """
    profile = pd.DataFrame()
    chk_raw = load_chk(chk=chk, model=model, run=run, output_dir=output_dir,
                       runs_path=runs_path, runs_prefix=runs_prefix, o_path=o_path)
    chk_data = chk_raw.all_data()

    for var in params:
        profile[var.strip()] = np.array(chk_data[var])

    if 'mass' in derived_params:
        add_mass_profile(profile)

    return profile


def add_mass_profile(profile):
    """Calculate interior/enclosed mass profile, and adds to given table

    parameters
    ----------
    profile : pd.DataFrame
        table as returned by extract_profile()
    """
    if ('r' not in profile.columns) or ('dens' not in profile.columns):
        raise ValueError(f'Need radius and density columns (r, dens) to calculate mass')

    profile['mass'] = quantities.get_mass_interior(radius=np.array(profile['r']),
                                                   density=np.array(profile['dens']))


def save_profile_cache(profile, chk, model, run='run', runs_path=None,
                       runs_prefix='run_', verbose=True):
    """Save profile to file for faster loading

    parameters
    ----------
    profile : pd.DataFrame
            table of profile properties as returned by extract_profile()
    chk : int
    model : str
    run : str
    runs_path : str
    runs_prefix : str
    verbose : bool
    """
    ensure_temp_dir_exists(model, runs_path=runs_path, runs_prefix=runs_prefix,
                           verbose=verbose)
    filepath = paths.profile_filepath(chk=chk, model=model, run=run,
                                      runs_path=runs_path, runs_prefix=runs_prefix)

    printv(f'Saving profile cache: {filepath}', verbose)
    profile.to_feather(filepath)


def load_profile_cache(chk, model, run='run', runs_path=None,
                       runs_prefix='run_', verbose=True):
    """Load pre-extracted profile (see: save_profile_cache)

    parameters
    ----------
    chk : int
    model : str
    run : str
    runs_path : str
    runs_prefix : str
    verbose : bool
    """
    filepath = paths.profile_filepath(chk=chk, model=model, run=run,
                                      runs_path=runs_path, runs_prefix=runs_prefix)

    printv(f'Loading profile cache: {filepath}', verbose)
    return load_feather(filepath)


# ===============================================================
#                      Chk files
# ===============================================================
def find_chk(path, match_str='hdf5_chk_', n_digits=4):
    """Return list of checkpoint (chk) files available in given directory
        returns as nparray of checkpoint numbers

    parameters
    ----------
    path : str
        path to directory to look in
    match_str : str
        string to match for in filename, to identify chk files
    n_digits : int
        number of digits at end of filename corresponding to checkpoint ID
    """
    file_list = os.listdir(path)
    chks = []

    for file in file_list:
        if match_str in file:
            chks += [int(file[-n_digits:])]

    return np.sort(chks)


def load_chk(chk, model, run='run', output_dir='output',
             runs_path=None, runs_prefix='run_', o_path=None):
    """Load checkpoint file using yt

    parameters
    ----------
    chk : int
    model : str
    run : str
    output_dir : str
    runs_path : str
    runs_prefix : str
    o_path : str
    """
    filepath = paths.chk_filepath(chk=chk, model=model, run=run,
                                  output_dir=output_dir, runs_path=runs_path,
                                  runs_prefix=runs_prefix, o_path=o_path)

    if not os.path.exists(filepath):
        raise FileNotFoundError(f'checkpoint {chk:04d} file does not exist: {filepath}')

    return yt.load(filepath)


# ===============================================================
#                      Timesteps
# ===============================================================
def extract_timesteps(chk_list, model, params=('time', 'nstep'), run='run',
                      output_dir='output', runs_path=None, runs_prefix='run_',
                      o_path=None):
    """Extract timestep quantities from chk files

    Returns: pd.DataFrame()

    parameters
    ----------
    chk_list : [int]
    model : str
    params : [str]
    run : str
    output_dir : str
    runs_path : str
    runs_prefix : str
    o_path : str
    """
    t0 = time.time()
    arrays = dict.fromkeys(params)
    chk0 = load_chk(chk_list[0], model=model, run=run, output_dir=output_dir,
                    runs_path=runs_path, runs_prefix=runs_prefix, o_path=o_path)
    for par in params:
        par_type = type(chk0.parameters[par])
        arrays[par] = np.zeros_like(chk_list, dtype=par_type)

    for i, chk in enumerate(chk_list[1:]):
        chk_raw = load_chk(chk, model=model, run=run, output_dir=output_dir,
                           runs_path=runs_path, runs_prefix=runs_prefix, o_path=o_path)
        for par in params:
            arrays[par][i+1] = chk_raw.parameters[par]

    chk_table = pd.DataFrame()
    chk_table['chk'] = chk_list
    for par, arr in arrays.items():
        chk_table[par] = arr

    chk_table.set_index('chk', inplace=True)

    t1 = time.time()
    print('='*20, f'\nTotal time: {t1-t0:.3f} s\n')
    return chk_table


def save_timesteps_cache(chk_table, model, run='run', runs_path=None,
                         runs_prefix='run_', verbose=True):
    """Save pre-extracted chk timesteps to file

    parameters
    ----------
    chk_table : pd.DataFrame
        table of chk timesteps, as returned by extract_timesteps()
    model : str
    run : str
    runs_path : str
    runs_prefix : str
    verbose : bool
    """
    ensure_temp_dir_exists(model, runs_path=runs_path, runs_prefix=runs_prefix,
                           verbose=verbose)
    filepath = paths.timesteps_filepath(model, run=run, runs_path=runs_path,
                                        runs_prefix=runs_prefix)
    printv(f'Saving timesteps cache: {filepath}', verbose)
    chk_table.to_feather(filepath)


def load_timesteps_cache(model, run='run', runs_path=None,
                         runs_prefix='run_', verbose=True):
    """Load pre-extracted chk timesteps to file

    parameters
    ----------
    model : str
    run : str
    runs_path : str
    runs_prefix : str
    verbose : bool
    """
    filepath = paths.timesteps_filepath(model=model, run=run, runs_path=runs_path,
                                        runs_prefix=runs_prefix)

    printv(f'Loading timesteps cache: {filepath}', verbose)
    return load_feather(filepath)


# ===============================================================
#                      Log files
# ===============================================================
def get_bounce_time(model, run='run', runs_path=None, runs_prefix='run_',
                    match_str='Bounce', verbose=True):
    """Get bounce time (s) from .log file

    parameters
    ----------
    model : str
    run : str
    runs_path : str
    runs_prefix : str
    match_str : str
        String which immediately precedes the bounce time
    verbose : bool
    """
    filepath = paths.log_filepath(run=run, model=model, runs_path=runs_path,
                                  runs_prefix=runs_prefix)
    bounce_time = 0.0
    printv(f'Getting bounce time: {filepath}', verbose)

    with open(filepath, 'r') as f:
        for line in f:
            if match_str in line:
                terms = line.split()
                bounce_time = float(terms[1])
                printv(f'Bounce = {bounce_time:.4f} s', verbose)
                break

        if bounce_time == 0.0:
            printv('Bounce time not found! Returning 0.0 s', verbose)

    return bounce_time


# ===============================================================
#                      SNEC models
# ===============================================================
def reduce_snec_profile(profile_dict):
    """Reduce given profile dictionary into a 2D nparray
        Returns: profile_array, timesteps, mass_grid

    parameters
    ----------
    profile_dict : {}
        Dictionary containing profile data, as returned from load_snec_xg()
    """
    timesteps = np.array(list(profile_dict.keys()))
    n_time = len(timesteps)
    
    mass_grid = profile_dict[timesteps[0]][:, 0]
    n_mass = len(mass_grid)
    
    profile_array = np.zeros((n_time, n_mass))
    
    for i, key in enumerate(timesteps):
        profile_array[i, :] = profile_dict[key][:, 1]
    
    return profile_array, timesteps, mass_grid
    

def load_snec_xg(filepath, verbose=True):
    """Load mass tracers from SNEC output .xg file, returns as dict

    parameters
    ----------
    filepath : str
    verbose : bool
    """    
    printv(f'Loading: {filepath}', verbose)
    n_lines = fast_line_count(filepath)

    profile = {}
    with open(filepath, 'r') as rf:
        count = 0
        for line in rf:
            printv(f'\r{100 * count/n_lines:.1f}%', verbose, end='')
            cols = line.split()

            # Beginning of time data - make key for this time
            if 'Time' in line:
                timesteps = float(cols[-1])
                profile[timesteps] = []

            # In time data -- build x,y arrays
            elif len(cols) == 2:
                profile[timesteps].append(np.fromstring(line, sep=' '))

            # End of time data (blank line) -- make list into array
            else:
                profile[timesteps] = np.array(profile[timesteps])
            count += 1

    printv('\n', verbose)
    return profile


# ===============================================================
#              Misc. file things
# ===============================================================
def load_feather(filepath):
    """Load a .feather file with pandas

    parameters
    ----------
    filepath : str
    """
    if os.path.exists(filepath):
        return pd.read_feather(filepath)
    else:
        raise FileNotFoundError


def try_mkdir(path, skip=False, verbose=True):
    """Try to make given directory

    parameters
    ----------
    path: str
    skip : bool
        do nothing if directory already exists
        if skip=false, will ask to overwrite an existing directory
    verbose : bool
    """
    printv(f'Creating directory  {path}', verbose)
    if os.path.exists(path):
        if skip:
            printv('Directory already exists - skipping', verbose)
        else:
            print('Directory exists')
            cont = input('Overwrite (DESTROY)? (y/[n]): ')

            if cont == 'y' or cont == 'Y':
                subprocess.run(['rm', '-r', path])
                subprocess.run(['mkdir', path])
            elif cont == 'n' or cont == 'N':
                sys.exit()
    else:
        subprocess.run(['mkdir', '-p', path], check=True)


def ensure_temp_dir_exists(model, runs_path=None, runs_prefix='run_', verbose=True):
    """Ensure temp directory exists (create if not)

    parameters
    ----------
    model : str
    runs_path : str
    runs_prefix : str
    verbose : bool
    """
    temp_path = paths.temp_path(model, runs_path=runs_path, runs_prefix=runs_prefix)
    try_mkdir(temp_path, skip=True, verbose=verbose)


def fast_line_count(filepath):
    """Efficiently find the number of lines in a file

    parameters
    ----------
    filepath: str
    """
    lines = 0
    buf_size = 1024 * 1024

    with open(filepath, 'rb') as f:
        read_f = f.raw.read
        buf = read_f(buf_size)

        while buf:
            lines += buf.count(b'\n')
            buf = read_f(buf_size)

    return lines

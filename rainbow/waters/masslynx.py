import os
import re
import struct
import numpy as np
from rainbow.datafile import DataFile


"""
SPECTRUM PARSING METHODS

"""
def parse_spectrum(path, prec=0):
    """
    """
    datafiles = []

    func_paths = sorted([os.path.join(path, fn) for fn in os.listdir(path) 
                         if re.match('^_FUNC[0-9]{3}.DAT$', fn)])
    func_i = 0
    inf = parse_funcinf(os.path.join(path, '_FUNCTNS.INF'))
    polarities = []
    calibs = []
    if '_extern.inf' in os.listdir(path):

        f = open(os.path.join(path, '_HEADER.TXT'), 'r')
        lines = f.read().splitlines()
        for line in lines:
            if line.startswith("$$ Cal Function"):
                calib = [float(s) for s in line.split(': ')[1].split(',')[:-1]]
                # assert(len(calib) == 5)
                calibs.append(calib)
        f.close()

        f = open(os.path.join(path, '_extern.inf'), 'rb')
        lines = f.read().splitlines()
        nums = []
        for i in range(len(lines)):
            if lines[i].startswith(b"Instrument Parameters"):
                assert(len(lines[i].split(b" ")) == 5)
                nums.append(int(lines[i].split(b" ")[4][:-1]))
                assert(lines[i+1].startswith(b"Polarity") or lines[i+2].startswith(b"Polarity"))
                if lines[i+1].startswith(b"Polarity"):
                    assert(len(lines[i+1].split(b'\t\t\t')) == 2)
                    polarity = chr(lines[i+1].split(b'\t\t\t')[1][-1])
                else:
                    assert(len(lines[i+2].split(b'\t')) == 2)
                    polarity = chr(lines[i+2].split(b'\t')[1][-1])
                polarities.append(polarity)
        assert(nums[0] == 1 and nums[-1] == len(nums))
        assert(nums == sorted(nums))
        f.close()
        
    while func_i < len(func_paths):
        polarity = None
        calib = None
        if func_i < len(polarities):
            polarity = polarities[func_i]
            if func_i < len(calibs):
                calib = calibs[func_i]
        datafiles.append(parse_func(func_paths[func_i], inf, prec, polarity, calib))
        func_i += 1

    return datafiles

def parse_func(path, inf, prec=0, polarity=None, calib=None):
    """ 
    """
    idx_path = path[:-3] + 'IDX'
    times, ylabels_per_time, data_len = parse_funcidx(idx_path)
    if data_len not in {2, 6, 8}:
        print(path, data_len, times)
    assert(data_len == 6 or data_len == 8 or data_len == 2)

    if data_len == 2:
        ylabels, data = parse_funcdat2(path, ylabels_per_time, inf, prec, calib)
    elif data_len == 6:
        ylabels, data = parse_funcdat6(path, ylabels_per_time, prec, calib)
    elif data_len == 8:
        ylabels, data = parse_funcdat8(path, ylabels_per_time, prec, calib) 
    
    detector = 'MS' if calib else 'UV'

    metadata = {}
    if polarity:
        metadata['polarity'] = polarity

    return DataFile(path, detector, times, ylabels, data, metadata)

def parse_funcinf(path):
    """ 
    """
    f = open(path, 'rb')
    while True:
        try:
            packed = struct.unpack('<H', f.read(2))[0]
            func = packed & 0x1F 
            form = packed >> 10
            f.read(16)
            num_scans = struct.unpack('<I', f.read(4))[0]
            f.read(10)
            f.read(32 * 4)
            q1 = np.ndarray(32, '<f', f.read(32 * 4))
            q3 = np.ndarray(32, '<f', f.read(34 * 4))
        except:
            break 
    assert(f.tell() == os.path.getsize(path))
    f.close()
    return (num_scans, func, q1, q3)

def parse_funcidx(path):
    """ 
    """
    f = open(path, 'rb')
    size = os.path.getsize(path)
    num_times = size // 22 
    assert(os.path.getsize(path) // 22 == os.path.getsize(path) / 22)
    times = np.empty(num_times, dtype=np.float32)
    ylabels_per_time = np.empty(num_times, dtype=np.uint32)
    int_unpack = struct.Struct('<I').unpack
    for i in range(num_times):
        offset = int_unpack(f.read(4))[0]
        info = struct.unpack('<I', f.read(4))[0]
        ylabels_per_time[i] = info & 0x3FFFFF
        if ylabels_per_time[i] != 0:
            last_offset = offset
            last_index = i
        calibrated_flag = (info & 0x40000000) >> 30
        assert(calibrated_flag == 0)
        f.read(4) # tic
        times[i] = struct.unpack('<f', f.read(4))[0]
        f.read(6)
    assert(f.tell() == os.path.getsize(f.name))
    f.close() 
    data_len = (os.path.getsize(path[:-3] + 'DAT') - last_offset) // ylabels_per_time[last_index]

    return times, ylabels_per_time, data_len

def parse_funcdat2(path, ylabels_per_time, inf, prec=0, calib=None):
    num_times, func, q1, q3 = inf
    num_datapairs = np.sum(ylabels_per_time)
    assert(np.all(ylabels_per_time == ylabels_per_time[0]))
    assert(os.path.getsize(path) == num_datapairs * 2)
    with open(path, 'rb') as f:
        raw_bytes = f.read()
    raw_values = np.ndarray(num_datapairs, '<H', raw_bytes)
    val_base = raw_values >> 3
    val_pow = raw_values & 0x7
    values = np.multiply(val_base, 4 ** val_pow, dtype=np.uint32)
    assert(func == 1)
    ylabels = q1[:ylabels_per_time[0]]
    data = np.empty((ylabels_per_time.size, ylabels_per_time[0]), dtype=np.uint32)
    index = 0
    for i in range(ylabels_per_time.size):
        for j in range(ylabels_per_time[0]):
            data[i][j] = values[index]
            index += 1

    return ylabels, data

def parse_funcdat6(path, ylabels_per_time, prec=0, calib=None):
    """
    """
    num_times = ylabels_per_time.size
    num_datapairs = np.sum(ylabels_per_time)
    assert(os.path.getsize(path) == num_datapairs * 6)

    # Optimized reading of 6-byte segments into `raw_values`. 
    with open(path, 'rb') as f:
        raw_bytes = f.read()
    leastsig = np.ndarray(num_datapairs, '<I', raw_bytes, 0, 6)
    mostsig = np.ndarray(num_datapairs, '<H', raw_bytes, 4, 6)
    raw_values = leastsig | (mostsig.astype(np.int64) << 32)
    del leastsig, mostsig, raw_bytes

    # The data is stored as key-value pairs. 
    # For example, in MS data these are mz-intensity pairs. 
    # Calculate the `keys` from each 6-byte segment. 
    key_bases = (raw_values & 0xFFFFFE000000) >> 25
    key_powers = (raw_values & 0x1F00000) >> 20
    key_powers -= 23
    keys = key_bases * (2.0 ** key_powers)
    del key_bases, key_powers

    # If it is MS data, calibrate the masses. 
    if calib:
        keys = calibrate(keys, calib)
    
    # Then round the keys to the nearest whole number. 
    keys = np.round(keys, prec)

    # Calculate the `values` from each 6-byte segment.
    val_bases = (raw_values & 0xFFFF).astype(np.int16)
    val_powers = (raw_values & 0xF0000) >> 16
    values = val_bases * (4 ** val_powers)
    del val_bases, val_powers, raw_values

    # Make the array of `ylabels` containing keys. 
    ylabels = np.unique(keys)
    ylabels.sort()

    # Fill the `data` array containing values. 
    # Optimized using numpy vectorization.
    key_indices = np.searchsorted(ylabels, keys)
    data = np.zeros((num_times, ylabels.size), dtype=np.int64)
    cur_index = 0
    for i in range(num_times):
        stop_index = cur_index + ylabels_per_time[i]
        np.add.at(
            data[i], 
            key_indices[cur_index:stop_index], 
            values[cur_index:stop_index])
        cur_index = stop_index
    del key_indices, keys, values, ylabels_per_time

    return ylabels, data

def parse_funcdat8(path, ylabels_per_time, prec=0, calib=None):
    """
    """
    num_times = ylabels_per_time.size
    num_datapairs = np.sum(ylabels_per_time)
    assert(os.path.getsize(path) == num_datapairs * 8)

    # Optimized reading of 8-byte segments into `raw_values`. 
    with open(path, 'rb') as f:
        raw_bytes = f.read()
    raw_values = np.ndarray(num_datapairs, '<Q', raw_bytes, 0, 8)

    # The data is stored as key-value pairs. 
    # For example, in MS data these are mz-intensity pairs. 
    # Split each segment into `key_bits` and `val_bits`.
    key_bits = raw_values >> 28 
    val_bits = raw_values & 0xFFFFFFF
    del raw_values, raw_bytes

    # Split `key_bits` into integer and fractional components.
    num_keyint_bits = key_bits >> 31  
    keyint_masks = pow(2, num_keyint_bits) - 1
    num_keyfrac_bits = 31 - num_keyint_bits 
    keyfrac_masks = pow(2, num_keyfrac_bits) - 1
    keyints = (key_bits >> num_keyfrac_bits) & keyint_masks 
    keyfracs = calc_frac(key_bits & keyfrac_masks, num_keyfrac_bits)
    del num_keyint_bits, num_keyfrac_bits, key_bits 
    del keyint_masks, keyfrac_masks

    # Get the `keys` by adding the components. 
    # If it is MS data, calibrate the masses. 
    keys = keyints + keyfracs
    if calib:
        keys = calibrate(keys, calib)
    del keyints, keyfracs 

    # Round the keys to the nearest whole number. 
    keys = np.round(keys, prec)

    # Find the integers that need to be scaled via left shift. 
    # This is based on the number of bits allocated for each integer.
    num_valint_bits = val_bits >> 22
    num_shifted = np.zeros(num_datapairs, np.uint8)
    shift_cond = num_valint_bits > 21 
    num_shifted[shift_cond] = num_valint_bits[shift_cond] - 21 
    num_valint_bits[shift_cond] = 21 
    del shift_cond

    # Split `val_bits` into integer and fractional components.
    valint_masks = pow(2, num_valint_bits) - 1
    num_valfrac_bits = 21 - num_valint_bits 
    valfrac_masks = pow(2, num_valfrac_bits) - 1
    valints = ((val_bits >> num_valfrac_bits) & valint_masks) << num_shifted
    valfracs = calc_frac(val_bits & valfrac_masks, num_valfrac_bits)
    del num_shifted, num_valint_bits, num_valfrac_bits
    del valint_masks, valfrac_masks

    # Get the `values` by adding the components. 
    values = valints + valfracs
    del valints, valfracs
   
    # Make the array of `ylabels` containing keys. 
    ylabels = np.unique(keys)
    ylabels.sort()

    # Fill the `data` array containing values. 
    # Optimized using numpy vectorization.
    key_indices = np.searchsorted(ylabels, keys)
    data = np.zeros((num_times, ylabels.size), dtype=np.int64)
    cur_index = 0
    for i in range(num_times):
        stop_index = cur_index + ylabels_per_time[i]
        np.add.at(
            data[i], 
            key_indices[cur_index:stop_index], 
            values[cur_index:stop_index])
        cur_index = stop_index
    del key_indices, keys, values, ylabels_per_time

    return ylabels, data

def calibrate(masses, calib_nums):
    """ 
    """
    calib_masses = np.zeros(masses.size, dtype=np.float32)
    var = np.ones(masses.size, dtype=np.float32)
    for coeff in calib_nums:
        calib_masses += coeff * var
        var *= masses
    del var 
    return calib_masses

def calc_frac(keyfrac_bits, num_bits):
    """ 
    """
    exponent = np.uint64(0x3FF << 52) 
    num_shifted = 52 - num_bits
    base = keyfrac_bits << num_shifted
    fracs = (exponent | base).view(np.float64)
    fracs -= 1.0
    del num_shifted, base
    return fracs


"""
ANALOG PARSING METHODS

"""
def parse_analog(path):
    """
    """
    datafiles = []

    dir_contents = os.listdir(path)
    if not '_CHROMS.INF' in dir_contents:
        return datafiles 

    analog_info = parse_chroinf(os.path.join(path, '_CHROMS.INF'))
    analog_paths = [fn for fn in os.listdir(path) if fn.startswith('_CHRO') and fn.endswith('.DAT')]
    assert(len(analog_info) == len(analog_paths))  
    for i in range(len(analog_info)):
        fn = os.path.join(path, f"_CHRO{i+1:0>3}.DAT")
        datafile = parse_chrodat(fn, *analog_info[i])
        if datafile:
            datafiles.append(datafile)
    return datafiles

def parse_chroinf(path):
    """
    """
    f = open(path, 'r')
    f.seek(0x84)

    analog_info = []
    end = os.path.getsize(path)
    while f.tell() < end:
        line = re.sub('[\0-\x04]|\$CC\$|\([0-9]*\)', '', f.read(0x55)).strip()
        line_split = line.split(',')
        assert(len(line_split) == 6 or len(line_split) == 1)
        info = []
        info.append(line_split[0])
        if len(line_split) == 6:
            info.append(line_split[5])
        analog_info.append(info)
    f.close()
    return analog_info

def parse_chrodat(path, name, units=None):
    """
    """
    data_start = 0x80
    num_times = (os.path.getsize(path) - data_start) // 8
    assert(data_start + num_times * 8 == os.path.getsize(path))

    with open(path, 'rb') as f:
        raw_bytes = f.read()
   
    if len(raw_bytes) <= 0x80:
        return None

    times_immut = np.ndarray(num_times, '<f', raw_bytes, data_start, 8)
    vals_immut = np.ndarray(num_times, '<f', raw_bytes, data_start+4, 8)
    times = times_immut.copy()
    vals = vals_immut.copy().reshape(-1, 1)
    del times_immut, vals_immut, raw_bytes

    detector = None
    if "CAD" in name:
        detector = 'CAD'
    elif "ELSD" in name:
        detector = 'ELSD'
    elif "nm@" in name:
        detector = 'UV'

    ylabels = np.array([''])
    metadata = {
        'signal': name,
    }
    if units: 
        metadata['unit'] = units 

    return DataFile(path, detector, times, ylabels, vals, metadata)


""" 
METADATA PARSING METHOD

"""

def parse_metadata(path):
    """
    Parses metadata from a Waters .raw directory.

    Specifically, the date and vial position are extracted from _HEADER.txt.

    Args:
        path (str): Path to the directory. 
    
    Returns:
        Dictionary containing directory metadata. 

    """
    metadata = {}
    metadata['vendor'] = "Waters"

    f = open(os.path.join(path, '_HEADER.TXT'), 'r')
    lines = f.read().splitlines()
    f.close()
    for line in lines:
        if line.startswith("$$ Acquired Date"):
            value = line.split(': ')[1]
            if not value.isspace():
                metadata['date'] = value + " "
        elif line.startswith("$$ Acquired Time"):
            # assert('date' in metadata)
            value = line.split(': ')[1]
            if not value.isspace():
                metadata['date'] += value
        if line.startswith("$$ Bottle Number"):
            value = line.split(': ')[1]
            if not value.isspace():
                metadata['vialpos'] = value
    return metadata 
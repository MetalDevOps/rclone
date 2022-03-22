import json
import shutil
import subprocess
import time
import warnings
from glob import glob
from pathlib import Path

from loguru import logger
from tqdm import tqdm


class MissingDestination(Exception):
    pass


class CheckRclone:

    def __init__(self, rclone):
        self.rclone = rclone

    def __call__(self, rclone):
        if rclone:
            return rclone
        if not rclone:
            pyrclonec = f'{Path.home()}/.pyrclonec'
            if Path(pyrclonec).exists():
                with open(pyrclonec) as f:
                    rclone = f.read().rstrip()
            else:
                logger.warning(
                    'Could not find rclone in your PATH. Enter it manually and the program will remember it.'
                )
                rclone = input('Path to rclone binary: ')
                if not Path(rclone).exists():
                    logger.error('The rclone path you entered does not exist.')
                    raise FileNotFoundError
                else:
                    with open(pyrclonec, 'w') as f:
                        f.write(rclone)
            return rclone


class Rclone(CheckRclone):

    def __init__(self):
        self.rclone = super().__call__(shutil.which('rclone'))

    def size_units(self, s, mult):
        if 'KiB' in s:
            s = round(float(s.split(' KiB')[0]) * 1024 / mult, 2)
        elif 'MiB' in s:
            s = round(float(s.split(' MiB')[0]) * 1.049e+6 / mult, 2)
        elif 'GiB' in s:
            s = round(float(s.split(' GiB')[0]) * 1.074e+9 / mult, 2)
        return s

    def stream_process(self, p, local_path, unit='MB'):
        if unit == 'MB':
            mult = 1e+6
        else:
            mult = 1

        if Path(local_path).is_dir():
            files = glob(f'{local_path}/**/*', recursive=True)

            size = 0
            for x in files:
                try:
                    size += Path(x).stat().st_size
                except FileNotFoundError:
                    continue

            size = round(size) / mult

        else:
            size = round(Path(local_path).stat().st_size / mult, 2)

        stream = p.poll() is None
        warnings.filterwarnings('ignore', message='clamping frac to range')
        with tqdm(total=size, unit=unit) as pbar:
            prog = 0
            for line in p.stdout:
                s = line.decode()
                if 'Transferred' in s and 'ETA' in s:
                    s = s.split('Transferred:')[1].split(
                        '\t')[1].lstrip().split(' / ')[0]
                    s = self.size_units(s, mult)
                    if isinstance(s, float):
                        pbar.update(s - prog)
                        prog = s
                elif 'Total size:' in s:
                    if prog == 0:
                        pbar.update(size)
                    pbar.write(s)
                    globals()['total_size'] = int(
                        s.split('(')[1].split(' ')[0])
                elif 'error' in s:
                    pbar.write(s)

    def process(self, subcommand, from_, to='', progress=True, _execute=False):
        if subcommand in ['ls', 'lsjson'] or _execute:
            progress = False
            P = ''
        else:
            P = '-P'
        if subcommand in ['copy', 'move'] and from_ and not to:
            raise MissingDestination(
                'The command requires passing a destination.')

        if subcommand == 'ls':
            subcommand = 'lsf'

        p = subprocess.Popen(f'{self.rclone} {subcommand} {from_} {to} {P}',
                             shell=True,
                             stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT)
        if progress:
            while self.stream_process(p, from_):
                time.sleep(0.1)

        if subcommand == 'size':
            return total_size

        if subcommand == 'lsjson':
            return json.loads(p.communicate()[0].decode())
        elif subcommand == 'ls':
            return p.communicate()[0].decode().rstrip().split('\n')

        elif _execute:
            return p.communicate()[0].decode().rstrip().replace('\t', ' ')

    def execute(self, command):
        return self.process(subcommand=command,
                            from_='',
                            to='',
                            progress=False,
                            _execute=True)

    def delete(*args, **kwargs):
        raise NotImplementedError(
            'delete is a protected command! Use `execute("...")` instead.')

    def __getattr__(self, attr):

        def wrapper(*args, **kwargs):
            return self.process(attr, *args)

        return wrapper
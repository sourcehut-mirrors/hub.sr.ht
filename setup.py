#!/usr/bin/env python3
from setuptools import setup
import subprocess
import os
import sys
import importlib.resources

with importlib.resources.path('srht', 'Makefile') as f:
    srht_path = f.parent.as_posix()

make = os.environ.get("MAKE", "make")
subp = subprocess.run([make, "SRHT_PATH=" + srht_path])
if subp.returncode != 0:
    sys.exit(subp.returncode)

setup()

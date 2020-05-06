#!/usr/bin/env python3
from distutils.core import setup
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

ver = os.environ.get("PKGVER") or subprocess.run(['git', 'describe', '--tags'],
      stdout=subprocess.PIPE).stdout.decode().strip()

setup(
  name = 'hubsrht',
  packages = [
      'hubsrht',
      'hubsrht.alembic',
      'hubsrht.alembic.versions',
      'hubsrht.blueprints',
      'hubsrht.types',
  ],
  version = ver,
  description = 'hub.sr.ht website',
  author = 'Drew DeVault',
  author_email = 'sir@cmpwn.com',
  url = 'https://git.sr.ht/~sircmpwn/hub.sr.ht',
  install_requires = ['srht'],
  license = 'AGPL-3.0',
  package_data={
      'hubsrht': [
          'templates/*.html',
          'static/*',
          'static/icons/*',
      ]
  },
  scripts = [
      'hubsrht-initdb',
      'hubsrht-migrate',
  ]
)

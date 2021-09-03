import os
import sys
import pytest
import subprocess

@pytest.fixture(scope='session')
def pyinstaller_bundles(tmpdir_factory):
    """Build pyinstaller bundles from test distributions."""
    test_distributions = "simple",

    pwd = os.path.abspath(os.curdir)
    this_dir = os.path.dirname(__file__)
    build_dir = tmpdir_factory.mktemp('build')
    dist_dir = tmpdir_factory.mktemp('dist')
    for dist in test_distributions:
        os.chdir(os.path.join(this_dir, 'testdata', dist))
        subprocess.check_call([sys.executable, 'setup.py',
                               'bdist_pyinstaller', '-b', str(build_dir), '-d', str(dist_dir)])

    os.chdir(pwd)
    return sorted(str(fname) for fname in dist_dir.listdir())
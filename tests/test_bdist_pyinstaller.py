import os
import sys
import subprocess
from itertools import chain

def test_bundles(tmpdir_factory):
    test_distributions = (("simple", "0.1", ("hello",)),)
    pwd = os.path.abspath(os.curdir)
    this_dir = os.path.dirname(__file__)
    build_dir = tmpdir_factory.mktemp('build')
    dist_dir = tmpdir_factory.mktemp('dist')
    for (dist_name, dist_version, entrypoints) in test_distributions:
        os.chdir(os.path.join(this_dir, 'testdata', dist_name))

        subprocess.check_call([sys.executable, 'setup.py',
                               'bdist_pyinstaller', '-b', str(build_dir), '-d', str(dist_dir)])

        # Verify if the bundle is created
        assert sorted(os.path.basename(str(fname))
                      for fname in dist_dir.listdir()) == ["{}-{}".format(dist_name, dist_version), ]

        subprocess.check_call([os.path.join(dist_dir, "{}-{}".format(dist_name, dist_version)), 'setup_aliases'])

        # Ensure that the bundle can create the aliases
        assert sorted(os.path.basename(str(fname))
                      for fname in dist_dir.listdir()) == list(chain(entrypoints, ["{}-{}".format(dist_name, dist_version), "{}-python".format(dist_name)]))

        # Execute the first entrypoint
        subprocess.check_call([os.path.join(dist_dir, entrypoints[0])])
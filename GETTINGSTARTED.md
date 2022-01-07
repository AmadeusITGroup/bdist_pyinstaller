### Installation
bdist_pyinstaller is a custom distutils command which is automatically exposed to the current python environment once it is installed with pip.
It can be installed from a repository compatible with PYPI or from a git.

An example installation procedure from PYPI:

```sh
# You need verify that the pip is pointing at the index where the package in question is present if you are using the PYPI mirror and/or a private repo:
cat ~/.pip/pip.conf
[global]
index-url = https://<your pypi mirror>/simple

# Install the package
python -m pip install bdist_pyinstaller

```

An example installation procedure from git:

```sh
python -m pip install git+https://github.com/AmadeusITGroup/bdist_pyinstaller.git

```

### Usage

*Note*: Programs written in python usually require at least the python runtime. Most often than not there is a number of extra dependencies in the form of python packages which have to be installed alongside. Furthermore, there is a high chance the program in question or any of its dependencies relies on shared objects(dll/so) which are installed on the OS level. There is also an element of compatibility level which needs to be met between the OS and the python program and/or its dependencies. In some cases we have to chose between our environment being up-to-date and being able to run our program which may rely on old version of some of the libraries. In some cases it may be severely impacting the security in other cases we may break some vital services which require different version of the afore mentioned libraries.
That makes the whole excercise even more interesting ;)

The idea is to create an executable, a self-extracting portable bundles from python programs to ease the deployment and to make it more reliable.

It can be done in a number of ways. However, depending on the structure of the package in question the complexity may vary from a trivial command with [pyinstaller](https://pyinstaller.readthedocs.io/en/latest/usage.html) to something very elaborate when one needs to write a custom spec file to guide pyinstaller through all the resources it should consider when bundling the script.

This custom command is not aiming at replacing pyinstaller. It still uses it behind the scenes. It should be treated as a helper mechanism to deal with bundling python programs which are already well configured in terms of their console entry points. It is clever enough to digest the standard package metadata, so there is no need to explicitly write the spec files in most of the cases. 

What is also worth noting is that bdist_pyinstaller composes the single dispatch script based on the exec name which in the case of multiple console entrypoints reduces the time needed to build the bundle. Furthermore, it simplifies the deployment as there is only one artifact generated. The bundle produced this way is used to install/expand itself into a series of hardlinks pointing at the original installer image. Depending on the link name the dispatcher it triggers different logic as per console entry point definition in the setup.py/cfg or toml metadata.

The dispatcher comes with some extra abilities: profiling and post-mortem debugging. To use them, one needs to set the environment variables: PROFILE and DEBUG accordingly. 
The profiling is done with the built-in *cProfile* and the reports(binary and txt) is generated with *pstats* as <package_name>_profile.bin and <package_name>_profile_stats.txt which are saved in the current folder.
Post-mortem debugger is activated when the main entrypoint of the program throws the exception.


#### Package configuration
Let's assume we have the following entrypoints defined in the setup.py:

```python
setup(
  ...
 entry_points={
        'console_scripts': [
            'bms=bmslib.cli:main',
            'bms-python=bmslib.cli:do_bms_python',

            # Embed the python major version in the executable name
            'bms-python%s=bmslib.cli:do_bms_python' % sys.version_info[0],

            'bms-gdb-wrapper=bmslib.gdb_wrapper:main',
        ],
        ...
  }
)
```

It is also possible to place it in setup.cfg:

```ini
...
[options.entry_points]
console_scripts =
    bms = bmslib.cli:main
    bms-python = bmslib.cli:do_bms_python
    bms-gdb-wrapper = bmslib.gdb_wrapper:main
...
```

#### Building and installing single-binary deliverables
```sh
# Assuming bdist_pyinstaller package is pre-installed, we can execute it as follows:
python setup.py bdist_pyinstaller

# The bundle can be found under pyinstaller_dist and its name is composed <package_name>-<pacakge-version>
ls pyinstaller_dist/
# amadeus-bms-2.5.4.216

# Setup links according the package matadata: entry_points => console_scripts
pyinstaller_dist/amadeus-bms-2.5.4.216 setup_aliases

# The hardlinks are crated next the installer bundle
ls pyinstaller_dist/
amadeus-bms-2.5.4.216  amadeus-bms-python  bms	bms-gdb-wrapper  bms-python  bms-python3

# From now on each of the hardlinks act accordingly to the spec in the package setup.
# The only difference is that they are self-contained :-)

```

Apart from the links mapped from the entries defined in the console_scripts there is <package_name>_python<major_version> created. It allows to run python interpretter interactively in the same runtime as the actual programs. The aim is to help in debugging and/or prototyping.

*Note*: The resulting binaries come with all their dependencies - including the python runtime and all the packages and libraries they need. The only requirement is that the OS that they are running on is shipped with glibc compliant with the binaries and there are some basic tools like tar, gz etc installed on it which is usually fulfilled on most of the linux distributions.

#### Special considerations

In some cases the bundle may be significant in size and the bootstrap process adds non-trivial overhead(typically ~1s, but it may vary). In this case one may consider using a one-directory bundle, which allows to skip this stage, which in many cases leads to a consistently better performance when comparing to a classic deployment. This happens due to a simplified package lookup as well as the fact the packages are frozen in the archive and processed in memory rather than reading them from disk.

Buidling a one-dir deliverable:

```sh
python setup.py bdist_pyinstaller --one_dir
```

All the extra non-python resources from all packages *within* the scope of the project are automatically bundled in. However, the same does not apply to dependencies, which are only included on python level.
When one needs to include the resources from the dependencies, it is possbile by passing a list of modules to be considered.

Including resources from dependencies:

```sh
python setup.py bdist_pyinstaller --extra-modules=module_one,module.two,etc
```

The resources would be accessible in the same way as if the package was installed by pip:
```python
import os
import module_one
resource_location = os.path.join(os.path.dirname(module_one.__file__), "resource.txt")
```

### Development

#### Pre-requisites
bdist_pyinstaller is written in python, therefore it is possible to work on it in multiple ways. However, we encourage new contributors to follow our recommendations to reduce the friction and the ramp-up time.

*Python version*:
  * 3.x is recommended(the CI is currently using 3.7)

*Build context*:
  * any Python 3.x installation should work here provided pyinstaller can be installed and works in such environment

*IDE*:
  * using a particular IDE is not enforced, but VSCode is a safe bet as there is a great community behind it and many people are familiar with it


#### Source code checkout
  * create your own fork if you intend to contribute the changes back
  * if you develop inside the container(optional), ensure the checkout is done in the workspace folder which can be easily shared between the host and the container e.g. mkdir ~/workspace && chmod 777 ~/workspace
  * start the container(optional) with podman or docker with the *workspace mounted*, so the build artifacts are detached from the lifecycle of the container i.e. they will still be accessible when you scratch the container or when it crashes:

```sh
git clone https://https://github.com/<user>/bdist_pyinstaller.git 
cd bdist_pyinstaller

# At this point we're ready to open the workspace in VSCode. The checkout can also be done entirely from VSCode or other IDE.

```

### Building from source
```sh
python setup.py build bdist_wheel
```
The deliverable is created inside **dist** folder: 
  * it is a python wheel which can be used to install the bdist_pyinstaller as a package and use it in other python programs
  

### Testing
All the tests in the project are done with [pytest](https://docs.pytest.org/en/stable/) and they are integrated into setup.py.

Examples:

```sh
python setup.py test

# or

pytest
pytest -vv 
pytest -vv -s -k test_bundles
...
```

Furthermore, when working in VSCode it is possible to benefit from the Test Explorer view(the extension is already added in the recommendations) and/or one of the pre-configured debug targets.


#### Error handling
Unrecoverable errors should not be masked, they should bubble up. However, if there is a chance to adapt to the environment without significantly changing the rules, it can be done. The key here is the transparency and simplicity. 
It is better to fail and do it as soon as it's clear that's the only option than keeping the process hanging for a long time.

####  Quality and unit test coverage
In order to prevent a significant number of regressions, the code coverage should be around 70% or higher. 

In order to reach the long term objective, we should follow a number of guidelines when writing new code:
  * New code must be covered at 70% or better
  * Bug fixes should be ideally reproduced by a test which links with the original issue.
  * All unit tests should pass prior to the code review i.e. test everything locally before creating the PR(the CI will ensure the tests are executed as well)

#### Documentation
The existing code base is far from perfect in terms of documentation. However, we should aim at gradual improvements:
  * Meaningful naming patterns and conventions
  * All new features must be documented at least on the code level (brief description of the more complex parts at least)
  * All new packages, modules, classes and functions should be described with [docstrings](https://www.python.org/dev/peps/pep-0257/)
  * Better still, it would be nice to introduce the user docs in rst format which can be used to generate the manual in a user friendly manner(html, pdf ..)

# coding: utf-8
# Copyright 2021 Amadeus IT Group
#
#    Licensed under the Apache License, Version 2.0 (the "License");
#    you may not use this file except in compliance with the License.
#    You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS,
#    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    See the License for the specific language governing permissions and
#    limitations under the License.
import sys
import traceback
import os
import re
from itertools import chain
from distutils.core import Command
from copy import copy
import subprocess
import importlib
import tarfile


def get_pip_index_url():
    """
    Reads the pip configuration and returns its global index.
    """
    ret_val = None
    if sys.version_info >= (3, 5):
        try:
            completed_process = subprocess.run(
                " ".join(
                    [sys.executable, "-m", "pip", "config", "get", "global.index-url"]
                ),
                shell=True,
                capture_output=True,
                check=True,
            )
            ret_val = completed_process.stdout.decode().strip()
        except subprocess.CalledProcessError:
            pass
    else:
        raise NotImplementedError(
            "This extension is meant to be used with Python 3.5 or newer"
        )
    return ret_val


def fqn_name(p, f):
    """
    Composes a fully qualified name of the function using both: its package as well as the name itself.
    """
    return "{}.{}".format(p, f).replace(".", "_")


class PyInstalerCmd(Command):
    """
    Extends build command to build a single pyinstaller binary with the dispatcher based on the exec image name.
    """

    description = (
        "create pyinstaller bundle using the console entry points as dispatch points"
    )
    user_options = [
        (
            "bdist-dir=",
            "b",
            "temporary directory for creating the distribution",
            "(default: build)",
        ),
        (
            "dist-dir=",
            "d",
            "directory to put final built distributions in",
            "(default: pyinstaller_dist)",
        ),
        (
            "extra-args=",
            None,
            "extra arguments to be passed to pyinstaller",
            "(default: None)",
        ),
        ("one-dir", None, "one directory mode", "(default: false)"),
    ]
    boolean_options = [
        "one-dir",
    ]

    def initialize_options(self):
        self.bdist_dir = None
        self.dist_dir = None
        self.extra_args = None
        self.one_dir = False

    def finalize_options(self):
        if self.bdist_dir is None:
            bdist_base = self.get_finalized_command("bdist").bdist_base
            self.bdist_dir = os.path.join(bdist_base, "bdist_pyinstaller")

    def run(self):
        if not self.distribution.packages:
            raise ValueError(
                "The list of modules seems to be empty(no packages detected). Please verify your configuration!"
            )

        index_url = get_pip_index_url()
        index_url_args = []
        if index_url:
            index_url_args.extend(["--index-url", index_url])

        # Note: that's primarily for pulling in the deps
        subprocess.check_call(
            " ".join(
                chain([sys.executable, "-m", "pip", "install", "."], index_url_args)
            ),
            shell=True,
        )

        subprocess.check_call(
            " ".join(
                chain(
                    (
                        sys.executable,
                        "-m",
                        "pip",
                        "install",
                        "pyinstaller",
                        "psutil",
                        "ipython",
                    ),
                    index_url_args,
                )
            ),
            shell=True,
        )

        from PyInstaller.__main__ import run as pyinstaller_run

        _argv_ = copy(sys.argv)

        pyinstaller_spec_file = "{}.spec".format(self.distribution.get_name())
        if os.path.exists(pyinstaller_spec_file):
            # Note: there is no need to sniff or compute anything, the spec is already present
            sys.argv = ["pyinstaller", pyinstaller_spec_file]
            sys.argc = len(sys.argv)
            pyinstaller_run()
            return

        """
        Single dispatcher:
        """
        PYINSTALLER_DISPATCHER = ".pyinstaller_dispatcher.py"
        console_script_entrypoint_regex = re.compile(
            r"(?P<script_name>[\w\-\.]+)[\s]*=[\s]*(?P<package_name>[\w\.]+)[\s]*:?[\s]*(?P<function_name>[\w]+)?"
        )
        console_scripts = set()
        for console_script in self.distribution.entry_points.get("console_scripts"):
            m = console_script_entrypoint_regex.match(console_script)
            if m:
                console_scripts.add(
                    (
                        m.groupdict().get("script_name"),
                        m.groupdict().get("package_name"),
                        m.groupdict().get("function_name"),
                    )
                )

        package_imports = set([p for _, p, f in console_scripts if p and not f])
        function_imports = set([(p, f) for _, p, f in console_scripts if p and f])

        package_imports.update(self.distribution.packages)
        sample_import_module = self.distribution.packages[0]

        with open(PYINSTALLER_DISPATCHER, "w") as pyinstaller_dispatcher_fl:
            # license preamble
            pyinstaller_dispatcher_fl.write(
                """
# Copyright 2021 Amadeus IT Group
#
#    Licensed under the Apache License, Version 2.0 (the "License");
#    you may not use this file except in compliance with the License.
#    You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS,
#    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    See the License for the specific language governing permissions and
#    limitations under the License.
"""
            )
            # imports
            pyinstaller_dispatcher_fl.write(
                "\n".join(
                    [
                        "from {} import {} as {}".format(p, f, fqn_name(p, f))
                        for p, f in function_imports
                    ]
                )
            )
            pyinstaller_dispatcher_fl.write("\n")
            pyinstaller_dispatcher_fl.write(
                "\n".join(["import {}".format(p) for p in sorted(package_imports)])
            )

            # dispatcher block
            pyinstaller_dispatcher_fl.write(
                """
import os
import runpy
import sys
import traceback

PROFILE = os.environ.get('PROFILE', 0)

def profile():
    import cProfile
    import pstats
    import io
    profile_filename = '{package_name}_profile.bin'
    cProfile.run('main()', profile_filename)
    out_stream = io.StringIO()
    with open("{package_name}_profile_stats.txt", "wb") as statsfile:
        p = pstats.Stats(profile_filename, stream=out_stream)
        stats = p.strip_dirs().sort_stats('cumulative')
        stats.print_stats()
        statsfile.write(out_stream.getvalue().encode())
    return sys.exit(0)

def setup_aliases(main_binary, aliases):
    base_dir = os.path.dirname(main_binary)
    for alias in aliases:
        dst_path = os.path.join(base_dir,alias)
        try:
            if os.path.basename(main_binary) == alias:
                continue
            if os.path.exists(dst_path):
                os.unlink(dst_path)
            os.link(main_binary, dst_path)
        except:
            print("Failed to create the link: {{}} -> {{}}".format(main_binary, dst_path))
    return 0

_CMD_ALIASES_ = {{}}

def itoolkit():
    from IPython import start_ipython
    sys.exit(start_ipython())

_CMD_ALIASES_["{package_name}-python"] = lambda x: itoolkit()

def main():
    # The entry point of the generated dispatch
    program_name = os.path.basename(sys.argv[0])

    try:
        import psutil
        process_dict = psutil.Process(os.getpid()).as_dict()
        process_name = process_dict.get('name')

        import {sample_import_module}
        _sample_import_dir_ = os.path.realpath(os.path.dirname({sample_import_module}.__file__))
        _base_dir_ = os.path.dirname(_sample_import_dir_)

        try:
            if sys.argv and len(sys.argv) == 2 and sys.argv[1] == 'setup_aliases':
                return setup_aliases(process_dict.get('cmdline')[0], _CMD_ALIASES_.keys())
            elif sys.argv and len(sys.argv) == 2 and sys.argv[1] == 'extract':
                import shutil
                if os.path.exists('./extracted_bundle/'):
                    shutil.rmtree('./extracted_bundle/')
                shutil.copytree(_base_dir_, './extracted_bundle/')
                return 0
            else:
                if process_name not in _CMD_ALIASES_ and os.environ.get('__process__'):
                    process_name = os.environ.get('__process__')
                return _CMD_ALIASES_.get(process_name, lambda x: 1)(process_name)
        except SystemExit:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            return exc_value.code
        except:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            print('ERROR: {{}}: {{}}\\n{{}}'.format(exc_type, exc_value, traceback.format_exc(15)))
            if os.environ.get('DEBUG'):
                import pdb
                pdb.post_mortem()
    except Exception as e:
        indent = len(program_name) * " "
        sys.stderr.write(program_name + ": " + repr(e) + "\\n")
        sys.stderr.write(indent + "  for help use --help")
        return 2
    return 0
            """.format(
                    package_name=self.distribution.get_name(),
                    sample_import_module=sample_import_module,
                )
            )

            for script_name, package_name, function_name in console_scripts:
                if function_name:
                    pyinstaller_dispatcher_fl.write(
                        """
_CMD_ALIASES_["{script_name}"] = lambda x: {function_name}()

""".format(
                            script_name=script_name,
                            package_name=package_name,
                            function_name=fqn_name(package_name, function_name),
                        )
                    )
                else:
                    pyinstaller_dispatcher_fl.write(
                        """
def dispatch_{package_name}():
    import runpy
    runpy.run_module({package_name}.__name__)

_CMD_ALIASES_["{script_name}"] = lambda x: dispatch_{package_name}()

""".format(
                            script_name=script_name,
                            package_name=package_name,
                            function_name=function_name,
                        )
                    )

            pyinstaller_dispatcher_fl.write(
                """
if __name__ == "__main__":
    if PROFILE:
        profile()
    sys.exit(main())  # pragma: no cover
"""
            )

        try:
            extra_binaries = set()
            extra_data = set()
            hidden_imports = set()

            packages_to_harvest = set(
                [p.split(".", 1)[0] for p in self.distribution.packages]
            )
            packages_to_harvest.add("parso")  # Note: It is required for IPython

            packages_to_harvest_list = [
                package_name for _, package_name, _ in console_scripts
            ]
            packages_to_harvest_list.extend(list(packages_to_harvest))

            for package_name in packages_to_harvest_list:
                _package_ = ""
                try:
                    _package_ = importlib.import_module(package_name)
                except:
                    print(f"It was not possible to import: {package_name}")
                    continue

                PACKAGE__ROOT = os.path.join(os.path.dirname(_package_.__file__))
                for root, dirs, files in os.walk(PACKAGE__ROOT):
                    for _file_ in files:
                        if _file_.endswith(".pyc"):
                            continue
                        _module_base_ = _file_.split(".", 1)[0]
                        src = os.path.join(PACKAGE__ROOT, root, _module_base_)
                        _python_module_path_segments_ = os.path.join(
                            _package_.__name__, src[len(PACKAGE__ROOT) + 1 :]
                        ).split(os.sep)
                        if _python_module_path_segments_[-1] == "__init__":
                            _python_module_ = ".".join(
                                _python_module_path_segments_[:-1]
                            )
                        else:
                            _python_module_ = ".".join(_python_module_path_segments_)

                        if _file_.endswith(".py"):
                            hidden_imports.add(_python_module_)

                        src = os.path.join(PACKAGE__ROOT, root, _file_)
                        dst = os.path.join(
                            "." + os.path.sep,
                            _package_.__name__,
                            src[len(PACKAGE__ROOT) + 1 :],
                        )
                        extra_data.add((src, os.path.dirname(dst)))

            add_extras_cmd = []
            [
                add_extras_cmd.extend(
                    ["--add-binary", "".join((item[0], os.path.pathsep, item[1]))]
                )
                for item in extra_binaries
            ]
            [
                add_extras_cmd.extend(
                    ["--add-data", "".join((item[0], os.path.pathsep, item[1]))]
                )
                for item in extra_data
            ]
            [
                add_extras_cmd.extend(["--hidden-import", "{}".format(item)])
                for item in hidden_imports
            ]

            pyinstaller_dist = self.distribution.command_options.get(
                "bdist_pyinstaller", {}
            ).get("dist_dir", ("", os.path.join(os.getcwd(), "pyinstaller_dist")))[1]
            if not os.path.exists(pyinstaller_dist):
                os.makedirs(pyinstaller_dist)

            one_dir = self.distribution.command_options.get(
                "bdist_pyinstaller", {}
            ).get("one_dir", False)
            extra_args = self.distribution.command_options.get(
                "bdist_pyinstaller", {}
            ).get("extra_args", ("", ""))[1]
            if extra_args:
                """
                NOTE: This is a very simple way of passing extra paramters to pyinstaller.
                    It wouldn't handle nested quoting + blank spaces. Work in progress.
                """
                extra_args = [arg.strip() for arg in extra_args.split() if arg.strip()]

            distribution_mode = "--onedir" if one_dir else "--onefile"
            target_name = "{}-{}".format(
                self.distribution.get_name(), self.distribution.get_version()
            )
            sys.argv = [
                "pyinstaller",
                "--clean",
                "--noconfirm",
                "--strip",
                distribution_mode,
                "--distpath",
                pyinstaller_dist,
                "--name",
                target_name,
                PYINSTALLER_DISPATCHER,
            ]
            sys.argv.extend(add_extras_cmd)
            if extra_args:
                sys.argv.extend(extra_args)

            sys.argc = len(sys.argv)
            pyinstaller_run()
            if one_dir:
                with tarfile.open(
                    os.path.join(pyinstaller_dist, "{}.tar.gz".format(target_name)),
                    mode="w:gz",
                ) as archive:
                    archive.add(
                        name=os.path.join(pyinstaller_dist, target_name),
                        arcname=target_name,
                        recursive=True,
                    )
        finally:
            sys.argv = _argv_

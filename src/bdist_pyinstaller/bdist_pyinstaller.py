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
import platform
import traceback
import os
import re
from itertools import chain
from distutils.core import Command
from distutils.debug import DEBUG
from distutils.errors import *
from distutils.file_util import write_file
from distutils import log
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
        (
            "extra-modules=",
            None,
            "modules to be explicitly bundled-in",
            "(default: None)",
        ),
        ("one-dir", None, "one directory mode", "(default: false)"),
        ("rpm", None, "create rpm deliverable", "(default: false)"),
        ("deb", None, "create deb deliverable", "(default: false)"),
    ]
    boolean_options = ["one-dir", "rpm", "deb"]

    def initialize_options(self):
        self.bdist_dir = None
        self.dist_dir = None
        self.extra_args = None
        self.extra_modules = None
        self.one_dir = False
        self.rpm = False
        self.deb = False
        self.aliases = []

    def finalize_options(self):
        if self.bdist_dir is None:
            bdist_base = self.get_finalized_command("bdist").bdist_base
            self.bdist_dir = os.path.join(bdist_base, "bdist_pyinstaller")

        if self.dist_dir is None:
            bdist_base = self.get_finalized_command("bdist").bdist_base
            self.dist_dir = os.path.join(bdist_base, "bdist_pyinstaller")

    def run(self):
        if not self.distribution.packages:
            raise ValueError(
                "The list of modules seems to be empty(no packages detected). Please verify your configuration!"
            )

        index_url = get_pip_index_url()
        index_url_args = []
        if index_url:
            index_url_args.extend(["--index-url", index_url])

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
                        "tomli",
                    ),
                    index_url_args,
                )
            ),
            shell=True,
        )

        # Note: that's primarily for pulling in dependencies
        subprocess.check_call(
            " ".join(
                chain([sys.executable, "-m", "pip", "install", "."], index_url_args)
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
            self.aliases.append("{}-python".format(self.distribution.get_name()))

            for script_name, package_name, function_name in console_scripts:
                self.aliases.append(script_name)
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

            if self.extra_modules:
                packages_to_harvest.update(
                    [
                        extra_module.strip()
                        for extra_module in self.extra_modules.split(",")
                        if extra_module.strip()
                    ]
                )

            packages_to_harvest_list = [
                package_name for _, package_name, _ in console_scripts
            ]
            packages_to_harvest_list.extend(list(packages_to_harvest))

            for package_name in packages_to_harvest_list:
                _package_ = ""
                try:
                    _package_ = importlib.import_module(package_name)
                except:
                    log.error(f"It was not possible to import: {package_name}")
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

            pyinstaller_dist = self.dist_dir or os.path.join(
                os.getcwd(), "pyinstaller_dist"
            )
            if not os.path.exists(pyinstaller_dist):
                os.makedirs(pyinstaller_dist)

            distribution_mode = "--onedir" if self.one_dir else "--onefile"
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
            if self.extra_args:
                """
                NOTE: This is a very simple way of passing extra paramters to pyinstaller.
                    It wouldn't handle nested quoting + blank spaces. Work in progress.
                """
                sys.argv.extend(
                    [arg.strip() for arg in self.extra_args.split() if arg.strip()]
                )

            sys.argc = len(sys.argv)
            pyinstaller_run()
            if self.one_dir:
                with tarfile.open(
                    os.path.join(pyinstaller_dist, "{}.tar.gz".format(target_name)),
                    mode="w:gz",
                ) as archive:
                    archive.add(
                        name=os.path.join(pyinstaller_dist, target_name),
                        arcname=target_name,
                        recursive=True,
                    )
            if self.rpm:
                self.create_rpm(pyinstaller_dist, target_name)

            if self.deb:
                self.create_deb(pyinstaller_dist, target_name)

        finally:
            sys.argv = _argv_

    def create_rpm(self, dist_location, dist_name):
        # Make all necessary directories
        rpm_base = os.path.join(dist_location, "rpm")
        rpm_dir = {}
        for d in ("SOURCES", "SPECS", "BUILD", "RPMS", "SRPMS"):
            rpm_dir[d] = os.path.join(rpm_base, d)
            self.mkpath(rpm_dir[d])
        spec_dir = rpm_dir["SPECS"]

        spec_path = os.path.join(spec_dir, f"{self.distribution.get_name()}.spec")
        self.execute(
            write_file,
            (spec_path, self._generate_rpm_spec_file(dist_location, dist_name)),
            "writing '%s'" % spec_path,
        )

        # build package
        log.info("building RPMs")
        rpm_cmd = ["rpmbuild"]

        rpm_cmd.append("-bb")
        rpm_cmd.extend(["--define", "_topdir %s" % os.path.abspath(rpm_base)])
        rpm_cmd.append("--clean")

        rpm_cmd.append(spec_path)

        nvr_string = "%{name}-%{version}-%{release}"
        src_rpm = nvr_string + ".src.rpm"
        non_src_rpm = "%{arch}/" + nvr_string + ".%{arch}.rpm"
        q_cmd = r"rpm -q --qf '%s %s\n' --specfile '%s'" % (
            src_rpm,
            non_src_rpm,
            spec_path,
        )

        out = os.popen(q_cmd)
        try:
            binary_rpms = []
            source_rpm = None
            while True:
                line = out.readline()
                if not line:
                    break
                l = line.strip().split()
                assert len(l) == 2
                binary_rpms.append(l[1])
                # The source rpm is named after the first entry in the spec file
                if source_rpm is None:
                    source_rpm = l[0]

            status = out.close()
            if status:
                raise DistutilsExecError("Failed to execute: %s" % repr(q_cmd))

        finally:
            out.close()

        self.spawn(rpm_cmd)

        if not self.dry_run:
            pyversion = "any"
            for rpm in binary_rpms:
                rpm = os.path.join(rpm_dir["RPMS"], rpm)
                if os.path.exists(rpm):
                    self.move_file(rpm, self.dist_dir)
                    filename = os.path.join(self.dist_dir, os.path.basename(rpm))
                    self.distribution.dist_files.append(
                        ("bdist_pyinstaller", pyversion, filename)
                    )

    def create_deb(self, dist_location, dist_name):
        # Make all necessary directories
        binary_target_base = "usr/bin"
        deb_base = os.path.join(dist_location, "deb")
        binaries_target_path = os.path.join(deb_base, binary_target_base)
        spec_path = os.path.join(deb_base, "DEBIAN", "control")
        self.mkpath(binaries_target_path)
        self.mkpath(os.path.dirname(spec_path))
        for alias in self.aliases:
            dst = os.path.join(binaries_target_path, alias)
            src = os.path.join(dist_location, dist_name)
            if os.path.exists(dst):
                os.unlink(dst)
            os.link(src, dst)

        arch_string = self._get_deb_build_arch()
        self.execute(
            write_file,
            (
                spec_path,
                self._generate_deb_spec_file(dist_location, dist_name, arch_string),
            ),
            f"writing '{spec_path}'",
        )

        os.chmod(deb_base, mode=0o755)
        os.chmod(os.path.dirname(spec_path), mode=0o755)

        # build package
        log.info("building DEBs")
        release = "1"
        deb_filename = os.path.join(
            deb_base,
            f"{self.distribution.get_name()}_{self.distribution.get_version()}_{release}_{arch_string}.deb",
        )
        deb_cmd = ["dpkg-deb", "--build", "--root-owner-group", deb_base, deb_filename]

        self.spawn(deb_cmd)
        if not self.dry_run:
            pyversion = "any"
            if os.path.exists(deb_filename):
                self.move_file(deb_filename, self.dist_dir)
                filename = os.path.join(self.dist_dir, os.path.basename(deb_filename))
                self.distribution.dist_files.append(
                    ("bdist_pyinstaller", pyversion, filename)
                )

    def _get_deb_build_arch(self):
        arch_string = "amd64"
        q_cmd = "dpkg-architecture -q DEB_BUILD_ARCH"
        out = os.popen("dpkg-architecture -q DEB_BUILD_ARCH")
        try:
            line = out.readline()
            if line:
                arch_string = line.strip()
            status = out.close()
            if status:
                raise DistutilsExecError(f"Failed to execute: {q_cmd}")

        finally:
            out.close()
        return arch_string

    def _generate_deb_spec_file(self, dist_location, dist_name, arch_string):
        return [
            f"Package: {self.distribution.get_name()}",
            f"Version: {self.distribution.get_version().replace('-','_')}",
            f"Architecture: {arch_string}",
            f"Maintainer: {self.distribution.get_author()} <{self.distribution.get_author_email()}>",
            f"""Description: {self.distribution.get_description()}""",
        ]

    def _generate_rpm_spec_file(self, dist_location, dist_name):
        """Generate the text of an RPM spec file and return it as a
        list of strings (one per line).
        """
        # definitions and headers
        spec_file = [
            f"%define name {self.distribution.get_name()}",
            f"%define version {self.distribution.get_version().replace('-','_')}",
            f"%define unmangled_version {self.distribution.get_version()}",
            f"%define release 1",
            "",
            f"Summary: {self.distribution.get_description()}",
        ]

        spec_file.extend(
            [
                "Name: %{name}",
                "Version: %{version}",
                "Release: %{release}",
            ]
        )

        spec_file.append("Source0: %{name}-%{unmangled_version}.tar.gz")

        spec_file.extend(
            [
                f"License: {self.distribution.get_license()}",
                f"Group: Development/Libraries",
                "BuildRoot: %{_tmppath}/%{name}-%{version}-%{release}-buildroot",
                "Prefix: %{_prefix}",
            ]
        )

        spec_file.append("BuildArch: %s" % platform.machine())

        if self.distribution.get_url() != "UNKNOWN":
            spec_file.append("Url: " + self.distribution.get_url())

        spec_file.append("AutoReq: 0")

        spec_file.extend(["", "%description", self.distribution.get_long_description()])

        dist_location = os.path.abspath(os.path.join(dist_location, dist_name))
        install_cmds = [
            "mkdir -p usr/bin",
        ]
        install_cmds.extend(
            [
                "ln -f {} usr/bin/{}".format(dist_location, alias)
                for alias in self.aliases
            ]
        )
        install_cmds.extend(
            [
                "mkdir -p $RPM_BUILD_ROOT",
                "cp -ar ./usr $RPM_BUILD_ROOT/",
            ]
        )

        script_options = [
            ("prep", "prep_script", None),
            ("build", "build_script", None),
            ("install", "install_script", install_cmds),
            ("clean", "clean_script", "rm -rf $RPM_BUILD_ROOT"),
            ("verifyscript", "verify_script", None),
            ("pre", "pre_install", None),
            ("post", "post_install", None),
            ("preun", "pre_uninstall", None),
            ("postun", "post_uninstall", None),
        ]

        for (rpm_opt, attr, default) in script_options:
            # Insert contents of file referred to, if no file is referred to
            # use 'default' as contents of script
            val = getattr(self, attr, None)
            if val or default:
                spec_file.extend(
                    [
                        "",
                        "%" + rpm_opt,
                    ]
                )
                if val:
                    with open(val) as f:
                        spec_file.extend(f.read().split("\n"))
                elif isinstance(default, list):
                    spec_file.extend(default)
                else:
                    spec_file.append(default)

        # files section
        spec_file.extend(
            [
                "",
                "%files",
            ]
        )
        spec_file.extend(["/usr/bin/{}".format(alias) for alias in self.aliases])

        spec_file.append("%defattr(-,root,root)")
        return spec_file

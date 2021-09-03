### Overview
bdist_pyinstaller is a side-car distutils command to automate creation of the pyinstaller packages in a non-intrusive way.

#### The problem dist_pyinstaller is trying to solve
The application written in Python is never directly executed natively. Similarly to Java, Python code is compiled into a byte code(opcode) and it's running on a *Python VM*.
As a consequence, to run anything written in Python one needs to have an *installation of Python* compiler+VM.
It usually comes as OS-dependent package(rpm, deb etc.) or it can be compiled from source.  
Furthermore, despite having a very rich core libraries at their disposal, Python programs often need to pull some *3rd party packages* in. Some packages require libraries which have to be pre-installed on the OS level.

This would require the combination of:

  * Internet connection or setting up the equivalent repositories holding the packages
  * Priviledge escalation if the installation of python and/or extra packages is to be treated as a system-wide one
  * An extra care when dealing with version upgrades(both python itself as well as the packages) as various applications often come with conflicting requirements which are not straight forward to solve on a shared platform. 

There are solutions to all these problems, but they all come with the extra complexity, reduced reliability and maintanance cost when the aim is to have simple and stable way of executing a given program/utility.

*bdist_installer* offers a very simple path from a well defined Python utility to a single binary with all the required bits frozen-in. That includes the Python runtime. Thanks to pyinstaller used behind the scenes it is very powerful, yet still very simple in non-trivial use-cases.


### Table of Contents

  * [Getting started](./GETTINGSTARTED.md)
  * [Contributing](./CONTRIBUTING.md)
  * [Help wanted](./HELPWANTED.md)
  * [Glossary](./GLOSSARY.md)
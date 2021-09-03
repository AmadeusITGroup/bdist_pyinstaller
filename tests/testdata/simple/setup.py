from setuptools import setup, find_packages

setup(name='simple',
      version='0.1',
      description=u'A simple package for testing purposes',
      packages=find_packages(include=['simple', 'simple.*']),
      entry_points={
          'console_scripts': [
              'hello=simple.cli:main',
          ],
      },
      include_package_data=True,
      zip_safe=False,
      )

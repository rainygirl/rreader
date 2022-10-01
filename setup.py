import os
import sys

from setuptools import setup, find_packages

if sys.version[0] == "2":
    sys.exit("Use Python 3")

requires = [
    "Pillow>=9.0.1",
    "wcwidth==0.1.8",
    "asciimatics==1.11.0",
    "feedparser>=5.2.1",
]

setup(
    name="rreader",
    version="1.1.2",
    description="RSS reader client for CLI, spinned off from rterm",
    long_description=open("./README.rst", "r").read(),
    classifiers=[
        "Environment :: Console",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3.7",
    ],
    keywords="RSS, CLI, command line, terminal",
    author="Lee JunHaeng",
    author_email="rainygirl@gmail.com",
    url="https://github.com/rainygirl/rreader",
    license="MIT License",
    packages=find_packages(exclude=[]),
    package_data={"": ["*.json"]},
    include_package_data=True,
    python_requires=">=3.7",
    zip_safe=False,
    install_requires=requires,
    entry_points="""
      # -*- Entry points: -*-
      [console_scripts]
      rr=rreader_src.run:do
      """,
)

#!/usr/bin/env python3

from setuptools import setup
from setuptools import find_packages


setup(
    name             = "litecompute_poc",
    description      = "some tests",
    author           = "Enjoy-Digital",
    url              = "http://enjoy-digital.fr",
    download_url     = "https://github.com/enjoy-digital/litecompute_poc",
    license          = "BSD",
    setup_requires   = [
        "develop", [
            "setuptools"
        ]
    ],
    install_requires = ["litex"],
    packages         = find_packages(),
)

from setuptools import setup
from Cython.Build import cythonize

setup(
    name='decrypt',
    ext_modules=cythonize("decrypt.pyx"),
    zip_safe=False,
)
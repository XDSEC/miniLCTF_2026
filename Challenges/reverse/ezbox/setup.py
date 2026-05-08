from setuptools import setup, Extension

setup(
    name='_core',
    ext_modules=[
        Extension(
            '_core',
            sources=['_core.c'],
            extra_compile_args=['-O2'],
        )
    ],
)

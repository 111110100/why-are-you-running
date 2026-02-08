#!/usr/bin/env python3
"""
Setup script for wayr - Why Are You Running?
"""

from setuptools import setup
import os

# Read the README for long description
def read_readme():
    readme_path = os.path.join(os.path.dirname(__file__), 'README.md')
    if os.path.exists(readme_path):
        with open(readme_path, 'r', encoding='utf-8') as f:
            return f.read()
    return ''

setup(
    name='wayr',
    version='1.0.2',
    description='Why Are You Running? - Explains why processes exist on your system',
    long_description=read_readme(),
    long_description_content_type='text/markdown',
    author='wayr contributors',
    author_email='',
    url='https://github.com/yourusername/wayr',
    py_modules=['wayr'],
    entry_points={
        'console_scripts': [
            'wayr=wayr:main',
        ],
    },
    classifiers=[
        'Development Status :: 4 - Beta',
        'Environment :: Console',
        'Intended Audience :: Developers',
        'Intended Audience :: System Administrators',
        'License :: OSI Approved :: MIT License',
        'Operating System :: POSIX :: Linux',
        'Operating System :: MacOS :: MacOS X',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Topic :: System :: Monitoring',
        'Topic :: System :: Systems Administration',
        'Topic :: Utilities',
    ],
    keywords='process debugging monitoring systemd docker pm2 diagnostics',
    python_requires='>=3.6',
    platforms=['Linux', 'macOS', 'Darwin'],
    license='MIT',
)

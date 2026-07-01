from setuptools import find_packages, setup


setup(
    name="prismax",
    version="0.1.0",
    description="PrismaX Python SDK for data uploads",
    long_description=open("README.md", encoding="utf-8").read(),
    long_description_content_type="text/markdown",
    python_requires=">=3.9",
    license="PolyForm Noncommercial License 1.0.0",
    keywords=["prismax", "upload", "sdk", "robotics", "mcap"],
    author="PrismaX",
    url="https://github.com/ChrisPrismax/prismax-sdk-python",
    project_urls={
        "Homepage": "https://github.com/ChrisPrismax/prismax-sdk-python",
        "Repository": "https://github.com/ChrisPrismax/prismax-sdk-python",
        "Issues": "https://github.com/ChrisPrismax/prismax-sdk-python/issues",
    },
    packages=find_packages(),
    install_requires=["requests>=2.31.0"],
    entry_points={
        "console_scripts": [
            "prismax=prismax.cli:main",
        ],
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: Other/Proprietary License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
)

"""
pip install -e .        →  registers `victor` CLI entry point
pip install -e ".[dev]" →  dev extras (pytest, ruff, pytest-cov)
pip install -e ".[audio]" → audio pipeline extras (librosa, sounddevice)
python -m victor.cli  also works without installing
"""
from setuptools import setup, find_packages

setup(
    name="victor",
    version="5.3.0",
    license="Proprietary",
    author="Varish Sharma",
    classifiers=[
        "License :: Other/Proprietary License",
        "Private :: Do Not Upload",  # blocks accidental PyPI publish
    ],
    packages=find_packages(include=["victor", "victor.*"]),
    install_requires=[
        "chromadb>=0.4.0",
        "sentence-transformers>=2.2.0",
        "networkx>=3.0",
        "click>=8.0",
        "rich>=13.0",
        "numpy>=1.24.0",
        "scipy>=1.10.0",
        "ollama>=0.1.0",
        "openai>=1.0.0",
        "pillow>=10.0.0",
    ],
    extras_require={
        "audio": [
            "librosa>=0.10.0",
            "sounddevice>=0.4.0",
        ],
        "dev": [
            "pytest>=7.0",
            "pytest-cov>=4.0",
            "ruff>=0.4.0",
        ],
    },
    python_requires=">=3.12",
    entry_points={
        "console_scripts": ["victor=victor.cli:cli"],
    },
)

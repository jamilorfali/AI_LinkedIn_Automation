from setuptools import setup, find_packages

setup(
    name="ai-linkedin-automation",
    version="0.1.0",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    install_requires=[
        "feedparser>=6.0.11",
        "PyYAML>=6.0.1",
        "python-dotenv>=1.0.1",
        "beautifulsoup4>=4.12.0",
        "python-dateutil>=2.9.0",
        "click>=8.1.7",
        "requests>=2.32.0",
    ],
    extras_require={
        "dev": [
            "pytest>=8.2.0",
            "ruff>=0.5.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "ai-linkedin = ai_linkedin_automation.cli:main",
        ],
    },
)

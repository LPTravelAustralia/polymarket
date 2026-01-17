"""
Setup configuration for Polymarket Trading Bot
"""
from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="polymarket-trading-bot",
    version="0.1.0",
    author="Polymarket Trading Bot Team",
    description="A comprehensive trading bot for Polymarket with AI-powered predictions",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/LPTravelAustralia/polymarket",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Topic :: Office/Business :: Financial :: Investment",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
    python_requires=">=3.8",
    install_requires=[
        "py-clob-client>=0.30.0",
        "web3>=6.0.0",
        "eth-account>=0.10.0",
        "openai>=1.0.0",
        "anthropic>=0.18.0",
        "langchain>=0.1.0",
        "langchain-openai>=0.0.5",
        "pandas>=2.0.0",
        "numpy>=1.24.0",
        "aiohttp>=3.9.0",
        "requests>=2.31.0",
        "httpx>=0.25.0",
        "python-dotenv>=1.0.0",
        "pydantic>=2.0.0",
        "pydantic-settings>=2.0.0",
        "loguru>=0.7.0",
        "python-dateutil>=2.8.0",
        "pytz>=2023.3",
    ],
    extras_require={
        "dev": [
            "pytest>=7.4.0",
            "pytest-asyncio>=0.21.0",
            "pytest-cov>=4.1.0",
            "black>=23.0.0",
            "flake8>=6.0.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "polymarket-bot=scripts.run_trading_bot:main",
            "polymarket-monitor=scripts.monitor_markets:main",
            "polymarket-arbitrage=scripts.run_arbitrage_bot:main",
            "polymarket-ai=scripts.run_ai_bot:main",
        ],
    },
)

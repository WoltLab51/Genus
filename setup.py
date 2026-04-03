from setuptools import setup, find_packages

setup(
    name="genus",
    version="0.1.0",
    packages=find_packages(exclude=["tests", "tests.*"]),
    python_requires=">=3.11",
    install_requires=[
        "fastapi>=0.111.0",
        "uvicorn[standard]>=0.29.0",
        "sqlalchemy>=2.0.30",
        "aiosqlite>=0.20.0",
        "pydantic>=2.7.0",
        "httpx>=0.27.0",
    ],
    extras_require={
        "dev": [
            "pytest>=8.2.0",
            "pytest-asyncio>=0.23.6",
        ],
    },
)

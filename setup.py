from setuptools import setup, find_packages

setup(
    name='ravendb_datahub_source',
    version='1.0.0',
    author='Verena Barth',
    author_email='Verena.Barth@viadee.com',
    description='RavenDB ingestion source for datahub',
    packages=find_packages(
        exclude=["*.tests.*", "tests", "*.tests", "tests.*"]
    ),
    license="MIT",
    keywords=[
        "ravendb",
        "nosql",
        "database",
        "pyravendb",
        "datahub",
        "metadata-ingestion"
    ],
    install_requires=[
        'datahub >= 0.10.4',
        'ravendb >= 5.2.4',
        "acryl_datahub>=0.10.1",
        # "docker_py==1.10.6",
        "numpy>=1.15.1",
        "pydantic>=1.9.1",
        "pytest>=6.2.3",
        "setuptools>=40.2.0",
        # "pytest-docker>=0.10.3,<0.12"
        "pytest-docker>=1.0.1",
        "deepdiff>=6.0.0"
        # Add any other dependencies your module requires
    ],
)

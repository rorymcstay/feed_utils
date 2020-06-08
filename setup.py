import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="feed_utils",
    version="0.7.1",
    author="Rory McStay",
    author_email="rory@rorymcstay.com",
    description="Common code for feed",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/rorymcstay/feed_utils",
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.6',
)

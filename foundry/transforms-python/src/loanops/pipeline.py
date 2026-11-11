"""Foundry Python transforms entry point: registers every transform in loanops.datasets."""

from transforms.api import Pipeline

from loanops import datasets

my_pipeline = Pipeline()
my_pipeline.discover_transforms(datasets)

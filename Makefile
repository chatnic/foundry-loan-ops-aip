.PHONY: setup data run test all

setup:
	python -m pip install -r requirements.txt

data:
	python data/generate_data.py --n 5000 --seed 42 --out data/raw

run:
	python local/loanops/run_local.py --data data/raw --out reports

test:
	python -m pytest -q

all: data run test

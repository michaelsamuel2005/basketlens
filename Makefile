.PHONY: setup data run deck tableau twin test
setup:
	pip install -e ".[dev]"
data:
	python -m basketlens.cli load
run:
	python -m basketlens.cli run --manufacturer 794 --category "COLD CEREAL"
deck:
	python -m basketlens.cli deck --manufacturer 794 --category "COLD CEREAL"
tableau:
	python -m basketlens.cli tableau --manufacturer 794 --category "COLD CEREAL"
twin:
	python -m basketlens.cli twin --seed 7
test:
	pytest -q -m "not slow"
